#!/bin/sh
# Startup clock check -- runs as willy-rover.service's ExecStartPre (owner, 2026-10-06).
#
# WHY: at boot the Witty Pi 5 daemon copies ITS RTC into the system clock (`date -s`), and on
# 2026-10-06 that RTC was a week and 36 minutes fast. The Pi 5's own RTC has no battery (reads
# 1970). systemd-timesyncd corrected the clock from the internet minutes later -- after this
# service had already started, so logs, retention ages and email timestamps were a week out.
#
# WHAT: wait up to CLOCK_SYNC_WAIT_S (45 s) for internet time, then write it to the Witty Pi
# RTC so the NEXT boot starts right even with no network. No internet in time: start anyway
# on the RTC's time and say so. Never fails the service -- a rover that will not start because
# the Wi-Fi is down is worse than one with a wrong clock.
#
# wp5 is the Witty Pi's menu CLI: 1 = write system time to RTC, 14 = exit. Run it as the
# service user, not root: a root run collides with the user's /run/lock/wittypi5_app.lock
# ("Another wp5 instance is already running").
WAIT=${CLOCK_SYNC_WAIT_S:-45}
i=0
while [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" != yes ]; do
    i=$((i+1))
    if [ "$i" -ge "$WAIT" ]; then
        echo "clock: no internet time after ${WAIT}s -- starting on the Witty Pi RTC's time ($(date -Is))"
        exit 0
    fi
    sleep 1
done
if printf '1\n14\n' | timeout 20 wp5 >/dev/null 2>&1; then
    echo "clock: internet time $(date -Is), written to the Witty Pi RTC"
else
    echo "clock: internet time $(date -Is); writing the Witty Pi RTC FAILED"
fi
exit 0
