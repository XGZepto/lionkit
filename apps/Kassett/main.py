# -*- coding: utf-8 -*-
"""Kassett: a Spotify Connect remote for Mac OS X Lion, built like a cassette deck.

The name is Swedish for cassette (Spotify started in Stockholm). Not made by Spotify."""
import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403
import objc
from PyObjCTools import AppHelper

from lionkit import cocoa, http, spotify
import art
import deck
import glyphs
import ownapp
import upnext

APP_NAME = "Kassett"
# The app's own Spotify Developer app (PKCE, so there is no secret to hide). Development Mode apps
# only accept a few allowlisted accounts; anyone else can point the app at their own Client ID with
#   defaults write page.zepto.kassett clientID <id>
CLIENT_ID = "3109bd6cf4aa4350b77a5f8c52e153d9"
POLL_EVERY = 3        # seconds between Spotify API polls; the deck animates in between
SEEK_STEP = 15000     # REW and FF move 15 seconds
FLASH = 6             # seconds an error stays in the bottom bar
SUPPORT = os.path.expanduser("~/Library/Caches/Kassett")

# `defaults write page.zepto.kassett DebugFakeState -bool yes` shows this instead of polling Spotify,
# so the deck can be checked without touching anyone's real playback.
FAKE_STATE = {
    "is_playing": True, "progress_ms": 103000, "shuffle_state": False,
    "device": {"id": "fake", "name": u"Living Room", "type": "Speaker", "volume_percent": 64},
    "context": {"type": "album", "uri": "spotify:album:fake"},
    "item": {"id": "fake1", "uri": "spotify:track:fake1", "type": "track", "name": u"The Lion’s Roar",
             "duration_ms": 245000, "artists": [{"id": "fakeartist", "name": u"First Aid Kit"}],
             "album": {"id": "fakealbum", "name": u"The Lion’s Roar", "release_date": "2012-01-13", "images": []}},
}


def log(message):
    """A line in ~/Library/Logs/Kassett.log (stderr isn't buffered, so it shows up right away)."""
    sys.stderr.write((u"%s\n" % message).encode("utf-8"))


def describe(item):
    """Title, artist line, album, year and artwork of a track or podcast episode."""
    if item.get("type") == "episode":
        show = item.get("show") or {}
        return {"title": item.get("name") or u"", "artist": show.get("name") or u"", "album": show.get("name") or u"",
                "year": (item.get("release_date") or u"")[:4], "images": item.get("images") or show.get("images")}
    album = item.get("album") or {}
    return {"title": item.get("name") or u"",
            "artist": u", ".join(a.get("name") or u"" for a in item.get("artists") or []),
            "album": album.get("name") or u"", "year": (album.get("release_date") or u"")[:4],
            "images": album.get("images")}


def subtitle(info):
    line = info["artist"]
    if info["album"] and info["album"] != info["artist"]:
        line += u" — " + info["album"]
    if info["year"]:
        line += u" (%s)" % info["year"]
    return line


class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, note):
        self.defaults = NSUserDefaults.standardUserDefaults()
        self.client = None
        self.state = None
        self.fetched_at = 0
        self.busy = False
        self.serial = 0
        self.ticks = 0
        self.devices = []
        self.profile = None
        self.item_id = None
        self.art_url = None
        self.context_uri, self.context_name, self.context_names = None, u"", {}
        self.flash_until, self.flash_text = 0, None
        self.volume_sent = 0
        self.library = None
        self.controllable = True   # False while the playing device only obeys Spotify's own apps
        self.fake = self.defaults.boolForKey_("DebugFakeState")
        if self.defaults.boolForKey_("DebugPerf"):
            import perf
            perf.start()
        art.shared()
        self.buildMenus()
        self.deck = deck.Deck.alloc().initWithApp_(self)
        self.deck.cassette.shell = self.defaults.stringForKey_("CassetteShell") or "clear"
        self.mini = deck.Mini.alloc().initWithApp_(self)
        self.upnext = None             # built the first time it's opened (it cost 0.75 s at launch)
        for w in (self.deck.window, self.mini.window):
            w.setReleasedWhenClosed_(False)
        self.connect()
        (self.mini if self.defaults.boolForKey_("MiniMode") else self.deck).window.makeKeyAndOrderFront_(None)
        if self.fake:
            self.state, self.fetched_at = copy.deepcopy(FAKE_STATE), time.time()
            self.applyState(None, 0)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1.0, self, "tick:", None, True)
        self.tick_(None)
        self.performSelector_withObject_afterDelay_("debugOpen:", None, 1.5)
        self.performSelector_withObject_afterDelay_("warmUp:", None, 3.0)
        if self.defaults.boolForKey_("DebugProbe"):
            self.performSelector_withObject_afterDelay_("debugProbe:", None, 4)
        if self.defaults.stringForKey_("DebugSnapshot"):
            self.performSelector_withObject_afterDelay_("debugSnapshot:", None,
                                                        self.defaults.floatForKey_("DebugSnapshotDelay") or 10)

    # ---- menus -------------------------------------------------------------------------------------
    def buildMenus(self):
        cmd, opt, shift = NSCommandKeyMask, NSAlternateKeyMask, NSShiftKeyMask
        cocoa.build_main_menu(APP_NAME, self, view_items=[
            (u"Show Library", "showLibrary:", "l"),
            (u"Switch to Mini Player", "toggleMini:", "m", cmd | shift),
            (u"Show Up Next", "showUpNext:", "u", cmd | opt), None])
        main = NSApp.mainMenu()
        view = main.itemWithTitle_("View").submenu()
        shells = view.addItemWithTitle_action_keyEquivalent_(u"Cassette", None, "")
        sub = NSMenu.alloc().initWithTitle_(u"Cassette")
        for title, key in ((u"Clear", "clear"), (u"Black", "black"), (u"Smoke", "smoke"), (u"White", "white")):
            it = sub.addItemWithTitle_action_keyEquivalent_(title, "setShell:", "")
            it.setRepresentedObject_(key)
            it.setTarget_(self)
        shells.setSubmenu_(sub)

        controls = NSMenu.alloc().initWithTitle_(u"Controls")
        left, right = NSLeftArrowFunctionKey, NSRightArrowFunctionKey
        up, down = NSUpArrowFunctionKey, NSDownArrowFunctionKey
        for spec in ((u"Play", "playPause:", "", 0), None,
                     (u"Next Song", "next:", right, cmd), (u"Previous Song", "previous:", left, cmd),
                     (u"Forward 15 Seconds", "fastForward:", right, cmd | opt),
                     (u"Back 15 Seconds", "rewind:", left, cmd | opt), None,
                     (u"Volume Up", "volumeUp:", up, cmd), (u"Volume Down", "volumeDown:", down, cmd), None,
                     (u"Show Current Song in Library", "showCurrentSong:", "l", cmd | opt),
                     (u"Go to Current Artist", "showCurrentArtist:", "", 0)):
            if spec is None:
                controls.addItem_(NSMenuItem.separatorItem())
                continue
            it = controls.addItemWithTitle_action_keyEquivalent_(spec[0], spec[1], spec[2])
            it.setKeyEquivalentModifierMask_(spec[3])
            it.setTarget_(self)
        top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(u"Controls", None, "")
        top.setSubmenu_(controls)
        main.insertItem_atIndex_(top, main.indexOfItemWithTitle_("Window"))

    def validateMenuItem_(self, item):
        action = item.action()
        has_item = bool(self.item())
        if action == "playPause:":
            item.setTitle_(u"Pause" if self.isPlaying() else u"Play")
            return self.loggedIn()
        if action in ("next:", "previous:", "fastForward:", "rewind:"):
            return has_item
        if action in ("showCurrentSong:", "showCurrentArtist:"):
            return deck.song_links(self.item()) is not None
        if action in ("volumeUp:", "volumeDown:"):
            return self.volume() is not None
        if action == "toggleMini:":
            item.setTitle_(u"Switch to Cassette Deck" if self.mini.window.isVisible() else u"Switch to Mini Player")
        if action == "showUpNext:":
            return self.loggedIn()
        if action == "setShell:":
            item.setState_(NSOnState if item.representedObject() == self.deck.cassette.shell else NSOffState)
        return True

    # ---- connection & state ------------------------------------------------------------------------
    def clientID(self):
        return (self.defaults.stringForKey_("clientID") or u"").strip() or CLIENT_ID

    def customClientID(self):
        """The Client ID of the person's own Spotify app, or an empty string when they use Kassett's."""
        cid = self.clientID()
        return u"" if cid == CLIENT_ID else cid

    def connect(self):
        self.client = spotify.Spotify(self.clientID())
        self.showLoggedIn(self.loggedIn())

    def loggedIn(self):
        return self.fake or bool(self.client and self.client.logged_in)

    def item(self):
        return (self.state or {}).get("item")

    def isPlaying(self):
        return bool(self.state and self.state.get("is_playing") and self.item())

    def volume(self):
        return ((self.state or {}).get("device") or {}).get("volume_percent")

    def showLoggedIn(self, logged_in):
        self.deck.showLoggedIn(logged_in)
        if logged_in:
            self.showNothing()
            return
        self.state, self.item_id = None, None
        hint = u"Log in with your Spotify Premium account"
        if self.client and self.client.keychain_error:
            hint = u"Open Kassett from the Dock to log in"
        self.deck.setTape(APP_NAME, hint)
        self.deck.setArt(None, u"", True)
        self.deck.setPlaying(False, False)
        self.deck.setPosition(0, 0, False)
        self.deck.setStatus(u"Not logged in to Spotify")
        self.mini.show(APP_NAME, hint, 0, False, False)

    def showNothing(self):
        self.item_id = None
        self.showLinks(None)
        self.deck.setTape(u"Nothing playing", u"Pick a song in the library, or start Spotify on a device")
        self.deck.setArt(None, u"", True)
        self.deck.setPlaying(False, False)
        self.deck.setPosition(0, 0, False)
        self.deck.setVolume(None, False)
        self.mini.show(u"Nothing playing", u"Kassett", 0, False, False)
        dev = (self.state or {}).get("device")
        if dev:
            self.deck.setStatus(u"Paused on %s" % dev.get("name"), glyphs.device_glyph(dev.get("type")))
        else:
            self.deck.setStatus(u"Spotify isn’t playing on any device right now")
        if self.library:
            self.library.showState(self.state, 0)

    def showLinks(self, links):
        self.deck.setLinks(links)
        self.mini.setLinks(links)
        if self.library:
            self.library.setLinks(links)

    # ---- from the playing song into the library ----------------------------------------------------
    def followLink(self, target):
        kind, object_id, song_uri = target
        if not object_id:
            return
        self.showLibrary_(None)
        self.library.reveal_uri = song_uri
        self.library.go((kind, object_id))

    def showCurrentSong_(self, sender):
        links = deck.song_links(self.item())
        if links:
            self.followLink(links["title"])

    def showCurrentArtist_(self, sender):
        links = deck.song_links(self.item())
        if links and links["artists"]:
            self.followLink(links["artists"][0][1])

    def nowPlayingMenu(self):
        """Right-click on the cassette, the LCD or the mini player."""
        links = deck.song_links(self.item())
        if not links:
            return None
        menu = NSMenu.alloc().initWithTitle_(u"Now Playing")
        menu.setAutoenablesItems_(False)

        def add(title, target):
            item = menu.addItemWithTitle_action_keyEquivalent_(title, "followLinkItem:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(list(target))
            item.setEnabled_(bool(target[1]))
        add(u"Show in Library", links["title"])
        album_name, album_target = links["album"]
        add(u"Go to Album \u201c%s\u201d" % album_name, album_target)
        for name, target in links["artists"]:
            add(u"Go to Artist \u201c%s\u201d" % name, target)
        menu.addItem_(NSMenuItem.separatorItem())
        like = menu.addItemWithTitle_action_keyEquivalent_(u"Add to Liked Songs", "likeCurrent:", "")
        like.setTarget_(self)
        return menu

    def followLinkItem_(self, sender):
        self.followLink(tuple(sender.representedObject()))

    def likeCurrent_(self, sender):
        item = self.item()
        if not item or self.fake:
            return

        def done(_, error):
            if error:
                return self.flash(unicode(error))
            self.note(u"Added \u201c%s\u201d to Liked Songs." % item.get("name"))
        cocoa.in_background(lambda: self.client.save([item["uri"]]), done)

    def note(self, text):
        """A short message in the bottom bar (like flash, without the warning sign)."""
        self.flash_text, self.flash_until = text, time.time() + 4
        self.applyStatus()

    def estimatedProgress(self):
        item = self.item()
        if not item:
            return 0
        p = self.state.get("progress_ms") or 0
        if self.state.get("is_playing"):
            p += (time.time() - self.fetched_at) * 1000
        return min(p, item.get("duration_ms") or p)

    def tick_(self, timer):
        self.ticks += 1
        item = self.item()
        if item and self.isPlaying():
            progress = self.estimatedProgress()
            self.showPosition(progress, False)
            if self.fake and progress >= item["duration_ms"]:
                self.state["progress_ms"], self.fetched_at = 0, time.time()
            elif progress >= item.get("duration_ms", 0) - 400 and self.ticks % 2 == 0:
                self.poll()
        if self.flash_text and time.time() > self.flash_until:
            self.flash_text = None
            self.applyStatus()
        if self.ticks % POLL_EVERY == 1 or timer is None:
            self.poll()

    def poll(self):
        if self.fake or self.busy or not (self.client and self.client.logged_in):
            return
        self.busy = True
        serial = self.serial
        cocoa.in_background(self.client.now_playing, lambda state, error: self.gotState(state, error, serial))

    def pollNow_(self, _):
        self.poll()

    def gotState(self, state, error, serial):
        self.busy = False
        if serial != self.serial:
            return  # a command went out while we were asking; this answer may predate it
        if error:
            if getattr(error, "reason", None) == "NOT_ALLOWLISTED":
                return self.notAllowlisted()
            self.flash(unicode(error))
            return
        expecting = getattr(self, "expecting", None)
        if expecting:
            check, deadline, _ = expecting
            if not check(state or {}) and time.time() < deadline:
                # Spotify hasn't applied the last command yet: keep showing it and ask again shortly,
                # instead of jumping back to the old state for a moment.
                self.performSelector_withObject_afterDelay_("pollNow:", None, 0.6)
                return
            self.expecting = None
        prev_id, prev_progress = self.item_id, self.estimatedProgress()
        self.state, self.fetched_at = state, time.time()
        self.applyState(prev_id, prev_progress)

    def expect(self, check, seconds=5.0):
        """After a command, ignore Spotify's answers that don't show it yet (for up to `seconds`)."""
        self.expecting = (check, time.time() + seconds, time.time())

    def applyState(self, prev_id, prev_progress):
        item = self.item()
        if not item:
            self.showNothing()
            return
        info = describe(item)
        progress = self.estimatedProgress()
        changed = item.get("id") != prev_id
        jumped = changed or abs(progress - prev_progress) > 2500
        self.item_id = item.get("id")
        dev = self.state.get("device") or {}
        self.controllable = not dev.get("is_restricted")
        self.deck.setTape(info["title"], subtitle(info))
        self.showLinks(deck.song_links(item))
        self.deck.setPlaying(self.isPlaying(), True, self.controllable)
        self.showPosition(progress, jumped)
        if time.time() < getattr(self, "volume_hold", 0):
            dev["volume_percent"] = self.deck.wheel.volume   # Spotify hasn't caught up with the wheel yet
        self.deck.setVolume(dev.get("volume_percent"), dev.get("supports_volume", True))
        self.applyStatus()
        self.showArt(info)
        self.updateContext(item)
        if self.library:
            self.library.showState(self.state, progress)
        if changed and self.upnext and self.upnext.isShown():
            self.refreshQueue()
        if not self.devices or self.ticks % (POLL_EVERY * 5) == 1:
            self.refreshDevices()

    def showPosition(self, progress, jumped):
        item = self.item() or {}
        duration = item.get("duration_ms") or 0
        self.deck.setPosition(progress, duration, jumped)
        info = describe(item) if item else {"title": u"", "artist": u""}
        self.mini.show(info["title"], info["artist"], float(progress) / duration if duration else 0,
                       self.isPlaying(), bool(item))
        if self.library:
            self.library.showProgress(progress, duration)

    def applyStatus(self):
        if self.flash_text:
            self.deck.setStatus(self.flash_text, None)
            return
        dev = (self.state or {}).get("device") or {}
        if not self.loggedIn():
            self.deck.setStatus(u"Not logged in to Spotify")
        elif dev:
            verb = u"Playing on" if self.isPlaying() else u"Paused on"
            text = u"%s %s" % (verb, dev.get("name") or u"Spotify")
            if dev.get("is_restricted"):
                text += u". Only the Spotify app can control this device."
            self.deck.setStatus(text, glyphs.device_glyph(dev.get("type")))

    def flash(self, text):
        self.flash_text, self.flash_until = u"⚠ " + text, time.time() + FLASH
        self.applyStatus()

    def showArt(self, info):
        url = art.large(info["images"])
        self.art_url = url
        name = info["album"] or info["title"]
        img = art.shared().image(url, lambda: url == self.art_url and self.showArt(info))
        self.deck.setArt(img, name, False)

    def updateContext(self, item):
        ctx = (self.state or {}).get("context") or {}
        uri = ctx.get("uri")
        if uri == self.context_uri:
            return
        self.context_uri = uri
        kind = ctx.get("type")
        name = None
        if not uri:
            name = u""
        elif ":collection" in uri:
            name = u"Liked Songs"
        elif kind == "album":
            name = (item.get("album") or {}).get("name")
        elif kind == "show":
            name = (item.get("show") or {}).get("name")
        name = self.context_names.get(uri, name)
        if name is not None:
            self.context_name = name
            return
        self.context_name = u""
        if self.fake:
            return
        object_id = uri.split(":")[-1]
        fetch = self.client.playlist if kind == "playlist" else self.client.artist if kind == "artist" else None
        if fetch is None:
            return

        def done(obj, error):
            if obj and not error:
                self.context_names[uri] = obj.get("name") or u""
                if self.context_uri == uri:
                    self.context_name = self.context_names[uri]
        cocoa.in_background(lambda: fetch(object_id), done)

    # ---- controls ----------------------------------------------------------------------------------
    def send(self, work, poll_after):
        """Run a player command in the background, then ask Spotify for the new state."""
        self.serial += 1
        if self.fake:
            return

        def done(_, error):
            if error:
                log("command failed: %r (HTTP %s, %s)" % (error, getattr(error, "status", "?"), getattr(error, "reason", None)))
                self.flash(unicode(error))
                self.expecting = None       # it didn't happen: show Spotify's real state straight away
            self.performSelector_withObject_afterDelay_("pollNow:", None, 0.1 if error else poll_after)
        cocoa.in_background(work, done)

    def setLocalPlaying(self, playing):
        if self.state and self.item():
            self.state["progress_ms"], self.fetched_at = self.estimatedProgress(), time.time()
            self.state["is_playing"] = playing
            self.deck.setPlaying(playing, True)
            self.showPosition(self.state["progress_ms"], False)
            self.applyStatus()

    def play_(self, sender):
        if not self.loggedIn():
            return self.logIn_(sender)
        if self.isPlaying():
            self.deck.setPlaying(True, True)  # keep the latched key down
            return
        self.setLocalPlaying(True)
        self.expect(lambda s: bool(s.get("is_playing")))
        self.send(self.client.play, 0.8)

    def pause_(self, sender):
        if not self.isPlaying():
            self.deck.setPlaying(False, bool(self.item()))
            return
        self.setLocalPlaying(False)
        self.expect(lambda s: not s.get("is_playing"))
        self.send(self.client.pause, 0.8)

    def playPause_(self, sender):
        (self.pause_ if self.isPlaying() else self.play_)(sender)

    def skip(self, work, back=False):
        old_id, was_at = self.item_id, self.estimatedProgress()
        if back and was_at > 4000:      # Spotify restarts the song rather than going back one
            self.expect(lambda s: (s.get("item") or {}).get("id") != old_id or (s.get("progress_ms") or 0) < 4000)
        else:
            self.expect(lambda s: (s.get("item") or {}).get("id") != old_id)
        if self.state and self.item():
            self.state["progress_ms"], self.fetched_at = 0, time.time()
            self.showPosition(0, True)
        self.send(work, 0.9)

    def next_(self, sender):
        self.skip(self.client.next)

    def previous_(self, sender):
        self.skip(self.client.previous, True)

    def seekTo(self, ms):
        item = self.item()
        if not item:
            return
        ms = max(0, min(ms, item.get("duration_ms", 0) - 1000))
        self.state["progress_ms"], self.fetched_at = ms, time.time()
        self.showPosition(ms, True)
        self.expect(lambda s: abs((s.get("progress_ms") or 0) - ms) < 4000)
        self.send(lambda: self.client.seek(ms), 0.8)

    def rewind_(self, sender):
        self.seekTo(self.estimatedProgress() - SEEK_STEP)

    def fastForward_(self, sender):
        self.seekTo(self.estimatedProgress() + SEEK_STEP)

    def seekToFraction(self, p):
        item = self.item()
        if item:
            self.seekTo(p * item.get("duration_ms", 0))

    def volumeChanged(self, volume, final):
        dev = (self.state or {}).get("device")
        if not dev:
            return
        dev["volume_percent"] = volume
        now = time.time()
        self.volume_hold = now + 3
        if final or now - self.volume_sent > 0.4:
            self.volume_sent = now
            self.send(lambda: self.client.set_volume(volume), 1.5)

    def volumeUp_(self, sender):
        if self.volume() is not None:
            self.deck.wheel.change(self.volume() + 8, True)

    def volumeDown_(self, sender):
        if self.volume() is not None:
            self.deck.wheel.change(self.volume() - 8, True)

    def handleKey(self, event):
        """Keys the deck and the library share: space plays or pauses, arrows skip."""
        chars = event.charactersIgnoringModifiers()
        mods = event.modifierFlags() & (NSCommandKeyMask | NSAlternateKeyMask | NSControlKeyMask)
        if mods or not chars:
            return False
        if chars == u" ":
            self.playPause_(None)
        elif chars == NSRightArrowFunctionKey and self.item():
            self.next_(None)
        elif chars == NSLeftArrowFunctionKey and self.item():
            self.previous_(None)
        else:
            return False
        return True

    def showPending(self, track):
        """Show the song someone just picked right away, on the deck, the mini player and in the
        library. Spotify's own state replaces it at the next poll (or puts things back if it failed)."""
        if not track or self.fake:
            return
        item = {"id": track["id"], "uri": track["uri"], "type": "track", "name": track["name"],
                "duration_ms": track["duration"],
                "artists": [{"id": i, "name": n} for i, n in track["artists"]],
                "album": {"id": track.get("album_id"), "name": track["album"],
                          "images": [{"url": track["big"], "width": 300}] if track.get("big") else []}}
        prev_id, prev_progress = self.item_id, self.estimatedProgress()
        uri, name = track["uri"], track["name"]
        self.expect(lambda s: (s.get("item") or {}).get("uri") == uri or (s.get("item") or {}).get("name") == name)
        state = dict(self.state or {})
        state.update(item=item, is_playing=True, progress_ms=0)
        self.state, self.fetched_at = state, time.time()
        self.applyState(prev_id, prev_progress)

    def playFrom(self, context, offset_uri, uris, position, shuffle):
        """Play a list: in its Spotify context (album, playlist, Liked Songs) when there is one,
        else as a list of songs. shuffle is True, False or None to leave Spotify's setting alone."""
        if self.fake or not self.loggedIn() or not (context or uris):
            return
        client = self.client
        current = bool((self.state or {}).get("shuffle_state"))
        recent = getattr(self, "expecting", None)
        if not (recent and time.time() - recent[2] < 0.3):     # showPending didn't just set one
            old_id = self.item_id
            self.expect(lambda s: (s.get("item") or {}).get("id") != old_id or
                        ((s.get("context") or {}).get("uri") == context and bool(s.get("is_playing"))))

        def work():
            if shuffle is not None and shuffle != current:
                try:
                    client.set_shuffle(shuffle)
                except spotify.SpotifyError:
                    pass  # nothing is active yet; play below still works on the last device
            if context:
                try:
                    client.play_context(context, offset_uri)
                    return
                except spotify.SpotifyError as e:
                    if not uris or e.reason in ("PREMIUM_REQUIRED", "NO_ACTIVE_DEVICE"):
                        raise
            client.play_tracks(uris, position)
        self.send(work, 0.5)
        self.performSelector_withObject_afterDelay_("pollNow:", None, 1.6)

    def setShell_(self, sender):
        self.deck.cassette.shell = sender.representedObject()
        self.deck.cassette.setNeedsDisplay_(True)
        self.defaults.setObject_forKey_(sender.representedObject(), "CassetteShell")

    # ---- windows -----------------------------------------------------------------------------------
    def showLibrary_(self, sender):
        if self.library is None:
            import library
            self.library = library.Library.alloc().initWithApp_(self)
            self.library.showState(self.state, self.estimatedProgress())
            self.library.setLinks(deck.song_links(self.item()))
        self.library.window.makeKeyAndOrderFront_(None)

    def warmUp_(self, _):
        import library  # noqa: F401  (loading it takes about 0.4 s; better now than on the first click)

    def showDeck_(self, sender):
        if self.mini.window.isVisible():
            self.mini.window.orderOut_(None)
        self.defaults.setBool_forKey_(False, "MiniMode")
        self.deck.window.makeKeyAndOrderFront_(None)
        self.deck.ensureTimer()

    def toggleMini_(self, sender):
        if self.mini.window.isVisible():
            return self.showDeck_(sender)
        if self.upnext:
            self.upnext.popover.close()
        self.deck.window.orderOut_(None)
        self.defaults.setBool_forKey_(True, "MiniMode")
        self.mini.window.makeKeyAndOrderFront_(None)
        self.showPosition(self.estimatedProgress(), False)

    def miniClosed(self):
        self.defaults.setBool_forKey_(False, "MiniMode")

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
        if not visible:
            self.showDeck_(None)
        return True

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True

    # ---- Up Next -----------------------------------------------------------------------------------
    def showUpNext_(self, sender):
        if self.mini.window.isVisible():
            self.showDeck_(sender)
        if self.upnext is None:
            self.upnext = upnext.UpNext.alloc().initWithApp_(self)
        self.upnext.toggleFrom_(self.deck.upNextButton)

    def refreshQueue(self):
        if self.fake:
            self.upnext.show(self.item(), self.context_name or u"The Lion’s Roar", [], None)
            return

        def done(q, error):
            q = q or {}
            current = q.get("currently_playing") or self.item()
            self.upnext.show(current, self.context_name, [t for t in q.get("queue") or [] if t], error and unicode(error))
        cocoa.in_background(self.client.queue, done)

    def addToQueue(self, uri, name):
        def done(_, error):
            if error:
                self.flash(unicode(error))
            elif self.upnext and self.upnext.isShown():
                self.refreshQueue()
        cocoa.in_background(lambda: self.client.add_to_queue(uri), done)

    # ---- Spotify Connect devices -------------------------------------------------------------------
    def refreshDevices(self):
        if self.fake:
            return

        def done(devices, error):
            if not error:
                self.devices = devices or []
        cocoa.in_background(self.client.devices, done)

    def chooseDevice_(self, sender):
        menu = NSMenu.alloc().initWithTitle_(u"Devices")
        menu.setAutoenablesItems_(False)
        head = menu.addItemWithTitle_action_keyEquivalent_(u"Play On", None, "")
        head.setEnabled_(False)
        para = NSMutableParagraphStyle.alloc().init()
        para.setTabStops_([NSTextTab.alloc().initWithType_location_(NSRightTabStopType, 260)])
        devices = list(self.devices)
        active = (self.state or {}).get("device")
        if active and active.get("id") not in [d.get("id") for d in devices]:
            devices.insert(0, dict(active, is_active=True))   # Spotify leaves restricted devices out of the list
        for d in devices:
            name = d.get("name") or u"Device"
            item = menu.addItemWithTitle_action_keyEquivalent_(name, "transferTo:", "")
            if d.get("is_restricted"):
                item.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
                    name + u"\tSpotify app only", {NSFontAttributeName: NSFont.menuFontOfSize_(14), NSParagraphStyleAttributeName: para}))
            item.setTarget_(self)
            item.setRepresentedObject_(d.get("id"))
            item.setState_(NSOnState if d.get("is_active") else NSOffState)
            item.setImage_(glyphs.image(glyphs.device_glyph(d.get("type")), 16))
            item.setEnabled_(bool(d.get("id")) and not d.get("is_restricted"))
            item.setIndentationLevel_(0)
        if not devices:
            none = menu.addItemWithTitle_action_keyEquivalent_(u"No devices found", None, "")
            none.setEnabled_(False)
        menu.addItem_(NSMenuItem.separatorItem())
        hint = menu.addItemWithTitle_action_keyEquivalent_(u"Open Spotify on a device to add it", None, "")
        hint.setEnabled_(False)
        height = menu.size().height
        where = NSMakePoint(0, -height - 4) if sender.isFlipped() else NSMakePoint(0, sender.frame().size.height + height + 4)
        menu.popUpMenuPositioningItem_atLocation_inView_(None, where, sender)
        self.refreshDevices()

    def transferTo_(self, sender):
        device_id, name = sender.representedObject(), sender.title().split(u"\t")[0]
        play = self.state is None or bool(self.state.get("is_playing"))
        self.deck.setStatus(u"Switching to %s…" % name, None)
        self.expect(lambda s: (s.get("device") or {}).get("id") == device_id, 8.0)

        def done(_, error):
            if error:
                self.flash(unicode(error))
                self.expecting = None
            self.refreshDevices()
            self.performSelector_withObject_afterDelay_("pollNow:", None, 1.0)
        self.serial += 1
        cocoa.in_background(lambda: self.client.transfer(device_id, play), done)

    # ---- login -------------------------------------------------------------------------------------
    def libraryClient(self):
        if self.fake:
            import fakeclient
            return fakeclient.FakeSpotify()
        return self.client

    def logInAgain_(self, sender):
        if self.client:
            self.client.logout()
        self.showLoggedIn(False)
        self.logIn_(sender)

    def logIn_(self, sender):
        self.connect()
        self.deck.setTape(u"Logging in…", u"Finish in the browser window")
        self.mini.show(u"Logging in…", u"Finish in the browser window", 0, False, False)

        def finished(error):
            cocoa.on_main(lambda: self.loginFinished(error))

        self.client.begin_login(lambda url: NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url)), finished)

    def loginFinished(self, error):
        if error:
            self.showLoggedIn(False)
            self.deck.setTape(APP_NAME, u"Login failed: %s" % error)
        else:
            self.showLoggedIn(True)
            NSApp.activateIgnoringOtherApps_(True)
            self.checkAllowed()
        self.updateAccount()

    def checkAllowed(self):
        """A Development Mode Spotify app lets anyone log in, then refuses accounts it hasn't added."""
        def done(profile, error):
            if getattr(error, "reason", None) == "NOT_ALLOWLISTED":
                return self.notAllowlisted()
            self.profile = None
            self.poll()
            if self.library:
                self.library.reload()
            self.updateAccount()
        cocoa.in_background(self.client.me, done)

    def notAllowlisted(self):
        if self.client and self.client.logged_in:
            self.client.logout()  # the login is no use to this Spotify app
        self.state, self.profile = None, None
        self.showLoggedIn(False)
        self.deck.setTape(APP_NAME, u"This Spotify account can’t use Kassett’s app")
        self.updateAccount()
        if self.library:
            self.library.reload()
        if getattr(self, "ownApp", None) is None:
            self.ownApp = ownapp.OwnAppSheet.alloc().initWithApp_(self)
        window = NSApp.keyWindow()
        if window not in (self.deck.window, getattr(self.library, "window", None)):
            self.showDeck_(None)
            window = self.deck.window
        self.ownApp.showFor(window)

    # ---- preferences: just the Spotify account -----------------------------------------------------
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
            self.accountLabel = self.label(v, NSMakeRect(112, 80, 190, 32), NSFont.systemFontOfSize_(11))
            self.accountLabel.cell().setLineBreakMode_(NSLineBreakByWordWrapping)
            self.accountLabel.setTextColor_(NSColor.grayColor())
            self.accountButton = NSButton.alloc().initWithFrame_(NSMakeRect(304, 92, 112, 32))
            self.accountButton.setBezelStyle_(NSRoundedBezelStyle)
            self.accountButton.setTarget_(self)
            self.accountButton.setAction_("accountAction:")
            v.addSubview_(self.accountButton)
            note = self.label(v, NSMakeRect(18, 12, 404, 34), NSFont.systemFontOfSize_(11))
            note.cell().setLineBreakMode_(NSLineBreakByWordWrapping)
            note.setTextColor_(NSColor.grayColor())
            note.setStringValue_(u"Kassett plays music on your phone, speakers and computers through Spotify "
                                 u"Connect, which needs Premium. Your login stays in this Mac’s login keychain.")
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
            self.accountLabel.setStringValue_(u"Log in with your Spotify Premium account.")
            self.accountButton.setTitle_(u"Log In…")
            self.avatar.setImage_(NSImage.imageNamed_(NSImageNameUser))
            return
        self.accountButton.setTitle_(u"Log Out")
        if self.profile is None:
            self.nameLabel.setStringValue_(u"Logged in")
            self.accountLabel.setStringValue_(u"Loading your profile…")
            self.avatar.setImage_(NSImage.imageNamed_(NSImageNameUser))
            cocoa.in_background(self.loadProfile, self.gotProfile)
            return
        p = self.profile
        self.nameLabel.setStringValue_(p.get("display_name") or p.get("id") or u"Spotify user")
        if self.client.missing_scopes():
            self.accountLabel.setStringValue_(u"Log out and in again to let Kassett follow artists for you.")
        else:
            self.accountLabel.setStringValue_(u"Connected to Spotify")
        if p.get("avatar_path"):
            self.avatar.setImage_(NSImage.alloc().initWithContentsOfFile_(p["avatar_path"]))

    def loadProfile(self):
        p = self.client.me() or {}
        images = p.get("images") or []
        if images:
            if not os.path.isdir(SUPPORT):
                os.makedirs(SUPPORT)
            path = os.path.join(SUPPORT, "avatar.jpg")
            http.request("GET", art.best_url(images, 72), output_path=path)
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
        if self.library:
            self.library.reload()

    # ---- hidden hooks for checking screens from the dev machine ------------------------------------
    def debugOpen_(self, _):
        """`defaults write page.zepto.kassett DebugOpenView <view>` opens a screen at launch:
        mini, upnext, ownapp, ownapp-guide, library, or library:<liked|albums|artists|playlist|album|artist|search:text>."""
        view = self.defaults.stringForKey_("DebugOpenView")
        if not view:
            return
        if view == "mini":
            self.toggleMini_(None)
        elif view == "upnext":
            self.upnext = upnext.UpNext.alloc().initWithApp_(self)
            self.upnext.popover.setBehavior_(upnext.POPOVER_APP_DEFINED)
            self.showUpNext_(None)
        elif view.startswith("ownapp"):
            self.ownApp = ownapp.OwnAppSheet.alloc().initWithApp_(self)
            self.ownApp.showFor(self.deck.window)
            if view == "ownapp-guide":
                self.ownApp.showGuide_(None)
        elif view == "song-album":
            self.showCurrentSong_(None)
        elif view == "song-artist":
            self.showCurrentArtist_(None)
        elif view == "bench":
            self.showLibrary_(None)
            self.library.bench()
        elif view.startswith("library"):
            self.showLibrary_(None)
            if ":" in view:
                self.library.debugOpen(view.split(":", 1)[1])


    def debugProbe_(self, _):
        """Send Spotify the volume it already has and log the raw answer (no audible change)."""
        from lionkit import http
        client = self.client

        def work():
            state = client.now_playing() or {}
            vol = (state.get("device") or {}).get("volume_percent")
            client._ensure_token()
            out = ["device %s volume %s playing %s" % ((state.get("device") or {}).get("type"), vol, state.get("is_playing"))]
            if vol is not None:
                r = http.request("PUT", spotify.API + "/me/player/volume?volume_percent=%d" % vol,
                                 headers={"Authorization": "Bearer " + client.access_token}, timeout=15)
                out.append("PUT volume without body -> HTTP %s %r" % (r.status, (r.body or "")[:300]))
                r = http.request("PUT", spotify.API + "/me/player/volume?volume_percent=%d" % vol, body="",
                                 headers={"Authorization": "Bearer " + client.access_token}, timeout=15)
                out.append("PUT volume with empty body -> HTTP %s %r" % (r.status, (r.body or "")[:300]))
            for d in client.devices():
                out.append("device type=%s active=%s restricted=%s volume=%s" % (
                    d.get("type"), d.get("is_active"), d.get("is_restricted"), d.get("supports_volume")))
            out.append("active device restricted: %s" % (state.get("device") or {}).get("is_restricted"))
            return "\n".join(out)
        cocoa.in_background(work, lambda result, error: log("probe: %s %s" % (result, error)))

    def debugSnapshot_(self, _):
        """`defaults write page.zepto.kassett DebugSnapshot /tmp/kassett` makes Kassett draw its visible
        windows into PNGs (/tmp/kassett-<window>.png). This works while the screen is locked."""
        prefix = self.defaults.stringForKey_("DebugSnapshot")
        windows = [("deck", self.deck.window), ("mini", self.mini.window),
                   ("library", getattr(self.library, "window", None)),
                   ("sheet", getattr(getattr(self, "ownApp", None), "sheet", None)),
                   ("upnext", self.upnext.view.window() if self.upnext and self.upnext.isShown() else None)]
        if self.library is not None:      # how long the visible library page takes to draw, five times
            page = [p for p in (self.library.gridPage, self.library.canvasPage, self.library.list.view) if not p.isHidden()]
            if page:
                times = []
                for _ in range(5):
                    start = time.time()
                    snapshot = page[0].bitmapImageRepForCachingDisplayInRect_(page[0].bounds())
                    page[0].cacheDisplayInRect_toBitmapImageRep_(page[0].bounds(), snapshot)
                    times.append((time.time() - start) * 1000)
                log("library page draw ms: %s" % u", ".join(u"%.0f" % t for t in times))
        for name, w in windows:
            if w is None or not w.isVisible():
                continue
            view = w.contentView().superview() or w.contentView()
            rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
            view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
            rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(
                "%s-%s.png" % (prefix, name), True)
            log("snapshot %s-%s.png" % (prefix, name))


if __name__ == "__main__":
    # Python 2 lets a busy background thread (parsing Spotify's JSON, say) keep the interpreter for
    # 100 bytecodes at a time, which on a two-core Mac can leave the main thread waiting long enough
    # to stutter. Switching every 10 keeps drawing and clicks responsive.
    sys.setcheckinterval(10)
    objc.setVerbose(True)  # full tracebacks in the log for errors inside Cocoa callbacks
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()
