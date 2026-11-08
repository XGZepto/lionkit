#!/usr/bin/env python3
"""Screenshot one app's windows on the Lion Mac without bringing them forward.

usage: tools/shot.py "App Name" [out.png]     (runs from Linux; captures over SSH)

Uses Quartz's window list to find the app's on-screen windows and `screencapture -l<id>`, so it
works even when the window is behind a full-screen app on another Space.
"""
import os
import subprocess
import sys

HOST = os.environ.get("LION_HOST", "lionmac")
REMOTE = r'''
import sys, subprocess
from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionAll, kCGNullWindowID
owner = sys.argv[1]
wins = [w for w in CGWindowListCopyWindowInfo(kCGWindowListOptionAll, kCGNullWindowID)
        if w.get("kCGWindowOwnerName") == owner and w.get("kCGWindowLayer") == 0
        and w["kCGWindowBounds"]["Height"] > 80]
if not wins:
    sys.exit("no window for %r" % owner)
wins.sort(key=lambda w: -w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
n = 0
for w in wins:
    if n == int(sys.argv[2]):
        break
    # hidden or off-screen windows can't be captured; skip them instead of giving up
    if subprocess.call(["screencapture", "-x", "-o", "-l%d" % w["kCGWindowNumber"], "/tmp/lk-shot-%d.png" % n],
                       stderr=open("/dev/null", "w")) == 0:
        print("/tmp/lk-shot-%d.png %s" % (n, w.get("kCGWindowName", "")))
        n += 1
'''


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    app, out = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "shot.png"
    count = int(os.environ.get("SHOT_WINDOWS", "1"))
    listing = subprocess.check_output(["ssh", "-o", "BatchMode=yes", HOST, "/usr/bin/python - '%s' %d" % (app, count)],
                                      input=REMOTE.encode()).decode().split("\n")
    for i, line in enumerate(l for l in listing if l.strip()):
        remote = line.split(" ", 1)[0]
        target = out if i == 0 else out.replace(".png", "-%d.png" % i)
        subprocess.check_call(["scp", "-q", "-o", "BatchMode=yes", "%s:%s" % (HOST, remote), target])
        print(target, "-", line.split(" ", 1)[1] if " " in line else "")


if __name__ == "__main__":
    main()
