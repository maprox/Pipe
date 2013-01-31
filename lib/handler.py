# -*- coding: utf8 -*-
'''
@project   Maprox <http://www.maprox.net>
@info      Abstract class for all implemented protocols
@copyright 2009-2012, Maprox LLC
'''

from datetime import datetime
import re
import json
import base64
from urllib.parse import urlencode
from kernel.logger import log
from kernel.config import conf
from kernel.dbmanager import db
from lib.storage import storage
from urllib.request import urlopen
import http.client
from lib.ip import get_ip

class AbstractHandler(object):
    """
     Abstract class for all implemented protocols
    """
    _buffer = None # buffer of the current dispatch loop (for storage save)

    default_options = {}

    transmissionEndSymbol = "\n"
    """ Symbol which marks end of transmission for PHP """

    uid = False
    """ Uid of currently connected device """

    re_request = re.compile('^OBS.*request\((?P<data>.+)\)$')
    re_success = re.compile('^OBS,success')

    def __init__(self, store, clientThread):
        """
         Constructor of Listener.
         @param store: kernel.pipe.Manager instance
         @param clientThread: Instance of kernel.server.ClientThread
        """
        log.debug('%s::__init__()', self.__class__)
        self.__store = store
        self.__thread = clientThread

    def getStore(self):
        """ Returns store object """
        return self.__store

    def getThread(self):
        """ Returns clientThread object """
        return self.__thread

    def dispatch(self):
        """
          Data processing method (after validation) from the device:
          clientThread thread of the socket;
        """
        log.debug('%s::dispatch()', self.__class__)
        buffer = self.recv()
        while len(buffer) > 0:
            self.processData(buffer)
            buffer = self.recv()


    def processData(self, data):
        """
         Processing of data from socket / storage.
         Must be overridden in child classes
         @param data: Data from socket
        """

        if not self.uid: return self

        current_db = db.get(self.uid)
        self.processRequest(current_db.getCommands())

        current_db = db.get(self.uid)
        if current_db.isSettingsReady():
            send = {}
            config = self.translateConfig(current_db.getSettings())
            send['config'] = json.dumps(config, separators=(',',':'))
            send['id_action'] = current_db.getSettingsTaskId()
            log.debug('Sending config: ' + conf.pipeSetUrl + urlencode(send))
            connection = urlopen(conf.pipeSetUrl, urlencode(send).encode())
            answer = connection.read()
            log.debug('Config answered: ' + answer.decode())
            #result = self.re_success.search(answer.decode(), 0)
            #if result:
            current_db.deleteSettings()
        return self

    def processRequest(self, data):
        """
         Processing of observer request from socket
         @param data: request
        """
        for command in data:
            function_name = 'processCommand' \
              + command['action'][0].upper() \
              + command['action'][1:]
            log.debug('Command is: ' + function_name)
            function = getattr(self, function_name)
            if 'value' in command:
                function(command['id'], command['value'])
            else:
                function(command['id'], None)
        return self

    def getTaskData(self, task, data = None):
        """
         Return close task data
         @param task: Task identifier
         @param data: Result data to send. [Optional]
         @return dict
        """
        message = { "id_action": task }
        if data is not None:
            content = data
            if isinstance(data, str):
                content = [{
                    "message": data
                }]
            message['data'] = json.dumps(content)
        return message

    def processCloseTask(self, task, data = None):
        """
         Close task
         @param task: Task identifier
         @param result: Result data to send. [Optional]
        """
        message = self.getTaskData(task, data)
        params = urlencode(message)
        log.debug('Close task: ' + conf.pipeFinishUrl + params)

        urlParts = re.search('//(.+?)(/.+)', conf.pipeFinishUrl)
        restHost = urlParts.group(1)
        restPath = urlParts.group(2)

        conn = http.client.HTTPConnection(restHost, 80)
        conn.request("POST", restPath, params, {
            "Content-type": "application/x-www-form-urlencoded",
            "Accept": "text/plain"
        })
        conn.getresponse()

    def recv(self):
        """
         Receiving data from socket
         @param the_socket: Instance of a socket object
         @return: String representation of data
        """
        sock = self.getThread().request
        sock.settimeout(conf.socketTimeout)
        total_data = []
        while True:
            try:
                data = sock.recv(conf.socketPacketLength)
            except Exception as E:
                break
            log.debug('Data chunk = %s', data)
            if not data: break
            total_data.append(data)
            # I don't know why [if not data: break] is not working,
            # so let's do break here
            if len(data) < conf.socketPacketLength: break
        log.debug('Total data = %s', total_data)
        return b''.join(total_data)

    def send(self, data):
        """
         Sends data to a socket
         @param data: data
        """
        sock = self.getThread().request
        sock.send(data)
        return self

    def store(self, packets):
        """
         Sends a list of packets to store
         @param packets: A list of packets
         @return: Instance of lib.falcon.answer.FalconAnswer
        """
        result = self.getStore().send(packets)
        if (result.isSuccess()):
            log.debug('%s::store() ... OK', self.__class__)
        else:
            log.error('%s::store():\n %s',
              self.__class__, result.getErrorsList())
            # send data to storage on error to save packets
            storage.save(self.uid if self.uid else 'unknown', self._buffer)
        return result

    def translate(self, data):
        """
         Translate gps-tracker data to observer pipe format
         @param data: dict() data from gps-tracker
        """
        raise NotImplementedError(
          "Not implemented Handler::translate() method")

    def translateConfig(self, data):
        """
         Translate gps-tracker config data to observer format
         @param data: {string[]} data from gps-tracker
        """
        raise NotImplementedError(
          "Not implemented Handler::translateConfig() method")

    def sendImages(self, images):
        """
         Sends image to the observer
         @param images: dict() of binary data like {'camera1': b'....'}
        """
        if not self.uid:
            log.error('Cant send an image - self.uid is not defined!')
            return
        imageslist = []
        for image in images:
            image['content'] = base64.b64encode(image['content']).decode()
            imageslist.append(image)
        observerPacket = {
          'uid': self.uid,
          'time': datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f'),
          'images': imageslist
        }
        result = self.store(observerPacket)
        if (result.isSuccess()):
            log.info('%s::sendImages(): Images have been sent.',
              self.__class__)
        else:
            #print(result.getErrorsList())
            # ? Error messages should be converted into readable format
            log.error('%s::sendImages():\n %s',
              self.__class__, result.getErrorsList())

    @classmethod
    def dictCheckItem(cls, data, name, value):
        """
         Checks if "name" is in "data" dict. If not, creates it with "value"
         @param data: input dict
         @param name: key of dict to check
         @param value: value of dict item at key "name"
        """
        if name not in data: data[name] = value

    def getInitiationConfig(self, rawConfig):
        """
         Returns prepared initiation data object
         @param rawConfig: input json string or dict
         @return: dict (json) object
        """
        data = rawConfig
        if isinstance(data, str): data = json.loads(data)
        self.dictCheckItem(data, 'identifier', '')
        # host and port part of input
        self.dictCheckItem(data, 'port', str(conf.port))
        if 'host' not in data:
            # host has exception calling dictCheckItem cause
            # it will execute get_ip() even if 'host' is in data
            data['host'] = str(get_ip())
        # device part of input
        self.dictCheckItem(data, 'device', {})
        self.dictCheckItem(data['device'], 'login', '')
        self.dictCheckItem(data['device'], 'password', '')
        # gprs part of input
        self.dictCheckItem(data, 'gprs', {})
        self.dictCheckItem(data['gprs'], 'apn', '')
        self.dictCheckItem(data['gprs'], 'username', '')
        self.dictCheckItem(data['gprs'], 'password', '')
        return data

    def getInitiationData(self, config):
        """
         Returns initialization data for SMS wich will be sent to device
         @param config: config dict
         @return: dict
        """
        return None

    def processCommandFormat(self, task, rawConfig):
        """
         Processing command to form config string
         @param task: id task
         @param rawConfig: request configuration
        """
        config = self.getInitiationConfig(rawConfig)
        buffer = self.getInitiationData(config)
        if buffer is not None:
            self.processCloseTask(task, buffer)
