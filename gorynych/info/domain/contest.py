'''
Contest Aggregate.
'''
from copy import deepcopy

import pytz
from zope.interface.interfaces import Interface

from gorynych.info.domain import race
from gorynych.common.domain.model import AggregateRoot, ValueObject
from gorynych.common.domain.types import Address, Country, Name
from gorynych.common.domain.events import ParagliderRegisteredOnContest
from gorynych.common.infrastructure import persistence
from gorynych.info.domain.ids import ContestID, PersonID, TrackerID, TransportID
from gorynych.common.exceptions import DomainError

AVAILABLE_PARTICIPANTS = ('winddummy', 'rescuer', 'organizer')


class ContestFactory(object):

    def create_contest(self, title, start_time, end_time,
                       contest_place, contest_country, hq_coords, timezone,
                       contest_id=None):
        address = Address(contest_place, contest_country, hq_coords)
        if end_time < start_time:
            raise ValueError("Start time must be less then end time.")
        if not contest_id:
            contest_id = ContestID()
        elif not isinstance(contest_id, ContestID):
            contest_id = ContestID.fromstring(contest_id)
        if not timezone in pytz.all_timezones_set:
            raise pytz.exceptions.UnknownTimeZoneError("Wrong timezone.")
        contest = Contest(contest_id, start_time, end_time, address)
        contest.title = title
        contest.timezone = timezone
        return contest


class Contest(AggregateRoot):

    def __init__(self, contest_id, start_time, end_time, address):
        super(Contest, self).__init__()
        self.id = contest_id
        self._title = ''
        self._timezone = ''
        self._start_time = start_time
        self._end_time = end_time
        self.address = address
        self._participants = dict()
        self.race_ids = set()
        self.retrieve_id = None

    @property
    def timezone(self):
        '''
        @return: full name of time zone in which contest take place (
        Europe/Moscow).
        @rtype: C{str}
        '''
        return self._timezone

    @timezone.setter
    def timezone(self, value):
        '''
        This is a blocking function! It read a file in usual blocking mode
        and it's better to wrap result in maybeDeferred.

        @param value: time zone full name
        @type value: C{str}
        '''
        if value in pytz.all_timezones_set:
            self._timezone = value

    @property
    def start_time(self):
        return self._start_time

    @start_time.setter
    def start_time(self, value):
        if int(value) == self.start_time:
            return
        old_start_time = self.start_time
        self._start_time = int(value)
        if not self._invariants_are_correct():
            self._start_time = old_start_time
            raise ValueError("Incorrect start_time violate aggregate's "
                             "invariants.")

    @property
    def end_time(self):
        return self._end_time

    @end_time.setter
    def end_time(self, value):
        if int(value) == self.end_time:
            return
        old_end_time = self.end_time
        self._end_time = int(value)
        if not self._invariants_are_correct():
            self._end_time = old_end_time
            raise ValueError("Incorrect end_time violate aggregate's "
                             "invariants.")

    def change_times(self, start_time, end_time):
        '''
        Change both start time and end time of context.
        @param start_time:
        @type start_time: C{int}
        @param end_time:
        @type end_time: C{int}
        @return:
        @rtype:
        @raise: ValueError if times violate aggregate's invariants.
        '''
        start_time = int(start_time)
        end_time = int(end_time)
        if int(start_time) >= int(end_time):
            raise ValueError("Start_time must be less then end_time.")
        if start_time == self.start_time:
            self.end_time = end_time
        elif end_time == self.end_time:
            self.start_time = start_time
        else:
            old_start_time = self.start_time
            old_end_time = self.end_time
            self._start_time = start_time
            self._end_time = end_time
            if not self._invariants_are_correct():
                self._start_time = old_start_time
                self._end_time = old_end_time
                raise ValueError("Times values violate aggregate's "
                                 "invariants.")

    @property
    def country(self):
        return self.address.country

    @country.setter
    def country(self, value):
        self.address = Address(self.place, Country(value),
                               self.address.coordinates)

    @property
    def place(self):
        return self.address.place

    @place.setter
    def place(self, value):
        self.address = Address(value, self.address.country,
                               self.address.coordinates)

    @property
    def hq_coords(self):
        '''

        @return:(float, float)
        @rtype: C{tuple}
        '''
        return self.address.coordinates

    @hq_coords.setter
    def hq_coords(self, value):
        self.address = Address(self.place, self.country, value)

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value.strip()

    def register_paraglider(self, pers, glider, cnum):
        paragliders_before = deepcopy(self._participants)
        glider = glider.strip().split(' ')[0].lower()
        self._participants[str(pers.id)] = dict(
            role='paraglider',
            name=pers.name.name,
            surname=pers.name.surname,
            email=pers.email,
            country=pers.country,
            glider=glider,
            contest_number=int(cnum),
            phone=pers.phone)
        if not self._invariants_are_correct():
            self._participants = paragliders_before
            raise ValueError("Paraglider must have unique contest number.")
        persistence.event_store().persist(ParagliderRegisteredOnContest(
            pers.id, self.id))
        return self

    def add_transport(self, trns, phone=""):
        self._participants[str(trns.id)] = dict(
            role='transport',
            title=trns.title,
            description=trns.description,
            type=trns.type,
            phone=phone)
        return self

    def add_rescuer(self, r_id, title, phone="", description=""):
        self._participants[r_id] = dict(
            role='rescuer',
            title=title,
            description=description,
            phone=phone)
        return self

    def add_winddummy(self, pers):
        self._participants[pers.id] = dict(
            role='winddummy',
            name=pers.name.name,
            surname=pers.name.surname,
            phone=pers.phone)
        return self

    def add_organizer(self, pers):
        self._participants[pers.id] = dict(
            role='organizer',
            email=pers.email)
        return self

    def remove_transport(self, transport_id):
        if transport_id in self.transport:
            del self.transport[transport_id]

    def _invariants_are_correct(self):
        """
        Check next invariants for contest:
        every paraglider has unique contest_number
        context start_time is less then end_time
        """
        contest_numbers = set()
        paragliders = set()
        for key in self.paragliders.keys():
                contest_numbers.add(
                    self.paragliders[key]['contest_number'])
                paragliders.add(key)
        all_contest_numbers_uniq = len(paragliders) == len(contest_numbers)

        end_after_start = int(self.start_time) < int(self.end_time)
        return all_contest_numbers_uniq and end_after_start

    def _rollback_register_paraglider(self, paraglider_before, person_id):
        # TODO: this function should rollback all paragliders. Am I need this
        # function?
        self._participants[person_id] = paraglider_before

    def apply_ContestRaceCreated(self, ev):
        self.race_ids.add(ev.payload)

    def change_participant_data(self, person_id, **kwargs):
        if not kwargs:
            raise ValueError("No new data has been received.")
        try:
            old_participant = deepcopy(self._participants[person_id])
        except KeyError:
            raise ValueError("No participant with such id.")

        for key in kwargs.keys():
            if key == 'contest_number':
                # TODO: check necessity of this.
                kwargs[key] = int(kwargs[key])
            if key == 'glider':
                kwargs[key] = kwargs[key].strip().split(' ')[0].lower()
            self._participants[person_id][key] = kwargs[key]

        if not self._invariants_are_correct():
            self._participants[person_id] = old_participant
            raise ValueError("Contest invariants violated.")

    def _get_participants(self, role):
        result = dict()
        for key in self._participants:
            if self._participants[key]['role'] == role:
                result[key] = self._participants[key]
        return result

    @property
    def paragliders(self):
        return self._get_participants('paraglider')

    @property
    def transport(self):
        return self._get_participants('transport')

    @property
    def winddummies(self):
        return self._get_participants('winddummy')

    @property
    def organizers(self):
        return self._get_participants('organizer')

    @property
    def rescuers(self):
        return self._get_participants('rescuer')


def change(cont, params):
    '''
    Do changes in contest.
    @param cont:
    @type cont: Contest
    @param params:
    @type params: dict
    @return:
    @rtype: Contest
    '''
    if params.get('start_time') and params.get('end_time'):
        cont.change_times(params['start_time'], params['end_time'])
        del params['start_time']
        del params['end_time']

    if params.get('coords'):
        lat, lon = params['coords'].split(',')
        cont.hq_coords = (lat, lon)
        del params['coords']

    for param in params.keys():
        setattr(cont, param, params[param])
    return cont


def change_participant(cont, participant_data):
    if 'glider' in participant_data:
        cont.change_participant_data(participant_data['person_id'],
                                     glider=participant_data['glider'])
    if 'contest_number' in participant_data:
        cont.change_participant_data(participant_data['person_id'],
                                     contest_number=participant_data['contest_number'])
    return cont
