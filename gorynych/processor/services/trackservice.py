import time

from twisted.python import log
from twisted.internet import threads, defer

from gorynych.common.domain import events
from gorynych.common.exceptions import NoGPSData
from gorynych.common.infrastructure import persistence as pe
from gorynych.processor.domain import TrackArchive, track
from gorynych.common.application import EventPollingService
from gorynych.common.domain.services import APIAccessor


API = APIAccessor()

ADD_TRACK_TO_GROUP = """
    INSERT INTO TRACKS_GROUP VALUES (%s,
        (SELECT ID FROM TRACK WHERE TRACK_ID=%s), %s);
"""

class ProcessorService(EventPollingService):
    '''
    Orchestrate track creation and parsing.
    '''
    in_progress = dict()
    ttl = 180
    @defer.inlineCallbacks
    def process_ArchiveURLReceived(self, ev):
        '''
        Download and process track archive.
        '''
        race_id = ev.aggregate_id
        url = ev.payload
        log.msg("URL received ", url)
        if url in self.in_progress and time.time() - self.in_progress[url] <\
                self.ttl:
            log.msg("Archive in process")
            # Don't process one url simultaneously.
            defer.returnValue('')
        else:
            res = yield defer.maybeDeferred(API.get_track_archive, str(race_id))
        if res['status'] == 'no archive':
            self.in_progress[url] = time.time()
            ta = TrackArchive(str(race_id), url)
            log.msg("Start unpacking archive %s for race %s" % (url, race_id))
            archinfo = yield threads.deferToThread(ta.process_archive)
            yield self._inform_about_paragliders(archinfo, race_id)
        yield self.event_dispatched(ev.id)

    def _inform_about_paragliders(self, archinfo, race_id):
        '''
        Inform system about finded paragliders, then inform system about
        succesfull archive unpacking.
        @param archinfo: ([{person_id, trackfile, contest_number}],
        [trackfile,], [person_id,])
        @type race_id: C{str}
        '''
        # TODO: add events for extra tracks and left paragliders.
        tracks, extra_tracks, left_paragliders = archinfo
        dlist = []
        es = pe.event_store()
        for di in tracks:
            ev = events.ParagliderFoundInArchive(race_id, payload=di, aggregate_type='race')
            dlist.append(es.persist(ev))
        d = defer.DeferredList(dlist, fireOnOneErrback=True)
        d.addCallback(lambda _:es.persist(events
                .TrackArchiveUnpacked(race_id, payload=archinfo, aggregate_type='race')))
        d.addCallback(lambda _:log.msg("Track archive for race %s unpacked"
                                       % race_id))
        return d

    @defer.inlineCallbacks
    def process_RaceGotTrack(self, ev):
        if ev.id in self.in_progress and (
                time.time() - self.in_progress[ev.id]) < self.ttl:
            defer.returnValue('')
        self.in_progress[ev.id] = time.time()
        race_id = ev.aggregate_id
        track_id = ev.payload['track_id']
        cn = ev.payload.get('contest_number')
        try:
            log.msg(">>>Adding track %s to group %s <<<" % (track_id,
                                str(race_id)))
            yield self.pool.runOperation(ADD_TRACK_TO_GROUP, (str(race_id),
                track_id, cn))
        except Exception as e:
            log.msg("Track %s hasn't been added to group %s because of %r" %
                    (track_id, race_id, e))
        res = yield defer.maybeDeferred(API.get_track_archive, str(race_id))
        processed = len(res['progress']['parsed_tracks']) + len(
            res['progress']['unparsed_tracks'])
        if len(res['progress']['paragliders_found']) == processed and not (
                res['status'] == 'parsed'):
            yield pe.event_store().persist(events.TrackArchiveParsed(
                race_id, aggregate_type='race'))
        yield self.event_dispatched(ev.id)


class TrackService(EventPollingService):
    '''
    TrackService parse track archive.
    '''
    polling_interval = 2
    in_progress = dict()
    ttl = 100

    def __init__(self, pool, event_store, track_repository):
        EventPollingService.__init__(self, pool, event_store)
        self.aggregates = dict()
        self.track_repository = track_repository

    def process_ParagliderFoundInArchive(self, ev):
        '''
        After this message TrackService start to listen events for this
         track.
        @param ev:
        @type ev:
        @return:
        @rtype:
        '''
        trackfile = ev.payload['trackfile']
        person_id = ev.payload['person_id']
        contest_number = ev.payload['contest_number']
        if trackfile in self.in_progress and (time.time() -
                                self.in_progress[trackfile] < self.ttl):
            log.msg("trackfile for %s in progress" % contest_number)
            # Don't process one url simultaneously.
            return
        self.in_progress[trackfile] = time.time()
        log.msg("Got trackfile for paraglider %s" % person_id)
        race_id = ev.aggregate_id
        try:
            race_task = API.get_race_task(str(race_id))
        except Exception as e:
            log.msg("Error in API call: %r" % e)
            race_task = None
        if not isinstance(race_task, dict):
            log.msg("Race task wasn't received from API: %r" % race_task)
            defer.returnValue('')
        track_type = 'competition_aftertask'
        track_id = track.TrackID()

        tc = events.TrackCreated(track_id)
        tc.payload = dict(race_task=race_task, track_type=track_type)
        def no_altitude_failure(failure):
            failure.trap(NoGPSData)
            log.err("Track %s don't has GPS altitude" % contest_number)
            ev = events.TrackWasNotParsed(race_id, aggregate_type='race')
            ev.payload = dict(contest_number=contest_number,
                reason=failure.getErrorMessage())
            d = self.event_store.persist(ev)
            return d

        d = self.event_store.persist(tc)
        d.addCallback(lambda _:self.execute_ProcessData(track_id, trackfile))
        d.addCallback(lambda _:log.msg("Trackfile %s processed" % person_id))
        d.addCallback(lambda _:self.append_track_to_race_and_person(race_id,
            track_id, track_type, contest_number, person_id))
        d.addCallback(lambda _:log.msg("trackfile %s data appended" % person_id))
        d.addErrback(no_altitude_failure)
        d.addCallback(lambda _:self.event_dispatched(ev.id))
        return d

    def execute_ProcessData(self, track_id, data):
        return self.update(track_id, 'process_data', data)

    @defer.inlineCallbacks
    def update(self, aggregate_id, method, *args, **kwargs):
        aggr = yield defer.maybeDeferred(self._get_aggregate, aggregate_id)
        getattr(aggr, method)(*args, **kwargs)
        # Persist points, state and events if any.
        yield self.persist(aggr)

    @defer.inlineCallbacks
    def _get_aggregate(self, _id):
        if not self.aggregates.get(_id):
            elist = yield self.event_store.load_events(_id)
            t = track.Track(_id, events=elist)
            self.aggregates[_id] = t
        defer.returnValue(self.aggregates[_id])

    def append_track_to_race_and_person(self, race_id, track_id, track_type,
            contest_number, person_id):
        '''
        When track is ready to be shown send messages for Race and Person to
         append this track to them.
        @param race_id:
        @type race_id:
        @param track_id:
        @type track_id:
        @param track_type:
        @type track_type:
        @param contest_number:
        @type contest_number:
        @param person_id:
        @type person_id:
        @return:
        @rtype:
        '''
        rgt = events.RaceGotTrack(race_id, aggregate_type='race')
        rgt.payload = dict(contest_number=contest_number,
            track_type=track_type, track_id=str(track_id))
        ptc = events.PersonGotTrack(person_id, str(track_id),
            aggregate_type='person')
        return self.event_store.persist([rgt, ptc])

    def persist(self, aggr):
        d = self.event_store.persist(aggr.changes)
        d.addCallback(lambda _:self.track_repository.save(aggr))
        return d


def pic(x, name, suf):
    import cPickle
    try:
        f = open('.'.join((name, suf, 'pickle')), 'wb')
        cPickle.dump(x, f)
        f.close()
    except Exception as e:
        print "in pic", str(e)
