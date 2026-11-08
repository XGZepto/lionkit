#!/bin/sh
# Install the LionKit dev launcher on the Mac (run over SSH by tools/launch.sh --install).
# launchd only loads it into the GUI session at the next login, or when the user runs the
# printed launchctl command in Terminal on the Mac.
set -e
D="$HOME/Library/LionKitDev"
PLIST="$HOME/Library/LaunchAgents/local.lionkit.devlauncher.plist"
mkdir -p "$D/queue" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cp "$(dirname "$0")/launcher.sh" "$D/launcher.sh"
chmod 755 "$D/launcher.sh"
cat > "$PLIST" <<PLEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>local.lionkit.devlauncher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>$D/launcher.sh</string>
    </array>
    <key>QueueDirectories</key>
    <array>
        <string>$D/queue</string>
    </array>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/lionkit-devlauncher.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/lionkit-devlauncher.log</string>
</dict>
</plist>
PLEOF
echo "Installed. To start it now, run this in Terminal on the Mac (not over SSH):"
echo "    launchctl load -w $PLIST"
