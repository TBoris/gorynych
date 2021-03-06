
from operator import xor

from zope.interface import implementer
from gorynych.receiver.parsers import IParseMessage
from functools import reduce


@implementer(IParseMessage)
class MobileTracker(object):
    '''
    Parser for some old mobile application which is not used.
    '''

    def __init__(self):
        self.format = dict(imei=0, lat=1, lon=2, alt=3,
                           h_speed=4, ts=5)
        self.convert = dict(imei=str, lat=float,
                            lon=float, alt=int, h_speed=float,
                            ts=int)

    def _separate_checksum(self, msg):
        delimeter = msg.index('*')
        data = msg[:delimeter]
        checksum = msg[delimeter + 1:]
        return data, checksum

    def check_message_correctness(self, msg):
        try:
            data, checksum = self._separate_checksum(msg)
            calculated_checksum = reduce(xor, map(ord, data))
            if calculated_checksum != int(checksum):
                raise ValueError("Incorrect checksum")
        except Exception as e:
            raise ValueError(str(e))
        return msg

    def parse(self, msg):
        data, checksum = self._separate_checksum(msg)
        data = data.split(',')
        if len(data) > 6:  # fucking decimal commas
            data = [data[0], data[1] + '.' + data[2], data[3] +
                    '.' + data[4], data[5], data[6] + '.' + data[7], data[8]]
        result = dict()
        for key in self.format.keys():
            result[key] = self.convert[key](data[self.format[key]])
        return result
