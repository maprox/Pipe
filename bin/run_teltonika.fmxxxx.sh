#!/usr/bin/env bash
echo 'Starting Teltonika fmxxxx listener'
python3 main.py -c conf/handlers/teltonika.fmxxxx.conf -l conf/logs/teltonika.fmxxxx.conf --pipe_process_mask=$1 -p $2 -s $3
