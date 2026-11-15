#!/bin/bash
cd "$(dirname "$0")"
PYTHON3=$(command -v python3.13 || command -v python3)  # av<14 (faster-whisper) has no wheel for newer python3
LOOP="while true; do PYTHONPATH=src $PYTHON3 -m tg_harness; sleep 2; done"
case "${1:-start}" in
  start)   pgrep -f -- "-m tg_harness" >/dev/null && { echo "already running"; exit 1; }
           nohup bash -c "$LOOP" >> bot.log 2>&1 < /dev/null &
           echo "started, log: $(pwd)/bot.log" ;;
  stop)    pkill -f "$LOOP"; pkill -f -- "-m tg_harness"; echo "stopped" ;;
  restart) "$0" stop; sleep 1; "$0" start ;;
  log)     tail -f bot.log ;;
  *)       echo "usage: $0 start|stop|restart|log"; exit 1 ;;
esac
