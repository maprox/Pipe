# -*- coding: utf8 -*-
'''
@project   Maprox <http://www.maprox.net>
@info      Galileo base class for other Galileo firmware
@copyright 2012, Maprox LLC
'''

from struct import pack

from kernel.logger import log
from lib.handler import AbstractHandler
import lib.handlers.galileo.packets as packets
import lib.handlers.galileo.commands as commands

# ---------------------------------------------------------------------------

class GalileoHandler(AbstractHandler):
    """
     Base handler for Galileo protocol
    """
    __commands = {}
    __commands_num_seq = 0
    __imageReceivingConfig = None
    __packNum = 0

    # private buffer for headPacket data
    __headPacketRawData = None
    
    def initialization(self):
        """
         Initialization of the handler
         @return:
        """
        super(GalileoHandler, self).initialization()
        self._packetsFactory = packets.PacketFactory()
        self._commandsFactory = commands.CommandFactory()

    def needCommandProcessing(self):
        """
         Returns false if we can not process commands
         @return: boolean
        """
        return self.uid and self.__imageReceivingConfig is None

    def processProtocolPacket(self, protocolPacket):
        """
         Process galileo packet.
         @param protocolPacket: Galileo protocol packet
        """
        #if (self.__packNum == 1) and (self.__imageReceivingConfig is None):
        #    self.__packNum += 1
        #    self.sendInternalCommand("Makephoto 1")

        observerPackets = self.translate(protocolPacket)
        self.sendAcknowledgement(protocolPacket)
        if not self.__headPacketRawData:
            self.__headPacketRawData = b''

        if protocolPacket.header == 1:
            self.__headPacketRawData = protocolPacket.rawData

        if protocolPacket.hasTag(0xE1):
            log.info('Device answer is "' +
                protocolPacket.getTag(0xE1).getValue() + '".')

        if len(observerPackets) > 0:
            if 'uid' in observerPackets[0]:
                self.headpack = observerPackets[0]
                self.uid = self.headpack['uid']
                log.info('HeadPack is stored.')
                if 'time' not in self.headpack:
                    observerPackets.remove(self.headpack)

        if protocolPacket.header == 4:
            return self.receiveImage(protocolPacket)

        if len(observerPackets) == 0: return
        log.info('Location packet found. Sending...')

        # MainPack
        for packet in observerPackets:
            packet.update(self.headpack)

        log.info(observerPackets)
        self.store(observerPackets)

    def sendInternalCommand(self, command):
        """
         Sends command to the tracker
         @param command: Command string
        """
        log.info('Sending "' + command + '"...')
        packet = packets.Packet()
        packet.header = 1
        packet.addTag(0x03, self.headpack['uid'])
        packet.addTag(0x04, self.headpack['uid2'])
        packet.addTag(0xE0, self.__commands_num_seq)
        packet.addTag(0xE1, command)
        self.send(packet.rawData)
        # save sended command in local dict
        self.__commands[self.__commands_num_seq] = packet
        self.__commands_num_seq += 1 # increase command number sequence

    def receiveImage(self, packet):
        """
         Receives an image from tracker.
         Sends it to the observer server, when totally received.
        """
        if (packet is None) or (packet.body is None) or (len(packet.body) == 0):
            log.error('Empty image packet. Transfer aborted!')
            return

        config = self.__imageReceivingConfig
        partnum = packet.body[0]
        if self.__imageReceivingConfig is None:
            self.__imageReceivingConfig = {
              'imageParts': {}
            }
            config = self.__imageReceivingConfig
            log.info('Image transfer is started.')
        else:
            if len(packet.body) > 1:
                log.debug('Image transfer in progress...')
                log.debug('Size of chunk is %d bytes', len(packet.body) - 1)
            else:
                imageData = b''
                imageParts = self.__imageReceivingConfig['imageParts']
                for num in sorted(imageParts.keys()):
                    imageData += imageParts[num]
                self.sendImages([{
                  'mime': 'image/jpeg',
                  'content': imageData
                }])
                self.__imageReceivingConfig = None
                log.debug('Transfer complete.')
                return

        imageData = packet.body[1:]
        config['imageParts'][partnum] = imageData

    def translate(self, data):
        """
         Translate gps-tracker data to observer pipe format
         @param data: dict() data from gps-tracker
        """
        packets = []
        if (data == None): return packets
        if (data.tags == None): return packets

        packet = {}
        sensor = {}
        prevNum = 0
        for tag in data.tags:
            num = tag.getNumber()

            if num < prevNum:
                self.setPacketSensors(packet, sensor)
                packets.append(packet)
                packet = {}
                sensor = {}

            prevNum = num
            value = tag.getValue()
            if num == 3: # IMEI
                packet['uid'] = value
            elif num == 4: # CODE
                packet['uid2'] = value
            elif num == 32: # Timestamp
                packet['time'] = value.strftime('%Y-%m-%dT%H:%M:%S.%f')
            elif num == 48: # Satellites count, Correctness, Lat, Lon
                packet.update(value)
                sensor['sat_count'] = value['satellitescount']
            elif num == 51: # Speed, Azimuth
                packet.update(value)
            elif num == 52: # Altitude
                packet['altitude'] = value
            elif num == 53: # HDOP
                packet['hdop'] = value
            elif num == 64: # Status
                sensor.update(value)
            elif num == 65: # External voltage
                sensor['ext_battery_voltage'] = value
            elif num == 66: # Internal accumulator voltage
                sensor['int_battery_voltage'] = value
            elif num == 67: # Terminal temperature
                sensor['int_temperature'] = value
            elif num == 68: # Acceleration
                sensor['acceleration_x'] = value['X']
                sensor['acceleration_y'] = value['Y']
                sensor['acceleration_z'] = value['Z']
            elif num == 69: # Digital outputs 1-16
                sensor.update(value)
            elif num == 70: # Digital inputs 1-16
                sensor.update(value)
            elif num in range(80, 84): # Analog input 0 - 4
                sensor['ain%d' % (num - 80)] = value
            elif num == 88:
                sensor['rs232_0'] = value
            elif num == 89:
                sensor['rs232_1'] = value
            elif num in range(112, 120):
                sensor['ext_temperature_%d' % (num - 112)] = value
            elif num == 144:
                sensor['ibutton_1'] = value
            elif num == 192:
                sensor['fms_total_fuel_consumption'] = value
            elif num == 193:
                sensor.update(value)
            elif num == 194:
                sensor['fms_total_mileage'] = value
            elif num == 195:
                sensor['can_b1'] = value
            elif num in range(196, 211):
                sensor['can_8bit_r%d' % (num - 196)] = value
            elif num == 211:
                sensor['ibutton_2'] = value
            elif num == 212:
                sensor['total_mileage'] = value
            elif num == 213:
                sensor.update(value)
            elif num in range(214, 219):
                sensor['can_16bit_r%d' % (num - 214)] = value
            elif num in range(219, 224):
                sensor['can_32bit_r%d' % (num - 219)] = value
            else:
                sensor['tag' + str(num)] = value
        self.setPacketSensors(packet, sensor)
        packets.append(packet)
        return packets

    def sendAcknowledgement(self, packet):
        """
         Sends acknowledgement to the socket
        """
        buf = self.getAckPacket(packet.crc)
        log.info("Send acknowledgement, crc = %d" % packet.crc)
        return self.send(buf)

    @classmethod
    def getAckPacket(cls, crc):
        """
          Returns acknowledgement buffer value
        """
        return pack('<BH', 2, crc)

    def getInitiationData(self, config):
        """
         Returns initialization data for SMS wich will be sent to device
         @param config: config dict
         @return: array of dict or dict
        """
        return [{
            "message": 'AddPhone 1234'
        }, {
            "message":
                'ServerIp ' + config['host'] + ',' + str(config['port'])
        }, {
            "message":
                'APN ' + config['gprs']['apn'] \
                 + ',' + config['gprs']['username'] \
                 + ',' + config['gprs']['password']
        }]


# ===========================================================================
# TESTS
# ===========================================================================

import unittest
class TestCase(unittest.TestCase):

    def setUp(self):
        import kernel.pipe as pipe
        self.handler = GalileoHandler(pipe.TestManager(), None)

    def test_packetData(self):
        data = b'\x01"\x00\x03868204000728070\x042\x00' \
             + b'\xe0\x00\x00\x00\x00\xe1\x08Photo ok\x137'
        protocolPackets = packets.Packet.getPacketsFromBuffer(data)
        for packet in protocolPackets:
            self.assertEqual(packet.header, 1)

    def test_packetNewTracker(self):
        data = b'\x01\xaa\x03\x03868204001578425\x042\x00\x10\xe7\x04 ' + \
               b'$\x17\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00' + \
               b'\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00B[\x0fC\x1a' +\
               b'F\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00' +\
               b'\x10\xe6\x04 \xf1\x16\x11Q0\x10\x00\x00\x00\x00\x00\x00' +\
               b'\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00' +\
               b'Bh\x0fC\x1aF\x00\x00P\x00\x00Q\x00\x00\x03' +\
               b'868204001578425\x042\x00\x10\xe5\x04 \xac\x16\x11Q0\x10' +\
               b'\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00' +\
               b'\x005\x00@\xc1#A\x00\x00Bb\x0fC\x1aF\x00\x00P\x00\x00Q' +\
               b'\x00\x00\x03868204001578425\x042\x00\x10\xe4\x04 4\x16' +\
               b'\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00' +\
               b'\x004\x00\x005\x00@\xc1#A\x00\x00Bo\x0fC\x1bF\x00\x00P' +\
               b'\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10\xe3' +\
               b'\x04 \xbb\x15\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003' +\
               b'\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00Bq\x0fC\x1bF' +\
               b'\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00' +\
               b'\x10\xe2\x04 C\x15\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00' +\
               b'\x003\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00Bt\x0f' +\
               b'C\x1bF\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042' +\
               b'\x00\x10\xe1\x04 \xcb\x14\x11Q0\x10\x00\x00\x00\x00\x00' +\
               b'\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00' +\
               b'\x00B\x82\x0fC\x1bF\x00\x00P\x00\x00Q\x00\x00\x03868204' +\
               b'001578425\x042\x00\x10\xe0\x04 R\x14\x11Q0\x10\x00\x00' +\
               b'\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00' +\
               b'@\xc1\x03A\x00\x00B\x90\x0fC\x1cF\x00\x00P\x00\x00Q\x00' +\
               b'\x00\x03868204001578425\x042\x00\x10\xdf\x04 4\x14\x11' +\
               b'Q0\xf0\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00\x00' +\
               b'4\x00\x005\x00@\xc1\x01A\x00\x00B\x94\x0fC\x1cF\x00\x00' +\
               b'P\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10\xde' +\
               b'\x04 \xf9\x13\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x00' +\
               b'3\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00B\x89\x0f' +\
               b'C\x1cF\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x04' +\
               b'2\x00\x10\xdd\x04 \x81\x13\x11Q0\x10\x00\x00\x00\x00' +\
               b'\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc1' +\
               b'#A\x00\x00B\x9d\x0fC\x1cF\x00\x00P\x00\x00Q\x00\x00' +\
               b'\x03868204001578425\x042\x00\x10\xdc\x04 \x0c\x13\x11' +\
               b'Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00' +\
               b'\x004\x00\x005\x00@\x81#A\x00\x00B\x9d\x0fC\x1cF\x00' +\
               b'\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10' +\
               b'\xdb\x04 \t\x13\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00' +\
               b'\x003\x00\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00B' +\
               b'\x9d\x0fC\x1cF\x00\x00P\x00\x00Q\x00\x00\x038682040015' +\
               b'78425\x042\x00\x10\xda\x04 \x05\x13\x11Q0\x10\x00\x00' +\
               b'\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00' +\
               b'@\xc0#A\x00\x00B\x9d\x0fC\x1cF\x00\x00P\x00\x00Q' +\
               b'\x00\x00\xf4\xdf'
        protocolPackets = packets.Packet.getPacketsFromBuffer(data)
        self.assertEqual(len(protocolPackets), 1)
        observerPackets = self.handler.translate(protocolPackets[0])
        self.assertEqual(len(observerPackets), 14)
        packet = observerPackets[6]
        self.assertEqual(packet['speed'], 0)
        self.assertEqual(packet['uid'], '868204001578425')

    def test_processData(self):
        data = b'\x01\xaa\x03\x03868204001578425\x042\x00\x10\xe7\x04 ' + \
               b'$\x17\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00' + \
               b'\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00B[\x0fC\x1a' +\
               b'F\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00' +\
               b'\x10\xe6\x04 \xf1\x16\x11Q0\x10\x00\x00\x00\x00\x00\x00' +\
               b'\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00' +\
               b'Bh\x0fC\x1aF\x00\x00P\x00\x00Q\x00\x00\x03' +\
               b'868204001578425\x042\x00\x10\xe5\x04 \xac\x16\x11Q0\x10' +\
               b'\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00' +\
               b'\x005\x00@\xc1#A\x00\x00Bb\x0fC\x1aF\x00\x00P\x00\x00Q' +\
               b'\x00\x00\x03868204001578425\x042\x00\x10\xe4\x04 4\x16' +\
               b'\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00' +\
               b'\x004\x00\x005\x00@\xc1#A\x00\x00Bo\x0fC\x1bF\x00\x00P' +\
               b'\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10\xe3' +\
               b'\x04 \xbb\x15\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003' +\
               b'\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00Bq\x0fC\x1bF' +\
               b'\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00' +\
               b'\x10\xe2\x04 C\x15\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00' +\
               b'\x003\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00Bt\x0f' +\
               b'C\x1bF\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x042' +\
               b'\x00\x10\xe1\x04 \xcb\x14\x11Q0\x10\x00\x00\x00\x00\x00' +\
               b'\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00' +\
               b'\x00B\x82\x0fC\x1bF\x00\x00P\x00\x00Q\x00\x00\x03868204' +\
               b'001578425\x042\x00\x10\xe0\x04 R\x14\x11Q0\x10\x00\x00' +\
               b'\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00' +\
               b'@\xc1\x03A\x00\x00B\x90\x0fC\x1cF\x00\x00P\x00\x00Q\x00' +\
               b'\x00\x03868204001578425\x042\x00\x10\xdf\x04 4\x14\x11' +\
               b'Q0\xf0\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00\x00' +\
               b'4\x00\x005\x00@\xc1\x01A\x00\x00B\x94\x0fC\x1cF\x00\x00' +\
               b'P\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10\xde' +\
               b'\x04 \xf9\x13\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00\x00' +\
               b'3\x00\x00\x00\x004\x00\x005\x00@\xc1#A\x00\x00B\x89\x0f' +\
               b'C\x1cF\x00\x00P\x00\x00Q\x00\x00\x03868204001578425\x04' +\
               b'2\x00\x10\xdd\x04 \x81\x13\x11Q0\x10\x00\x00\x00\x00' +\
               b'\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00@\xc1' +\
               b'#A\x00\x00B\x9d\x0fC\x1cF\x00\x00P\x00\x00Q\x00\x00' +\
               b'\x03868204001578425\x042\x00\x10\xdc\x04 \x0c\x13\x11' +\
               b'Q0\x10\x00\x00\x00\x00\x00\x00\x00\x003\x00\x00\x00' +\
               b'\x004\x00\x005\x00@\x81#A\x00\x00B\x9d\x0fC\x1cF\x00' +\
               b'\x00P\x00\x00Q\x00\x00\x03868204001578425\x042\x00\x10' +\
               b'\xdb\x04 \t\x13\x11Q0\x10\x00\x00\x00\x00\x00\x00\x00' +\
               b'\x003\x00\x00\x00\x004\x00\x005\x00@\xc0#A\x00\x00B' +\
               b'\x9d\x0fC\x1cF\x00\x00P\x00\x00Q\x00\x00\x038682040015' +\
               b'78425\x042\x00\x10\xda\x04 \x05\x13\x11Q0\x10\x00\x00' +\
               b'\x00\x00\x00\x00\x00\x003\x00\x00\x00\x004\x00\x005\x00' +\
               b'@\xc0#A\x00\x00B\x9d\x0fC\x1cF\x00\x00P\x00\x00Q' +\
               b'\x00\x00\xf4\xdf'

        h = self.handler
        h.processData(data)
        stored_packets = h.getStore().get_stored_packets()

        self.assertEqual(len(stored_packets), 14)
        packet = stored_packets[6]
        self.assertEqual(packet['speed'], 0)
        self.assertEqual(packet['uid'], '868204001578425')

    def test_packetDataTwoChunks(self):
        h = self.handler
        h.processData(
            b'\x01\x17\x80\x01\x11\x02\xc7\x03868204007113185\x042\x00\x00\xb7'
        )
        h.processData(
            b"\x01\xc0\x83\x042\x00\x10\xaa\x0b I\xd8\xbfR0\x0f4\x80"
            b"P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:AG`B7\x10Q"
            b"\x1b\x03\x042\x00\x10\xa9\x0b \xcf\xd7\xbfR0\x0f4\x80"
            b"P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A}`B5\x10Q"
            b"3\x03\x042\x00\x10\xa8\x0b V\xd7\xbfR0\x0f4\x80P\x030"
            b"\x9b8\x023\x00\x00\x00\x005\x06@\x00:Ax`B4\x10Q3\x03\x04"
            b"2\x00\x10\xa7\x0b \xdc\xd6\xbfR0\x0f4\x80P\x030\x9b8\x02"
            b"3\x00\x00\x00\x005\x06@\x00:A\x84`B5\x10Q'\x03\x042\x00"
            b"\x10\xa6\x0b c\xd6\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00"
            b"\x00\x005\x06@\x00:Aw`B6\x10Q3\x03\x042\x00\x10\xa5\x0b "
            b"\xea\xd5\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00\x00\x005"
            b"\x06@\x00:A\x94`B6\x10Q'\x03\x042\x00\x10\xa4\x0b q\xd5"
            b"\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00"
            b":Aw`B.\x10Q2\x03\x042\x00\x10\xa3\x0b \xf7\xd4\xbfR0\x0f4"
            b"\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x8e`B6"
            b"\x10Q#\x03\x042\x00\x10\xa2\x0b ~\xd4\xbfR0\x0f4\x80P\x03"
            b"0\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x94`B5\x10Q\x06"
            b"\x03\x042\x00\x10\xa1\x0b \x05\xd4\xbfR0\x0f4\x80P\x030"
            b"\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x98`B6\x10Q2\x03"
            b"\x042\x00\x10\xa0\x0b \x8b\xd3\xbfR0\x0f4\x80P\x030\x9b"
            b"8\x023\x00\x00\x00\x005\x06@\x00:A\x98`B4\x10Q8\x03\x04"
            b"2\x00\x10\x9f\x0b \x12\xd3\xbfR0\x0f4\x80P\x030\x9b8\x02"
            b"3\x00\x00\x00\x005\x06@\x00:A\x97`B1\x10Q\x15\x03\x042"
            b"\x00\x10\x9e\x0b \x99\xd2\xbfR0\x0f4\x80P\x03"
        )
        h.processData(
            b'0\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x98`B<\x10Q"\x03'
            b'\x042\x00\x10\x9d\x0b  \xd2\xbfR0\x0f4\x80P\x030\x9b8\x02'
            b'3\x00\x00\x00\x005\x06@\x00:A\x9f`B9\x10Q(\x03\x042\x00'
            b'\x10\x9c\x0b \xa6\xd1\xbfR0\x0f4\x80P\x030\x9b8\x023\x00'
            b'\x00\x00\x005\x06@\x00:Am`B8\x10Q\x01\x03\x042\x00\x10'
            b'\x9b\x0b .\xd1\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00\x00'
            b'\x005\x06@\x00:A\x81`B9\x10Q*\x03\x042\x00\x10\x9a\x0b '
            b'\xb5\xd0\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00\x00\x00'
            b'5\x06@\x00:Ar`B=\x10Q\x00\x03\x042\x00\x10\x99\x0b ;\xd0'
            b'\xbfR0\x0f4\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00'
            b':Ap`B;\x10Q\xf6\x02\x042\x00\x10\x98\x0b \xc2\xcf\xbfR0'
            b'\x0f4\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x8d'
            b'`B8\x10Q\x15\x03\x042\x00\x10\x97\x0b I\xcf\xbfR0\x0f4'
            b'\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x81`B7'
            b'\x10Q\x1c\x03\x042\x00\x10\x96\x0b \xcf\xce\xbfR0\x0f4'
            b'\x80P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x9a`B='
            b'\x10Q\x1e\x03\x042\x00\x10\x95\x0b V\xce\xbfR0\x0f4\x80'
            b'P\x030\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x8e`B:\x10'
            b'Q&\x03\x042\x00\x10\x94\x0b \xdd\xcd\xbfR0\x0f4\x80P\x03'
            b'0\x9b8\x023\x00\x00\x00\x005\x06@\x00:A\x8e`B1\x10Q0\x03'
            b'\x042\x00\x10\x93\x0b d\xcd\xbfR0\x0f4\x80P\x030\x9b8\x02'
            b'3\x00\x00\x00\x005\x06@\x00:A\x9b`B;\x10Q\x1b\x03\xea\xde'
        )
        stored_packets = h.getStore().get_stored_packets()

        self.assertEqual(len(stored_packets), 24)
        packet = stored_packets[6]
        self.assertEqual(packet['speed'], 0)
        self.assertEqual(packet['uid'], '868204007113185')

    def test_packetDataWithCANData(self):
        h = self.handler
        h.processData(
            b'\x01\x17\x80\x01\x11\x02\xc7\x03868204007113185\x042\x00\x00\xb7'
        )
        h.processData(
            b'\x01<\x83\x03356917057458304\x042\x00\x104s \x8c@\xbaW0\x0c' +
            b'D`,\x03l\xd8\xfd\x023\x00\x00\x00\x004{\x005\x06@\x08:A\x14' +
            b'0B\x1f\x10C\x1aE\xff\x00G\x00\x00\x00\nP\x00\x00\xa0\x00\xa1' +
            b'\x00\xa2\x00\xa3\x00\xa4\x00\xa5\x00\xa6\x00\xa7\x00\xa8\x00' +
            b'\xa9\x00\xaa\x00\xab\x00\xac\x00\xad\x00\xae\x00\xaf\x00\xb0' +
            b'\x00\x00\xb1\x00\x00\xb2\x00\x00\xb3\x00\x00\xb4\x00\x00\xb5' +
            b'\x00\x00\xb6\x00\x00\xb7\x00\x00\xb8\x00\x00\xb9\x00\x00\xc0' +
            b'\x00\x00\x00\x00\xc1\x00\x00\x00\x00\xc2\x00\x00\x00\x00\xc3' +
            b'\x00\x00\x00\x00\xc4\x00\xc5\x00\xc6\x00\xc7\x00\xc8\x00\xc9' +
            b'\x00\xca\x00\xcb\x00\xcc\x00\xcd\x00\xce\x00\xcf\x00\xd0\x00' +
            b'\xd1\x00\xd2\x00\xd4D\x00\x00\x00\xd6\x00\x00\xd7\x00\x00\xd8' +
            b'\x00\x00\xd9\x00\x00\xda\x00\x00\xdb\x00\x00\x00\x00\xdc\x00' +
            b'\x00\x00\x00\xdd\x00\x00\x00\x00\xde\x00\x00\x00\x00\xdf\x00' +
            b'\x00\x00\x00\xf0\x00\x00\x00\x00\xf1\x00\x00\x00\x00\xf2\x00' +
            b'\x00\x00\x00\xf3\x00\x00\x00\x00\xf4\x00\x00\x00\x00\xf5\x00' +
            b'\x00\x00\x00\xf6\x00\x00\x00\x00\xf7\x00\x00\x00\x00\xf8\x00' +
            b'\x00\x00\x00\xf9\x00\x00\x00\x00\x03356917057458304\x042\x00' +
            b'\x103s \x8b@\xbaW0\x0cD`,\x03l\xd8\xfd\x023\x00\x00\x00\x00' +
            b'4{\x005\x06@\x08:A\x0f0B\x1e\x10C\x1aE\xff\x00G\x00\x00\x00' +
            b'\nP\x00\x00\xa0\x00\xa1\x00\xa2\x00\xa3\x00\xa4\x00\xa5\x00' +
            b'\xa6\x00\xa7\x00\xa8\x00\xa9\x00\xaa\x00\xab\x00\xac\x00\xad' +
            b'\x00\xae\x00\xaf\x00\xb0\x00\x00\xb1\x00\x00\xb2\x00\x00\xb3' +
            b'\x00\x00\xb4\x00\x00\xb5\x00\x00\xb6\x00\x00\xb7\x00\x00\xb8' +
            b'\x00\x00\xb9\x00\x00\xc0\x00\x00\x00\x00\xc1\x00\x00\x00\x00' +
            b'\xc2\x00\x00\x00\x00\xc3\x00\x00\x00\x00\xc4\x00\xc5\x00\xc6' +
            b'\x00\xc7\x00\xc8\x00\xc9\x00\xca\x00\xcb\x00\xcc\x00\xcd\x00' +
            b'\xce\x00\xcf\x00\xd0\x00\xd1\x00\xd2\x00\xd4D\x00\x00\x00\xd6' +
            b'\x00\x00\xd7\x00\x00\xd8\x00\x00\xd9\x00\x00\xda\x00\x00\xdb' +
            b'\x00\x00\x00\x00\xdc\x00\x00\x00\x00\xdd\x00\x00\x00\x00\xde' +
            b'\x00\x00\x00\x00\xdf\x00\x00\x00\x00\xf0\x00\x00\x00\x00\xf1' +
            b'\x00\x00\x00\x00\xf2\x00\x00\x00\x00\xf3\x00\x00\x00\x00\xf4' +
            b'\x00\x00\x00\x00\xf5\x00\x00\x00\x00\xf6\x00\x00\x00\x00\xf7' +
            b'\x00\x00\x00\x00\xf8\x00\x00\x00\x00\xf9\x00\x00\x00\x00\x03' +
            b'356917057458304\x042\x00\x102s {@\xbaW0\x0cD`,\x03l\xd8\xfd' +
            b'\x023\x00\x00\x00\x004{\x005\x06@\x08:A\x180B\x1f\x10C\x1aE' +
            b'\xff\x00G\x00\x00\x00\nP\x00\x00\xa0\x00\xa1\x00\xa2\x00\xa3' +
            b'\x00\xa4\x00\xa5\x00\xa6\x00\xa7\x00\xa8\x00\xa9\x00\xaa\x00' +
            b'\xab\x00\xac\x00\xad\x00\xae\x00\xaf\x00\xb0\x00\x00\xb1\x00' +
            b'\x00\xb2\x00\x00\xb3\x00\x00\xb4\x00\x00\xb5\x00\x00\xb6\x00' +
            b'\x00\xb7\x00\x00\xb8\x00\x00\xb9\x00\x00\xc0\x00\x00\x00\x00' +
            b'\xc1\x00\x00\x00\x00\xc2\x00\x00\x00\x00\xc3\x00\x00\x00\x00' +
            b'\xc4\x00\xc5\x00\xc6\x00\xc7\x00\xc8\x00\xc9\x00\xca\x00\xcb' +
            b'\x00\xcc\x00\xcd\x00\xce\x00\xcf\x00\xd0\x00\xd1\x00\xd2\x00' +
            b'\xd4D\x00\x00\x00\xd6\x00\x00\xd7\x00\x00\xd8\x00\x00\xd9\x00' +
            b'\x00\xda\x00\x00\xdb\x00\x00\x00\x00\xdc\x00\x00\x00\x00\xdd' +
            b'\x00\x00\x00\x00\xde\x00\x00\x00\x00\xdf\x00\x00\x00\x00\xf0' +
            b'\x00\x00\x00\x00\xf1\x00\x00\x00\x00\xf2\x00\x00\x00\x00\xf3' +
            b'\x00\x00\x00\x00\xf4\x00\x00\x00\x00\xf5\x00\x00\x00\x00\xf6' +
            b'\x00\x00\x00\x00\xf7\x00\x00\x00\x00\xf8\x00\x00\x00\x00\xf9' +
            b'\x00\x00\x00\x00\x9d\x1e'
        )
        stored_packets = h.getStore().get_stored_packets()

        self.assertEqual(len(stored_packets), 3)
        packet = stored_packets[1]
        self.assertEqual(packet['speed'], 0)
        self.assertEqual(packet['uid'], '356917057458304')