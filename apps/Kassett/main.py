# -*- coding: utf-8 -*-
"""Kassett: a Spotify Connect remote for Mac OS X Lion, in the style of iTunes 10.

The name is Swedish for cassette (Spotify started in Stockholm). Not made by Spotify."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403
from PyObjCTools import AppHelper

from lionkit import cocoa, http, icons, spotify

APP_NAME = "Kassett"
# The app's own Spotify Developer app (PKCE, so there is no secret to hide). Developer-mode apps only
# accept up to 25 allowlisted accounts; anyone else can point the app at their own Client ID with
#   defaults write page.zepto.kassett clientID <id>
CLIENT_ID = "3109bd6cf4aa4350b77a5f8c52e153d9"
DEVICE_ICONS = {"Computer": "computer", "Smartphone": "phone", "Tablet": "phone"}
POLL_EVERY = 3  # seconds between Spotify API polls; the LCD ticks every second in between


def rgb(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def fmt(ms):
    s = max(0, int(ms / 1000))
    return u"%d:%02d" % (s // 60, s % 60)


class LCDView(NSView):
    """The iTunes 10 status display: track, artist, progress bar and times."""

    def initWithFrame_(self, frame):
        self = super(LCDView, self).initWithFrame_(frame)
        if self:
            self.line1, self.line2 = APP_NAME, u""
            self.progress, self.duration = 0, 0
        return self

    def drawRect_(self, rect):
        b = NSInsetRect(self.bounds(), 0.5, 0.5)
        shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 6, 6)
        NSGradient.alloc().initWithStartingColor_endingColor_(rgb(247, 249, 238), rgb(214, 220, 198)).drawInBezierPath_angle_(shape, -90)
        rgb(120, 124, 110).set()
        shape.setLineWidth_(1)
        shape.stroke()
        w, h = b.size.width, b.size.height

        def centered(text, y, font, color):
            para = NSMutableParagraphStyle.alloc().init()
            para.setAlignment_(NSCenterTextAlignment)
            para.setLineBreakMode_(NSLineBreakByTruncatingTail)
            attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color, NSParagraphStyleAttributeName: para}
            NSAttributedString.alloc().initWithString_attributes_(text, attrs).drawInRect_(NSMakeRect(36, y, w - 72, 16))

        ink = rgb(40, 42, 36)
        centered(self.line1, h - 22, NSFont.boldSystemFontOfSize_(12), ink)
        centered(self.line2, h - 39, NSFont.systemFontOfSize_(11), rgb(70, 72, 64))
        if self.duration:
            track = NSMakeRect(46, 12, w - 92, 7)
            NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.18).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(track, 3.5, 3.5).fill()
            filled = NSMakeRect(track.origin.x, track.origin.y,
                                track.size.width * min(1.0, float(self.progress) / self.duration), track.size.height)
            rgb(60, 64, 54).set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(filled, 3.5, 3.5).fill()
            small = {NSFontAttributeName: NSFont.systemFontOfSize_(9.5), NSForegroundColorAttributeName: ink}
            NSAttributedString.alloc().initWithString_attributes_(fmt(self.progress), small).drawAtPoint_(NSMakePoint(10, 8))
            remain = NSAttributedString.alloc().initWithString_attributes_(u"-" + fmt(self.duration - self.progress), small)
            remain.drawAtPoint_(NSMakePoint(w - 10 - remain.size().width, 8))


class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, note):
        self.defaults = NSUserDefaults.standardUserDefaults()
        self.client = None
        self.state = None
        self.fetched_at = 0
        self.art_url = None
        self.busy = False
        self.ticks = 0
        self.devices = []
        self.profile = None
        cocoa.build_main_menu(APP_NAME, self)
        self.buildWindow()
        self.connect()
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1.0, self, "tick:", None, True)
        self.tick_(None)

    def buildWindow(self):
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 480, 170),
            NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSTexturedBackgroundWindowMask,
            NSBackingStoreBuffered, False)
        w.setTitle_(APP_NAME)
        w.setFrameAutosaveName_("KassettMain")
        if not w.setFrameUsingName_("KassettMain"):
            w.center()
        v = w.contentView()

        self.art = NSImageView.alloc().initWithFrame_(NSMakeRect(14, 14, 142, 142))
        self.art.setImageFrameStyle_(NSImageFramePhoto)
        self.art.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        v.addSubview_(self.art)

        self.lcd = LCDView.alloc().initWithFrame_(NSMakeRect(170, 82, 296, 74))
        v.addSubview_(self.lcd)

        def button(title, x, width, action):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(x, 40, width, 30))
            b.setBezelStyle_(NSTexturedRoundedBezelStyle)
            b.setTitle_(title)
            b.setTarget_(self)
            b.setAction_(action)
            v.addSubview_(b)
            return b

        self.prevButton = button(u"◀◀", 170, 46, "previous:")
        self.playButton = button(u"▶", 220, 56, "playPause:")
        self.nextButton = button(u"▶▶", 280, 46, "next:")

        self.volume = NSSlider.alloc().initWithFrame_(NSMakeRect(338, 45, 128, 21))
        self.volume.cell().setControlSize_(NSSmallControlSize)
        self.volume.setMinValue_(0)
        self.volume.setMaxValue_(100)
        self.volume.setContinuous_(False)
        self.volume.setTarget_(self)
        self.volume.setAction_("setVolume:")
        v.addSubview_(self.volume)

        self.device = NSTextField.alloc().initWithFrame_(NSMakeRect(170, 14, 252, 17))
        self.device.setBezeled_(False)
        self.device.setDrawsBackground_(False)
        self.device.setEditable_(False)
        self.device.setAlignment_(NSLeftTextAlignment)
        self.device.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        self.device.setFont_(NSFont.systemFontOfSize_(11))
        self.device.cell().setBackgroundStyle_(NSBackgroundStyleRaised)
        v.addSubview_(self.device)

        # Like iTunes 10's AirPlay button: pick which Spotify Connect device plays.
        self.airplay = NSButton.alloc().initWithFrame_(NSMakeRect(428, 10, 38, 25))
        self.airplay.setBezelStyle_(NSTexturedRoundedBezelStyle)
        self.airplay.setImage_(icons.template("airplay"))
        self.airplay.setImagePosition_(NSImageOnly)
        self.airplay.setToolTip_(u"Choose where Spotify plays")
        self.airplay.setTarget_(self)
        self.airplay.setAction_("chooseDevice:")
        v.addSubview_(self.airplay)

        self.loginButton = NSButton.alloc().initWithFrame_(NSMakeRect(220, 38, 196, 32))
        self.loginButton.setBezelStyle_(NSRoundedBezelStyle)
        self.loginButton.setTitle_(u"Log In to Spotify…")
        self.loginButton.setTarget_(self)
        self.loginButton.setAction_("logIn:")
        v.addSubview_(self.loginButton)

        self.window = w
        w.makeKeyAndOrderFront_(None)

    # ---- connection & state ----------------------------------------------------------------
    def clientID(self):
        return (self.defaults.stringForKey_("clientID") or u"").strip() or CLIENT_ID

    def connect(self):
        self.client = spotify.Spotify(self.clientID())
        self.showLoggedIn(self.client.logged_in)

    def showLoggedIn(self, logged_in):
        for control in (self.prevButton, self.playButton, self.nextButton, self.volume, self.airplay):
            control.setHidden_(not logged_in)
        self.loginButton.setHidden_(logged_in)
        if not logged_in:
            self.lcd.line1 = APP_NAME
            self.lcd.line2 = u"Log in with your Spotify Premium account"
            if self.client and self.client.keychain_error:
                self.lcd.line2 = u"Open Kassett from the Dock to log in"
            self.lcd.duration = 0
            self.lcd.setNeedsDisplay_(True)
            self.device.setStringValue_(u"")
            self.art.setImage_(NSImage.imageNamed_(NSImageNameApplicationIcon))

    def tick_(self, timer):
        self.ticks += 1
        if self.state and self.state.get("is_playing"):
            self.lcd.progress = min(self.state["progress_ms"] + (time.time() - self.fetched_at) * 1000,
                                    self.lcd.duration)
            self.lcd.setNeedsDisplay_(True)
        if self.ticks % POLL_EVERY == 1 or timer is None:
            self.poll()

    def poll(self):
        if self.busy or not (self.client and self.client.logged_in):
            return
        self.busy = True
        cocoa.in_background(self.client.now_playing, self.gotState)

    def gotState(self, state, error):
        self.busy = False
        if error:
            self.device.setStringValue_(u"⚠ %s" % error)
            return
        self.state, self.fetched_at = state, time.time()
        item = (state or {}).get("item")
        if not item:
            self.lcd.line1, self.lcd.line2, self.lcd.duration = u"Nothing playing", u"Start Spotify on your phone or speaker", 0
            self.device.setStringValue_(u"")
            self.lcd.setNeedsDisplay_(True)
            return
        artists = u", ".join(a["name"] for a in item.get("artists", []))
        album = (item.get("album") or {}).get("name", u"")
        self.lcd.line1 = item.get("name", u"")
        self.lcd.line2 = u"%s — %s" % (artists, album) if album else artists
        self.lcd.duration = item.get("duration_ms", 0)
        self.lcd.progress = state.get("progress_ms", 0)
        self.lcd.setNeedsDisplay_(True)
        self.playButton.setTitle_(u"❚❚" if state.get("is_playing") else u"▶")
        dev = state.get("device") or {}
        if dev.get("volume_percent") is not None:
            self.volume.setIntValue_(dev["volume_percent"])
        self.device.setStringValue_(u"Playing on %s" % dev.get("name", u"Spotify"))
        if not self.devices or self.ticks % (POLL_EVERY * 5) == 1:
            self.refreshDevices()
        images = (item.get("album") or {}).get("images") or []  # largest first: 640, 300, 64 px
        url = images[1]["url"] if len(images) > 1 else (images[0]["url"] if images else None)
        if url and url != self.art_url:
            self.art_url = url
            path = os.path.join(tempfile.gettempdir(), "kassett-art.jpg")
            cocoa.in_background(lambda: http.request("GET", url, output_path=path) and path, self.gotArt)

    def gotArt(self, path, error):
        if path and not error:
            self.art.setImage_(NSImage.alloc().initWithContentsOfFile_(path))

    # ---- controls ----------------------------------------------------------------------------
    def command(self, fn, arg=None):
        def done(_, error):
            if error:
                self.device.setStringValue_(u"⚠ %s" % error)
            self.performSelector_withObject_afterDelay_("pollNow:", None, 0.6)
        cocoa.in_background(lambda: fn() if arg is None else fn(arg), done)

    def pollNow_(self, _):
        self.poll()

    # ---- Spotify Connect devices -------------------------------------------------------------
    def refreshDevices(self):
        def done(devices, error):
            if not error:
                self.devices = devices or []
        cocoa.in_background(self.client.devices, done)

    def chooseDevice_(self, sender):
        menu = NSMenu.alloc().initWithTitle_(u"Devices")
        menu.setAutoenablesItems_(False)
        if not self.devices:
            note = menu.addItemWithTitle_action_keyEquivalent_(u"No devices found", None, "")
            note.setEnabled_(False)
            hint = menu.addItemWithTitle_action_keyEquivalent_(u"Open Spotify on your phone or speaker", None, "")
            hint.setEnabled_(False)
        for d in self.devices:
            item = menu.addItemWithTitle_action_keyEquivalent_(d.get("name") or u"Device", "transferTo:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(d["id"])
            item.setState_(NSOnState if d.get("is_active") else NSOffState)
            image = icons.template(DEVICE_ICONS.get(d.get("type"), "speaker")).copy()
            image.setSize_(NSMakeSize(16, 16))
            item.setImage_(image)
            item.setEnabled_(bool(d.get("id")) and not d.get("is_restricted"))
        menu.popUpMenuPositioningItem_atLocation_inView_(None, NSMakePoint(0, sender.frame().size.height + 3), sender)
        self.refreshDevices()

    def transferTo_(self, sender):
        device_id, name = sender.representedObject(), sender.title()
        play = self.state is None or bool(self.state.get("is_playing"))
        self.device.setStringValue_(u"Switching to %s\u2026" % name)

        def done(_, error):
            if error:
                self.device.setStringValue_(u"\u26a0 %s" % error)
            self.refreshDevices()
            self.performSelector_withObject_afterDelay_("pollNow:", None, 1.0)

        cocoa.in_background(lambda: self.client.transfer(device_id, play), done)

    def playPause_(self, sender):
        playing = bool(self.state and self.state.get("is_playing"))
        self.playButton.setTitle_(u"▶" if playing else u"❚❚")
        if self.state:
            self.state["is_playing"] = not playing
            self.state["progress_ms"], self.fetched_at = self.lcd.progress, time.time()
        self.command(self.client.pause if playing else self.client.play)

    def next_(self, sender):
        self.command(self.client.next)

    def previous_(self, sender):
        self.command(self.client.previous)

    def setVolume_(self, sender):
        self.command(self.client.set_volume, sender.intValue())

    def logIn_(self, sender):
        self.connect()
        self.lcd.line1, self.lcd.line2 = u"Logging in…", u"Finish in the browser window"
        self.lcd.setNeedsDisplay_(True)

        def finished(error):
            cocoa.on_main(lambda: self.loginFinished(error))

        self.client.begin_login(lambda url: NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url)), finished)

    def loginFinished(self, error):
        if error:
            self.showLoggedIn(False)
            self.lcd.line2 = u"Login failed: %s" % error
            self.lcd.setNeedsDisplay_(True)
        else:
            self.showLoggedIn(True)
            NSApp.activateIgnoringOtherApps_(True)
            self.poll()
        self.updateAccount()

    # ---- preferences: just the Spotify account ------------------------------------------------
    def showPreferences_(self, sender):
        if not getattr(self, "prefs", None):
            p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 440, 172), NSTitledWindowMask | NSClosableWindowMask, NSBackingStoreBuffered, False)
            p.setTitle_(u"Spotify Account")
            v = p.contentView()
            box = NSBox.alloc().initWithFrame_(NSMakeRect(14, 56, 412, 104))
            box.setTitlePosition_(NSNoTitle)
            v.addSubview_(box)
            self.avatar = NSImageView.alloc().initWithFrame_(NSMakeRect(28, 72, 72, 72))
            self.avatar.setImageFrameStyle_(NSImageFramePhoto)
            self.avatar.setImageScaling_(NSImageScaleProportionallyUpOrDown)
            v.addSubview_(self.avatar)
            self.nameLabel = self.label(v, NSMakeRect(112, 114, 190, 20), NSFont.boldSystemFontOfSize_(14))
            self.accountLabel = self.label(v, NSMakeRect(112, 94, 190, 17), NSFont.systemFontOfSize_(11))
            self.accountLabel.setTextColor_(NSColor.grayColor())
            self.accountButton = NSButton.alloc().initWithFrame_(NSMakeRect(304, 92, 112, 32))
            self.accountButton.setBezelStyle_(NSRoundedBezelStyle)
            self.accountButton.setTarget_(self)
            self.accountButton.setAction_("accountAction:")
            v.addSubview_(self.accountButton)
            note = self.label(v, NSMakeRect(18, 12, 404, 34), NSFont.systemFontOfSize_(11))
            note.setTextColor_(NSColor.grayColor())
            note.setStringValue_(u"Kassett plays music on your phone, speakers and computers through "
                                 u"Spotify Connect. Your login stays in this Mac\u2019s login keychain.")
            self.prefs = p
        self.updateAccount()
        self.prefs.center()
        self.prefs.makeKeyAndOrderFront_(None)

    def label(self, view, frame, font):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setFont_(font)
        f.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        view.addSubview_(f)
        return f

    def updateAccount(self):
        if not getattr(self, "prefs", None):
            return
        logged_in = bool(self.client and self.client.logged_in)
        if not logged_in:
            self.nameLabel.setStringValue_(u"Not logged in")
            self.accountLabel.setStringValue_(u"Use your Spotify Premium account")
            self.accountButton.setTitle_(u"Log In\u2026")
            self.avatar.setImage_(NSImage.imageNamed_(NSImageNameUser))
            return
        self.accountButton.setTitle_(u"Log Out")
        if self.profile is None:
            self.nameLabel.setStringValue_(u"Logged in")
            self.accountLabel.setStringValue_(u"Loading your profile\u2026")
            self.avatar.setImage_(NSImage.imageNamed_(NSImageNameUser))
            cocoa.in_background(self.loadProfile, self.gotProfile)
            return
        p = self.profile
        self.nameLabel.setStringValue_(p.get("display_name") or p.get("id") or u"Spotify user")
        plan = u"Spotify Premium" if p.get("product") == "premium" else u"Spotify Free (Premium needed)"
        if self.client.missing_scopes():
            plan = u"Log out and in again to enable new features"
        self.accountLabel.setStringValue_(plan)
        if p.get("avatar_path"):
            self.avatar.setImage_(NSImage.alloc().initWithContentsOfFile_(p["avatar_path"]))

    def loadProfile(self):
        p = self.client.me() or {}
        images = p.get("images") or []
        if images:
            path = os.path.join(tempfile.gettempdir(), "kassett-avatar.jpg")
            http.request("GET", images[0]["url"], output_path=path)
            p["avatar_path"] = path
        return p

    def gotProfile(self, profile, error):
        self.profile = profile if not error else {"display_name": u"Logged in"}
        self.updateAccount()

    def accountAction_(self, sender):
        if self.client and self.client.logged_in:
            self.logOut_(sender)
        else:
            self.logIn_(sender)

    def logOut_(self, sender):
        if self.client:
            self.client.logout()
        self.state, self.profile, self.devices = None, None, []
        self.showLoggedIn(False)
        self.updateAccount()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True


if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()
