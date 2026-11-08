#!/usr/bin/env python3
"""Render a Dashboard widget in Lion's own WebKit, off screen, and save PNGs of it.

usage: tools/widget_preview.py widgets/Forecast.wdgt out.png [options]
  --prefs JSON          widget preferences, e.g. '{"place": "{\\"name\\": ...}"}'
  --wait SECONDS        let the widget load and fetch before the first shot (default 4)
  --eval JS             run this JavaScript before the first shot
  --shot OUT.png=JS     after the first shot, run JS and save another PNG (repeatable)
  --settle SECONDS      wait after each --eval/--shot script (default 1)
  --bg COLOR|none       backdrop, like Dashboard's dimmed desktop (default #50555c); none
                        keeps the transparency (for Default.png)

Runs from Linux: copies the widget to a temp dir on the Mac (LION_HOST, default lionmac) and
renders it with /usr/bin/python and PyObjC in a window that never comes on screen (no Dock icon,
no focus change). A stand-in `widget` object runs widget.system() through /bin/sh in the
widget's folder, so network calls are real; preferences live only for the run. Console
messages, JavaScript errors and alerts are printed.
"""
import argparse
import base64
import json
import os
import subprocess
import sys

HOST = os.environ.get("LION_HOST", "lionmac")

REMOTE = r'''# -*- coding: utf-8 -*-
import base64, json, os, plistlib, subprocess, sys, time
import objc
from AppKit import *
from Foundation import *
from WebKit import *

args = json.loads(base64.b64decode(sys.argv[1]))
wdgt = args["widget"]
info = plistlib.readPlist(os.path.join(wdgt, "Info.plist"))
size = [info.get("Width", 300), info.get("Height", 200)]

SHIM = """
(function () {
    var prefs = %s;
    window.widget = {
        identifier: "preview",
        preferenceForKey: function (k) { return prefs.hasOwnProperty(k) ? prefs[k] : undefined; },
        setPreferenceForKey: function (v, k) {
            if (v === null || v === undefined) delete prefs[k]; else prefs[k] = v;
        },
        system: function (cmd, handler) {
            var r = JSON.parse(prompt("lk-system", cmd));
            var obj = { status: r.status, outputString: r.out, errorString: r.err,
                        write: function () {}, close: function () {}, cancel: function () {} };
            if (handler) setTimeout(function () { handler(obj); }, 10);
            return obj;
        },
        openURL: function (u) { console.log("widget.openURL " + u); },
        openApplication: function (b) { console.log("widget.openApplication " + b); },
        prepareForTransition: function () {},
        performTransition: function () {},
        setCloseBoxOffset: function () {},
        resizeAndMoveTo: function (x, y, w, h) { window.resizeTo(w, h); }
    };
    window.resizeTo = function (w, h) { prompt("lk-resize", w + "," + h); };
})();
""" % json.dumps(args.get("prefs") or {})


class Delegate(NSObject):
    def webView_didClearWindowObject_forFrame_(self, view, window_object, frame):
        window_object.evaluateWebScript_(SHIM)

    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_(self, view, message, frame):
        print("alert: %s" % message.encode("utf-8"))

    def webView_runJavaScriptTextInputPanelWithPrompt_defaultText_initiatedByFrame_(self, view, kind, text, frame):
        if kind == "lk-resize":
            w, h = [int(float(v)) for v in text.split(",")]
            size[:] = [w, h]
            window.setContentSize_((w, h))
            view.setFrame_(((0, 0), (w, h)))
            return u"ok"
        if kind == "lk-system":
            p = subprocess.Popen(["/bin/sh", "-c", text.encode("utf-8")], cwd=wdgt,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            print("system [%d]: %s" % (p.returncode, text.encode("utf-8")[:160]))
            return json.dumps({"status": p.returncode, "out": out.decode("utf-8", "replace"),
                               "err": err.decode("utf-8", "replace")})
        return None

    @objc.typedSelector("v@:@@")
    def webView_addMessageToConsole_(self, view, message):
        print("console: %s (%s:%s)" % (message.get("message", u"").encode("utf-8"),
                                       os.path.basename(message.get("sourceURL", u"") or u""),
                                       message.get("lineNumber", "")))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))


def snapshot(path):
    view.display()
    rect = ((0, 0), tuple(size))
    rep = view.bitmapImageRepForCachingDisplayInRect_(rect)
    view.cacheDisplayInRect_toBitmapImageRep_(rect, rep)
    if args.get("bg") != "none":
        flat = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, size[0], size[1], 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(flat))
        hexcolor = args.get("bg") or "#50555c"
        r, g, b = [int(hexcolor[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1).set()
        NSRectFill(rect)
        rep.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            rect, rect, NSCompositeSourceOver, 1.0, False, None)
        NSGraphicsContext.restoreGraphicsState()
        rep = flat
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)
    print("shot %s %dx%d" % (os.path.basename(path), size[0], size[1]))


app = NSApplication.sharedApplication()
app.setActivationPolicy_(2)   # NSApplicationActivationPolicyProhibited: no Dock icon, no focus
window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((-6000, -6000), tuple(size)), NSBorderlessWindowMask, NSBackingStoreBuffered, False)
window.setOpaque_(False)
window.setBackgroundColor_(NSColor.clearColor())
view = WebView.alloc().initWithFrame_frameName_groupName_(((0, 0), tuple(size)), None, None)
view.setDrawsBackground_(False)
prefs = view.preferences()
if prefs.respondsToSelector_("setAllowFileAccessFromFileURLs:"):
    prefs.setAllowFileAccessFromFileURLs_(True)
delegate = Delegate.alloc().init()
view.setFrameLoadDelegate_(delegate)
view.setUIDelegate_(delegate)
window.setContentView_(view)
main_html = os.path.join(wdgt, info["MainHTML"])
view.mainFrame().loadRequest_(NSURLRequest.requestWithURL_(NSURL.fileURLWithPath_(main_html)))

pump(args.get("wait", 4))
if args.get("eval"):
    view.stringByEvaluatingJavaScriptFromString_(args["eval"])
    pump(args.get("settle", 1))
snapshot(args["out"])
for out, script in args.get("shots", []):
    view.stringByEvaluatingJavaScriptFromString_(script)
    pump(args.get("settle", 1))
    snapshot(out)
'''


def ssh(command, data=None):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, command], input=data,
                          stdout=subprocess.PIPE, check=True).stdout.decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("widget")
    parser.add_argument("out")
    parser.add_argument("--prefs", default="{}")
    parser.add_argument("--wait", type=float, default=4)
    parser.add_argument("--eval")
    parser.add_argument("--shot", action="append", default=[])
    parser.add_argument("--settle", type=float, default=1)
    parser.add_argument("--bg", default="#50555c")
    a = parser.parse_args()

    widget = a.widget.rstrip("/")
    name = os.path.basename(widget)
    remote = ssh("mktemp -d /tmp/lk-preview.XXXXXX").strip()
    try:
        tar = subprocess.run(["tar", "-C", os.path.dirname(os.path.abspath(widget)), "-czf", "-", name],
                             stdout=subprocess.PIPE, check=True).stdout
        ssh("tar -xzf - -C %s" % remote, tar)
        shots = []
        for i, spec in enumerate(a.shot):
            out, script = spec.split("=", 1)
            shots.append([out, "%s/shot-%d.png" % (remote, i + 1), script])
        params = {"widget": "%s/%s" % (remote, name), "out": "%s/shot-0.png" % remote,
                  "prefs": json.loads(a.prefs), "wait": a.wait, "eval": a.eval, "settle": a.settle,
                  "bg": a.bg, "shots": [[r, s] for _, r, s in shots]}
        encoded = base64.b64encode(json.dumps(params).encode()).decode()
        sys.stdout.write(ssh("/usr/bin/python - %s 2>&1" % encoded, REMOTE.encode()))
        for local, remote_path in [(a.out, params["out"])] + [(o, r) for o, r, _ in shots]:
            subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "%s:%s" % (HOST, remote_path), local], check=True)
    finally:
        ssh("rm -rf %s" % remote)


if __name__ == "__main__":
    main()
