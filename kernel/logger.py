# -*- coding: utf8 -*-
"""
@project   Maprox <http://www.maprox.net>
@info      Logger
@copyright 2009-2012, Maprox LLC
"""

import os
import time
import logging
import logging.config
from kernel.options import options

# set UTC timezone for logging time
logging.Formatter.converter = time.gmtime

# read logging configuration
if options.logs == 'stdout':
    logging.config.dictConfig({
        'version': 1,
        'formatters': {
            'standard': {
                'format': '%(asctime)s %(levelname)s: %(message)s',
                'datefmt': '%Y.%m.%d %H:%M:%S'
            },
        },
        'handlers': {
            'default': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': 'DEBUG',
            },
        }
    })
else:
    if not os.path.exists(options.logs):
        options.logs = 'conf/logs.conf'
    logging.config.fileConfig(options.logs)

# expose logger instance
log = logging.getLogger()