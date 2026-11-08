#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Build a Lion .app bundle around a PyObjC app (runs ON the Mac, with the system Python 2.7).

usage: build_app.py <app source dir> <destination dir>

The source dir holds main.py, app.json ({"name", "id", "version"}) and optionally icon.py
(a render(path, size) function that draws the icon with AppKit).
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
LAUNCHER = """#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Library/Logs"
exec "$DIR/python" "$DIR/../Resources/main.py" "$@" >>"$HOME/Library/Logs/%(exe)s.log" 2>&1
"""


def build(src, dest):
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
    # A private copy of the Python binary makes this bundle the process's main bundle,
    # so the menu bar and Dock show the app's own name and icon instead of "Python".
    shutil.copy(PYTHON, os.path.join(contents, "MacOS", "python"))
    launcher = os.path.join(contents, "MacOS", exe)
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
    icon_py = os.path.join(src, "icon.py")
    if os.path.exists(icon_py):
        png = os.path.join(resources, "AppIcon.png")
        imp.load_source("app_icon", icon_py).render(png, 512)
        subprocess.check_call(["sips", "-s", "format", "icns", png, "--out",
                               os.path.join(resources, "AppIcon.icns")], stdout=open(os.devnull, "w"))
        os.remove(png)
        info["CFBundleIconFile"] = "AppIcon"
    plistlib.writePlist(info, os.path.join(contents, "Info.plist"))
    subprocess.call([LSREGISTER, "-f", app])
    print("built %s" % app)


if __name__ == "__main__":
    build(os.path.abspath(sys.argv[1]), sys.argv[2])
