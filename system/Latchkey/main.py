# -*- coding: utf-8 -*-
"""Latchkey: keeps a Lion Mac on Wi-Fi networks that offer WPA2 and WPA3 together.

Lion files such "transition" networks under WPA2 Enterprise and won't join them. Latchkey lives in
the menu bar: choose the network, type its password once (it goes into the login keychain), and
Latchkey joins it with plain WPA2. Whenever the Mac drops off Wi-Fi and Lion doesn't get it back,
Latchkey rejoins a remembered network. It leaves the Mac alone while Wi-Fi is off or on another
network.

For screenshots without real network names: `defaults write page.zepto.latchkey Demo -bool YES`
(see README.md for the other demo settings)."""
from __future__ import print_function

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403
from PyObjCTools import AppHelper

from lionkit import cocoa, keychain
import art
import wifi

APP_NAME = "Latchkey"
SERVICE = "Latchkey"  # keychain service; the account is the network name
POLL = 5.0           # seconds between status checks (no scanning)
SETTLE = 8           # after a drop, a wake or Wi-Fi coming on, give Lion this long to rejoin by itself
RETRY = 30           # seconds between searches while no remembered network is in range
BACKOFF = (30, 60, 120, 300)  # after 1, 2, 3, 4+ failed joins in a row
MENU_W = 290
ROW_H = 19
NO_PASSWORD = 3


def log(*parts):
    # stdout is a log file, so Python 2 would encode unicode as ASCII and fail on a curly quote
    parts = [p.encode("utf-8") if isinstance(p, unicode) else p for p in parts]
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *parts)
    sys.stdout.flush()


def rgb(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def q(name):
    return u"“%s”" % name


def names_text(names):
    if len(names) == 1:
        return q(names[0])
    if len(names) == 2:
        return u"%s or %s" % (q(names[0]), q(names[1]))
    return u"your networks"


def in_words(seconds):
    if seconds < 45:
        return u"in a moment" if seconds < 10 else u"in %d seconds" % (int(math.ceil(seconds / 5.0)) * 5)
    minutes = int(round(seconds / 60.0))
    return u"in a minute" if minutes <= 1 else u"in %d minutes" % minutes


def failure_text(code):
    if code == wifi.NOT_FOUND:
        return u"The network isn't in range."
    if code == wifi.NO_WPA2:
        return u"Its access points only offer WPA3, which Lion can't use."
    if code == NO_PASSWORD:
        return u"Latchkey doesn't have its password."
    if code in (-3905, -3912, -3924, -3925):
        return u"The password may be wrong, or the signal is too weak."
    if code == -3930:
        return u"Lion didn't allow it. Network preferences may ask for an administrator to change networks."
    return u"Lion reported error %s." % code


def password_ok(kind, password):
    if kind in (wifi.WPA, wifi.TRANSITION):
        if len(password) == 64:
            return all(c in u"0123456789abcdefABCDEF" for c in password)
        return 8 <= len(password) <= 63
    if kind == wifi.WEP:
        return len(password) > 0
    return True


def text_height(text, font, width):
    s = NSAttributedString.alloc().initWithString_attributes_(text, {NSFontAttributeName: font})
    return math.ceil(s.boundingRectWithSize_options_(NSMakeSize(width, 1000), NSStringDrawingUsesLineFragmentOrigin).size.height)


def draw_text(text, rect, font, color, align=NSLeftTextAlignment, truncate=True):
    para = NSMutableParagraphStyle.alloc().init()
    para.setAlignment_(align)
    if truncate:
        para.setLineBreakMode_(NSLineBreakByTruncatingTail)
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color, NSParagraphStyleAttributeName: para}
    NSAttributedString.alloc().initWithString_attributes_(text, attrs).drawInRect_(rect)


# ---- remembered networks and login items ----------------------------------------------------------
class Store(object):
    """Remembered networks: their names in the app's defaults, their passwords in the login keychain."""

    def __init__(self, defaults):
        self.d = defaults

    def networks(self):
        return [unicode(n) for n in (self.d.arrayForKey_("Networks") or [])]

    def password(self, ssid):
        return keychain.get(SERVICE, ssid)

    def remember(self, ssid, password):
        keychain.set(SERVICE, ssid, password)
        names = self.networks()
        if ssid not in names:
            self.d.setObject_forKey_(names + [ssid], "Networks")
        self.set_verified(ssid, False)

    def forget(self, ssid):
        keychain.delete(SERVICE, ssid)
        self.d.setObject_forKey_([n for n in self.networks() if n != ssid], "Networks")
        self.set_verified(ssid, False)

    def verified(self, ssid):
        return ssid in [unicode(n) for n in (self.d.arrayForKey_("Verified") or [])]

    def set_verified(self, ssid, yes=True):
        names = [unicode(n) for n in (self.d.arrayForKey_("Verified") or []) if n != ssid]
        self.d.setObject_forKey_(names + [ssid] if yes else names, "Verified")


class DemoStore(Store):
    """The demo's remembered network ("Juniper", password "demo"), kept in memory only."""

    def __init__(self, state):
        self.saved = {} if state == "fresh" else {u"Juniper": u"demo"}
        self.checked = set([u"Juniper"]) if state == "connected" else set()

    def networks(self):
        return sorted(self.saved)

    def password(self, ssid):
        return self.saved.get(ssid)

    def remember(self, ssid, password):
        self.saved[ssid] = password
        self.checked.discard(ssid)

    def forget(self, ssid):
        self.saved.pop(ssid, None)
        self.checked.discard(ssid)

    def verified(self, ssid):
        return ssid in self.checked

    def set_verified(self, ssid, yes=True):
        (self.checked.add if yes else self.checked.discard)(ssid)


class LoginItems(object):
    """The app's entry in System Preferences > Users & Groups > Login Items."""

    def __init__(self):
        self.path = NSBundle.mainBundle().bundlePath()

    def _find(self):
        import LaunchServices as LS
        items = LS.LSSharedFileListCreate(None, LS.kLSSharedFileListSessionLoginItems, None)
        snapshot, _ = LS.LSSharedFileListCopySnapshot(items, None)
        for item in snapshot or []:
            resolved = LS.LSSharedFileListItemResolve(item, 3, None, None)  # no UI, don't mount volumes
            err, url = resolved[0], resolved[1]
            if err == 0 and url is not None and url.path() == self.path:
                return LS, items, item
        return LS, items, None

    def enabled(self):
        try:
            return self._find()[2] is not None
        except Exception as e:
            log("can't read login items:", e)
            return False

    def set(self, on):
        LS, items, item = self._find()
        if on and item is None:
            LS.LSSharedFileListInsertItemURL(items, LS.kLSSharedFileListItemLast, None, None,
                                             NSURL.fileURLWithPath_(self.path), None, None)
        elif not on and item is not None:
            LS.LSSharedFileListItemRemove(items, item)


class DemoLoginItems(object):
    def __init__(self):
        self.on = True

    def enabled(self):
        return self.on

    def set(self, on):
        self.on = on


# ---- menu views -----------------------------------------------------------------------------------
TITLE_FONT = NSFont.menuFontOfSize_(14)
DETAIL_FONT = NSFont.systemFontOfSize_(11)


class StatusView(NSView):
    """The menu's first row: a status light (or a spinner), what's happening, and what's next."""

    def initWithFrame_(self, frame):
        self = super(StatusView, self).initWithFrame_(frame)
        if self:
            self.light, self.title, self.detail, self.busy = "gray", u"", u"", False
            self.spinner = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(5, 0, 12, 12))
            self.spinner.setStyle_(NSProgressIndicatorSpinningStyle)
            self.spinner.setControlSize_(NSMiniControlSize)
            self.spinner.setDisplayedWhenStopped_(False)
            self.spinner.setUsesThreadedAnimation_(True)
            self.addSubview_(self.spinner)
            self.setAutoresizingMask_(NSViewWidthSizable)
        return self

    def show(self, light, title, detail, busy):
        if (light, title, detail, busy) == (self.light, self.title, self.detail, self.busy):
            return
        self.light, self.title, self.detail, self.busy = light, title, detail, busy
        w = self.frame().size.width
        dh = text_height(detail, DETAIL_FONT, w - 21 - 14) if detail else 0
        h = 4 + 18 + (dh + 1 if detail else 0) + 4
        self.setFrameSize_(NSMakeSize(w, h))
        self.spinner.setFrameOrigin_(NSMakePoint(5, h - 4 - 15))
        if busy:
            self.spinner.startAnimation_(None)
        else:
            self.spinner.stopAnimation_(None)
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        w, h = self.bounds().size.width, self.bounds().size.height
        if not self.busy:
            art.draw_image(art.status_light(self.light), 6, h - 4 - 15)
        draw_text(self.title, NSMakeRect(21, h - 4 - 18, w - 21 - 14, 18), TITLE_FONT, NSColor.controlTextColor())
        if self.detail:
            draw_text(self.detail, NSMakeRect(21, 4, w - 21 - 14, h - 4 - 18 - 4), DETAIL_FONT,
                      NSColor.disabledControlTextColor(), truncate=False)


class NetworkRow(NSView):
    """One network, laid out like Lion's Wi-Fi menu: checkmark, name, lock, signal fan."""

    def initWithFrame_(self, frame):
        self = super(NetworkRow, self).initWithFrame_(frame)
        if self:
            self.network, self.current, self.owner, self.preview_highlight = None, False, None, False
            self.setAutoresizingMask_(NSViewWidthSizable)
        return self

    def highlighted(self):
        item = self.enclosingMenuItem()
        on = item.isHighlighted() if item is not None else self.preview_highlight
        return bool(on) and self.network.joinable

    def drawRect_(self, rect):
        n, hl = self.network, self.highlighted()
        w, h = self.bounds().size.width, self.bounds().size.height
        if hl:
            NSColor.selectedMenuItemColor().set()
            NSRectFill(self.bounds())
        if hl:
            ink = NSColor.selectedMenuItemTextColor()
        else:
            ink = NSColor.controlTextColor() if n.joinable else NSColor.disabledControlTextColor()
        x = w - 14 - 16
        art.draw_image(art.signal_fan(wifi.bars(n.rssi), hl, n.joinable), x, 4)
        if n.secure:
            x -= 6 + 9
            art.draw_image(art.lock(hl, n.joinable), x, 4)
        if not n.joinable:
            reason = u"WPA3 only" if n.kind == wifi.WPA3 else u"Enterprise"
            rw = 70
            x -= 6 + rw
            draw_text(reason, NSMakeRect(x, 2, rw, 14), DETAIL_FONT, NSColor.disabledControlTextColor(), NSRightTextAlignment)
        if self.current:
            draw_text(u"✓", NSMakeRect(5, 0, 16, 18), TITLE_FONT, ink)
        draw_text(n.ssid, NSMakeRect(21, 0, x - 8 - 21, 18), TITLE_FONT, ink)

    def mouseUp_(self, event):
        item = self.enclosingMenuItem()
        if item is None or not self.network.joinable:
            return
        item.menu().cancelTracking()
        self.owner.performSelector_withObject_afterDelay_("chooseNetwork:", self.network.ssid, 0.0)


# ---- the join dialog ------------------------------------------------------------------------------
def label(text, frame, font, wraps=False):
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setFont_(font)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    if wraps:
        f.cell().setWraps_(True)
    else:
        f.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    return f


def checkbox(title, frame, target, action):
    b = NSButton.alloc().initWithFrame_(frame)
    b.setButtonType_(NSSwitchButton)
    b.setTitle_(title)
    b.setTarget_(target)
    b.setAction_(action)
    return b


def panel_text(mode, ssid, kind):
    if mode == "other":
        return (u"Find and join a Wi-Fi network.",
                u"Enter the network's name and password. Latchkey also finds networks that hide their name.")
    if mode == "save":
        return (u"This Mac is already on %s." % q(ssid),
                u"Enter the network's password, and Latchkey will use it to rejoin whenever the connection "
                u"drops. The password is kept in your keychain.")
    if mode == "retry":
        return (u"Latchkey couldn't join %s." % q(ssid),
                u"Enter the network's password again. Latchkey keeps the new password in your keychain "
                u"once it works.")
    if kind == wifi.TRANSITION:
        return (u"%s uses WPA2 and WPA3, which Lion can't join on its own." % q(ssid),
                u"Enter the network's password, and Latchkey will join it with WPA2 now and rejoin it "
                u"whenever the connection drops. The password is kept in your keychain.")
    return (u"The Wi-Fi network %s requires a password." % q(ssid),
            u"Latchkey will join it now and rejoin it whenever the connection drops. The password is "
            u"kept in your keychain.")


class JoinPanel(NSObject):
    """Lion's "requires a WPA2 password" dialog, with a status line for the join underneath."""

    def setup(self, owner, mode, ssid, kind):
        self.owner, self.mode, self.ssid, self.kind = owner, mode, ssid, kind
        W, x0, labelW = 456, 104, (100 if mode == "other" else 70)
        tw = W - x0 - 20
        message, info = panel_text(mode, ssid, kind)
        bold = NSFont.boldSystemFontOfSize_(13)
        small = NSFont.systemFontOfSize_(11)
        mh = text_height(message, bold, tw - 4)
        ih = text_height(info, small, tw - 4)
        fields = 2 if mode == "other" else 1
        self.ask_login = not owner.login_items.enabled()
        boxes = 2 if self.ask_login else 1
        H = 20 + mh + 6 + ih + 14 + fields * 30 + boxes * 22 + 8 + 22 + 8 + 32 + 12

        self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), NSTitledWindowMask, NSBackingStoreBuffered, True)
        self.window.setTitle_(u"")
        self.window.setHidesOnDeactivate_(False)
        self.window.setReleasedWhenClosed_(False)
        v = self.window.contentView()

        icon = NSImageView.alloc().initWithFrame_(NSMakeRect(24, H - 15 - 64, 64, 64))
        icon.setImage_(NSApp.applicationIconImage())
        v.addSubview_(icon)
        y = H - 20 - mh
        v.addSubview_(label(message, NSMakeRect(x0, y, tw, mh), bold, True))
        y -= 6 + ih
        v.addSubview_(label(info, NSMakeRect(x0, y, tw, ih), small, True))
        y -= 14

        fx, fw = x0 + labelW + 6, W - 20 - (x0 + labelW + 6)
        regular = NSFont.systemFontOfSize_(13)
        self.nameField = None
        if mode == "other":
            y -= 22
            name = label(u"Network Name:", NSMakeRect(x0, y + 2, labelW, 17), regular)
            name.setAlignment_(NSRightTextAlignment)
            v.addSubview_(name)
            self.nameField = NSTextField.alloc().initWithFrame_(NSMakeRect(fx, y, fw, 22))
            self.nameField.setDelegate_(self)
            v.addSubview_(self.nameField)
            y -= 8
        y -= 22
        pl = label(u"Password:", NSMakeRect(x0, y + 2, labelW, 17), regular)
        pl.setAlignment_(NSRightTextAlignment)
        v.addSubview_(pl)
        self.secret = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(fx, y, fw, 22))
        self.plain = NSTextField.alloc().initWithFrame_(NSMakeRect(fx, y, fw, 22))
        self.plain.setHidden_(True)
        for f in (self.secret, self.plain):
            f.setDelegate_(self)
            v.addSubview_(f)
        y -= 8 + 22
        self.showBox = checkbox(u"Show password", NSMakeRect(fx - 2, y, fw, 18), self, "toggleShow:")
        v.addSubview_(self.showBox)
        self.loginBox = None
        if self.ask_login:
            y -= 22
            self.loginBox = checkbox(u"Open Latchkey at login", NSMakeRect(fx - 2, y, fw, 18), None, None)
            self.loginBox.setState_(NSOnState)
            v.addSubview_(self.loginBox)

        self.spinner = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(x0, 56, 16, 16))
        self.spinner.setStyle_(NSProgressIndicatorSpinningStyle)
        self.spinner.setControlSize_(NSSmallControlSize)
        self.spinner.setDisplayedWhenStopped_(False)
        v.addSubview_(self.spinner)
        self.caution = NSImageView.alloc().initWithFrame_(NSMakeRect(x0, 56, 16, 16))
        self.caution.setImage_(NSImage.imageNamed_(NSImageNameCaution))
        self.caution.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.caution.setHidden_(True)
        v.addSubview_(self.caution)
        self.statusLine = label(u"", NSMakeRect(x0 + 22, 55, tw - 22, 17), small)
        v.addSubview_(self.statusLine)

        self.okButton = NSButton.alloc().initWithFrame_(NSMakeRect(W - 14 - 96, 12, 96, 32))
        self.okButton.setBezelStyle_(NSRoundedBezelStyle)
        self.okButton.setTitle_(u"Save" if mode == "save" else u"Join")
        self.okButton.setKeyEquivalent_(u"\r")
        self.okButton.setTarget_(self)
        self.okButton.setAction_("confirm:")
        v.addSubview_(self.okButton)
        self.cancelButton = NSButton.alloc().initWithFrame_(NSMakeRect(W - 14 - 96 - 96, 12, 96, 32))
        self.cancelButton.setBezelStyle_(NSRoundedBezelStyle)
        self.cancelButton.setTitle_(u"Cancel")
        self.cancelButton.setKeyEquivalent_(u"\x1b")
        self.cancelButton.setTarget_(self)
        self.cancelButton.setAction_("cancel:")
        v.addSubview_(self.cancelButton)

        first = self.nameField or self.secret
        self.window.setInitialFirstResponder_(first)
        self.validate()
        self.window.center()

    def show(self, activate):
        if activate:
            NSApp.activateIgnoringOtherApps_(True)
            self.window.makeKeyAndOrderFront_(None)
        else:
            self.window.orderFront_(None)  # behind the active app's windows: for screenshots

    def close(self):
        self.window.orderOut_(None)

    def field(self):
        return self.plain if self.showBox.state() == NSOnState else self.secret

    def target(self):
        return self.nameField.stringValue().strip() if self.nameField else self.ssid

    def validate(self):
        password = self.field().stringValue()
        ok = password_ok(self.kind, password) if self.kind else True
        if self.nameField is not None:
            ok = ok and bool(self.target())
        self.okButton.setEnabled_(ok)

    def controlTextDidChange_(self, note):
        self.validate()

    def toggleShow_(self, sender):
        old, new = (self.secret, self.plain) if sender.state() == NSOnState else (self.plain, self.secret)
        new.setStringValue_(old.stringValue())
        old.setHidden_(True)
        new.setHidden_(False)
        self.window.makeFirstResponder_(new)
        editor = new.currentEditor()
        if editor is not None:
            editor.setSelectedRange_(NSMakeRange(len(new.stringValue()), 0))

    def setBusy(self, busy, text):
        for control in (self.secret, self.plain, self.nameField, self.showBox, self.loginBox, self.okButton):
            if control is not None:
                control.setEnabled_(not busy)
        if not busy:
            self.validate()
        self.caution.setHidden_(True)
        self.statusLine.setTextColor_(NSColor.controlTextColor())
        self.statusLine.setStringValue_(text)
        if busy:
            self.spinner.startAnimation_(None)
        else:
            self.spinner.stopAnimation_(None)

    def showError(self, text):
        self.setBusy(False, text)
        self.caution.setHidden_(False)
        self.statusLine.setTextColor_(rgb(178, 74, 16))
        self.window.makeFirstResponder_(self.field())
        shake(self.window)

    def wantsLogin(self):
        return self.loginBox is not None and self.loginBox.state() == NSOnState

    def confirm_(self, sender):
        password = self.field().stringValue()
        if self.mode == "save":
            self.owner.panelSave(self, self.ssid, password)
        else:
            self.setBusy(True, u"Joining %s…" % q(self.target()))
            self.owner.panelJoin(self, self.target(), password, self.kind)

    def cancel_(self, sender):
        self.close()
        self.owner.panelClosed(self)

    def finished(self, ok, message):
        if ok:
            self.close()
            self.owner.panelClosed(self)
        else:
            self.showError(message)


def shake(window):
    """Lion's login-window "no": a quick side-to-side shake."""
    try:
        from Quartz import CAKeyframeAnimation
        o = window.frame().origin
        anim = CAKeyframeAnimation.animation()
        anim.setValues_([NSValue.valueWithPoint_(NSMakePoint(o.x + dx, o.y)) for dx in (0, -7, 7, -5, 5, -2, 0)])
        anim.setDuration_(0.4)
        window.setAnimations_({"frameOrigin": anim})
        window.animator().setFrameOrigin_(o)
    except Exception as e:
        log("no shake:", e)


# ---- the app --------------------------------------------------------------------------------------
class Latchkey(NSObject):

    def applicationDidFinishLaunching_(self, note):
        d = self.defaults = NSUserDefaults.standardUserDefaults()
        self.demo = d.boolForKey_("Demo")
        if self.demo:
            state = d.stringForKey_("DemoState") or "connected"
            self.wifi = wifi.Demo(state, d.floatForKey_("DemoJoinSeconds") or 2.5)
            self.store, self.login_items = DemoStore(state), DemoLoginItems()
        else:
            self.wifi, self.store, self.login_items = wifi.CoreWLAN(), Store(d), LoginItems()
        self.status = self.wifi.status()
        self.phase = None      # "search" or "join" while Latchkey is working
        self.target = None     # the network it's looking for or joining
        self.failure = None    # (network, message) after a failed join
        self.failures = 0      # failed joins in a row
        self.away = False      # the last search found none of the remembered networks
        self.next_try = time.time() + (2 if self.demo else SETTLE)
        self.networks = None   # the last scan, or None before the first one
        self.scanning = False
        self.scanned_at = 0
        self.menu_open = False
        self.panel = None
        self.frame = 0
        self.glyphs = {}
        self.rows = []
        self.preview_header = None
        cocoa.build_main_menu(APP_NAME, self, has_prefs=False)  # so Cmd-V works in the password field
        self.buildStatusItem()
        self.observe()
        self.addTimer(POLL, "poll:")
        self.addTimer(0.3, "animate:")
        self.refresh()
        log("started", "(demo)" if self.demo else "", "remembering %d network(s)" % len(self.store.networks()))
        if self.demo and d.stringForKey_("DebugOpen"):
            self.performSelector_withObject_afterDelay_("debugOpen:", d.stringForKey_("DebugOpen"), 1.5)

    def addTimer(self, seconds, selector):
        # Common modes, so the status keeps moving while the menu is open.
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(seconds, self, selector, None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)

    def observe(self):
        if not self.demo:
            center = NSNotificationCenter.defaultCenter()
            for name in wifi.notification_names():
                center.addObserver_selector_name_object_(self, "wifiChanged:", name, None)
        NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self, "didWake:", NSWorkspaceDidWakeNotification, None)

    def wifiChanged_(self, note):
        self.performSelectorOnMainThread_withObject_waitUntilDone_("poll:", None, False)

    def didWake_(self, note):
        self.next_try = max(self.next_try, time.time() + SETTLE)
        self.scanned_at = 0

    # ---- keeping the Mac on a remembered network ----------------------------------------------
    def poll_(self, timer):
        old, s = self.status, self.wifi.status()
        self.status = s
        if (old.ssid and not s.ssid) or (s.power and not old.power):
            self.next_try = max(self.next_try, time.time() + SETTLE)  # Lion gets the first try
        if s.ssid:
            self.away, self.failure, self.failures = False, None, 0
        self.maybeRejoin()
        self.refresh()

    def maybeRejoin(self):
        s, names = self.status, self.store.networks()
        if self.phase or not names or not (s.present and s.power) or s.ssid or s.busy:
            return
        if time.time() >= self.next_try:
            self.search(names)

    def search(self, names):
        self.phase, self.target = "search", names[0] if len(names) == 1 else None
        self.refresh()
        scan = self.wifi.scan

        def work():
            return [n for name in names for n in scan(name) if n.ssid == name and n.joinable]

        def done(found, error):
            self.phase = self.target = None
            if error is not None or not found:
                if error is not None:
                    log("search failed:", repr(error))
                self.away = error is None
                self.next_try = time.time() + RETRY
                self.refresh()
                return
            self.away = False
            self.join(max(found, key=lambda n: n.rssi).ssid, None, False, None)
        cocoa.in_background(work, done)

    def join(self, ssid, password, reconnect, panel):
        """Join in the background. A password of None means the saved one; a new one is remembered
        once the join works."""
        self.phase, self.target = "join", ssid
        self.refresh()
        store, wf = self.store, self.wifi
        log("joining", q(ssid), "(reconnect)" if reconnect else "")

        def work():
            pw = password if password is not None else store.password(ssid)
            if pw is None:
                return False, NO_PASSWORD
            return wf.join(ssid, pw or None, reconnect)

        def done(result, error):
            self.phase = self.target = None
            ok, code = result if error is None else (False, None)
            message = failure_text(code) if error is None else u"Something went wrong: %s" % error
            if ok:
                log("joined", q(ssid))
                self.failure, self.failures = None, 0
                try:
                    if password:
                        store.remember(ssid, password)
                        if panel is not None and panel.wantsLogin():
                            self.setLoginItem(True)
                    if ssid in store.networks():
                        store.set_verified(ssid)
                except Exception as e:
                    log("couldn't save the password:", e)
                    ok, message = False, u"Latchkey joined, but couldn't save the password in your keychain."
            else:
                log("couldn't join", q(ssid) + ":", code if error is None else repr(error))
                self.failures += 1
                self.next_try = time.time() + BACKOFF[min(self.failures, len(BACKOFF)) - 1]
                self.failure = (ssid, message)
            self.poll_(None)
            if panel is not None:
                panel.finished(ok, message)
        cocoa.in_background(work, done)

    # ---- what the menu bar shows --------------------------------------------------------------
    def describe(self):
        """(light, title, detail, busy) for the menu's status row."""
        s, names = self.status, self.store.networks()
        if not s.present:
            return "gray", u"No Wi-Fi hardware", u"Latchkey needs a Mac with Wi-Fi.", False
        if not s.power:
            return "gray", u"Wi-Fi is off", u"Latchkey rejoins your network once Wi-Fi is back on.", False
        if self.phase == "join":
            return "amber", u"Joining %s…" % q(self.target), u"", True
        if self.phase == "search":
            return "amber", u"Looking for %s…" % names_text(names), u"", True
        if s.ssid:
            title = u"Connected to %s" % q(s.ssid)
            if s.ssid in names:
                return "green", title, u"Latchkey rejoins it if the connection drops.", False
            if names:
                return "green", title, u"Latchkey rejoins %s when this Mac isn't on any network." % names_text(names), False
            return "green", title, u"Choose the network that Lion keeps losing, and Latchkey will rejoin it for you.", False
        when = in_words(max(0, self.next_try - time.time()))
        if self.failure:
            return "orange", u"Couldn't join %s" % q(self.failure[0]), u"%s Latchkey tries again %s." % (self.failure[1], when), False
        if s.busy:
            return "amber", u"Lion is joining a network…", u"", True
        if names and self.away:
            return "gray", u"Not connected", u"%s isn't in range. Latchkey looks again %s." % (names_text(names), when), False
        if names:
            return "gray", u"Not connected", u"Latchkey looks for %s %s." % (names_text(names), when), False
        return "gray", u"Not connected", u"Choose a network to join it.", False

    def glyph(self, lit, highlighted, dim):
        key = (lit, highlighted, dim)
        if key not in self.glyphs:
            self.glyphs[key] = art.menubar_glyph(lit, highlighted, dim)
        return self.glyphs[key]

    def busy(self):
        return bool(self.phase) or self.status.busy

    def refresh(self):
        s = self.status
        dim = not (s.present and s.power)
        if self.busy():
            lit = self.frame % 3 + 1
        else:
            lit = max(1, wifi.bars(s.rssi) - 1) if s.ssid else 0
        self.item.setImage_(self.glyph(lit, False, dim))
        self.item.setAlternateImage_(self.glyph(lit, True, dim))
        light, title, detail, busy = self.describe()
        self.item.setToolTip_(u"Latchkey: %s" % title)
        self.header.show(light, title, detail, busy)
        if self.preview_header is not None:
            self.preview_header.show(light, title, detail, busy)
            top = self.preview_header.superview().bounds().size.height - 4
            self.preview_header.setFrameOrigin_(NSMakePoint(0, top - self.preview_header.frame().size.height))
        if self.menu_open:
            for item in self.rows:
                if item.view() is not None:
                    item.view().current = item.view().network.ssid == s.ssid
                    item.view().setNeedsDisplay_(True)

    def animate_(self, timer):
        if self.busy():
            self.frame += 1
            self.refresh()

    # ---- the menu ------------------------------------------------------------------------------
    def buildStatusItem(self):
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.item.setHighlightMode_(True)
        self.menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        self.menu.setAutoenablesItems_(False)
        self.menu.setDelegate_(self)
        self.item.setMenu_(self.menu)
        self.header = StatusView.alloc().initWithFrame_(NSMakeRect(0, 0, MENU_W, 26))
        self.rebuildMenu()

    def add(self, menu, title, action, represented=None, key=u""):
        item = menu.addItemWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self)
        if represented is not None:
            item.setRepresentedObject_(represented)
        return item

    def rebuildMenu(self):
        m, s, names = self.menu, self.status, self.store.networks()
        m.removeAllItems()
        head = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(u"", None, u"")
        head.setView_(self.header)
        head.setEnabled_(False)
        m.addItem_(head)
        m.addItem_(NSMenuItem.separatorItem())
        self.rows = []
        self.rows_at = m.numberOfItems() if s.present and s.power else None
        if self.rows_at is not None:
            self.insertRows()
            m.addItem_(NSMenuItem.separatorItem())

        if self.failure and self.failure[0] in names and s.power:
            self.add(m, u"Enter Password for %s…" % q(self.failure[0]), "enterPassword:", self.failure[0])
        self.add(m, u"Join Other Network…", "joinOther:").setEnabled_(bool(s.present and s.power))
        if names:
            forget = NSMenu.alloc().initWithTitle_(u"Forget Network")
            for name in names:
                self.add(forget, name, "forget:", name)
            m.addItemWithTitle_action_keyEquivalent_(u"Forget Network", None, u"").setSubmenu_(forget)
        m.addItem_(NSMenuItem.separatorItem())
        self.add(m, u"Open at Login", "toggleLogin:").setState_(NSOnState if self.login_items.enabled() else NSOffState)
        self.add(m, u"Open Network Preferences…", "openNetworkPreferences:")
        m.addItem_(NSMenuItem.separatorItem())
        self.add(m, u"About Latchkey", "about:")
        self.add(m, u"Quit Latchkey", "terminate:", None, u"q").setTarget_(NSApp)

    def insertRows(self):
        nets = self.networks
        at = self.rows_at
        if not nets:
            text = u"Looking for networks…" if nets is None or self.scanning else u"No networks in range"
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(text, None, u"")
            item.setEnabled_(False)
            self.menu.insertItem_atIndex_(item, at)
            self.rows.append(item)
            return
        for i, n in enumerate(nets):
            row = NetworkRow.alloc().initWithFrame_(NSMakeRect(0, 0, MENU_W, ROW_H))
            row.network, row.current, row.owner = n, n.ssid == self.status.ssid, self
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(n.ssid, None, u"")
            item.setView_(row)
            item.setEnabled_(n.joinable)
            if not n.joinable:
                item.setToolTip_(u"Lion can't join networks that only offer WPA3." if n.kind == wifi.WPA3
                                 else u"Latchkey doesn't handle WPA2 Enterprise logins. Use the Wi-Fi menu.")
            self.menu.insertItem_atIndex_(item, at + i)
            self.rows.append(item)

    def replaceRows(self):
        if self.rows_at is None:
            return
        for item in self.rows:
            self.menu.removeItem_(item)
        self.rows = []
        self.insertRows()

    def menuNeedsUpdate_(self, menu):
        if menu is self.menu:
            self.rebuildMenu()

    def menuWillOpen_(self, menu):
        if menu is self.menu:
            self.menu_open = True
            self.scanIfStale()

    def menuDidClose_(self, menu):
        if menu is self.menu:
            self.menu_open = False

    def menu_willHighlightItem_(self, menu, item):
        for row in self.rows:
            if row.view() is not None:
                row.view().setNeedsDisplay_(True)

    def scanIfStale(self):
        s = self.status
        if self.scanning or self.phase or not (s.present and s.power) or time.time() - self.scanned_at < 10:
            return
        self.scanning = True

        def done(nets, error):
            self.scanning = False
            self.scanned_at = time.time()
            if error is None:
                self.networks = wifi.strongest(nets)
            else:
                log("scan failed:", repr(error))
                self.networks = self.networks or []
            if self.menu_open:
                self.replaceRows()
        cocoa.in_background(self.wifi.scan, done)

    # ---- menu actions --------------------------------------------------------------------------
    def chooseNetwork_(self, ssid):
        net = [n for n in self.networks or [] if n.ssid == ssid]
        if not net or self.phase:
            return
        net, s, names = net[0], self.status, self.store.networks()
        if ssid == s.ssid:
            if ssid not in names and net.secure:
                self.openPanel("save", ssid, net.kind)
        elif not net.secure:
            self.join(ssid, u"", False, None)
        elif ssid in names:
            self.join(ssid, None, False, None)
        else:
            self.openPanel("join", ssid, net.kind)

    def enterPassword_(self, sender):
        ssid = sender.representedObject()
        kind = [n.kind for n in self.networks or [] if n.ssid == ssid]
        self.openPanel("retry", ssid, kind[0] if kind else wifi.WPA)

    def joinOther_(self, sender):
        self.openPanel("other", None, None)

    def forget_(self, sender):
        ssid = sender.representedObject()
        alert = NSAlert.alloc().init()
        alert.setMessageText_(u"Forget %s?" % q(ssid))
        alert.setInformativeText_(u"Latchkey will stop rejoining this network and remove its password from "
                                  u"your keychain. Lion's own Wi-Fi settings stay as they are.")
        alert.addButtonWithTitle_(u"Forget")
        alert.addButtonWithTitle_(u"Cancel")
        NSApp.activateIgnoringOtherApps_(True)
        if alert.runModal() == NSAlertFirstButtonReturn:
            self.store.forget(ssid)
            if self.failure and self.failure[0] == ssid:
                self.failure = None
            log("forgot", q(ssid))
            self.refresh()

    def toggleLogin_(self, sender):
        self.setLoginItem(sender.state() != NSOnState)

    def setLoginItem(self, on):
        try:
            self.login_items.set(on)
        except Exception as e:
            log("couldn't change login items:", repr(e))

    def openNetworkPreferences_(self, sender):
        NSWorkspace.sharedWorkspace().openFile_("/System/Library/PreferencePanes/Network.prefPane")

    def about_(self, sender):
        NSApp.activateIgnoringOtherApps_(True)
        NSApp.orderFrontStandardAboutPanel_(None)

    # ---- the join dialog -----------------------------------------------------------------------
    def openPanel(self, mode, ssid, kind, activate=True):
        if self.panel is not None:
            self.panel.close()
        self.panel = JoinPanel.alloc().init()
        self.panel.setup(self, mode, ssid, kind)
        self.panel.show(activate)
        return self.panel

    def panelJoin(self, panel, ssid, password, kind):
        if self.phase:
            panel.finished(False, u"Latchkey is busy joining %s. Try again in a moment." % q(self.target or u"a network"))
            return
        self.join(ssid, password, False, panel)

    def panelSave(self, panel, ssid, password):
        try:
            self.store.remember(ssid, password)
        except Exception as e:
            log("couldn't save the password:", e)
            panel.showError(u"Latchkey couldn't save the password in your keychain.")
            return
        if panel.wantsLogin():
            self.setLoginItem(True)
        log("saved the password for", q(ssid))
        panel.finished(True, None)
        self.refresh()

    def panelClosed(self, panel):
        if self.panel is panel:
            self.panel = None

    # ---- screenshots (demo mode only) ----------------------------------------------------------
    def debugOpen_(self, what):
        what = unicode(what)
        if what == "preview":
            self.showPreview()
        elif what == "save":
            self.openPanel("save", u"Juniper", wifi.TRANSITION, False)
        elif what == "other":
            self.openPanel("other", None, None, False)
        elif what in ("join", "joining", "error"):
            p = self.openPanel("join", u"Starling 5G", wifi.TRANSITION, False)
            p.secret.setStringValue_(u"correct horse")
            p.validate()
            if what == "joining":
                p.setBusy(True, u"Joining %s…" % q(u"Starling 5G"))
            elif what == "error":
                p.showError(failure_text(-3924))

    def showPreview(self):
        """The menu's custom rows in a window, since an open menu can't be captured over SSH."""
        self.networks = wifi.strongest(self.wifi.scan())
        h = 4 + 18 + 3 * 14 + 4  # room for three lines of detail
        rows = len(self.networks)
        W, H = MENU_W, 4 + h + 12 + rows * ROW_H + 4
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), NSTitledWindowMask, NSBackingStoreBuffered, True)
        win.setTitle_(u"Menu preview")
        v = win.contentView()
        bg = NSBox.alloc().initWithFrame_(v.bounds())
        bg.setBoxType_(NSBoxCustom)
        bg.setBorderType_(NSNoBorder)
        bg.setFillColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.97))
        v.addSubview_(bg)
        header = StatusView.alloc().initWithFrame_(NSMakeRect(0, H - 4 - h, W, h))
        v.addSubview_(header)
        self.preview_header = header
        self.refresh()
        line = NSBox.alloc().initWithFrame_(NSMakeRect(0, H - 4 - h - 7, W, 1))
        line.setBoxType_(NSBoxSeparator)
        v.addSubview_(line)
        y = H - 4 - h - 12
        for i, n in enumerate(self.networks):
            y -= ROW_H
            row = NetworkRow.alloc().initWithFrame_(NSMakeRect(0, y, W, ROW_H))
            row.network, row.current, row.owner = n, n.ssid == self.status.ssid, self
            row.preview_highlight = (i == 4)
            v.addSubview_(row)
        win.center()
        win.orderFront_(None)
        self.preview = win


if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = Latchkey.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()
