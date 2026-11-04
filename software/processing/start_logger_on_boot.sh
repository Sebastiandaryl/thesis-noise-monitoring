#!/bin/bash
# Restarts the village logger after a power cut. Run from cron (@reboot).
# The Pi has no clock battery, so it waits until the time is synced over the
# internet; otherwise readings would get wrong timestamps.
# Disable before the defense (crontab -e, delete the @reboot line), because
# the logger holds the microphone and live_monitor.py needs it.

LOG=~/thesis/data/logging/boot_restarts.log
until [ "$(timedatectl show -p NTPSynchronized --value)" = "yes" ]; do sleep 10; done
sleep 20   # let the sound card and Wi-Fi settle
echo "$(date '+%F %T') boot: starting logger" >> "$LOG"
tmux new -d -s logger "source ~/thesis/venv/bin/activate && cd ~/thesis/software/processing && python noise_logger.py --site home_garage --site-id N01 --url https://noisemonitoringsystem.pythonanywhere.com; bash"
