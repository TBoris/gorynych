'''
Application Services for info context.
'''
import simplejson as json

from zope.interface import Interface
from twisted.application.service import Service
from twisted.internet import defer
from twisted.python import log

from gorynych.info.domain import contest, person, race
from gorynych.common.infrastructure import persistence
from gorynych.common.domain.types import checkpoint_from_geojson


class TrackerService(Interface):
    '''
    Application Service which work with Tracker aggregate.
    '''

    def create_tracker(tracker_id, device_id, device_type):
        '''
        Create new tracker.
        @param tracker_id:
        @type tracker_id:
        @param device_id:
        @type device_id:
        @param device_type:
        @type device_type:
        @return: new tracker
        @rtype: Tracker
        '''

    def change_tracker_name(tracker_id, new_name):
        '''

        @param tracker_id:
        @type tracker_id:
        @param new_name:
        @type new_name:
        @return: changed tracker
        @rtype: Tracker
        '''

    def get_tracker(tracker_id):
        '''

        @param tracker_id:
        @type tracker_id:
        @return: a tracker
        @rtype: Tracker
        '''

    def get_trackers(tracker_ids):
        '''
        Get a bunch of trackers
        @param tracker_ids:
        @type tracker_ids: list
        @return: a list of trackers,
        @rtype: Tracker
        '''

    def assign_tracker_to(tracker_id, assignee_id):
        '''
        Assign a tracker with tracker_id to person or transport with
        assignee_id.
        @param tracker_id:
        @type tracker_id:
        @param assignee_id:
        @type assignee_id:
        @return:
        @rtype:
        '''

    def unassign_tracker(tracker_id):
        '''
        Unassign tracker with tracker_id from someone if tracker is assigned.
        @param tracker_id:
        @type tracker_id:
        @return:
        @rtype:
        '''


class ApplicationService(Service):
    def __init__(self, event_store=None):
        if not event_store:
            event_store = persistence.event_store()
        self.event_store = event_store
        self.pool = self.event_store.store.pool

    def startService(self):
        log.msg("Starting DB pool.")
        d = self.pool.start()
        d.addCallback(lambda _: log.msg("Pool started successfully."))
        d.addCallbacks(lambda _:log.msg("Connection established."))
        d.addCallback(lambda _:self.event_store.store.initialize())
        d.addCallback(lambda _:Service.startService(self))
        return d.addCallback(lambda _: log.msg("Service started."))

    def stopService(self):
        Service.stopService(self)
        return self.pool.close()

    ############## Contest Service part #############
    def create_new_contest(self, params):
        '''
        Create totally new contest and save it to repository.
        @param params:
        @type params:
        @return: C{Deferred} which will be fired with L{Contest} aggregate.
        @rtype: L{Contest}
        '''
        id = contest.ContestID()
        contest_factory = contest.ContestFactory()
        cont = contest_factory.create_contest(params['title'],
                                              params['start_time'],
                                              params['end_time'],
                                              params['place'],
                                              params['country'],
                                              params['hq_coords'],
                                              params['timezone'],
                                              id)
        d = defer.succeed(cont)
        d.addCallback(persistence.get_repository(contest.IContestRepository)
        .save)
        return d

    def get_contests(self, params=None):
        '''
        Return a list of contests
        @param params: offset and limits can be here
        @type params: dict
        @return:
        @rtype:
        '''
        return self._get_aggregates_list(params, contest.IContestRepository)

    def get_contest(self, params):
        '''
        Return contest by id.
        @param params:
        @type params: C{dict}
        @return: Contest wrapped by Deferred.
        @rtype: C{Deffered}
        '''
        return self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)

    def change_contest(self, params):
        '''
        Change contest information.
        @param params:
        @type params:
        @return:
        @rtype:
        '''

        def change(cont, params):
            '''
            Do actual changes in contest.
            @param cont:
            @type cont:
            @param params:
            @type params:
            @return:
            @rtype:
            '''
            if params.get('start_time') and params.get('end_time'):
                cont.change_times(params['start_time'], params['end_time'])
                del params['start_time']
                del params['end_time']

            for param in params.keys():
                setattr(cont, param, params[param])
            return cont

        if params.has_key('contest_id'):
            params['id'] = params['contest_id']
            del params['contest_id']
        return self._change_aggregate(params, contest.IContestRepository,
                                      change)

    def register_paraglider_on_contest(self, params):
        '''

        @param params:
        @type params:
        @return: Contest with registered paraglider wrapped in Deferred.
        @rtype: C{Contest}
        '''
        d = self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)
        d.addCallback(lambda cont: cont.register_paraglider(
            person.PersonID.fromstring(params['person_id']), params['glider'],
            params['contest_number']))
        d.addCallback(
            persistence.get_repository(contest.IContestRepository).save)
        return d

    def get_contest_paragliders(self, params):
        '''
        Return list with race paragliders.
        @param params:
        @type params:
        @return:
        @rtype:
        '''
        d = self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)
        d.addCallback(lambda cont: cont.paragliders)
        return d

    def change_paraglider(self, params):
        '''
        Change paraglider information either for race or contest.
        @param params:
        @type params:
        @return:
        @rtype:
        '''

        def change(cont):
            if params.has_key('glider'):
                cont.change_participant_data(params['person_id'],
                                             glider=params['glider'])
            if params.has_key('contest_number'):
                cont.change_participant_data(params['person_id'],
                                     contest_number=params['contest_number'])
            return cont

        d = self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)
        d.addCallback(change)
        d.addCallback(persistence.get_repository(contest.IContestRepository)
        .save)
        return d


    ############## Person Service part ##############
    def create_new_person(self, params):
        factory = person.PersonFactory()
        year, month, day = params['reg_date'].split(',')
        pers = factory.create_person(params['name'], params['surname'],
                                     params['country'], params['email'], year,
                                     month, day)
        d = defer.succeed(pers)
        d.addCallback(persistence.get_repository(person.IPersonRepository).
        save)
        return d

    def get_person(self, params):
        return self._get_aggregate(params['person_id'],
                                   person.IPersonRepository)

    def get_persons(self, params=None):
        return self._get_aggregates_list(params, person.IPersonRepository)

    def change_person(self, params):
        def change(pers, params):
            new_name = dict()
            if params.get('name'):
                new_name['name'] = params['name']
            if params.get('surname'):
                new_name['surname'] = params['surname']
            pers.name = new_name
            if params.get('country'):
                pers.country = params['country']
            return pers

        if params.has_key('person_id'):
            params['id'] = params['person_id']
            del params['person_id']
        return self._change_aggregate(params, person.IPersonRepository,
                                      change)

    ############## Race Service part ################
    @defer.inlineCallbacks
    def create_new_race_for_contest(self, params):
        cont = yield self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)
        r = yield cont.new_race(params['race_type'], params['checkpoints'],
                      params['title'])
        yield persistence.get_repository(race.IRaceRepository).save(r)
        yield persistence.get_repository(contest.IContestRepository).save(
            cont)
        defer.returnValue(r)

    def get_contest_races(self, params):
        '''
        Return list of races for contest.
        @param params:
        @type params:
        @return:
        @rtype:
        '''
        d = self._get_aggregate(params['contest_id'],
                                contest.IContestRepository)
        d.addCallback(lambda cont: [self._get_aggregate(id,
                             race.IRaceRepository) for id in cont.race_ids])
        d.addCallback(defer.gatherResults, consumeErrors=True)
        return d

    @defer.inlineCallbacks
    def get_contest_race(self, params):
        '''
        Return info about race in contest and about corresponding contest.
        @param params:
        @type params:
        @return:
        @rtype:
        '''
        r = yield self._get_aggregate(params['race_id'],
                                      race.IRaceRepository)
        c = yield self._get_aggregate(params['contest_id'],
                                      contest.IContestRepository)
        defer.returnValue((c, r))

    def change_contest_race(self, params):
        '''
        Change information about race in contest.
        @param params:
        @type params:
        @return: Race
        @rtype:
        '''
        def change(r):
            if params.has_key('checkpoints'):
                ch_list = json.loads(params['checkpoints'])['features']
                checkpoints = []
                for ch in ch_list:
                    checkpoints.append(checkpoint_from_geojson(ch))
                r.checkpoints = checkpoints
            if params.has_key('race_title'):
                r.title = params['race_title']
            return r

        d = self._get_aggregate(params['race_id'], race.IRaceRepository)
        d.addCallback(change)
        d.addCallback(persistence.get_repository(race.IRaceRepository).save)
        return d

    def get_race_paragliders(self, params):
        return self._get_aggregate(params['race_id'], race.IRaceRepository)

    def get_race(self, params):
        return self._get_aggregate(params['race_id'], race.IRaceRepository)

    def add_track_archive(self, params):
        d = self._get_aggregate(params['race_id'], race.IRaceRepository)
        return d.addCallback(lambda r: r.add_track_archive(params['url']))

    ############## common methods ###################
    def _get_aggregate(self, id, repository):
        d = defer.succeed(id)
        d.addCallback(persistence.get_repository(repository).get_by_id)
        return d

    def _change_aggregate(self, params, repo_interface, change_func):
        id = params.get('id')
        if not id:
            raise ValueError("Aggregate's id hasn't been received.")
        del params['id']

        d = self._get_aggregate(id, repo_interface)
        d.addCallback(change_func, params)
        d.addCallback(persistence.get_repository(repo_interface).save)
        return d

    def _get_aggregates_list(self, limit_offset_params, repo_interface):
        if limit_offset_params:
            limit = limit_offset_params.get('limit', None)
            offset = limit_offset_params.get('offset', 0)
        else:
            limit = None
            offset = 0

        d = defer.succeed(limit)
        d.addCallback(persistence.get_repository(repo_interface).get_list,
                      offset)
        return d
