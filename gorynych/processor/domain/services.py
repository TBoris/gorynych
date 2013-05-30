__author__ = 'Boris Tsema'

from calendar import timegm
import time

import scipy as sc
from scipy import signal, interpolate
import numpy as np
import numpy.ma as ma

from gorynych.common.domain.services import point_dist_calculator

def choose_offline_parser(trackname):
    if trackname.endswith('.igc'): return IGCTrackParser
    else: return KMLTrackParser


class IGCTrackParser(object):
    '''
    Domain service which parse .igc tracks.
    Receive filename and parse it.
    '''
    def __init__(self, dtype):
        self.dtype = dtype

    def parse(self, filename):
        f = open(filename, 'r')
        date = ''
        ts, lat, lon, alt = [], [], [], []
        for line in f:
            if line.startswith('HFDTE'):
                date = line[-8:-2]
            elif line.startswith('B'):
                ts.append(int(timegm(time.strptime(date + line[1:7],
                                                   '%d%m%y%H%M%S'))))
                lat.append(self.latitude(line[7:15]))
                lon.append(self.longitude(line[15:24]))
                # TODO: rewrite with one region.
                # Use altitude from GPS only.
                alt.append(float(line[25:35][5:10]))
        result = sc.empty(len(ts), dtype=self.dtype)
        result['timestamp'] = sc.array(ts)
        result['lat'] = sc.array(lat)
        result['lon'] = sc.array(lon)
        result['alt'] = sc.array(alt)
        return result

    def latitude(self, lat):
        """Convert gps coordinates. Use string, return string.
        >>> latitude('37550333S')
        '-37.917222'
        >>> latitude('37550333N')
        '37.917222'
        >>> latitude('3800002N')
        '38.000033'
        """
        dd_lat = int(lat[:2])
        mm_lat = lat[2:4]
        ssss_lat = lat[4:7]
        sep = '.'
        mm = round(float(sep.join((mm_lat, ssss_lat)))/60, 6)
        if lat[-1:] == "N":
            sign = ''
        else:
            sign = '-'
        return ''.join((sign, str(dd_lat + mm)))

    def longitude(self, lon):
        """Convert gps coordinates
        >>> longitude('029072171E')
        '29.120285'
        >>> longitude('029072171W')
        '-29.120285'
        """
        dd_lon = int(lon[:3])
        mm_lon = lon[3:5]
        sep = '.'
        ssss_lon = lon[5:8]
        mm = round(float(sep.join((mm_lon, ssss_lon)))/60, 6)
        if lon[-1:] == "E":
            sign = ''
        else:
            sign = '-'
        return ''.join((sign, str(dd_lon + mm)))


class KMLTrackParser(object):
    '''
    Domain service which parse .kml tracks.
    '''
    pass


class ParaglidingTrackCorrector(object):
    '''

    '''
    # TODO: Rewrite methods with performance in mind (no extra array
    # creation etc...)
    altmin = 50
    altmax = 6000
    maxdifs = [('alt', 40), ('lat', 0.001), ('lon', 0.001)]

    def _find_points_outside_corridor(self, points, lowborder, highborder):
        '''
        Find point with values outside corridor. Return lists with indexes
        of points lower lowborder and list with items higher highborder.
        @param points:
        @type points: C{numpy.array}
        @param lowborder:
        @type lowborder:
        @param highborder:
        @type highborder:
        @return: array of ultralow points indexes, array of ultrahigh points
         indexes
        @rtype: C{tuple} of two C{numpy.array}
        '''
        ultrahigh_idxs = np.where(points > highborder)
        ultralow_idxs = np.where(points < lowborder)
        return ultralow_idxs, ultrahigh_idxs

    def _place_alt_in_corridor(self, alt):
        '''
        Find altitudes which is outside of alt corridor and replace it with
        highest possible or lowest possible.
        @param alt:
        @type alt: C{numpy.array}
        @return:
        @rtype:
        '''
        alts_low, alts_high = self._find_points_outside_corridor(
            alt, self.altmin, self.altmax)
        for idx in alts_high:
            alt[idx] = self.altmax
        for idx in alts_low:
            alt[idx] = self.altmin
        return alt

    def _mark_outside_altitudes(self, item):
        '''
        Find points which altitudes out of corridor. Delete bounding points
        return bad points inside the track.

        @param item: array with dtype defined in CompetitionTrack.
        @type item: C{numpy.array}
        @return:
        @rtype:
        '''
        # Mark points which is out of self.altmin-self.altmax corridor.
        alts_low, alts_high = self._find_points_outside_corridor(
                                    item['alt'], self.altmin, self.altmax)
        outside_idxs = np.concatenate(alts_low, alts_high)
        outside_idxs.sort()
        # Delete bounding bad points if any.
        while outside_idxs[-1] == len(item['timestamp']) - 1:
            item = np.delete(item, [outside_idxs[-1]])
            outside_idxs = np.delete(outside_idxs, np.s_[-1])
        # Delete first bounding points if any.
        fb = None
        for i, idx in enumerate(outside_idxs):
            while outside_idxs[i] == i:
                fb = i
        if fb:
            item = np.delete(item, np.s_[:fb + 1])
            outside_idxs = np.delete(outside_idxs, np.s_[:fb + 1])

        return outside_idxs, item

    def correct_data(self, item):
        '''
        Main idea: if points has bad altitude we just drop it.
        Here we are looking for bad longitude and latitude and smoothing it.
        @param item: numpy array with dtype defined in CompetitionTrack
        @type item: np.array
        @return:
        @rtype: np.array
        '''
        outside_idxs, item = self._mark_outside_altitudes(item)
        # delete bad points in the array
        x = np.delete(item['timestamp'], outside_idxs)
        for dif in self.maxdifs:
            # Delete bad points in the array.
            y = np.delete(item[dif[0]], outside_idxs)
            # Now y array has the same indexes as x.
            if len(y) - len(x):
                raise SystemExit("UFO was here: %s %s %s"
                                 % (len(x), len(y), dif[0]))
            try:
                kern_size = 3
                exc = self._median_finder(y, dif[1], kern_size)
            except Exception as e:
                raise Exception("while looking for initial exc points %s: %s",
                        dif[0], e)
            if outside_idxs or exc:
                if exc:
                    # Median filter found points. Smooth it.
                    try:
                        # here was some bug, TODO: test it and delete
                        if len(y) < 10: continue
                        smoothed = self._interpolate(y, x, exc)
                    except Exception as e:
                        raise Exception("error while smoothing y: %r, x: %r, exc: %s, "
                           "error: %r" % (y, x, exc, e))
                    counter = 1
                    while exc and counter < 15:
                        exc = self._median_finder(smoothed, dif[1],
                                           kern_size + int(counter / 5) * 2)
                        smoothed = self._interpolate(smoothed, x, exc)
                        counter += 1
                    # Now I have smoothed array with some excluded points.
                    y = smoothed

                # Points inside the array has been removed,
                # so we need to interpolate it.
                try:
                    tck = interpolate.splrep(x, y, s=0)
                except Exception as e:
                    raise Exception("while preparing for interpolating %s: %s"
                                    % (dif[0], e))
                try:
                    y = interpolate.splev(item['timestamp'], tck, der=0)
                except Exception as e:
                    raise Exception("while interpolating %s: %s" %
                                    (dif[0], e))
                if dif[0] == 'alt':
                    y = self._place_alt_in_corridor(y)

            item[dif[0]] = y
        return item

    def _median_finder(self, y, maxdif, kern_size=3):
        '''Go through 2-d array and eliminate highly-deviated points.
        maxdif - maximum allowed difference between point and smoothed point.
        Return tuple (list of bad points (int), lastitem (int)).
        If last point of y is bad point, then lastitem will be previous good point
        in kern_size region from the end of y, or y[-kern_size] if no good points
        in that region.
        '''
        kern_size = int(kern_size)
        filtered = y.copy()
        filtered[0] = np.mean(filtered[:kern_size])
        filtered = signal.medfilt(filtered, kern_size)
        filtered[len(filtered) - 1] = np.mean(filtered[kern_size:])
        result = y - signal.medfilt(filtered, kern_size)
        bads = np.where(abs(result) > maxdif)
        return bads

    def _interpolate(self, y, x, exclude=None):
        '''
        Smooth y(x). exclude - list of points to exclude while smoothing.
        '''
        if exclude:
            _x = np.delete(x, exclude)
            y = np.delete(y, exclude)
        else:
            _x = x
        tck = interpolate.splrep(_x, y, s=0)
        ynew = interpolate.splev(x, tck, der=0)
        return ynew


def vspeed_calculator(alt, times):
    result = np.ediff1d(alt, to_begin=1) / np.ediff1d(times, to_begin=1)
    np.around(result, decimals=2, out=result)
    return result


def gspeed_calculator(lat, lon, times):
    result = [1]
    for i in xrange(len(times) - 1):
        result.append(point_dist_calculator(lat[i], lon[i], lat[i+1],lon[i+1]))
    result = np.array(result) / np.ediff1d(times, to_begin=1)
    np.around(result, decimals=1, out=result)
    return  result


class OfflineCorrectorService:
    '''
    Cut track and correct it.
    '''
    # Maximum gap in track after which it accounted as finished (in seconds).
    maxtimediff = 300

    def _clean_timestamps(self, track, stime, etime):
        '''
        Cut track in time and make array with timestamps monotonic.
        @param track:
        @type track:
        @return:
        @rtype:
        '''
        data = ma.masked_inside(track, stime, etime)
        track = track.compress(data.mask)
        # Eliminate repetitive points.
        times, indices = np.unique(track['timestamp'], return_index=True)
        track = track[indices]
        # Here we still can has points reversed in time. Fix it.
        tdifs = np.ediff1d(data['timestamp'], to_begin=1)
        # At first let's find end of track by timeout, if any.
        track_end_idxs = np.where(tdifs > self.maxtimediff)[0]
        if track_end_idxs:
            track_end_idxs = track_end_idxs[0]
            track = track[:track_end_idxs]
            tdifs = tdifs[:track_end_idxs]

        # Eliminate reverse points.
        data = ma.masked_greater(tdifs, 0)
        track = track.compress(data.mask)
        return track

    def correct_track(self, track, stime, etime):
        '''
        Receive raw parsed data, cut it and looks for bad times.
        @param track: array with dtype defined in L{CompetitionTrack}
        @type track: C{numpy.array}
        @return track without dublicated or reversed points in timescale.
        @rtype: C{numpy.array}
        '''
        # Eliminate points outside task time.
        track = self._clean_timestamps(track, stime, etime)
        return ParaglidingTrackCorrector().correct_data(track)


def runs_of_ones_array(bits):
    '''
    Calculate start and end indexes of subarray of ones in array.
    @param bits:
    @type bits:
    @return:
    @rtype:
    '''
    # make sure all runs of ones are well-bounded
    bounded = np.hstack(([0], bits, [0]))
    # get 1 at run starts and -1 at run ends
    difs = np.diff(bounded)
    run_starts, = np.where(difs > 0)
    run_ends, = np.where(difs < 0)
    return run_starts, run_ends


class ParagliderTrackMixin:
    # I'm not sure that this is needed for offline tracks so I just left it.
    threshold_speed = 10
    # Threshold value for 'not started'-'flying' change in km/h.
    sf_speed = 20
    # Threshold value for 'flying'-'not started' change in km/h.
    fs_speed = 10
    # Time interval in which is allowed for pilot to be slow, seconds.
    slow_interval = 60
    alt_interval = 5

    __state = 'not started'

    def sky_earth_definer(self):
        overspeed_idxs = np.where(self.data['g_speed'] > self.threshold_speed)
        rs, re = runs_of_ones_array(overspeed_idxs)
        for i in xrange(len(rs)):
            if self.data['timestamp'][re[i]] - self.data['timestamp'][re[i]] \
                    > self.slow_interval:
                # TODO: wrap it in event.
                self.__state = 'flying'
                ts = self.data['timestamp'][re[i]]
                break

        lowspeed_idxs = np.where(self.data['g_speed'] < self.threshold_speed)
        rls, rle = runs_of_ones_array(lowspeed_idxs)
        # TODO: do the same as above.

    def _state_work(self, kw):
        ''' Calculate pilot's state.'''
        if kw['hs'] > self.sf_speed and self.__state == 'not started':
            self.__state = 'flying'
        if self.__state == 'flying':
            if self._slow and (kw['ts'] -
                self._became_slow >= self.slow_interval):
                self.state = 'landed'
            elif self._slow and (kw['hs'] > self.fs_speed or
                    abs(kw['alt'] - self._slow_alt) > self.alt_interval):
                self._slow = False
            elif (not self._slow) and kw['hs'] < self.fs_speed:
                self._slow = True
                self._slow_alt = kw['alt']
                self._became_slow = kw['ts']

        if (self.last_wp > self._task['p_amount'] - 1 and
            self.race.is_finished(self.state, (self.lat, self.lon))):
            self.state = 'finished'
            self.fin_time = self.ts

