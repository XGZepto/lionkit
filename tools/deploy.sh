#!/bin/sh
# Push the sources to the Lion Mac over SSH and build/install the apps and widgets there.
# usage: tools/deploy.sh [app-dir ...]     (default: every app under apps/ and widgets/)
#
# Each run builds from its own temporary directory on the Mac, so several checkouts (agents in
# different worktrees) can deploy at once as long as they don't build the same app.
set -e
cd "$(dirname "$0")/.."
HOST=${LION_HOST:-lionmac}
SRC=$(ssh -o BatchMode=yes "$HOST" 'mktemp -d /tmp/lionkit-src.XXXXXX')
trap 'ssh -o BatchMode=yes "$HOST" "rm -rf $SRC"' EXIT

tar --exclude='*.pyc' --exclude='__pycache__' -czf - lionkit apps widgets tools/build_app.py 2>/dev/null |
    ssh -o BatchMode=yes "$HOST" "tar -xzf - -C $SRC 2>/dev/null"

targets="$*"
[ -n "$targets" ] || targets="$(ls -d apps/* widgets/* 2>/dev/null)"
for t in $targets; do
    t=${t%/}
    case "$t" in
        apps/*)    ssh -o BatchMode=yes "$HOST" "cd $SRC && /usr/bin/python tools/build_app.py '$t' /Applications" ;;
        widgets/*) ssh -o BatchMode=yes "$HOST" "mkdir -p ~/Library/Widgets && rm -rf ~/Library/Widgets/$(basename "$t") && cp -R $SRC/'$t' ~/Library/Widgets/ && echo installed widget $(basename "$t")" ;;
        *)         echo "skipping $t (not under apps/ or widgets/)" >&2 ;;
    esac
done
