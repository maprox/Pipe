#!/usr/bin/env bash
echo 'Starting Naviset GT-20 listener'
python3 main.py -c conf/handlers/naviset.gt20.conf -l conf/logs/naviset.gt20.conf --pipe_process_mask=$1 -p $2 -s $3
