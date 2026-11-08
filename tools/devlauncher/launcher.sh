#!/bin/sh
# LionKit dev launcher. launchd runs this in the GUI (Aqua) session whenever a request file lands in
# ~/Library/LionKitDev/queue, so apps it opens can use the unlocked login keychain (apps opened over
# SSH can't). A request is one line: "<open|relaunch|quit> <App Name>". See tools/launch.sh.
Q="$HOME/Library/LionKitDev/queue"
for req in "$Q"/*; do
    [ -f "$req" ] || continue
    read -r action name < "$req"
    rm -f "$req"
    case "$name" in
        "" | *[!A-Za-z0-9\ ]*) echo "$(date '+%F %T') rejected app name: $name"; continue ;;
    esac
    app="/Applications/$name.app"
    [ -d "$app" ] || { echo "$(date '+%F %T') no such app: $app"; continue; }
    case "$action" in
        quit | relaunch)
            osascript -e 'with timeout of 10 seconds' -e "tell application \"$name\" to quit" -e 'end timeout' ;;
    esac
    case "$action" in
        relaunch) sleep 2; open -g "$app" ;;
        open) open -g "$app" ;;
    esac
    echo "$(date '+%F %T') $action $name"
done
