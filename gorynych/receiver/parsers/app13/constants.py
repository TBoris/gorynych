# encoding: utf-8

"""
*Proto classes contain fields as defined in the protocol. In case
of any protocol changes you need to edit them accordingly
"""
from struct import Struct

HEADER = Struct('!BBH')
MAGIC_BYTE = 0xBA


class BasePointProto(object):
    LAT = 'lat_base'
    LON = 'long_base'
    TS = 'time_base'
    ALT = 'alt_base'
    ANGLE_DIV = 'angle_div'
    TIMEDELTA = 'time_step'
    H_SPEED = 'h_speed'
    V_SPEED = 'v_speed'


class PointProto(object):
    LAT = 'LAT'
    LON = 'LONG'
    TS = 'TIME'
    ALT = 'ALT'
    H_SPEED = 'H_SPEED'
    V_SPEED = 'V_SPEED'


class FrameId(object):
    MOBILEID = 1
    PATHCHUNK = 2
    PATHCHUNK_ZIPPED = 3
    PATHCHUNK_CONF = 4
    RPC_CALL = 5
    RPC_RESPONSE = 6
    RPC_MESSAGE = 7
    DEBUG_FRAME = 100
    MAGIC_RESERVE = 0xBA
