# -*- coding: utf-8 -*-
"""The Up Next popover: what's playing and what Spotify will play next (GET /me/player/queue)."""
from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403

import art
import glyphs
import paint
from paint import hexc

POPOVER_MINIMAL, POPOVER_TRANSIENT, POPOVER_APP_DEFINED = 0, 1, 0   # not in PyObjC 2.3's metadata
W, H = 300, 340
LIST_TOP, FOOTER = 126, 32
ROW = 34
BLUE = hexc("#2f6fd1")


def artists_of(track):
    if track.get("type") == "episode":
        return (track.get("show") or {}).get("name") or u""
    return u", ".join(a.get("name") or u"" for a in track.get("artists") or [])


def images_of(track):
    if track.get("type") == "episode":
        return track.get("images") or (track.get("show") or {}).get("images")
    return (track.get("album") or {}).get("images")


class Flipped(NSView):
    def isFlipped(self):
        return True


class UpNextView(Flipped):
    def initWithFrame_(self, frame):
        self = super(UpNextView, self).initWithFrame_(frame)
        if self:
            self.current, self.context = None, u""
        return self

    def drawRect_(self, rect):
        # Lion's minimal popover lets the window behind show through; the list reads better opaque.
        paint.fill(paint.rounded(self.bounds(), 5), "#ffffff", "#f4f4f4")
        f13, f12b, f11, f10b = paint.ui(13, True), paint.ui(12, True), paint.ui(11), paint.ui(10, True)
        gray = "#6b6b6b"
        paint.text(u"Up Next", NSMakeRect(14, 11, 70, 18), f13, "#222222")
        if self.context:
            paint.text(u"from " + self.context, NSMakeRect(14 + paint.text_width(u"Up Next", f13) + 8, 13, 200, 16),
                       f11, gray)
        paint.text(u"NOW PLAYING", NSMakeRect(14, 34, 200, 16), f10b, gray, kern=0.6)
        t = self.current
        if t:
            cover = NSMakeRect(14, 56, 34, 34)
            img = art.shared().image(art.small(images_of(t)), self.redraw, "small")
            if img:
                paint.image(img, cover)
            else:
                art.draw_placeholder(cover, (t.get("album") or {}).get("name") or t.get("name"))
            paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(cover, -0.5, -0.5)), paint.white(0, 0.2))
            paint.text(t.get("name"), NSMakeRect(57, 57, 175, 16), f12b, "#222222")
            paint.text(artists_of(t), NSMakeRect(57, 74, 175, 15), f11, gray)
            glyphs.draw_at("now_playing", 240, 66, BLUE)
            paint.text(paint.fmt(t.get("duration_ms")), NSMakeRect(254, 65, 32, 15), f11, gray, NSRightTextAlignment)
        else:
            paint.text(u"Nothing is playing.", NSMakeRect(14, 64, 260, 16), f11, gray)
        paint.fill(NSMakeRect(0, 99, W, 1), "#e3e3e3")
        paint.text(u"NEXT", NSMakeRect(14, 108, 200, 16), f10b, gray, kern=0.6)
        paint.fill(NSMakeRect(0, H - FOOTER, W, 1), "#e3e3e3")
        paint.text(u"Right-click any song in the library and choose Add to Up Next.",
                   NSMakeRect(14, H - FOOTER + 6, W - 28, 28), paint.ui(10.5), gray, truncate=False)

    def redraw(self):
        self.setNeedsDisplay_(True)


class QueueView(Flipped):
    def initWithFrame_(self, frame):
        self = super(QueueView, self).initWithFrame_(frame)
        if self:
            self.tracks, self.selected, self.message = [], -1, u"Loading…"
        return self

    def setTracks_message_(self, tracks, message):
        self.tracks, self.message, self.selected = tracks, message, -1
        width = self.superview().frame().size.width if self.superview() else W
        self.setFrameSize_(NSMakeSize(width, max(len(tracks) * ROW, self.superview().frame().size.height
                                                 if self.superview() else 0)))
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        w = self.bounds().size.width
        if not self.tracks:
            paint.text(self.message, NSMakeRect(14, 8, w - 28, 44), paint.ui(11), "#6b6b6b", truncate=False)
            return
        first = max(0, int(rect.origin.y // ROW))
        last = min(len(self.tracks), int((rect.origin.y + rect.size.height) // ROW) + 1)
        for i in range(first, last):
            self.drawRow(i, w)

    def drawRow(self, i, w):
        t = self.tracks[i]
        y = i * ROW
        sel = i == self.selected
        if sel:
            paint.fill(NSMakeRect(0, y, w, ROW), "#5d93e0", "#2f6ac6")
        else:
            paint.fill(NSMakeRect(0, y + ROW - 1, w, 1), "#ececec")
        fg = "#ffffff" if sel else "#222222"
        cover = NSMakeRect(14, y + 4, 26, 26)
        img = art.shared().image(art.small(images_of(t)), lambda i=i: self.setNeedsDisplayInRect_(
            NSMakeRect(0, i * ROW, w, ROW)), "small")
        if img:
            paint.image(img, cover)
        else:
            art.draw_placeholder(cover, (t.get("album") or {}).get("name") or t.get("name"))
        paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(cover, -0.5, -0.5)), paint.white(0, 0.2))
        paint.text(t.get("name"), NSMakeRect(49, y + 4, w - 49 - 50, 16), paint.ui(12), fg)
        paint.text(artists_of(t), NSMakeRect(49, y + 18, w - 49 - 50, 14), paint.ui(10.5),
                   paint.white(1, 0.85) if sel else hexc("#222222", 0.75))
        paint.text(paint.fmt(t.get("duration_ms")), NSMakeRect(w - 46, y + 10, 32, 15), paint.ui(11),
                   paint.white(1, 0.9) if sel else hexc("#222222", 0.8), NSRightTextAlignment)

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        i = int(p.y // ROW)
        self.selected = i if 0 <= i < len(self.tracks) else -1
        self.setNeedsDisplay_(True)


class UpNext(NSObject):
    def initWithApp_(self, app):
        self = super(UpNext, self).init()
        if self is None:
            return None
        self.app = app
        self.view = UpNextView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, LIST_TOP, W, H - LIST_TOP - FOOTER))
        scroll.setDrawsBackground_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSNoBorder)
        scroll.setAutohidesScrollers_(True)
        self.list = QueueView.alloc().initWithFrame_(scroll.contentView().bounds())
        scroll.setDocumentView_(self.list)
        self.view.addSubview_(scroll)
        controller = NSViewController.alloc().init()
        controller.setView_(self.view)
        self.popover = NSPopover.alloc().init()
        self.popover.setContentViewController_(controller)
        self.popover.setContentSize_(NSMakeSize(W, H))
        self.popover.setAppearance_(POPOVER_MINIMAL)
        self.popover.setBehavior_(POPOVER_TRANSIENT)
        self.popover.setAnimates_(True)
        self.controller = controller
        return self

    def isShown(self):
        return self.popover.isShown()

    def toggleFrom_(self, button):
        if self.popover.isShown():
            self.popover.performClose_(None)
            return
        self.list.setTracks_message_([], u"Loading…")
        self.popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button,
                                                              NSMinYEdge if button.isFlipped() else NSMaxYEdge)
        self.app.refreshQueue()

    def show(self, current, context, queue, error):
        self.view.current, self.view.context = current, context
        self.view.setNeedsDisplay_(True)
        if error:
            self.list.setTracks_message_([], u"Spotify didn't send the queue: %s" % error)
        elif not queue:
            self.list.setTracks_message_([], u"Nothing is queued after this song.")
        else:
            self.list.setTracks_message_(queue[:30], u"")
