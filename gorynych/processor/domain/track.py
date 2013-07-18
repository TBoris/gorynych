# coding=utf-8
'''
Track aggregate.
'''
from twisted.internet import defer
from gorynych.common.exceptions import NoAggregate
from gorynych.common.infrastructure import persistence as pe

__author__ = 'Boris Tsema'
import uuid

import numpy as np

from gorynych.common.domain.model import AggregateRoot, ValueObject, DomainIdentifier
from gorynych.info.domain.ids import namespace_uuid_validator
from gorynych.common.domain import events
from gorynych.common.domain.types import checkpoint_collection_from_geojson
from gorynych.processor.domain import services
from twisted.python import log


DTYPE = [('id', 'i4'), ('timestamp', 'i4'), ('lat', 'f4'),
    ('lon', 'f4'), ('alt', 'i2'), ('g_speed', 'f4'), ('v_speed', 'f4'),
    ('distance', 'i4')]

EARTH_RADIUS = 6371000

def track_types(ttype):
    types = dict(competition_aftertask=services.FileParserAdapter(DTYPE),
        online=services.OnlineTrashAdapter(DTYPE))
    return types.get(ttype)


def race_tasks(rtask):
    assert isinstance(rtask, dict), "Race task must be dict."
    tasks = dict(racetogoal=RaceToGoal)
    res = tasks.get(rtask['race_type'])
    if res:
        return res(rtask)


class TrackID(DomainIdentifier):
    '''
    trck-749e0d12574a4d4594e72488461574d0'
    namespace-uuid4.hex
    '''
    def __init__(self):
        _uid = uuid.uuid4().hex
        self._id = '-'.join(('trck', _uid))

    def _string_is_valid_id(self, string):
        return namespace_uuid_validator(string, 'trck')


class TrackState(ValueObject):
    '''
    Hold track state. Memento.
    '''
    states = ['not started', 'started', 'finished', 'landed']
    def __init__(self, id, event_list):
        self.id = id
        # Time when track speed become more then threshold.
        self.become_fast = None
        self.become_slow = None
        self.track_type = None
        self.race_task = None
        self.last_checkpoint = 0
        self.state = 'not started'
        self.statechanged_at = None
        self.started = False
        self.in_air = False
        self.start_time = None
        # Buffer for points.
        self._buffer = np.empty(0, dtype=DTYPE)
        # Time at which track has been ended.
        self.end_time = None
        self.ended = False
        self.finish_time = None
        self.last_distance = 0
        for ev in event_list:
            self.mutate(ev)

    def mutate(self, ev):
        '''
        Mutate state according to event. Analog of apply method in AggregateRoot.
        '''
        evname = ev.__class__.__name__
        if hasattr(self, 'apply_' + evname):
            getattr(self, 'apply_' + evname)(ev)

    def apply_TrackCreated(self, ev):
        self.track_type = ev.payload['track_type']
        self.race_task = ev.payload['race_task']

    def apply_TrackCheckpointTaken(self, ev):
        n = ev.payload[0]
        if self.last_checkpoint < n:
            self.last_checkpoint = n

    def apply_TrackStarted(self, ev):
        if not self.started:
            self.state = 'started'
            self.start_time = ev.occured_on
            self.statechanged_at = ev.occured_on
            self.started = True

    def apply_TrackEnded(self, ev):
        if not self.state == 'finished':
            self.state = ev.payload['state']
            self.statechanged_at = ev.occured_on
        self.ended = True
        self.end_time = ev.occured_on
        self.last_distance = ev.payload.get('distance')

    def apply_TrackFinished(self, ev):
        if not self.state == 'finished':
            self.state = 'finished'
            self.statechanged_at = ev.occured_on

    def apply_TrackFinishTimeReceived(self, ev):
        self.finish_time = ev.payload

    def apply_TrackInAir(self, ev):
        self.in_air = True

    def apply_TrackSlowedDown(self, ev):
        self.become_fast, self.become_slow = None, ev.occured_on

    def apply_TrackSpeedExceeded(self, ev):
        self.become_slow, self.become_fast = None, ev.occured_on

    def apply_TrackLanded(self, ev):
        self.in_air = False
        if not self.state == 'finished':
            self.state = 'landed'
            self.last_distance = int(ev.payload)
            self.statechanged_at = ev.occured_on

    def get_state(self):
        result = dict()
        result['state'] = self.state
        result['statechanged_at'] = self.statechanged_at
        return result


class Track(AggregateRoot):

    flush_time = 60 # unused?
    dtype = DTYPE

    def __init__(self, id, events=None):
        super(Track, self).__init__()
        self.id = id
        self._id = None
        self._state = TrackState(id, events)
        self._task = None
        self._type = None
        self.changes = []
        self.points = np.empty(0, dtype=self.dtype)

    def apply(self, ev):
        if isinstance(ev, list):
            for e in ev:
                self._state.mutate(e)
                self.changes.append(e)
        else:
            self._state.mutate(ev)
            self.changes.append(ev)

    def process_data(self, data):
        # Here TrackType read data and return it in good common format.
        data = self.type.read(data)
        # Now TrackType correct points and calculate smth if needed.
        points, evs = self.type.process(data,
            self.task.start_time, self.task.end_time, self._state)
        self.apply(evs)
        if points is None:
            return
        evs = services.ParagliderSkyEarth(self._state).state_work(points)
        self.apply(evs)
        # Task process points and emit new events if occur.
        points, ev_list = self.task.process(points, self._state, self.id)
        self.apply(ev_list)
        self.points = np.hstack((self.points, points))
        # Look for state after processing and do all correctness.
        evlist = self.type.correct(self)
        self.apply(evlist)

    @property
    def state(self):
        return self._state.get_state()

    @property
    def task(self):
        if not self._task:
            self._task = race_tasks(self._state.race_task)
        return self._task

    @property
    def type(self):
        if not self._type:
            self._type = track_types(self._state.track_type)
        return self._type

    def reset(self):
        self.changes=[]
        self.points = np.empty(0, dtype=self.dtype)


class RaceToGoal(object):
    '''
    Incapsulate race parameters calculation.
    '''
    type = 'racetogoal'
    wp_error = 300
    def __init__(self, task):
        chlist = task['checkpoints']
        self.checkpoints = checkpoint_collection_from_geojson(chlist)
        self.start_time = int(task['start_time'])
        self.end_time = int(task['end_time'])
        self.calculate_path()

    def calculate_path(self):
        '''
        For a list of checkpoints calculate distance from concrete
        checkpoint to the goal.
        @return:
        @rtype:
        '''
        self.checkpoints.reverse()
        self.checkpoints[0].distance = 0
        for idx, p in enumerate(self.checkpoints[1:]):
            p.distance = int(p.distance_to(self.checkpoints[idx]))
            p.distance += self.checkpoints[idx].distance
        self.checkpoints.reverse()

    def process(self, points, taskstate, _id):
        '''
        Process points and emit events if needed.
        @param points: array with points for some seconds (minute usually).
        @type points: C{np.array}
        @param taskstate: read-only object implementing track state.
        @type taskstate: L{TrackState}
        @return: (points, event list)
        @rtype: (np.array, list)
        '''
        assert isinstance(points, np.ndarray), "Got %s instead of array" % \
                                               type(points)
        assert points.dtype == DTYPE
        eventlist = []
        lastchp = taskstate.last_checkpoint
        if lastchp < len(self.checkpoints) - 1:
            nextchp = self.checkpoints[lastchp + 1]
        else:
            # Last point taken but we still have data.
            for p in points:
                p['distance'] = 200
            return points, []
        if taskstate.state == 'landed':
            if taskstate.last_distance:
                for p in points:
                    p['distance'] = taskstate.last_distance
                return points, []
            else:
                for p in points:
                    p['distance'] = 200
                return points, []

        ended = taskstate.ended
        for idx, p in np.ndenumerate(points):
            dist = nextchp.distance_to((p['lat'], p['lon']))
            if dist - nextchp.radius <= self.wp_error and not ended:
                eventlist.append(
                    events.TrackCheckpointTaken(_id, (lastchp+1, int(dist)),
                                                    occured_on=p['timestamp']))
                if nextchp.type == 'es':
                    eventlist.append(events.TrackFinishTimeReceived(_id,
                        payload=p['timestamp']))
                    self.wp_error = 20
                if nextchp.type == 'goal':
                    eventlist.append(events.TrackFinished(_id,
                        occured_on=taskstate.finish_time))
                    ended = True
                    self.wp_error = 20
                if nextchp.type == 'ss':
                    eventlist.append(events.TrackStarted(_id,
                        occured_on=p['timestamp']))
                if lastchp + 1 < len(self.checkpoints) - 1:
                    nextchp = self.checkpoints[lastchp + 2]
                    lastchp += 1
            p['distance'] = int(dist + nextchp.distance)

        return points, eventlist



