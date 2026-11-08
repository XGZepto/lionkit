# -*- coding: utf-8 -*-
"""The sheet shown when Spotify won't let an account use Kassett's own Spotify app.

Kassett's app is in Spotify's Development Mode, which only works for accounts its owner has added
by hand. Anyone else can create a free Spotify app of their own and give Kassett its Client ID."""
import re

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403

from lionkit import spotify

DASHBOARD = "https://developer.spotify.com/dashboard"
W = 500
SHORT, TALL = 168, 386


def label(view, frame, text, bold=False, size=11, selectable=False):
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(selectable)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    f.cell().setWraps_(True)
    f.setStringValue_(text)
    view.addSubview_(f)
    return f


def button(view, frame, title, target, action, key=None):
    b = NSButton.alloc().initWithFrame_(frame)
    b.setBezelStyle_(NSRoundedBezelStyle)
    b.setTitle_(title)
    b.setTarget_(target)
    b.setAction_(action)
    if key is not None:
        b.setKeyEquivalent_(key)
    view.addSubview_(b)
    return b


class OwnAppSheet(NSObject):
    def initWithApp_(self, app):
        self = super(OwnAppSheet, self).init()
        if self is None:
            return None
        self.app = app
        self.sheet = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, SHORT), NSTitledWindowMask, NSBackingStoreBuffered, False)
        self.sheet.setReleasedWhenClosed_(False)
        self.intro = self.buildIntro()
        self.guide = self.buildGuide()
        return self

    def page(self, height):
        v = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, height))
        icon = NSImageView.alloc().initWithFrame_(NSMakeRect(24, height - 20 - 64, 64, 64))
        icon.setImage_(NSImage.imageNamed_(NSImageNameApplicationIcon))
        v.addSubview_(icon)
        return v

    def buildIntro(self):
        v = self.page(SHORT)
        x, w = 104, W - 104 - 20
        label(v, NSMakeRect(x, SHORT - 38, w, 18), u"Spotify won’t let this account use Kassett yet", True, 13)
        label(v, NSMakeRect(x, SHORT - 112, w, 70),
              u"Kassett’s own Spotify app is in Spotify’s Development Mode, so it only works for a short "
              u"list of accounts. You can make a free Spotify app of your own in a few minutes, and Kassett will "
              u"use it instead. The account that makes the app needs Spotify Premium.")
        button(v, NSMakeRect(W - 20 - 210, 14, 210, 32), u"Use My Own Spotify App…", self, "showGuide:", u"\r")
        button(v, NSMakeRect(W - 20 - 210 - 110, 14, 110, 32), u"Not Now", self, "cancel:", u"\x1b")
        return v

    def buildGuide(self):
        v = self.page(TALL)
        x, w = 104, W - 104 - 20

        def top(y, h):
            return NSMakeRect(x, TALL - y - h, w, h)
        label(v, top(20, 18), u"Use your own Spotify app", True, 13)
        label(v, top(44, 30), u"1. Open the Spotify Developer Dashboard, log in with your Spotify account and "
                              u"click Create app.")
        button(v, NSMakeRect(x - 6, TALL - 106, 170, 32), u"Open the Dashboard", self, "openDashboard:")
        label(v, top(112, 44), u"2. Give the app any name and description. Under Redirect URIs, add this address, "
                               u"tick Web API, agree to Spotify’s terms and click Save.")
        uri = NSTextField.alloc().initWithFrame_(top(160, 22))
        uri.setFrameSize_(NSMakeSize(w - 90, 22))
        uri.setStringValue_(spotify.REDIRECT_URI)
        uri.setEditable_(False)
        uri.setSelectable_(True)
        uri.setFont_(NSFont.userFixedPitchFontOfSize_(11))
        v.addSubview_(uri)
        button(v, NSMakeRect(x + w - 84, TALL - 160 - 26, 86, 28), u"Copy", self, "copyURI:")
        label(v, top(196, 30), u"3. Open the new app’s Settings, copy its Client ID and paste it here.")
        label(v, top(234, 17), u"Client ID:")
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(x + 64, TALL - 234 - 20, w - 64, 22))
        field.cell().setPlaceholderString_(u"32 letters and digits")
        field.setDelegate_(self)
        v.addSubview_(field)
        self.field = field
        self.problem = label(v, top(262, 30), u"")
        self.problem.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.75, 0.25, 0.1, 1))
        label(v, top(290, 30), u"The Client ID isn’t a secret. Kassett keeps it in its preferences, and your "
                               u"login stays in this Mac’s keychain.").setTextColor_(NSColor.grayColor())
        self.saveButton = button(v, NSMakeRect(W - 20 - 160, 14, 160, 32), u"Save and Log In", self, "save:", u"\r")
        self.saveButton.setEnabled_(False)
        button(v, NSMakeRect(W - 20 - 160 - 100, 14, 100, 32), u"Cancel", self, "cancel:", u"\x1b")
        return v

    def showFor(self, window):
        if self.sheet.isVisible():
            return
        self.sheet.setContentView_(self.intro)
        self.sheet.setContentSize_(NSMakeSize(W, SHORT))
        NSApp.beginSheet_modalForWindow_modalDelegate_didEndSelector_contextInfo_(self.sheet, window, None, None, None)

    def showGuide_(self, sender):
        frame = self.sheet.frame()
        grow = TALL - SHORT
        self.sheet.setContentView_(NSView.alloc().initWithFrame_(NSMakeRect(0, 0, W, SHORT)))
        self.sheet.setFrame_display_animate_(NSMakeRect(frame.origin.x, frame.origin.y - grow, frame.size.width,
                                                        frame.size.height + grow), True, True)
        self.sheet.setContentView_(self.guide)
        self.field.setStringValue_(self.app.customClientID())
        self.controlTextDidChange_(None)
        self.sheet.makeFirstResponder_(self.field)

    def controlTextDidChange_(self, note):
        text = self.field.stringValue().strip()
        valid = bool(re.match(r"^[0-9a-fA-F]{32}$", text))
        self.saveButton.setEnabled_(valid)
        self.problem.setStringValue_(u"" if valid or not text else
                                     u"A Client ID is 32 letters and digits, like the one on the app’s Settings page.")

    def openDashboard_(self, sender):
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(DASHBOARD))

    def copyURI_(self, sender):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.writeObjects_([spotify.REDIRECT_URI])

    def close(self):
        NSApp.endSheet_(self.sheet)
        self.sheet.orderOut_(None)

    def cancel_(self, sender):
        self.close()

    def save_(self, sender):
        self.app.defaults.setObject_forKey_(self.field.stringValue().strip(), "clientID")
        self.close()
        self.app.logIn_(None)
