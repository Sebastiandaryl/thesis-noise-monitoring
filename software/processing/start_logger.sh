#!/bin/bash
# Auto-start for noise_logger.py after a reboot or power outage (run from cron @reboot).
# Only runs while data/logging/AUTOSTART exists; delete that file to turn auto-start off.
# The Pi has no clock battery, so wait (up to 30 min) for the internet time before logging.
THESIS=/home/aidrivennoise/thesis
[ -f "$THESIS/data/logging/AUTOSTART" ] || exit 0
SITE=$(cat "$THESIS/data/logging/AUTOSTART"); SITE=${SITE:-home_garage}
for i in $(seq 180); do
    [ "$(timedatectl show -p NTPSynchronized --value)" = "yes" ] && break
    sleep 10
done
sleep 20   # let the sound card come up
cd "$THESIS/software/processing"
tmux new-session -d -s logger "$THESIS/venv/bin/python noise_logger.py --site $SITE 2>&1 | tee -a $THESIS/data/logging/logger_console.log"
