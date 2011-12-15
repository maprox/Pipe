# -*- coding: utf8 -*-
'''
@project   Maprox Observer <http://maprox.net/observer>
@info      Restoring from storage
@copyright 2009-2011, Maprox Ltd.
@author    sunsay <box@sunsay.ru>
@link      $HeadURL: http://vcs.maprox.net/svn/observer/Server/trunk/kernel/dispatcher.py $
@version   $Id: dispatcher.py 406 2011-02-28 14:24:53Z sunsay $
'''

import re
import socket
import time

from kernel.logger import log
from kernel.config import conf
from lib.storage import storage

try:
  timestamp = str(int(time.time()))
  for record in storage.load():
    host, port = "localhost", int(record['port'])
    for item in record['data']:
      try:
        # Connect to server and send data
        # Create a socket (SOCK_STREAM means a TCP socket)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
          sock.connect((host, port))

          contents = item['contents'].split(',')
          for line in contents:
            time.sleep(1)
            sock.send(bytes(line, 'UTF-8'))

          storage.delete(item, record['port'], timestamp)
        except Exception as E:
          log.error(E)
        finally:
          sock.close()
      except Exception as E:
        log.error(E)
except Exception as E:
  log.error(E)
