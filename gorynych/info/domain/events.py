'''
List of domain events in context "info".
'''
from gorynych.common.domain.model import DomainEvent
from gorynych.common.infrastructure import serializer


class ArchiveURLReceived(DomainEvent):
    '''
    Notify processing system that new archive with tracks has been loaded for
    race.
    Event fields:
    @param id: race id
    @param url: url with track archive.
    '''
    serializer = serializer.StringSerializer()


class RaceCheckpointsChanged(DomainEvent):
    '''
    Notify other systems (such as processor) about checkpoints change.
    @todo: think about more explicit name for this event.
    Event fields:
    @param id: race id
    @param payload: list with new checkpoints. List of L{Checkpoints}.
    '''
    from gorynych.common.domain.types import checkpoint_from_geojson
    serializer = serializer.GeoObjectListSerializer(checkpoint_from_geojson)


class ParagliderRegisteredOnContest(DomainEvent):
    '''
    Person with id id registered on contest with id contest_id as paraglider.
    Event is fired to notificate users.
    Event fields:
    @param aggregate_id: L{PersonID}
    @param payload: L{ContestID}
    '''
    from gorynych.info.domain.contest import ContestID
    serializer = serializer.IdentifierObjectSerializer(ContestID)


class TrackerAssigned(DomainEvent):
    '''
    This event is fired then tracker is assigned to someone.

    Event fields are:
    @param id: id of aggregate to which tracker has been assigned.
    @param tracker_id: tracker id.
    '''


class TrackerUnAssigned(DomainEvent):
    '''
    This event is fired then tracker is unassigned from person or transport.
    @param aggregate_id: id of aggregate from which tracker has been
    unassigned.
    @param payload: id of Tracker aggregate.
    '''
