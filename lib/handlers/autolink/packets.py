# -*- coding: utf8 -*-
"""
@project   Maprox <http://www.maprox.net>
@info      Autolink packets
@copyright 2013, Maprox LLC
"""

from struct import unpack, pack
from datetime import datetime
import binascii
from lib.bits import *
from lib.packets import *   
from lib.factory import AbstractPacketFactory

# ---------------------------------------------------------------------------

class AutolinkPacket(BasePacket):
    """
     Base packet for autolink protocol
    """
    _fmtHeader = '<H'   # header format

    # private properties
    __packetId = None

    def _parseHeader(self):
        """
         Parses header data.
         If return None, then offset is shifted to calcsize(self._fmtHeader)
         otherwise to the returned value
         @return:
        """
        self.__packetId = unpack("<B", self._head[:1])[0]
        return None

    @property
    def packetId(self):
        if self._rebuild: self._build()
        return self.__packetId

    @packetId.setter
    def packetId(self, value):
        if 0 <= value <= 0xFF:
            self.__packetId = value
            self._rebuild = True

# ---------------------------------------------------------------------------

class Header(AutolinkPacket):
    """
      Head packet of autolink messaging protocol
    """
    # private properties
    __protocolVersion = None
    __deviceImei = None

    def _parseHeader(self):
        """
         Parses header data.
         If return None, then offset is shifted to calcsize(self._fmtHeader)
         otherwise to the returned value
         @return:
        """
        super(Header, self)._parseHeader()
        self.__protocolVersion = unpack("<B", self._head[1:2])[0]
        return None

    def _parseLength(self):
        """
         Parses length of the packet
         @protected
        """
        # read header and length
        self._length = 8

    def _parseBody(self):
        """
         Parses body of the packet
         @protected
        """
        super(Header, self)._parseBody()
        self.__deviceImei = str(unpack('<Q', self._body)[0])

    def _buildBody(self):
        """
         Builds rawData from object variables
         @protected
        """
        result = super(Header, self)._buildBody()
        result += pack('<Q', int(self.__deviceImei))
        return result

    @property
    def protocolVersion(self):
        if self._rebuild: self._build()
        return self.__protocolVersion

    @protocolVersion.setter
    def protocolVersion(self, value):
        if 0 <= value <= 0xFF:
            self.__protocolVersion = value
            self._rebuild = True

    @property
    def deviceImei(self):
        if self._rebuild: self._build()
        return self.__deviceImei

    @deviceImei.setter
    def deviceImei(self, value):
        self.__deviceImei = value
        self._rebuild = True

# ---------------------------------------------------------------------------

class Package(AutolinkPacket):
    """
      Data packet of autolink messaging protocol
    """
    # private properties
    __sequenceNum = None
    __packets = None
    
    def _parseHeader(self):
        """
         Parses header data.
         If return None, then offset is shifted to calcsize(self._fmtHeader)
         otherwise to the returned value
         @return:
        """
        super(Package, self)._parseHeader()
        self.__sequenceNum = unpack("<B", self._head[1:2])[0]
        return None

    def _parseLength(self):
        """
         Parses packet length data.
         If return None, then offset is shifted to calcsize(self._fmtLength)
         otherwise to the returned value
         @return:
        """
        # It is sad that we don't know the length
        # of the packet, so let's determine it by parsing packets
        buffer = self._rawData[2:]
        self.__packets = []
        self._length = 1
        while True:
            packet = Packet(buffer)
            buffer = packet.rawDataTail
            self.__packets.append(packet)
            self._length += len(packet.rawData) # increase package length
            if not buffer or (buffer[:1] == b'\x5d'): break

    @property
    def sequenceNum(self):
        if self._rebuild: self._build()
        return self.__sequenceNum

    @sequenceNum.setter
    def sequenceNum(self, value):
        self.__sequenceNum = value
        self._rebuild = True

    @property
    def packets(self):
        if self._rebuild: self._build()
        return self.__packets

# ---------------------------------------------------------------------------

PACKET_TYPE_PING = 0
PACKET_TYPE_DATA = 1
PACKET_TYPE_TEXT = 3
PACKET_TYPE_PHOTO = 4

# ---------------------------------------------------------------------------

class Packet(BasePacket):
    """
      Data packet of autolink messaging protocol
    """
    _fmtHeader = '<B'   # header format
    _fmtLength = '<H'   # packet length format
    _fmtChecksum = '<B' # checksum format

    # private properties
    __timestamp = None
    __params = None

    def _parseLength(self):
        """
         Parses packet length data.
         If return None, then offset is shifted to calcsize(self._fmtLength)
         otherwise to the returned value
         @return:
        """
        # It is sad that we don't know the length
        # of the packet, so let's determine it by parsing packets
        self.__timestamp = unpack('<L', self._rawData[3:7])[0]
        return 2 + 4 # length size + timestamp size

    def _parseBody(self):
        """
         Parses body of the packet
         @protected
        """
        super(Packet, self)._parseBody()
        self.__params = {}
        sensors = {}
        bodyLength = len(self._body)
        offset = 0
        while offset < bodyLength:
            num = unpack('<B', self.body[offset:offset + 1])[0]
            val = self.body[offset+1:offset+5]
            if num == 1:
                ebv, ibv = unpack('<HH', val)
                sensors['ext_battery_voltage'] = ebv
                sensors['int_battery_voltage'] = ibv
            elif num == 2:
                sensors['ibutton'] = unpack('<L', val)[0]
            elif num == 3:
                latitude = unpack('f', val)[0]
                sensors['latitude'] = latitude
            elif num == 4:
                longitude = unpack('f', val)[0]
                sensors['longitude'] = longitude
            elif num == 5:
                azimuth, altitude, sat, speed = unpack('<BBBB', val)
                speed *= 1.852
                altitude *= 10
                azimuth *= 2
                sat_gps = bitRangeValue(sat, 0, 4)
                sat_glonass = bitRangeValue(sat, 4, 8)
                sensors['sat_count'] = sat_glonass + sat_gps
                sensors['sat_count_gps'] = sat_gps
                sensors['sat_count_glonass'] = sat_glonass
                sensors['speed'] = speed
                sensors['altitude'] = altitude
                sensors['azimuth'] = azimuth
            elif num == 6: pass
            elif num == 7: pass # LAC, CID
            elif num == 8: pass # GSM signal strength, MCC, MNC
            elif num == 9:
                status = unpack('<L', val)[0]
                for i in range(8):
                    sensors['din%d' % i] = bitValue(status, i)
                for j in range(5):
                    sensors['ain%d' % j] = bitValue(status, 8 + j)
                sensors['gsm_modem_status'] = bitRangeValue(status, 12, 14)
                sensors['gps_module_status'] = bitRangeValue(status, 14, 16)
                sensors['moving'] = bitValue(status, 16)
                #sensors['sos'] = bitValue(status, 20) # what can i do???
                sensors['armed'] = bitValue(status, 20)
                sensors['acc'] = bitValue(status, 21)
                sensors['ext_battery_voltage'] =\
                    bitRangeValue(status, 24, 32) * 150
            elif num == 6:
                pass
            elif num == 6:
                pass
            elif num == 6:
                pass
            offset += 5
        self.__params['sensors'] = sensors.copy()
        # old fashioned params
        for key in ['latitude', 'longitude', 'speed', 'altitude', 'azimuth']:
            if key in sensors:
                self.__params[key] = sensors[key]
        if 'sat_count' in sensors:
            self.__params['satellitescount'] = sensors['sat_count']
        self.__params['hdop'] = 1 # fake hdop

    def calculateChecksum(self, data = None):
        """
         Returns calculated checksum
         @return: int
        """
        if not data:
            data = pack('<L', self.__timestamp)
            data += self._body
        checksum = sum(int(c) for c in data) & 0xFF
        return checksum

    @property
    def packetType(self):
        if self._rebuild: self._build()
        return self._header

    @packetType.setter
    def packetType(self, value):
        if 0 <= value <= 0xFF:
            self._header = value
            self._rebuild = True

    @property
    def timestamp(self):
        if self._rebuild: self._build()
        return datetime.utcfromtimestamp(self.__timestamp)

    @timestamp.setter
    def timestamp(self, value):
        if isinstance(value, datetime):
            self.__timestamp = value.timestamp()
            self._rebuild = True

    @property
    def params(self):
        if self._rebuild: self._build()
        return self.__params

# ---------------------------------------------------------------------------
 

class PacketFactory(AbstractPacketFactory):
    """
     Packet factory
    """

    @classmethod
    def getClass(cls, packetPrefix):
        """
         Returns a tag class by number
         @param packetPrefix: one byte buffer
        """
        classes = {
            b'\xff': Header,
            b'\x5b': Package
        }
        if not (packetPrefix in classes):
            return None
        return classes[packetPrefix]

    def getInstance(self, data = None):
        """
          Returns a tag instance by its number
        """
        if data is None: return

        # read packetId
        packetPrefix = data[:1]

        CLASS = self.getClass(packetPrefix)
        if not CLASS:
            raise Exception('Packet %s is not found' %
                binascii.hexlify(packetPrefix).decode())
        return CLASS(data)

# ===========================================================================
# TESTS
# ===========================================================================

import unittest
class TestCase(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.factory = PacketFactory()
        pass

    def test_headPacket(self):
        packet = self.factory.getInstance(
          b'\xff\x22\xf3\x0c\x45\xf5\xc9\x0f\x03\x00')
        self.assertEqual(isinstance(packet, Header), True)
        self.assertEqual(isinstance(packet, Package), False)
        self.assertEqual(packet.packetId, 255)
        self.assertEqual(packet.protocolVersion, 34)
        self.assertEqual(packet.deviceImei, '861785007918323')

    def test_packet(self):
        data = (
            b'\x01\x55\x00\xc5\xcf\xc2\x51' +
            b'\x03\x4d\x8b\x5e\x42\x04\x18\xd6\x14\x42' +
            b'\x05\x05\x16\x0a\x00\x09\x02\xe0\xcc\x64' +
            b'\x15\xf5\x01\x00\x00\x20\x00\x00\x00\x00' +
            b'\x24\x00\x00\x00\x00\x2a\x3a\xcd\x00\x00' +
            b'\x2C\x71\xCD\x00\x00\x2D\x2E\xCD\x00\x00' +
            b'\x2E\x6C\xCD\x00\x00\x2F\x3F\xCD\x00\x00' +
            b'\x30\x4D\xCD\x00\x00\x31\x46\xCD\x00\x00' +
            b'\xFA\xF8\x01\x00\x00\xFA\xF8\x01\x00\x00' +
            b'\xFA\x90\x01\x00\x00\x62'
        )
        packet = Packet(data)
        self.assertEqual(packet.packetType, PACKET_TYPE_DATA)
        self.assertEqual(packet.length, 85)
        self.assertEqual(packet.timestamp, datetime(2013, 6, 20, 9, 47, 49))
        sensors = packet.params['sensors']
        self.assertEqual(sensors['ext_battery_voltage'], 15000)

    def test_packagePacket(self):
        packet = self.factory.getInstance(
            b'\x5B\x01\x01\x55\x00\xc5\xcf\xc2\x51' +
            b'\x03\x4d\x8b\x5e\x42\x04\x18\xd6\x14\x42' +
            b'\x05\x05\x16\x0a\x00\x09\x02\xe0\xcc\x64' +
            b'\x15\xf5\x01\x00\x00\x20\x00\x00\x00\x00' +
            b'\x24\x00\x00\x00\x00\x2a\x3a\xcd\x00\x00' +
            b'\x2C\x71\xCD\x00\x00\x2D\x2E\xCD\x00\x00' +
            b'\x2E\x6C\xCD\x00\x00\x2F\x3F\xCD\x00\x00' +
            b'\x30\x4D\xCD\x00\x00\x31\x46\xCD\x00\x00' +
            b'\xFA\xF8\x01\x00\x00\xFA\xF8\x01\x00\x00' +
            b'\xFA\x90\x01\x00\x00\x62\x01\x50\x00\x5B\xD0\xC2\x51' +
            b'\x03\x4D\x8B\x5E\x42\x04\x18\xD6\x14\x42' +
            b'\x05\x05\x16\x0A\x00\x09\x02\xE0\xCC\x64' +
            b'\x15\xF5\x01\x00\x00\x20\x00\x00\x00\x00' +
            b'\x24\x00\x00\x00\x00\x2A\x3A\xCD\x00\x00' +
            b'\x2C\x71\xCD\x00\x00\x2D\x2E\xCD\x00\x00' +
            b'\x2E\x6C\xCD\x00\x00\x2F\x3F\xCD\x00\x00' +
            b'\x30\x4D\xCD\x00\x00\x31\x46\xCD\x00\x00' +
            b'\xFA\xF8\x01\x00\x00\xFA\xF8\x01\x00\x00' +
            b'\x6E\x5d'
        )
        self.assertEqual(isinstance(packet, Header), False)
        self.assertEqual(isinstance(packet, Package), True)
        self.assertEqual(packet.packetId, 91)
        self.assertEqual(packet.sequenceNum, 1)
        self.assertEqual(len(packet.packets), 2)
        p = packet.packets[1]
        self.assertIsInstance(p, Packet)
        self.assertEqual(p.timestamp, datetime(2013, 6, 20, 9, 50, 19))
        self.assertAlmostEqual(p.params['latitude'], 55.6360359)
        self.assertAlmostEqual(p.params['longitude'], 37.20907592)
        sensors = p.params['sensors']
        self.assertEqual(sensors['sat_count'], 10)
        self.assertEqual(sensors['sat_count_gps'], 10)
        self.assertEqual(sensors['sat_count_glonass'], 0)
        self.assertEqual(sensors['speed'], 0.00)
        self.assertEqual(sensors['altitude'], 220)
        self.assertEqual(sensors['azimuth'], 10)
        self.assertEqual(sensors['ext_battery_voltage'], 15000)

    def test_realPacket(self):
        packet = self.factory.getInstance(
            b'[\x01\x01\x14\x00F\xbe\x1fR\xfc\x7fN\x00\x00\xfd\xa5' +
            b'\x90\xc8)\xfe\xaa\xfa\x17\x0c\xff.O\x00\x00\xa2\x01\x1e' +
            b'\x00P\xbe\x1fR\x03|\x8b^B\x04\x0c\xd6\x14B\x05\x00\x13' +
            b'\x08\x00\t\x00\x90\xc5V\xfa,\x01\x00\x00\xfa7\x01\x00' +
            b'\x00\x92\x01-\x00\xe6\xbe\x1fR\x03|\x8b^B\x04\x0c\xd6' +
            b'\x14B\x05\x00\x15\t\x00\t\x02\xe0\xc4V\x15\xf4\x01\x00' +
            b'\x00F\x00\x00\x1b\x00(R\xcb\x00\x00\xfa\xf8\x01\x00\x00' +
            b'\xfa\xf8\x01\x00\x00\xb9\x012\x00|\xbf\x1fR\x03|\x8b^B' +
            b'\x04\x0c\xd6\x14B\x05\x00\x15\x07\x00\t\x02\xa0\xc4V\x15' +
            b'\xf4\x01\x00\x00F\x00\x00\x1b\x00(R\xcb\x00\x00\xfa\xf8' +
            b'\x01\x00\x00\xfa\xf8\x01\x00\x00\xfa\x90\x01\x00\x00\x99' +
            b'\x01-\x00\x12\xc0\x1fR\x03|\x8b^B\x04\x0c\xd6\x14B\x05' +
            b'\x00\x15\x08\x00\t\x02\xa0\xc4V\x15\xf4\x01\x00\x00F\xc2' +
            b'\x00\x1b\x00(R\xcb\x00\x00\xfa\xf8\x01\x00\x00\xfa' +
            b'\xf8\x01\x00\x00h]'
        )
        self.assertEqual(isinstance(packet, Header), False)
        self.assertEqual(isinstance(packet, Package), True)
        self.assertEqual(packet.packetId, 91)
        self.assertEqual(packet.sequenceNum, 1)
        self.assertEqual(len(packet.packets), 5)
        p = packet.packets[0]
        self.assertEqual(p.timestamp, datetime(2013, 8, 29, 21, 33, 58))