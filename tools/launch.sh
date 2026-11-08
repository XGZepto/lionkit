#!/bin/sh
# Open, relaunch or quit an app on the Lion Mac through the dev launcher, so it runs in the GUI
# session with the login keychain unlocked (apps started straight over SSH see it as locked).
#
# usage: tools/launch.sh [open|relaunch|quit] "App Name"
#        tools/launch.sh --install          (one-time; then the user loads it from Terminal on the Mac)
set -e
cd "$(dirname "$0")/.."
HOST=${LION_HOST:-lionmac}
if [ "$1" = "--install" ]; then
    tar -czf - tools/devlauncher | ssh -o BatchMode=yes "$HOST" \
        'D=$(mktemp -d /tmp/lk-dev.XXXXXX) && tar -xzf - -C $D && sh $D/tools/devlauncher/install.sh; rm -rf $D'
    exit
fi
action=$1 name=$2
case "$action" in open | relaunch | quit) ;; *) echo "usage: $0 [open|relaunch|quit] \"App Name\"" >&2; exit 2 ;; esac
case "$name" in "" | *[!A-Za-z0-9\ ]*) echo "bad app name: $name" >&2; exit 2 ;; esac
req="req.$(date +%s).$$"
ssh -o BatchMode=yes "$HOST" "mkdir -p ~/Library/LionKitDev/queue && echo '$action $name' > ~/Library/LionKitDev/queue/$req.tmp && mv ~/Library/LionKitDev/queue/$req.tmp ~/Library/LionKitDev/queue/$req
for i in 1 2 3 4 5 6 7 8 9 10; do [ -f ~/Library/LionKitDev/queue/$req ] || exit 0; sleep 1; done
rm -f ~/Library/LionKitDev/queue/$req
echo 'The dev launcher is not running. Ask the user to run this in Terminal on the Mac:' >&2
echo '    launchctl load -w ~/Library/LaunchAgents/local.lionkit.devlauncher.plist' >&2
exit 1"
