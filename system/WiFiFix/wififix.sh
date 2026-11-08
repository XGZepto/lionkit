#!/bin/bash
# WiFiFix for OS X Lion: keeps the Mac joined to a WPA2/WPA3 "transition" network.
#
# Lion's CoreWLAN sees the WPA3 (SAE) entry it doesn't understand and labels such
# networks "WPA2 Enterprise", so it never auto-joins them. A small LaunchAgent checks
# every 30 seconds; if Wi-Fi is on but not connected, it hides the WPA3 entry from the
# scan result and joins with plain WPA2-Personal, which the router still accepts.
#
# Install:   bash wififix.sh
# Uninstall: bash wififix.sh uninstall
set -e

DIR="$HOME/Library/WiFiFix"
PLIST="$HOME/Library/LaunchAgents/local.wififix.plist"
LOG="$HOME/Library/Logs/wififix.log"

if [ "$1" = "uninstall" ]; then
    launchctl unload -w "$PLIST" 2>/dev/null || true
    rm -rf "$DIR" "$PLIST"
    echo "WiFiFix removed."
    exit 0
fi

mkdir -p "$DIR" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

printf "Wi-Fi network name: "
read -r SSID
[ -n "$SSID" ] || { echo "No network name given."; exit 1; }
printf "Wi-Fi password (not shown while typing): "
read -rs PASS
echo

(umask 077 && printf '%s\n%s\n' "$SSID" "$PASS" > "$DIR/config")

cat > "$DIR/wifi-join.py" <<'PYEOF'
#!/usr/bin/python
# Joins a WPA2/WPA3 transition-mode network on OS X Lion (see wififix.sh).
from __future__ import print_function
import os
import sys
import time

import objc

objc.loadBundle('CoreWLAN', globals(), '/System/Library/Frameworks/CoreWLAN.framework')

AKM_PSK = 2  # RSN auth suite 2 = WPA2-PSK; WPA3-SAE is 8, which Lion doesn't know
VERBOSE = '--verbose' in sys.argv


def log(*args):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *args)
    sys.stdout.flush()


def unwrap(result):
    # PyObjC returns (value, error) when it knows about an NSError** out-parameter.
    return result[0] if isinstance(result, tuple) else result


def wifi_on(iface):
    for name in ('powerOn', 'power'):
        if hasattr(iface, name):
            return bool(getattr(iface, name)())
    return True


def main():
    with open(os.path.expanduser('~/Library/WiFiFix/config')) as f:
        ssid, password = f.read().split('\n')[:2]

    iface = CWInterface.interface()
    if iface is None or not wifi_on(iface):
        if VERBOSE:
            log('Wi-Fi is off; leaving it alone')
        return 0
    if iface.ssid():
        if VERBOSE:
            log('already connected to', iface.ssid())
        return 0

    nets = list(unwrap(iface.scanForNetworksWithName_error_(ssid, None)) or [])
    if not nets:
        if VERBOSE:
            log(ssid, 'not in range')
        return 0

    nets.sort(key=lambda n: n.rssiValue(), reverse=True)
    for net in nets:
        rec = net.valueForKey_('scanRecord').mutableCopy()
        rsn = rec.objectForKey_('RSN_IE')
        if rsn is not None:
            akms = list(rsn.objectForKey_('IE_KEY_RSN_AUTHSELS') or [])
            if AKM_PSK not in akms:
                continue  # WPA3-only access point; Lion can't join it
            rsn = rsn.mutableCopy()
            rsn.setObject_forKey_([AKM_PSK], 'IE_KEY_RSN_AUTHSELS')
            rec.setObject_forKey_(rsn, 'RSN_IE')
            net.setValue_forKey_(rec, 'scanRecord')
        if unwrap(iface.associateToNetwork_password_error_(net, password, None)):
            log('joined', ssid, 'via', net.bssid())
            return 0

    log('could not join', ssid, '(wrong password?)')
    return 1


if __name__ == '__main__':
    sys.exit(main())
PYEOF

cat > "$PLIST" <<PLEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>local.wififix</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python</string>
        <string>$DIR/wifi-join.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
</dict>
</plist>
PLEOF

launchctl unload -w "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo "Installed. Checking now:"
/usr/bin/python "$DIR/wifi-join.py" --verbose
echo "Log file: $LOG"
