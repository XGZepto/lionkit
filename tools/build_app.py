#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Build a Lion .app bundle around a PyObjC app (runs ON the Mac, with the system Python 2.7).

usage: build_app.py [--release] <app source dir> <destination dir>

The source dir holds main.py, app.json ({"name", "id", "version"}, optionally "copyright" and
"info": extra Info.plist keys) and optionally icon.py
(a render(path, size) function that draws the icon with AppKit).

A dev build copies Apple's Python binary into the bundle and uses the shared runtime in
~/Library/LionKit. A --release build is for other people's Macs: it embeds the trimmed runtime
from tools/LionKit (run tools/build_lionkit.py first) as Contents/Resources/runtime, leaves
Apple's binary out (its launcher copies it from the system on first run), and isn't registered
with LaunchServices, so a build in a temp folder leaves no trace.
"""
import imp
import json
import os
import plistlib
import py_compile
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = "/System/Library/Frameworks/Python.framework/Versions/2.7/Resources/Python.app/Contents/MacOS/Python"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")
RUNTIME = os.path.join(ROOT, "tools", "LionKit")
LAUNCHER = """#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Library/Logs"
exec "$DIR/python" "$DIR/../Resources/main.py" "$@" >>"$HOME/Library/Logs/%(exe)s.log" 2>&1
"""
# Apple's binary isn't ours to redistribute, so a release app copies it in on its first run (the
# copy names the menu bar and Dock after the app). Where the bundle is read-only, such as inside
# the disk image, it runs the system's binary instead: everything works, but it shows as Python.
RELEASE_LAUNCHER = """#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
SYS=%(python)s
if [ ! -x "$DIR/python" ]; then
    cp "$SYS" "$DIR/.python.$$" 2>/dev/null && mv -f "$DIR/.python.$$" "$DIR/python" 2>/dev/null
    rm -f "$DIR/.python.$$" 2>/dev/null
fi
[ -x "$DIR/python" ] && PY="$DIR/python" || PY="$SYS"
mkdir -p "$HOME/Library/Logs"
exec "$PY" "$DIR/../Resources/main.py" "$@" >>"$HOME/Library/Logs/%(exe)s.log" 2>&1
"""


def build(src, dest, release=False):
    if release and not os.path.exists(os.path.join(RUNTIME, "bin", "curl")):
        sys.exit("no runtime in %s: run tools/build_lionkit.py --no-install first" % RUNTIME)
    meta = json.load(open(os.path.join(src, "app.json")))
    for folder in (src, os.path.join(ROOT, "lionkit")):  # fail the deploy, not the launch, on a typo
        for f in os.listdir(folder):
            if f.endswith(".py"):
                py_compile.compile(os.path.join(folder, f), doraise=True)
    name = meta["name"]
    exe = name.replace(" ", "")
    app = os.path.join(dest, name + ".app")
    contents = os.path.join(app, "Contents")
    if os.path.exists(app):
        shutil.rmtree(app)
    os.makedirs(os.path.join(contents, "MacOS"))
    resources = os.path.join(contents, "Resources")

    shutil.copytree(src, resources, ignore=shutil.ignore_patterns("*.pyc", "app.json", "icon.py"))
    shutil.copytree(os.path.join(ROOT, "lionkit"), os.path.join(resources, "lionkit"),
                    ignore=shutil.ignore_patterns("*.pyc"))
    launcher = os.path.join(contents, "MacOS", exe)
    if release:
        shutil.copytree(RUNTIME, os.path.join(resources, "runtime"), symlinks=True)
        with open(launcher, "w") as f:
            f.write(RELEASE_LAUNCHER % {"exe": exe, "python": PYTHON})
    else:
        # A private copy of the Python binary makes this bundle the process's main bundle,
        # so the menu bar and Dock show the app's own name and icon instead of "Python".
        shutil.copy(PYTHON, os.path.join(contents, "MacOS", "python"))
        with open(launcher, "w") as f:
            f.write(LAUNCHER % {"exe": exe})
    os.chmod(launcher, 0o755)

    info = {
        "CFBundleName": name, "CFBundleDisplayName": name, "CFBundleExecutable": exe,
        "CFBundleIdentifier": meta["id"], "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": meta["version"], "CFBundleVersion": meta["version"],
        "LSMinimumSystemVersion": "10.7", "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": meta.get("copyright", ""),
    }
    info.update(meta.get("info", {}))  # extra Info.plist keys, e.g. LSUIElement for a menu bar app
    icon_py = os.path.join(src, "icon.py")
    if os.path.exists(icon_py):
        png = os.path.join(resources, "AppIcon.png")
        imp.load_source("app_icon", icon_py).render(png, 512)
        subprocess.check_call(["sips", "-s", "format", "icns", png, "--out",
                               os.path.join(resources, "AppIcon.icns")], stdout=open(os.devnull, "w"))
        os.remove(png)
        info["CFBundleIconFile"] = "AppIcon"
    plistlib.writePlist(info, os.path.join(contents, "Info.plist"))
    if not release:
        subprocess.call([LSREGISTER, "-f", app])
    print("built %s%s" % (app, " (release)" if release else ""))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--release"]
    if len(args) != 2:
        sys.exit(__doc__)
    build(os.path.abspath(args[0]), args[1], "--release" in sys.argv)
