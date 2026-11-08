# -*- coding: utf-8 -*-
"""Update checks against the website's updates.json, with a Lion-style sheet.

updates.json maps the last part of each app's bundle id to its newest release:

    {"kassett": {"version": "0.5", "page": "https://github.com/.../releases/tag/kassett-v0.5",
                 "notes": "What changed, in a sentence or two."}}

cocoa.build_main_menu calls install(), which adds "Check for Updates…" to the app menu and, in
release builds (the ones that carry their own runtime), checks by itself at most once a day.
Set the LionKitUpdatesURL default to test against another URL or a file:// path.
"""
import json
import os
import plistlib
import re
import time

from AppKit import NSAlert, NSAlertFirstButtonReturn, NSApp, NSWorkspace
from Foundation import NSBundle, NSObject, NSTimer, NSURL, NSUserDefaults
from PyObjCTools import AppHelper

from lionkit import cocoa, http

URL = "https://xgzepto.github.io/lionkit/updates.json"
DAY = 24 * 60 * 60
LAST_CHECK = "LionKitLastUpdateCheck"
SAFARI, MOMIJI = "com.apple.Safari", "org.mozilla.momiji-stable"  # Safari on Lion can't open GitHub
# Contents/Info.plist, found from Contents/Resources/lionkit/, so it's right even when the app runs
# under the system's Python binary (its main bundle is then Python.app).
INFO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Info.plist")

_updater = []


def version_tuple(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or ""))


def open_page(url):
    """Open url in the default browser, or in Momiji when the default is Lion's Safari."""
    ws = NSWorkspace.sharedWorkspace()
    nsurl = NSURL.URLWithString_(url)
    handler = ws.URLForApplicationToOpenURL_(nsurl)
    default = NSBundle.bundleWithURL_(handler).bundleIdentifier() if handler else None
    if default in (None, SAFARI) and ws.absolutePathForAppBundleWithIdentifier_(MOMIJI):
        ws.openURLs_withAppBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifiers_(
            [nsurl], MOMIJI, 0, None, None)
    else:
        ws.openURL_(nsurl)


class Updater(NSObject):
    page = None

    def checkForUpdates_(self, sender):
        check(True)

    def autoCheck_(self, timer):
        if time.time() - NSUserDefaults.standardUserDefaults().doubleForKey_(LAST_CHECK) >= DAY:
            check(False)

    @AppHelper.endSheetMethod
    def alertDidEnd_returnCode_contextInfo_(self, alert, code, info):
        if code == NSAlertFirstButtonReturn and self.page:
            open_page(self.page)


def check(interactive):
    try:
        info = plistlib.readPlist(INFO)
    except Exception:
        return  # not inside an app bundle
    key = info["CFBundleIdentifier"].split(".")[-1]
    name, have = info.get("CFBundleName", key), info.get("CFBundleShortVersionString", "0")
    defaults = NSUserDefaults.standardUserDefaults()
    url = defaults.stringForKey_("LionKitUpdatesURL") or URL

    def done(data, error):
        if error:
            if interactive:
                show(u"%s couldn\u2019t check for updates." % name,
                     u"The update information didn\u2019t load (%s). Please try again later." % error, None, True)
            return
        entry = (data or {}).get(key) or {}
        if version_tuple(entry.get("version")) > version_tuple(have):
            details = u"%s %s is out, and you have %s. %s" % (name, entry["version"], have, entry.get("notes") or u"")
            if show(u"A new version of %s is available." % name, details.strip(), entry.get("page"), interactive):
                defaults.setDouble_forKey_(time.time(), LAST_CHECK)
        else:
            defaults.setDouble_forKey_(time.time(), LAST_CHECK)
            if interactive:
                show(u"%s is up to date." % name, u"Version %s is the newest version." % have, None, True)

    cocoa.in_background(lambda: fetch(url), done)


def fetch(url):
    if url.startswith("file://"):  # for testing; curl reports no HTTP status for files
        return json.load(open(url[len("file://"):]))
    return http.get_json(url, timeout=20)


def show(message, details, page, interactive):
    """A sheet on the front window. Automatic checks never interrupt another sheet or pop up a
    window-less alert; they return False and try again later."""
    alert = NSAlert.alloc().init()
    alert.setMessageText_(message)
    alert.setInformativeText_(details)
    if page:
        alert.addButtonWithTitle_(u"Download")
        alert.addButtonWithTitle_(u"Not Now")
    updater = _updater[0]
    updater.page = page
    window = NSApp().mainWindow() or NSApp().keyWindow()
    if not window:
        visible = [w for w in NSApp().windows() if w.isVisible() and w.canBecomeMainWindow()]
        window = visible[0] if visible else None
    if window and not window.attachedSheet():
        alert.beginSheetModalForWindow_modalDelegate_didEndSelector_contextInfo_(
            window, updater, "alertDidEnd:returnCode:contextInfo:", 0)
        return True
    if interactive:
        updater.alertDidEnd_returnCode_contextInfo_(alert, alert.runModal(), 0)
        return True
    return False


def install(app_menu, index):
    """Add "Check for Updates…" at index in the app menu; release builds also check daily."""
    if not _updater:
        _updater.append(Updater.alloc().init())
        if http.LIONKIT == http.BUNDLED:
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                10.0, _updater[0], "autoCheck:", None, False)
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                3600.0, _updater[0], "autoCheck:", None, True)
    item = app_menu.insertItemWithTitle_action_keyEquivalent_atIndex_(
        u"Check for Updates…", "checkForUpdates:", "", index)
    item.setTarget_(_updater[0])
