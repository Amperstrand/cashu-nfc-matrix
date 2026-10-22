#!/usr/bin/env bash
# Assert the bench phone is on the LAB wifi before any HIL run.
# Exit 0 = on lab wifi; exit 1 with instructions otherwise.
set -euo pipefail
IP=$(adb -s RF8NB01ZYAH shell ip addr show wlan0 2>/dev/null | grep -o 'inet [0-9.]*' | awk '{print $2}')
if [[ "$IP" == 192.168.13.* ]]; then
    echo "lab wifi ok: $IP"
    exit 0
fi
echo "phone NOT on lab wifi (wlan0: ${IP:-none}) — run bench/wifi_connect.py" >&2
exit 1
