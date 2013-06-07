import json
import os
import time

from shapely.geometry import Point
import mock
import requests

from twisted.internet import defer
from twisted.trial import unittest

from gorynych.test.test_info import create_geojson_checkpoints
from gorynych.common.domain.types import Checkpoint
from gorynych.processor.services.trackservice import ProcessorService, TrackService
from gorynych.processor.domain import track
from gorynych.info.domain.ids import RaceID, PersonID
from gorynych.common.domain import events


URL = 'http://localhost:8085'
data = open(os.path.join(os.path.dirname(__file__), '1120-5321.json'),
                'r').read()
DATA = json.loads(data)

test_race = json.loads('{"race_title":"Test Trackservice Task","race_type":"racetogoal","start_time":"1347704100","end_time":"1347724800","bearing":"None","checkpoints":{"type": "FeatureCollection", "features": [{"geometry": {"type": "Point", "coordinates": [43.9785, 6.48]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 1, "name": "D01", "checkpoint_type": "to", "open_time": 1347704100}}, {"geometry": {"type": "Point", "coordinates": [43.9785, 6.48]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 3000, "name": "D01", "checkpoint_type": "ss", "open_time": 1347707700}}, {"geometry": {"type": "Point", "coordinates": [44.3711, 6.3098]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 21000, "name": "B46", "checkpoint_type": "ordinal", "open_time": 1347704100}}, {"geometry": {"type": "Point", "coordinates": [43.9511, 6.3708]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 2000, "name": "B20", "checkpoint_type": "ordinal", "open_time": 1347704100}}, {"geometry": {"type": "Point", "coordinates": [44.0455, 6.3602]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 400, "name": "B43", "checkpoint_type": "ordinal", "open_time": 1347704100}}, {"geometry": {"type": "Point", "coordinates": [43.9658, 6.5578]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 1500, "name": "B37", "checkpoint_type": "es", "open_time": 1347704100}}, {"geometry": {"type": "Point", "coordinates": [43.9658, 6.5578]}, "type": "Feature", "properties": {"close_time": 1347724800, "radius": 1000, "name": "B37", "checkpoint_type": "goal", "open_time": 1347704100}}]}}')

def create_checkpoints():
    ch_keys = DATA['waypoints'].keys()
    ch_keys.sort()
    result = []
    for key in ch_keys:
        # list: ["lat", u'lon', u'radius', u'name', 'dist', ss_open_time,
        # 'is_start', 'is_finish',
        ch = DATA['waypoints'][key]
        open_time = int(DATA['task_start'])
        close_time = int(DATA['task_end'])
        ch_type = 'ordinal'
        if int(ch[6]):
            open_time = int(ch[5])
            ch_type = 'ss'
        elif int(ch[7]):
            ch_type = 'es'
        if int(key) == 1:
            ch_type = 'to'
        if int(key) == 7:
            ch_type = 'goal'
        result.append(Checkpoint(ch[3], Point(float(ch[0]), float(ch[1])),
                                 ch_type,
            (open_time, close_time), int(ch[2])))
    return result


def create_contest(title='Test TrackService contest'):
    params = dict(title=title, start_time=1,
                  end_time=int(time.time()),
                  place = 'La France', country='ru',
                  hq_coords='43.3,23.1', timezone='Europe/Paris')
    r = requests.post(URL + '/contest', data=params)
    print r.text
    return r.json()['id']


def register_paragliders_on_contest(cont_id):
    pilots = DATA['pilots']
    for key in pilots.keys():
        params = dict(name=pilots[key]['name'].split(' ')[0],
                           surname=pilots[key]['name'].split(' ')[1],
                           country='ru',
                           email='s@s.ru', reg_date='2012,12,12')
        r = requests.post(URL + '/person', data=params)
        pers_id = r.json()['id']
        params = dict(person_id=pers_id, glider='mantra',
                      contest_number=str(key))
        r = requests.post('/'.join((URL, 'contest', cont_id,
                                'paraglider')), data=params)


def create_race(contest_id, checkpoints=None):
    if not checkpoints:
        checkpoints = create_geojson_checkpoints()
    params = dict(title="Test TrackService Task", race_type='racetogoal',
                  checkpoints=checkpoints)
    return requests.post('/'.join((URL, 'contest', contest_id, 'race')),
                         data=params)

def raise_callback():
    d = defer.Deferred()
    d.addCallback(lambda x: None)
    d.callback(1)
    return d

class ParsingTest(unittest.TestCase):

    def test_parsing(self):
        # create contest, person, register paragliders, create race:
        cont_id = create_contest()
        print "contest created: ", cont_id
        register_paragliders_on_contest(cont_id)
        print "paragliders registered"
        race = create_race(cont_id,
                           create_geojson_checkpoints(create_checkpoints()))
        print race.text
        race_id = race.json()['id']
        # self.init_task(race_id)
        r = requests.post('/'.join((URL, 'contest', cont_id, 'race',
                                    race_id, 'track_archive')),
                                  data={'url':
                                      'http://localhost:8080/16items.zip'})
        print r.text
        print r.status_code


class TestProcessorService(unittest.TestCase):
    def setUp(self):
        self.ps = ProcessorService(1)
        self.pe_patch = mock.patch('gorynych.processor.services.trackservice.pe')
        self.pe = self.pe_patch.start()

    def tearDown(self):
        self.pe_patch.stop()

    def test_inform_about_paragliders(self):
        i0 = {'person_id': 'person_id', 'trackfile':'1.igc',
            'contest_number': '1'}
        i1, i2 = [], []
        rid = RaceID()
        es = mock.Mock()
        self.pe.event_store.return_value = es
        es.persist.return_value = raise_callback()
        result = self.ps._inform_about_paragliders([[i0], i1, i2], rid)

        ev1 = events.ParagliderFoundInArchive(rid, payload=i0)
        ev2 = events.TrackArchiveUnpacked(rid, payload=[[i0], i1, i2])
        expected = [mock.call(ev1), mock.call(ev2)]
        self.assertListEqual(es.persist.mock_calls, expected)


class TestTrackService(unittest.TestCase):

    @defer.inlineCallbacks
    def test_get_aggregate(self):
        es = mock.Mock()
        es.load_events = mock.Mock()
        es.load_events.return_value = self.track_created(tid)
        ts = TrackService(mock.Mock(), es, mock.Mock())
        self.assertEqual(len(ts.aggregates), 0)

        tid = track.TrackID()
        d = yield ts._get_aggregate(tid)
        self.assertIsInstance(d, track.Track)
        self.assertEqual(d.id, tid)
        self.assertEqual(len(ts.aggregates), 1)

        d2 = yield ts._get_aggregate(tid)
        self.assertIsInstance(d2, track.Track)
        self.assertEqual(len(ts.aggregates), 1)

    def track_created(self, tid):
        e1 = events.TrackCreated(tid,
            dict(track_type='competition_aftertask', race_task=test_race))
        return [e1]

    @defer.inlineCallbacks
    def test_process_ParagliderFoundInArchive(self):
        es = mock.Mock()
        es.persist.return_value = raise_callback()
        ts = TrackService(mock.Mock(), es, mock.Mock())
        ts.execute_ProcessData = mock.Mock()
        ts.append_track_to_race_and_person = mock.Mock()
        ts.event_dispatched = mock.Mock()

        rid = RaceID.fromstring('r-f4887979-257d-482d-a15c-e87e6eeba2b8')
        ev = events.ParagliderFoundInArchive(rid)
        ev.payload = dict(trackfile='trackfile.2.igc', contest_number='2',
            person_id=PersonID())

        result = yield ts.process_events([ev])
        ts.process_ParagliderFoundInArchive = mock.Mock()
        ts.process_ParagliderFoundInArchive.assert_called_with(1)
        print result

