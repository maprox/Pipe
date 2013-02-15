# -*- coding: utf8 -*-
'''
@project   Maprox <http://www.maprox.net>
@info      Teltonika FMXXXXX base class
@copyright 2013, Maprox LLC
'''


import json
import binascii
from struct import pack
from lib.ip import get_ip

from kernel.logger import log
from kernel.config import conf
from kernel.dbmanager import db
from lib.handler import AbstractHandler
import lib.consts as consts
import binascii
import lib.handlers.teltonika.packets as packets

# ---------------------------------------------------------------------------

class TeltonikaHandler(AbstractHandler):
    """
     Base handler for Teltonika FMXXXXX protocol
    """

    # private buffer for headPacket data
    __headPacketRawData = None

    def processData(self, data):
        """
         Processing of data from socket / storage.
         @param data: Data from socket
         @param packnum: Number of socket packet (defaults to 0)
         @return: self
        """
        protocolPackets = packets.PacketFactory.getPacketsFromBuffer(data)
        for protocolPacket in protocolPackets:
            self.processProtocolPacket(protocolPacket)

        return super(TeltonikaHandler, self).processData(data)

    def processProtocolPacket(self, protocolPacket):
        """
         Process teltonika packet.
         @type protocolPacket: packets.Packet
         @param protocolPacket: Teltonika protocol packet
        """
        if not self.__headPacketRawData:
            self.__headPacketRawData = b''

        if isinstance(protocolPacket, packets.PacketHead):
            log.info('HeadPack is stored.')
            self.__headPacketRawData = protocolPacket.rawData
            self.uid = protocolPacket.deviceImei

        if not self.uid:
            return log.error('HeadPack is not found!')

        # try to configure this tracker
        if self.configure():
            return

        # sends the acknowledgment
        self.sendAcknowledgement(protocolPacket)

        if isinstance(protocolPacket, packets.PacketHead):
            return

        observerPackets = self.translate(protocolPacket)
        if len(observerPackets) == 0:
            log.info('Location packet not found. Exiting...')
            return

        log.info(observerPackets)
        self._buffer = self.__headPacketRawData + protocolPacket.rawData
        self.store(observerPackets)

    def configure(self):
        current_db = db.get(self.uid)
        if not current_db.has('config'):
            return False
        data = current_db.get('config')
        self.send(data)
        log.debug('Configuration data sent = %s', data)
        config = packets.TeltonikaConfiguration(data)
        answer = b''
        try:
            log.debug('Waiting for the answer from device...')
            answer = self.recv()
        except Exception as E:
            log.error(E)
        current_db.remove('config')
        return config.isCorrectAnswer(answer)

    def sendCommand(self, command):
        """
         Sends command to the tracker
         @param command: Command string
        """
        log.info('Sending "' + command + '"...')
        log.info('[IS NOT IMPLEMENTED]')

    def receiveImage(self, packet):
        """
         Receives an image from tracker.
         Sends it to the observer server, when totally received.
        """
        log.error('Image receiving...')
        log.info('[IS NOT IMPLEMENTED]')

    def translate(self, protocolPacket):
        """
         Translate gps-tracker data to observer pipe format
         @param protocolPacket: Teltonika protocol packet
        """
        list = []
        if (protocolPacket == None): return list
        if not isinstance(protocolPacket, packets.PacketData):
            return list
        if (len(protocolPacket.AvlDataArray.items) == 0):
            return list
        for item in protocolPacket.AvlDataArray.items:
            packet = {'uid': self.uid}
            packet.update(item.params)
            packet['time'] = packet['time'].strftime('%Y-%m-%dT%H:%M:%S.%f')
            packet['hdop'] = 1 # temporarily manual value of hdop
            list.append(packet)
        return list

    def sendAcknowledgement(self, packet):
        """
         Sends acknowledgement to the socket
         @param packet: a L{packets.BasePacket} subclass
        """
        buf = self.getAckPacket(packet)
        log.info("Send acknowledgement: h" + binascii.hexlify(buf).decode())
        return self.send(buf)

    @classmethod
    def getAckPacket(cls, packet):
        """
         Returns acknowledgement buffer value
         @param packet: a L{packets.Packet} subclass
        """
        if isinstance(packet, packets.PacketHead):
            return b'\x01'
        else:
            return pack('>L', len(packet.AvlDataArray.items))

    def processCommandExecute(self, task, data):
        """
         Execute command for the device
         @param task: id task
         @param data: data dict()
        """
        log.info('Observer is sending a command:')
        log.info(data)
        self.sendCommand(data['command'])

    @classmethod
    def packString(cls, value):
        strLen = len(value)
        result = pack('>B', strLen)
        if strLen > 0:
            result += value.encode()
        return result

    def getInitiationSmsBuffer(self, data):
        """
         Returns initiation sms buffer
         @param data:
         @return:
        """
        # TP-UDH
        pushSmsPort = 0x07D1 # WDP Port listening for “push” SMS
        buffer = b'\x06\x05\x04'
        buffer += pack('>H', pushSmsPort)
        buffer += b'\x00\x00'
        # TP-UD
        buffer += self.packString(data['device']['login'])
        buffer += self.packString(data['device']['password'])
        buffer += self.packString(str(get_ip()))
        buffer += pack('>H', data['port'])
        buffer += self.packString(data['gprs']['apn'])
        buffer += self.packString(data['gprs']['username'])
        buffer += self.packString(data['gprs']['password'])
        return buffer

    def getInitiationData(self, config):
        """
         Returns initialization data for SMS wich will be sent to device
         @param config: config dict
         @return: array of dict or dict
        """
        # create config packet and save it to the database
        packet = self.getConfigurationPacket(config)
        current_db = db.get(config['identifier'])
        current_db.set('config', packet.rawData)
        log.info(packet.rawData)
        # create push-sms for configuration
        buffer = self.getInitiationSmsBuffer(config)
        data = [{
            'message': binascii.hexlify(buffer).decode(),
            'bin': consts.SMS_BINARY_HEX_STRING,
            'push': True
        }]
        return data

    def getConfigurationPacket(self, config):
        """
         Returns Teltonika configuration packet
         @param config: config dict
         @return:
        """
        packet = packets.TeltonikaConfiguration()
        packet.packetId = 1
        packet.addParam(packets.CFG_TARGET_SERVER_IP_ADDRESS, str(get_ip()))
        packet.addParam(packets.CFG_TARGET_SERVER_PORT, str(config['port']))
        packet.addParam(packets.CFG_APN_NAME, config['gprs']['apn'])
        packet.addParam(packets.CFG_APN_USERNAME, config['gprs']['username'])
        packet.addParam(packets.CFG_APN_PASSWORD, config['gprs']['password'])
        packet.addParam(packets.CFG_SMS_LOGIN, config['device']['login'])
        packet.addParam(packets.CFG_SMS_PASSWORD, config['device']['password'])
        packet.addParam(packets.CFG_GPRS_CONTENT_ACTIVATION, 1) # Enable
        packet.addParam(packets.CFG_OPERATOR_LIST, '25002') # MegaFON
        # on stop config
        packet.addParam(packets.CFG_VEHICLE_ON_STOP_MIN_PERIOD, 60) # seconds
        packet.addParam(packets.CFG_VEHICLE_ON_STOP_MIN_SAVED_RECORDS, 1)
        packet.addParam(packets.CFG_VEHICLE_ON_STOP_SEND_PERIOD, 180) # seconds
        # moving config
        packet.addParam(packets.CFG_VEHICLE_MOVING_MIN_PERIOD, 20) # seconds
        packet.addParam(packets.CFG_VEHICLE_MOVING_MIN_SAVED_RECORDS, 1)
        packet.addParam(packets.CFG_VEHICLE_MOVING_SEND_PERIOD, 60) # seconds
        return packet

    def processCommandReadSettings(self, task, data):
        """
         Sending command to read all of device configuration
         @param task: id task
         @param data: data string
        """
        log.error('Teltonika::processCommandReadSettings NOT IMPLEMENTED')
        self.processCloseTask(task, None)

    def processCommandSetOption(self, task, data):
        """
         Set device configuration
         @param task: id task
         @param data: data dict()
        """
        log.error('Teltonika::processCommandSetOption NOT IMPLEMENTED')
        self.processCloseTask(task, None)

# ===========================================================================
# TESTS
# ===========================================================================

import unittest
import kernel.pipe as pipe

class TestCase(unittest.TestCase):

    def setUp(self):
        self.handler = TeltonikaHandler(pipe.Manager(), None)
        pass

    def test_packetAcknowledgement(self):
        h = self.handler
        data = b'\x00\x00\x00\x00\x00\x00\x00\x2c\x08\x01\x00\x00\x01\x13' +\
               b'\xfc\x20\x8d\xff\x00\x0f\x14\xf6\x50\x20\x9c\xca\x80\x00' +\
               b'\x6f\x00\xd6\x04\x00\x04\x00\x04\x03\x01\x01\x15\x03\x16' +\
               b'\x03\x00\x01\x46\x00\x00\x01\x5d\x00\x01\x00\x00\xcf\x77'
        packet = packets.PacketData(data)
        self.assertEqual(h.getAckPacket(packet), b'\x00\x00\x00\x01')
        packet = packets.PacketFactory.getInstance(b'\x00\x0f012896001609129')
        self.assertEqual(h.getAckPacket(packet), b'\x01')
