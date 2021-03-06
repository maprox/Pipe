# -*- coding: utf8 -*-
'''
@project   Maprox <http://www.maprox.net>
@info      Globalsat TR-151
@copyright 2009-2013, Maprox LLC
'''

import re
import json
from datetime import datetime

from kernel.logger import log
from lib.handler import AbstractHandler
from lib.handlers.globalsat.commands_tr151 import CommandFactory
from lib.geo import Geo

class Handler(AbstractHandler):
    """ Globalsat. TR-151 """

    _reportFormat = "RAB27GHKLM"
    _smsFormat1 = "RAB27GHKLM"

    #$___,17,1,061212,211240,E05010.1943,N5323.4416,135.8,0.56,313.46,5,1.80!
    # uid R  A B             2           7          G     H    K      L M   !

    re_patterns = {
        'line': '\$(?P<S>\w+){fields}!',
        'field': ',(?P<{field}>{value})',
        'unknownField': '[\w\.]+',
        'report': {
            'A': '\d+',
            'B': '\d{6},\d{6}',
            '2': '[EW]\d+(\.\d+)?',
            '7': '[NS]\d+(\.\d+)?',
            'G': '\d+(\.\d+)?',
            'H': '\d+(\.\d+)?',
            'K': '\d+(\.\d+)?',
            'L': '\d+',
            'M': '\d+(\.\d+)?',
            'N': '\d+',
            'R': '\d+'
        }
    }

    re_patterns_sms_format1 = {
        'line': '(?P<S>\w+){fields}!',
        'field': re_patterns['field'],
        'unknownField': re_patterns['unknownField'],
        'report': re_patterns['report']
    }

    re_compiled = {
        'report': None,
        'sms_format1': None
    }

    def initialization(self):
        """
         Initialization of the handler
         @return:
        """
        self._commandsFactory = CommandFactory()
        self.__compileRegularExpressions()

    def __getRegularExpression(self, expression, patterns):
        """
         Compiling of regular expression
         @param expression: Fields expression
         @param patterns: Dict of fields patterns
        """
        fieldsStr = ""
        for char in expression:
            pattern = patterns['unknownField']
            if char in patterns['report']:
                pattern = patterns['report'][char]
                # We need to avoid digital names of groups
            fieldName = char
            if char.isdigit():
                fieldName = "d" + char
            fieldsStr += str.format(patterns['field'],
                                    field = fieldName, value = pattern)
        return str.format(patterns['line'], fields = fieldsStr)

    def __compileRegularExpressions(self):
        """
         Compiling of regular expressions
        """
        self.re_compiled['report'] = re.compile(
            self.__getRegularExpression(self._reportFormat, self.re_patterns),
            flags = re.IGNORECASE)
        self.re_compiled['sms_format1'] = re.compile(
            self.__getRegularExpression(self._smsFormat1,
                self.re_patterns_sms_format1),
            flags = re.IGNORECASE)
        return self

    def processData(self, data, format = 'report'):
        """
         Processing of data from socket / storage.
         @param data: Data from socket
         @param format: Source of data format ('report' or 'sms')
        """
        self.processDataBuffer(data, format)
        return super(Handler, self).processData(data)

    def processDataBuffer(self, buffer, format = 'report'):
        """
         Processing of data from socket / storage.
         @param buffer: Data from socket
         @param format: Source of data format ('report' or 'sms')
        """
        # let's work with text data
        data = buffer.decode()
        rc = self.re_compiled[format]
        position = 0

        log.debug("Data received:\n%s", data)
        m = rc.search(data, position)
        if not m:
            self.processError(data)

        while m:
            # - OK. we found it, let's see for checksum
            log.debug("Raw match found.")
            data_device = m.groupdict()
            packetObserver = self.translate(data_device)
            log.info(packetObserver)
            self.uid = packetObserver['uid']
            self.store([packetObserver])
            position += len(m.group(0))
            m = rc.search(data, position)

    def processError(self, data):
        """
         OK. Our pattern doesn't match the socket or config data.
         The source of the problem can be in wrong report format.
        """
        log.error("Unknown data format...")

    def sendAcknowledgement(self, packet):
        """
         Sends acknowledgement to the socket
         @param packet: a L{packets.Packet} subclass
        """
        buf = self.getAckPacket(packet)
        log.info("Send acknowledgement, crc = %d" % packet.crc)
        return self.send(buf)

    @classmethod
    def getAckPacket(cls, packet):
        """
         Returns acknowledgement buffer value
         @param packet: Received packet
        """
        return b"$OK!"

    def translate(self, data):
        """
         Translate gps-tracker data to observer pipe format
         @param data: dict() data from gps-tracker
        """
        packet = {}
        sensor = {}
        for char in data:
            value = data[char]
            # IMEI / UID
            if char == "S":
                packet['uid'] = value
            # TIME
            elif char == "B":
                try:
                    dt = datetime.strptime(value, '%d%m%y,%H%M%S')
                except:
                    dt = datetime.strptime('00', '%y')
                packet['time'] = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
            # COORD
            elif char in ("d1", "d2", "d3"):
                packet['longitude'] = Geo.getLongitude(value)
            elif char in ("d6", "d7", "d8"):
                packet['latitude'] = Geo.getLatitude(value)
            # ALTITUDE
            elif char == "G":
                packet['altitude'] = int(round(float(value)))
            # SPEED (knots)
            elif char == "H":
                packet['speed'] = 1.852 * float(value)
            # SPEED (km/hr)
            elif char == "I":
                packet['speed'] = value
            # SPEED (mile/hr)
            elif char == "J":
                packet['speed'] = 1.609344 * float(value)
            # Satellites count
            elif char == "L":
                packet['satellitescount'] = int(value)
                sensor['sat_count'] = int(value)
            # Azimuth - driving direction
            elif char == "K":
                packet['azimuth'] = int(round(float(value)))
            # HDOP (Horizontal Dilution of Precision)
            elif char == "M":
                packet['hdop'] = float(value)
            # Report Mode
            elif char == "A":
                if int(value) == 5:
                    sensor['sos'] = 1
        self.setPacketSensors(packet, sensor)
        return packet

# ===========================================================================
# TESTS
# ===========================================================================

import unittest
class TestCase(unittest.TestCase):

    def setUp(self):
        pass

    def test_packetData(self):
        import kernel.pipe as pipe
        h = Handler(pipe.Manager(), None)
        data = "$353681044879914,17,1,061212,211240,E05010.1943," + \
            "N5323.4416,135.8,0.56,313.46,5,1.80!"
        rc = h.re_compiled['report']
        m = rc.search(data, 0)
        packet = h.translate(m.groupdict())
        self.assertEqual(packet['uid'], "353681044879914")
        self.assertEqual(packet['time'], "2012-12-06T21:12:40.000000")
        self.assertEqual(packet['altitude'], 136)
        self.assertEqual(packet['azimuth'], 313)
        self.assertEqual(packet['longitude'], 50.169905)

    def test_packetDataSmsFormat(self):
        import kernel.pipe as pipe
        h = Handler(pipe.Manager(), None)
        data = "??353681041178468,0,1,160113,033435,E05011.4364," + \
               "N5314.3921,119.9,1.48,23.78,4,6.27!"
        rc = h.re_compiled['sms_format1']
        m = rc.search(data, 0)
        packet = h.translate(m.groupdict())
        self.assertEqual(packet['uid'], "353681041178468")
        self.assertEqual(packet['time'], "2013-01-16T03:34:35.000000")
        self.assertEqual(packet['altitude'], 120)
        self.assertEqual(packet['azimuth'], 24)
        self.assertEqual(packet['longitude'], 50.19060666666667)
