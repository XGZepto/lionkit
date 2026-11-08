# -*- coding: utf-8 -*-
"""The library browser: a source list (Liked Songs, Albums, Artists, playlists), iTunes 10 style
track lists, album and artist grids, the artist page and search, drawn after design/kassett.

Lists load 50 rows at a time as you scroll, and only small fields are kept from each item."""
import collections
import HTMLParser
import math
import os
import random
import re
import time

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403
from Quartz import (CABasicAnimation, CALayer, CAMediaTimingFunction, CATransaction,
                    CATransform3DMakeRotation, CATransformLayer, kCAMediaTimingFunctionEaseInEaseOut)

from lionkit import cocoa, spotify
import art
import glyphs
import paint
import sides
from paint import hexc, white
import deck
from deck import INK

SIDEBAR = 210
BAR = 26
LIST_HEAD = 168
ARTIST_HEAD = 170
SORTS = [(u"Recently Added", None), (u"Title", "name"), (u"Artist", "artist"), (u"Year", "year")]
SOURCE_BLUE = hexc("#2f69c6")
_html = HTMLParser.HTMLParser()


# ---- small copies of Spotify's objects (made on background threads) ---------------------------------
def slim_track(t, album=None):
    album = album or t.get("album") or {}
    return {"uri": t.get("uri"), "id": t.get("id"), "name": t.get("name") or u"",
            "artists": [(a.get("id"), a.get("name") or u"") for a in t.get("artists") or []],
            "album": album.get("name") or u"", "album_id": album.get("id"),
            "image": art.small(album.get("images")), "big": art.large(album.get("images")), "duration": t.get("duration_ms") or 0,
            "disc": t.get("disc_number") or 1, "number": t.get("track_number"),
            "playable": t.get("is_playable", True) is not False and not t.get("is_local")}


def artist_line(t):
    return u", ".join(n for _, n in t["artists"])


def slim_album(a):
    return {"uri": a.get("uri"), "id": a.get("id"), "name": a.get("name") or u"",
            "artist": u", ".join(x.get("name") or u"" for x in a.get("artists") or []),
            "artist_id": ((a.get("artists") or [{}])[0]).get("id"),
            "year": (a.get("release_date") or u"")[:4], "image": art.large(a.get("images")),
            "images": a.get("images") or [], "total": a.get("total_tracks") or 0}


def slim_artist(a):
    return {"uri": a.get("uri"), "id": a.get("id"), "name": a.get("name") or u"",
            "image": art.best_url(a.get("images"), 160), "big": art.best_url(a.get("images"), 300)}


def clean(text):
    return _html.unescape(re.sub(r"<[^>]+>", u"", text or u"")).strip()


def slim_playlist(p, me_id):
    owner = p.get("owner") or {}
    paging = spotify.playlist_items_paging(p) or {}
    return {"uri": p.get("uri"), "id": p.get("id"), "name": p.get("name") or u"",
            "owner": owner.get("display_name") or owner.get("id") or u"", "owner_id": owner.get("id"),
            "mine": owner.get("id") == me_id or bool(p.get("collaborative")),
            "image": art.large(p.get("images")), "total": paging.get("total") or 0,
            "description": clean(p.get("description"))}


def side_rows(rows):
    """An album's songs with a header row before each side, like the track listing on a J-card."""
    album_sides = sides.split(rows)
    if len(album_sides) < 2:
        return rows
    multi_disc = len(set(r["disc"] for r in rows)) > 1
    out = []
    for side in album_sides:
        title = u"%s \u00b7 %s" % (sides.heading(side, multi_disc), paint.total_time(side["duration"]))
        out.append({"header": True, "title": title.upper(), "uri": None, "playable": False, "duration": 0,
                    "name": u"", "artists": [], "album": u""})
        out += [rows[i] for i in side["tracks"]]
    return out


def songs_and_time(rows, total):
    rows = [r for r in rows if not r.get("header")]
    n = paint.plural(total, u"song")
    if total and len(rows) >= total:
        return u"%s, %s" % (n, paint.total_time(sum(r["duration"] for r in rows)))
    return n


class LibraryFlipped(NSView):
    def isFlipped(self):
        return True


# ---- the source list ---------------------------------------------------------------------------------
class SourceCell(NSTextFieldCell):
    def drawInteriorWithFrame_inView_(self, frame, view):
        item = self.objectValue()
        if not hasattr(item, "objectForKey_"):
            return super(SourceCell, self).drawInteriorWithFrame_inView_(frame, view)
        dark = self.backgroundStyle() == NSBackgroundStyleDark
        x, y, w, h = frame.origin.x, frame.origin.y, frame.size.width, frame.size.height
        glyphs.draw(item["glyph"], NSMakeRect(x + 1, y + (h - 15) / 2.0, 15, 15),
                    NSColor.whiteColor() if dark else hexc("#5a6b80"))
        badge = item.get("badge") or u""
        bw = 0
        if badge:
            f = paint.ui(10, True)
            bw = max(16, paint.text_width(badge, f) + 12)
            pill = NSMakeRect(x + w - bw - 2, y + (h - 15) / 2.0, bw, 15)
            paint.fill(paint.rounded(pill, 7.5), white(1) if dark else hexc("#8796ab"))
            paint.text(badge, NSMakeRect(pill.origin.x, pill.origin.y + 1, bw, 13), f,
                       SOURCE_BLUE if dark else white(1), NSCenterTextAlignment)
        sh = paint.shadow(1, 1, white(0, 0.35)) if dark else None
        paint.text(item["title"], NSMakeRect(x + 23, y + (h - 16) / 2.0, w - 25 - bw - 4, 16),
                   paint.ui(12, dark), white(1) if dark else "#1d1d1d", sh=sh)


# ---- a canvas of drawn, clickable items (grids, the artist page, search results) ----------------------
PAD = 10   # room round a cached item for its shadow


def have_art(url):
    """Whether a picture is already on disk (a cheap check, so a cached tape can be redrawn once it is)."""
    return bool(url) and os.path.exists(art.path_for(url))


def draw_blank_case(r):
    """A plain empty case, shown for a moment while the real tape is drawn."""
    case = paint.rounded(r, 3)
    paint.fill(case, white(1, 0.12), white(1, 0.04))
    paint.stroke(paint.rounded(NSInsetRect(r, 0.5, 0.5), 2.5), white(1, 0.35), 1)


def case_key(e):
    a, r = e["data"], e["rect"]
    return ("case", a.get("id"), a.get("image"), int(r.size.width), int(r.size.height), have_art(a.get("image")))


def circle_key(e):
    a, r = e["data"], e["rect"]
    return ("circle", a.get("id"), int(r.size.width), int(r.size.height), have_art(a.get("image")))


class OvershootClipView(NSClipView):
    """When Lion's scrolling bounces past the top or bottom of a page, paint what would be there:
    the page's `top_fill` and `bottom_fill` (the artist photo carrying on, the walnut wall), else white."""

    def drawRect_(self, rect):
        page = self.documentView()
        height = page.frame().size.height if page else 0
        for area, fill in ((NSIntersectionRect(rect, NSMakeRect(rect.origin.x, -1e5, rect.size.width, 1e5)),
                            getattr(page, "top_fill", None)),
                           (NSIntersectionRect(rect, NSMakeRect(rect.origin.x, height, rect.size.width, 1e5)),
                            getattr(page, "bottom_fill", None))):
            if area.size.width <= 0 or area.size.height <= 0:
                continue
            if fill:
                fill(area)
            else:
                paint.fill(area, "#ffffff")


class CanvasView(LibraryFlipped):
    """Asks `builder(width)` for (items, height). Each item is a dict with a `rect`, a `draw(item,
    selected)` function and optional `click`, `double` and `menu` callbacks."""

    def initWithFrame_(self, frame):
        self = super(CanvasView, self).initWithFrame_(frame)
        if self:
            self.builder, self.nearEnd, self.backdrop = None, None, None
            self.top_fill, self.bottom_fill = None, None     # what shows past the ends when scrolling bounces
            self.items, self.selected, self.width = [], None, 0
            self.rendered = collections.OrderedDict()     # cache key -> NSImage of an item, most recent last
        return self

    def acceptsFirstResponder(self):
        return True

    def isOpaque(self):
        return True       # it paints every pixel, so the scroll view can copy what's already drawn

    def watch(self):
        clip = self.superview()
        clip.setPostsFrameChangedNotifications_(True)
        clip.setPostsBoundsChangedNotifications_(True)
        nc = NSNotificationCenter.defaultCenter()
        nc.addObserver_selector_name_object_(self, "clipResized:", NSViewFrameDidChangeNotification, clip)
        nc.addObserver_selector_name_object_(self, "clipScrolled:", NSViewBoundsDidChangeNotification, clip)

    def clipResized_(self, note):
        if int(self.superview().bounds().size.width) != self.width:
            self.rebuild()

    def clipScrolled_(self, note):
        visible = self.superview().documentVisibleRect()
        if self.nearEnd and visible.origin.y + visible.size.height > self.frame().size.height - 400:
            self.nearEnd()

    def rebuild(self):
        clip = self.superview()
        if clip is None or self.builder is None:
            return
        self.width = int(clip.bounds().size.width)
        self.items, height = self.builder(self.width)
        self.setFrameSize_(NSMakeSize(self.width, max(height, clip.bounds().size.height)))
        self.setNeedsDisplay_(True)

    def scrollToTop(self):
        self.scrollPoint_(NSMakePoint(0, 0))

    def drawRect_(self, rect):
        if self.backdrop:
            self.backdrop(rect)
        else:
            paint.fill(rect, "#ffffff")
        budget = time.time() + 0.03      # draw new tapes for at most 30 ms, the rest on the next passes
        later = []
        for it in self.items:
            r = it["rect"]
            if not NSIntersectsRect(rect, NSInsetRect(r, -PAD, -PAD)):
                continue
            key = it.get("cache") and it["cache"](it)
            if not key:
                it["draw"](it, it is self.selected)
                continue
            img = self.rendered.pop(key, None)
            if img is None:
                if time.time() > budget:
                    draw_blank_case(r)
                    later.append(r)
                    continue
                img = self.render(it)
            self.rendered[key] = img
            while len(self.rendered) > 160:
                self.rendered.popitem(last=False)
            img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                NSInsetRect(r, -PAD, -PAD), NSZeroRect, NSCompositeSourceOver, 1.0, True, None)
        if later:
            self.pending = later
            self.performSelector_withObject_afterDelay_("drawPending:", None, 0.01)

    def drawPending_(self, _):
        for r in getattr(self, "pending", []):
            self.setNeedsDisplayInRect_(NSInsetRect(r, -PAD, -PAD))
        self.pending = []

    def render(self, it):
        """Draw an item once into a bitmap the size it's shown at, shadow and all."""
        r = it["rect"]
        img = NSImage.alloc().initWithSize_(NSMakeSize(r.size.width + 2 * PAD, r.size.height + 2 * PAD))
        img.lockFocusFlipped_(True)
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(PAD - r.origin.x, PAD - r.origin.y)
        t.concat()
        it["draw"](it, False)
        img.unlockFocus()
        return img

    def itemAt(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        for it in reversed(self.items):
            if NSPointInRect(p, it["rect"]) and (it.get("click") or it.get("double") or it.get("menu")):
                return it
        return None

    def mouseDown_(self, event):
        it = self.itemAt(event)
        if it is not self.selected and it is not None and it.get("selectable"):
            if self.selected is not None:
                self.setNeedsDisplayInRect_(self.selected["rect"])
            self.selected = it
            self.setNeedsDisplayInRect_(it["rect"])
        if it is None:
            return
        if event.clickCount() == 2 and it.get("double"):
            it["double"](it)
        elif event.clickCount() == 1 and it.get("click"):
            it["click"](it)

    def menuForEvent_(self, event):
        it = self.itemAt(event)
        if it is None or not it.get("menu"):
            return None
        if it.get("selectable"):
            self.selected = it
            self.setNeedsDisplay_(True)
        return it["menu"](it)

    def keyDown_(self, event):
        lib = getattr(self, "library", None)
        if not (lib and lib.app.handleKey(event)):
            super(CanvasView, self).keyDown_(event)

    def redrawItem(self, it):
        self.setNeedsDisplayInRect_(it["rect"])


def draw_cover(rect, url, name, canvas, round_=False, caption=True, shadow=True, small=False):
    img = art.shared().image(url, lambda: canvas.setNeedsDisplayInRect_(NSInsetRect(rect, -8, -8)),
                             "small" if small else "large")
    shape = NSBezierPath.bezierPathWithOvalInRect_(rect) if round_ else NSBezierPath.bezierPathWithRect_(rect)
    if shadow:
        paint.with_shadow(paint.shadow(2, 5, white(0, 0.35)), lambda: paint.fill(shape, "#888888"))
    if img is not None:
        paint.clipped(shape, lambda: paint.image(img, rect))
    elif round_:
        art.draw_placeholder(rect, name, None, True)
        f = paint.font("Helvetica-Bold", max(10, int(rect.size.width * 0.29)), True)
        paint.text(art.initials(name), NSMakeRect(rect.origin.x, rect.origin.y + (rect.size.height - f.ascender() * 1.25) / 2,
                                                  rect.size.width, rect.size.height), f, white(1, 0.92), NSCenterTextAlignment)
    else:
        art.draw_placeholder(rect, name, name.upper() if caption else None,
                             caption_size=max(9, int(rect.size.width / 11)))
    if round_:
        paint.stroke(NSBezierPath.bezierPathWithOvalInRect_(NSInsetRect(rect, 1.5, 1.5)), white(1, 0.85),
                     3 if rect.size.width > 90 else 2)
    elif small:
        paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(rect, -0.5, -0.5)), white(0, 0.2))


CASE_RATIO = 109 / 69.0      # a Norelco cassette case standing upright, 69 x 109 mm
_bands = {}


def band_color(url, img):
    """The J-card's printed band takes the cover's average colour, darkened so white type reads."""
    if url in _bands:
        return _bands[url]
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, 1, 1, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.setCurrentContext_(ctx)
    ctx.setImageInterpolation_(NSImageInterpolationHigh)
    img.drawInRect_fromRect_operation_fraction_(NSMakeRect(0, 0, 1, 1), NSZeroRect, NSCompositeCopy, 1.0)
    NSGraphicsContext.restoreGraphicsState()
    color = rep.colorAtX_y_(0, 0).blendedColorWithFraction_ofColor_(0.38, NSColor.blackColor())
    _bands[url] = color
    return color


def draw_case(r, canvas, image=None, title=u"", artist=u"", note=u"", kind="album"):
    """A cassette in its clear plastic case, seen from the front. Albums show a printed J-card (the
    square cover above a band with the artist and title); mixtapes (playlists, Liked Songs) have a
    cream card with the name written in marker."""
    x, y, w, h = r.origin.x, r.origin.y, r.size.width, r.size.height
    case = paint.rounded(r, 3)
    paint.with_shadow(paint.shadow(3, 5, white(0, 0.5)), lambda: paint.fill(case, "#1c1c1c"))
    card = NSMakeRect(x + 5, y + 4, w - 9, h - 8)
    art = NSMakeRect(card.origin.x, card.origin.y, card.size.width, card.size.width)
    band = NSMakeRect(card.origin.x, art.origin.y + art.size.height, card.size.width, card.size.height - art.size.height)
    small = max(6.0, w / 16.0)
    img = art_image(image, canvas, NSInsetRect(r, -8, -8)) if image else None
    if kind == "album":
        if img is not None:
            paint.image(img, art)
            paint.fill(band, band_color(image, img))
        else:
            draw_cover_placeholder(art, title)
            c1 = art_palette(title)
            paint.fill(band, paint.hexc(c1).blendedColorWithFraction_ofColor_(0.38, NSColor.blackColor()))
        tx, tw = band.origin.x + 6, band.size.width - 12
        paint.text(artist.upper(), NSMakeRect(tx, band.origin.y + 6, tw, small + 4), paint.font("Helvetica-Bold", small, True),
                   white(1, 0.78), kern=0.8)
        f = paint.font("Helvetica-Bold", small * 1.45, True)
        paint.text(title, NSMakeRect(tx, band.origin.y + 8 + small, tw, band.size.height - small - 22), f, white(1), truncate=False)
        paint.text(note or u"STEREO", NSMakeRect(tx, band.origin.y + band.size.height - small - 6, tw, small + 3),
                   paint.font("Helvetica-Bold", small * 0.9, True), white(1, 0.6), NSRightTextAlignment, kern=1)
    else:
        paint.fill(card, "#f8f4e8", "#ece5d2")
        if kind == "liked":
            paint.fill(art, ("#8fb6ee", 0), ("#3a63c4", 0.6), ("#2a3f8f", 1), angle=45)
            glyphs.draw("heart", NSInsetRect(art, art.size.width * 0.3, art.size.width * 0.3), white(1))
        elif img is not None:
            paint.image(img, art)
        else:
            for ly in range(int(art.origin.y + 14), int(art.origin.y + art.size.height), 12):
                paint.fill(NSMakeRect(art.origin.x + 6, ly, art.size.width - 12, 1), paint.hexc("#466eaa", 0.25))
        paint.fill(NSMakeRect(band.origin.x, band.origin.y, band.size.width, 1), white(0, 0.12))
        for ly in range(int(band.origin.y + small * 2.6), int(band.origin.y + band.size.height - 4), int(small * 2.2)):
            paint.fill(NSMakeRect(band.origin.x + 5, ly, band.size.width - 10, 1), paint.hexc("#466eaa", 0.25))
        marker = paint.font("MarkerFelt-Wide", small * 2.0)
        paint.text(title, NSMakeRect(band.origin.x + 6, band.origin.y + small * 2.6 - marker.ascender() - 1,
                                     band.size.width - 12, small * 2.6 + 4), marker, INK)
        paint.text(note, NSMakeRect(band.origin.x + 6, band.origin.y + band.size.height - small - 6, band.size.width - 12,
                                    small + 3), paint.font("Helvetica-Bold", small * 0.9, True), "#8a8170", kern=1)
    paint.fill(NSMakeRect(x + 5, y + 4, 3, h - 8), white(0, 0.18))          # where the J-card folds round the spine

    def plastic():
        paint.fill(r, white(1, 0.10), white(1, 0.02))
        paint.gradient((white(1, 0.30), 0), (white(1, 0.06), 0.42), (white(1, 0), 0.43), (white(1, 0.04), 0.7),
                       (white(1, 0), 1)).drawInRect_angle_(r, 70)
        for i in range(3):                                                    # the grip ridges on the opening edge
            paint.fill(NSMakeRect(x + w - 4 + i, y + h * 0.3, 1, h * 0.4), white(1, 0.3) if i % 2 == 0 else white(0, 0.2))
    paint.clipped(case, plastic)
    for hy in (y + 8, y + h - 20):                                           # hinge pins on the spine side
        paint.fill(paint.rounded(NSMakeRect(x + 1, hy, 3, 12), 1.5), white(1, 0.4))
    paint.stroke(paint.rounded(NSInsetRect(r, 0.5, 0.5), 2.5), white(1, 0.45), 1)
    paint.stroke(paint.rounded(NSInsetRect(r, -0.5, -0.5), 3.5), white(0, 0.45), 1)


def art_image(url, canvas, dirty):
    return art.shared().image(url, lambda: canvas.setNeedsDisplayInRect_(dirty))


def art_palette(name):
    return art.placeholder(name)[1]


def draw_cover_placeholder(rect, name):
    art.draw_placeholder(rect, name, name.upper(), caption_size=max(8, int(rect.size.width / 10)))


# ---- the shelf -----------------------------------------------------------------------------------------
_wall = {}


def wall_color():
    """Dark walnut for the wall behind the shelves, as a pattern so it tiles cheaply."""
    if "c" not in _wall:
        def grain():
            paint.fill(NSMakeRect(0, 0, 256, 256), "#3d2716")
            rnd = random.Random(3)
            for _ in range(140):
                x = rnd.uniform(0, 256)
                paint.fill(NSMakeRect(x, 0, rnd.uniform(0.5, 2.5), 256),
                           white(1, rnd.uniform(0.01, 0.05)) if rnd.random() < 0.5 else white(0, rnd.uniform(0.03, 0.12)))
        img = NSImage.alloc().initWithSize_(NSMakeSize(256, 256))
        img.lockFocus()
        grain()
        img.unlockFocus()
        _wall["c"] = NSColor.colorWithPatternImage_(img)
    return _wall["c"]


def draw_wall(rect):
    NSGraphicsContext.currentContext().setPatternPhase_(NSMakePoint(0, 0))
    wall_color().set()
    NSBezierPath.fillRect_(rect)


def draw_board(width, y):
    """A shelf board: its lit top surface, its front edge and the shadow it casts on the wall."""
    paint.fill(NSMakeRect(0, y, width, 9), "#b37c4a", "#9a6537")
    paint.fill(NSMakeRect(0, y, width, 1), white(1, 0.35))
    paint.fill(NSMakeRect(0, y + 9, width, 13), "#7a4c28", "#55331a")
    paint.fill(NSMakeRect(0, y + 9, width, 1), white(1, 0.18))
    paint.fill(NSMakeRect(0, y + 22, width, 12), white(0, 0.55), white(0, 0))


def draw_pill(rect, title, blue, pressed=False):
    shape = paint.rounded(rect, rect.size.height / 2.0)
    if blue:
        paint.fill(shape, "#24509a")
        inner = paint.rounded(NSInsetRect(rect, 1, 1), rect.size.height / 2.0 - 1)
        paint.fill(inner, ("#4a86d4" if pressed else "#5d9ae6", 0), ("#2c6bcc", 0.5), ("#1d58b8", 0.51), ("#3a78d6", 1))
        paint.clipped(inner, lambda: paint.fill(NSMakeRect(rect.origin.x, rect.origin.y + 1, rect.size.width, 1),
                                                white(1, 0.45)))
        color, sh = white(1), paint.shadow(-1, 0, white(0, 0.35))
    else:
        paint.fill(shape, "#9a9a9a")
        inner = paint.rounded(NSInsetRect(rect, 1, 1), rect.size.height / 2.0 - 1)
        paint.fill(inner, "#dcdcdc" if pressed else "#ffffff", "#e3e3e3")
        color, sh = hexc("#222222"), None
    f = paint.ui(12, blue)
    paint.text(title, NSMakeRect(rect.origin.x, rect.origin.y + (rect.size.height - 15) / 2.0, rect.size.width, 16),
               f, color, NSCenterTextAlignment, sh=sh)


def pill_width(title, blue):
    return paint.text_width(title, paint.ui(12, blue)) + (34 if blue else 28)


class PillCell(NSButtonCell):
    def drawWithFrame_inView_(self, frame, view):
        style = getattr(self, "style", "white")
        if style == "glass":   # the Follow button on the artist header
            shape = paint.rounded(NSInsetRect(frame, 0.5, 0.5), frame.size.height / 2.0)
            paint.fill(shape, white(1, 0.28 if self.isHighlighted() else 0.16))
            paint.stroke(shape, white(1, 0.6), 1)
            paint.text(self.title(), NSMakeRect(0, (frame.size.height - 14) / 2.0, frame.size.width, 15),
                       paint.ui(11, True), white(1), NSCenterTextAlignment)
            return
        draw_pill(NSMakeRect(0, 0, frame.size.width, frame.size.height - 1), self.title(), style == "blue",
                  self.isHighlighted())


class PillButton(NSButton):
    def isFlipped(self):
        return True


def make_pill(parent, title, style, target, action):
    b = PillButton.alloc().initWithFrame_(NSMakeRect(0, 0, 80, 25))
    cell = PillCell.alloc().init()
    cell.style = style
    cell.setButtonType_(NSMomentaryChangeButton)
    b.setCell_(cell)
    b.setTitle_(title)
    b.setTarget_(target)
    b.setAction_(action)
    parent.addSubview_(b)
    return b


# ---- the track list (playlists, Liked Songs, albums) -------------------------------------------------
class TrackTable(NSTableView):
    def drawBackgroundInClipRect_(self, clip):
        paint.fill(clip, "#ffffff")
        h = self.rowHeight() + self.intercellSpacing().height
        first = int(clip.origin.y // h)
        last = int((clip.origin.y + clip.size.height) // h) + 1
        stripe = hexc("#f1f5fa")
        for i in range(first, last + 1):
            if i % 2:
                paint.fill(NSMakeRect(clip.origin.x, i * h, clip.size.width, h), stripe)

    def menuForEvent_(self, event):
        row = self.rowAtPoint_(self.convertPoint_fromView_(event.locationInWindow(), None))
        if row < 0:
            return None
        if not self.isRowSelected_(row):
            self.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)
        if self.owner.rows[row].get("header"):
            return None
        return self.owner.trackMenu(self.owner.rows[row], row)

    def keyDown_(self, event):
        if event.charactersIgnoringModifiers() in (u"\r", u"\x03") and self.selectedRow() >= 0:
            self.owner.playRow_(self)
        elif not self.owner.library.app.handleKey(event):
            super(TrackTable, self).keyDown_(event)


class NumberCell(NSTextFieldCell):
    def drawInteriorWithFrame_inView_(self, frame, view):
        if getattr(self, "playing", False):
            dark = self.backgroundStyle() == NSBackgroundStyleDark
            glyphs.draw_at("now_playing", frame.origin.x + frame.size.width - 20, frame.origin.y + (frame.size.height - 12) / 2.0,
                           white(1) if dark else hexc("#2f6fd1"))
            return
        super(NumberCell, self).drawInteriorWithFrame_inView_(frame, view)


class ListHeader(LibraryFlipped):
    def initWithFrame_(self, frame):
        self = super(ListHeader, self).initWithFrame_(frame)
        if self:
            self.kind, self.title, self.meta, self.desc, self.image, self.heart = u"", u"", u"", u"", None, False
            self.artist = u""
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        paint.fill(b, "#fbfbfb", "#ebebeb")
        paint.fill(NSMakeRect(0, b.size.height - 1, b.size.width, 1), "#c9c9c9")
        case = NSMakeRect(26, 14, 88, 88 * CASE_RATIO)
        kind = "liked" if self.heart else ("album" if self.kind == u"ALBUM" else "mixtape")
        note = u"MIXTAPE" if kind != "album" else u"STEREO"
        draw_case(case, self, self.image, self.title, self.artist, note, kind)
        x, w = 136, b.size.width - 136 - 22
        paint.text(self.kind, NSMakeRect(x, 20, w, 14), paint.ui(10, True), "#5f5f5f", kern=0.8)
        paint.text(self.title, NSMakeRect(x, 33, w, 34), paint.font("Helvetica-Bold", 28, True), "#1d1d1d", kern=-0.4)
        paint.text(self.meta, NSMakeRect(x, 70, w, 16), paint.ui(12), "#4a4a4a")
        italic = NSFontManager.sharedFontManager().convertFont_toHaveTrait_(paint.ui(12), NSItalicFontMask)
        paint.text(self.desc, NSMakeRect(x, 88, w, 32), italic, "#5f5f5f", truncate=False)


class ListPage(NSObject):
    COLUMNS = [("n", u"#", 44), ("name", u"Name", 260), ("artist", u"Artist", 170), ("album", u"Album", 190),
               ("time", u"Time", 64)]

    def initWithLibrary_frame_(self, library, frame):
        self = super(ListPage, self).init()
        if self is None:
            return None
        self.library = library
        self.rows, self.total, self.kind, self.source = [], 0, None, None
        v = NSView.alloc().initWithFrame_(frame)
        v.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        w, h = frame.size.width, frame.size.height
        self.header = ListHeader.alloc().initWithFrame_(NSMakeRect(0, h - LIST_HEAD, w, LIST_HEAD))
        self.header.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        v.addSubview_(self.header)
        self.playButton = make_pill(self.header, u"▶  Play", "blue", self, "playAll:")
        self.shuffleButton = make_pill(self.header, u"Shuffle", "white", self, "shuffleAll:")
        self.saveButton = make_pill(self.header, u"♡ Save to Library", "white", self, "toggleSaved:")

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h - LIST_HEAD))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSNoBorder)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        t = TrackTable.alloc().initWithFrame_(scroll.contentView().bounds())
        t.owner = self
        t.setRowHeight_(18)
        t.setIntercellSpacing_(NSMakeSize(3, 2))
        t.setColumnAutoresizingStyle_(NSTableViewUniformColumnAutoresizingStyle)
        t.setAllowsMultipleSelection_(False)
        t.setFocusRingType_(NSFocusRingTypeNone)
        self.cols = {}
        for key, title, width in self.COLUMNS:
            col = NSTableColumn.alloc().initWithIdentifier_(key)
            col.headerCell().setStringValue_(title)
            col.setWidth_(width)
            cell = NumberCell.alloc().init() if key == "n" else NSTextFieldCell.alloc().init()
            cell.setFont_(paint.ui(12))
            cell.setLineBreakMode_(NSLineBreakByTruncatingTail)
            if key in ("n", "time"):
                cell.setAlignment_(NSRightTextAlignment)
                col.headerCell().setAlignment_(NSRightTextAlignment)
                col.setResizingMask_(NSTableColumnNoResizing)
            else:
                col.setResizingMask_(NSTableColumnAutoresizingMask | NSTableColumnUserResizingMask)
            col.setDataCell_(cell)
            col.setEditable_(False)
            t.addTableColumn_(col)
            self.cols[key] = col
        t.setDataSource_(self)
        t.setDelegate_(self)
        t.setTarget_(self)
        t.setDoubleAction_("playRow:")
        scroll.setDocumentView_(t)
        v.addSubview_(scroll)
        self.notice = NSTextField.alloc().initWithFrame_(NSMakeRect(40, h - LIST_HEAD - 110, w - 80, 60))
        for f in (self.notice,):
            f.setBezeled_(False)
            f.setDrawsBackground_(False)
            f.setEditable_(False)
            f.setSelectable_(False)
            f.setAlignment_(NSCenterTextAlignment)
            f.setFont_(paint.ui(12))
            f.setTextColor_(hexc("#6b6b6b"))
            f.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        v.addSubview_(self.notice)
        self.table, self.scroll, self.view = t, scroll, v
        return self

    def show(self, kind, source, rows, total, header, saved=None):
        """kind: liked, playlist or album. source: the slim playlist or album (None for Liked Songs)."""
        self.kind, self.source, self.rows, self.total = kind, source, rows, total
        album_view = kind == "album"
        for key in ("artist", "album"):
            self.cols[key].setHidden_(album_view)
        self.header.kind, self.header.title, self.header.meta, self.header.desc = header
        self.header.heart = kind == "liked"
        self.header.image = (source or {}).get("image")
        self.header.artist = (source or {}).get("artist") or (source or {}).get("owner") or u""
        self.header.setNeedsDisplay_(True)
        x = 136
        for b, title, show in ((self.playButton, u"▶  Play", True), (self.shuffleButton, u"Shuffle", True),
                               (self.saveButton, self.saveTitle(saved), album_view)):
            b.setHidden_(not show)
            if show:
                b.setTitle_(title)
                width = pill_width(title, b is self.playButton)
                b.setFrame_(NSMakeRect(x, LIST_HEAD - 20 - 25, width, 25))
                x += width + 8
        self.notice.setStringValue_(u"")
        self.table.reloadData()
        self.table.scrollRowToVisible_(0)
        self.table.deselectAll_(None)

    def saveTitle(self, saved):
        return u"✓ In Your Library" if saved else u"♡ Save to Library"

    def setNotice(self, text):
        self.notice.setStringValue_(text)

    def append(self, rows, total):
        self.rows.extend(rows)
        self.total = total
        self.table.noteNumberOfRowsChanged()

    # data source
    def numberOfRowsInTableView_(self, t):
        return len(self.rows)

    def tracks(self):
        return [r for r in self.rows if not r.get("header")]

    def tableView_isGroupRow_(self, t, row):
        return bool(self.rows[row].get("header"))

    def tableView_shouldSelectRow_(self, t, row):
        return not self.rows[row].get("header")

    def tableView_heightOfRow_(self, t, row):
        return 22 if self.rows[row].get("header") else 18

    def tableView_dataCellForTableColumn_row_(self, t, col, row):
        if col is None:                     # AppKit asks for one wide cell for a group row
            if not self.rows[row].get("header"):
                return None
            if getattr(self, "sideCell", None) is None:
                self.sideCell = NSTextFieldCell.alloc().init()
                self.sideCell.setFont_(paint.ui(10, True))
                self.sideCell.setTextColor_(hexc("#5f5f5f"))
            return self.sideCell
        return col.dataCellForRow_(row)

    def tableView_objectValueForTableColumn_row_(self, t, col, row):
        if row >= len(self.rows) - 15:
            self.library.loadMore()
        r = self.rows[row]
        if r.get("header"):
            return r["title"] if col is None else u""
        key = col.identifier()
        if key == "n":
            if self.kind == "album" and r.get("number"):
                return unicode(r["number"])
            return unicode(row + 1)
        if key == "name":
            return r["name"]
        if key == "artist":
            return artist_line(r)
        if key == "album":
            return r["album"]
        return paint.fmt(r["duration"])

    def tableView_willDisplayCell_forTableColumn_row_(self, t, cell, col, row):
        r = self.rows[row]
        if r.get("header") or col is None:
            return
        key = col.identifier()
        if key == "n":
            cell.playing = r["uri"] == self.library.playing_uri
            cell.setTextColor_(hexc("#6b6b6b"))
        else:
            cell.setTextColor_(hexc("#1d1d1d") if r["playable"] else hexc("#9a9a9a"))

    def tableView_shouldEditTableColumn_row_(self, t, col, row):
        return False

    # actions
    def playRow_(self, sender):
        row = self.table.clickedRow() if sender is self.table and self.table.clickedRow() >= 0 else self.table.selectedRow()
        if 0 <= row < len(self.rows) and not self.rows[row].get("header"):
            tracks = self.tracks()
            self.library.playRows(self.kind, self.source, tracks, tracks.index(self.rows[row]))

    def playAll_(self, sender):
        self.library.playRows(self.kind, self.source, self.tracks(), None, False)

    def shuffleAll_(self, sender):
        self.library.playRows(self.kind, self.source, self.tracks(), None, True)

    def toggleSaved_(self, sender):
        self.library.toggleSaved(self.source, self.saveButton)

    def trackMenu(self, r, row):
        tracks = self.tracks()
        return self.library.trackMenu(r, lambda: self.library.playRows(self.kind, self.source, tracks, tracks.index(r)),
                                      self.kind == "liked")

    def refreshPlaying(self):
        self.table.setNeedsDisplay_(True)


# ---- the window --------------------------------------------------------------------------------------
class ToolbarLCDView(LibraryFlipped):
    """iTunes 10's status display, small enough for the toolbar. Click it to see the deck."""

    def initWithFrame_(self, frame):
        self = super(ToolbarLCDView, self).initWithFrame_(frame)
        if self:
            self.line1, self.line2, self.p, self.onClick = u"Kassett", u"Nothing playing", 0.0, None
            self.links, self.hits, self.onLink = None, [], None
        return self

    def setLinks(self, links):
        self.links = links
        self.hits = self.layOut(False)
        if self.window():
            self.window().invalidateCursorRectsForView_(self)
        self.setNeedsDisplay_(True)

    def layOut(self, draw):
        if not self.links:
            return []
        w = self.bounds().size.width - 1
        tw = min(w - 24, paint.text_width(self.line1, paint.ui(11, True)))
        hits = [(NSMakeRect((w - tw) / 2.0, 3, tw, 13), self.links["title"])]
        return hits + deck.lay_out_links(deck.line_segments(self.links), 12, 15, w - 24, paint.ui(10), "#464840",
                                         center=True, draw=draw)

    def resetCursorRects(self):
        for r, _ in self.hits:
            self.addCursorRect_cursor_(r, NSCursor.pointingHandCursor())

    def mouseDownCanMoveWindow(self):
        # The library is a textured window: without this a click here also starts dragging it, and the
        # window being dragged comes to the front, over the player the click just brought up.
        return False

    def drawRect_(self, rect):
        b = NSMakeRect(0.5, 0.5, self.bounds().size.width - 1, self.bounds().size.height - 2)
        if getattr(self, "glass", None) is None:       # the LCD's glass, drawn once

            def glass():
                paint.fill(paint.rounded(NSOffsetRect(b, 0, 1), 5), white(1, 0.6))
                shape = paint.rounded(b, 5)
                paint.fill(shape, "#f7f9ee", "#d6dcc6")
                paint.inner_shadow(shape, 1, 2, white(0, 0.18))
                paint.stroke(shape, "#787c6e", 1)
            size = self.bounds().size
            self.glass = NSImage.alloc().initWithSize_(size)
            self.glass.lockFocusFlipped_(True)
            glass()
            self.glass.unlockFocus()
        self.glass.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            self.bounds(), NSZeroRect, NSCompositeSourceOver, 1.0, True, None)
        w = b.size.width
        paint.text(self.line1, NSMakeRect(12, 3, w - 24, 14), paint.ui(11, True), "#282a24", NSCenterTextAlignment)
        if self.links:
            self.hits = self.layOut(True)
        else:
            paint.text(self.line2, NSMakeRect(12, 15, w - 24, 13), paint.ui(10), "#464840", NSCenterTextAlignment)
        track = NSMakeRect((w - 300) / 2.0, 28, 300, 3)
        paint.fill(paint.rounded(track, 1.5), white(0, 0.18))
        if self.p:
            paint.fill(paint.rounded(NSMakeRect(track.origin.x, 28, max(3, 300 * self.p), 3), 1.5), "#3c4036")

    def mouseDown_(self, event):
        p = deck.point_at(self, event)
        for r, target in self.hits:
            if NSPointInRect(p, r) and self.onLink:
                return self.onLink(target)
        if self.onClick:
            self.onClick()


class MessageView(LibraryFlipped):
    def initWithFrame_(self, frame):
        self = super(MessageView, self).initWithFrame_(frame)
        if self:
            self.title, self.text = u"", u""
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        paint.fill(b, "#ffffff")
        w = min(420, b.size.width - 60)
        x = (b.size.width - w) / 2.0
        y = b.size.height * 0.32
        paint.text(self.title, NSMakeRect(x, y, w, 24), paint.font("Helvetica-Bold", 18, True), "#4a4a4a",
                   NSCenterTextAlignment)
        paint.text(self.text, NSMakeRect(x, y + 30, w, 60), paint.ui(12), "#6b6b6b", NSCenterTextAlignment, truncate=False)


class Library(NSObject):
    def initWithApp_(self, app):
        self = super(Library, self).init()
        if self is None:
            return None
        self.app = app
        self.client = app.client
        self.history, self.index = [], -1
        self.serial = 0
        self.me_id = None
        self.playlists, self.liked_total = [], None
        self.playing_uri = None
        self.grid, self.grid_next, self.grid_kind, self.grid_sort = [], None, None, None
        self.loading_more = False
        self.more = None          # callable that loads the next page of the current view, or None
        self.debug = None
        self.groups, self.syncing = [], False
        self.build()
        self.reload()
        return self

    # ---- building the window ------------------------------------------------------------------------
    def build(self):
        mask = (NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask |
                NSTexturedBackgroundWindowMask)
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 1060, 620), mask, NSBackingStoreBuffered, False)
        w.setTitle_(u"Library")
        w.setMinSize_(NSMakeSize(860, 460))
        w.setReleasedWhenClosed_(False)
        w.setContentBorderThickness_forEdge_(BAR, NSMinYEdge)
        w.setFrameAutosaveName_("KassettLibrary")
        if not w.setFrameUsingName_("KassettLibrary"):
            w.center()
        self.window = w
        toolbar = NSToolbar.alloc().initWithIdentifier_("KassettLibraryToolbar")
        toolbar.setDelegate_(self)
        toolbar.setDisplayMode_(NSToolbarDisplayModeIconOnly)
        toolbar.setAllowsUserCustomization_(False)
        w.setToolbar_(toolbar)

        content = w.contentView()
        cw, ch = content.frame().size.width, content.frame().size.height
        split = NSSplitView.alloc().initWithFrame_(NSMakeRect(0, BAR, cw, ch - BAR))
        split.setVertical_(True)
        split.setDividerStyle_(NSSplitViewDividerStyleThin)
        split.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        split.setDelegate_(self)
        self.split = split

        side = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, SIDEBAR, ch - BAR))
        side.setHasVerticalScroller_(True)
        side.setBorderType_(NSNoBorder)
        side.setAutohidesScrollers_(True)
        ov = NSOutlineView.alloc().initWithFrame_(side.bounds())
        col = NSTableColumn.alloc().initWithIdentifier_("source")
        col.setWidth_(SIDEBAR - 16)
        ov.addTableColumn_(col)
        ov.setOutlineTableColumn_(col)
        ov.setHeaderView_(None)
        ov.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleSourceList)
        ov.setColumnAutoresizingStyle_(NSTableViewUniformColumnAutoresizingStyle)
        ov.setIndentationPerLevel_(4)
        ov.setFloatsGroupRows_(False)
        ov.setDataSource_(self)
        ov.setDelegate_(self)
        side.setDocumentView_(ov)
        self.outline = ov
        self.sourceCell = SourceCell.alloc().init()
        self.groups = []

        pages = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, cw - SIDEBAR - 1, ch - BAR))
        pages.setAutoresizesSubviews_(True)
        self.pages = pages
        pw, ph = pages.frame().size.width, pages.frame().size.height

        # Grids of albums or artists, under a header bar with the title and a sort menu.
        grid = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, pw, ph))
        grid.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.gridBar = GridBar.alloc().initWithFrame_(NSMakeRect(0, ph - 30, pw, 30))
        self.gridBar.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        grid.addSubview_(self.gridBar)
        self.sortPopup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(pw - 150, ph - 27, 136, 22), False)
        self.sortPopup.cell().setControlSize_(NSSmallControlSize)
        self.sortPopup.setFont_(paint.ui(11))
        self.sortPopup.addItemsWithTitles_([t for t, _ in SORTS])
        self.sortPopup.setTarget_(self)
        self.sortPopup.setAction_("sortChanged:")
        self.sortPopup.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        grid.addSubview_(self.sortPopup)
        self.gridCanvas, gridScroll = self.makeCanvas(NSMakeRect(0, 0, pw, ph - 30))
        grid.addSubview_(gridScroll)
        self.gridPage = grid

        self.list = ListPage.alloc().initWithLibrary_frame_(self, NSMakeRect(0, 0, pw, ph))
        self.canvas, canvasScroll = self.makeCanvas(NSMakeRect(0, 0, pw, ph))
        self.canvasPage = canvasScroll
        self.followButton = make_pill(self.canvas, u"✓ Following", "glass", self, "toggleFollow:")
        self.followButton.setHidden_(True)
        self.message = MessageView.alloc().initWithFrame_(NSMakeRect(0, 0, pw, ph))
        self.message.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.loginButton = NSButton.alloc().initWithFrame_(NSMakeRect((pw - 200) / 2, ph * 0.68 - 100, 200, 32))
        self.loginButton.setBezelStyle_(NSRoundedBezelStyle)
        self.loginButton.setTitle_(u"Log In to Spotify…")
        self.loginButton.setTarget_(self.app)
        self.loginButton.setAction_("logIn:")
        self.loginButton.setAutoresizingMask_(NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin)
        self.message.addSubview_(self.loginButton)
        for page in (grid, self.list.view, canvasScroll, self.message):
            page.setHidden_(True)
            pages.addSubview_(page)
        self.fade = FadeView.alloc().initWithFrame_(pages.bounds())
        self.fade.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.fade.setHidden_(True)
        pages.addSubview_(self.fade)
        self.flip = FlipView.alloc().initWithFrame_(pages.bounds())
        self.flip.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        pages.addSubview_(self.flip)

        split.addSubview_(side)
        split.addSubview_(pages)
        content.addSubview_(split)
        side.setFrame_(NSMakeRect(0, 0, SIDEBAR, ch - BAR))
        pages.setFrame_(NSMakeRect(SIDEBAR + 1, 0, cw - SIDEBAR - 1, ch - BAR))
        split.adjustSubviews()

        self.spinner = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(10, 5, 16, 16))
        self.spinner.setStyle_(NSProgressIndicatorSpinningStyle)
        self.spinner.setControlSize_(NSSmallControlSize)
        self.spinner.setDisplayedWhenStopped_(False)
        content.addSubview_(self.spinner)
        self.status = NSTextField.alloc().initWithFrame_(NSMakeRect(40, 5, cw - 80, 16))
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setSelectable_(False)
        self.status.setAlignment_(NSCenterTextAlignment)
        self.status.setFont_(paint.ui(11))
        self.status.cell().setBackgroundStyle_(NSBackgroundStyleRaised)
        self.status.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        self.status.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(self.status)

    def makeCanvas(self, frame):
        scroll = NSScrollView.alloc().initWithFrame_(frame)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSNoBorder)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        clip = OvershootClipView.alloc().initWithFrame_(scroll.contentView().frame())
        scroll.setContentView_(clip)
        canvas = CanvasView.alloc().initWithFrame_(scroll.contentView().bounds())
        canvas.library = self
        scroll.setDocumentView_(canvas)
        canvas.watch()
        return canvas, scroll

    # split view: the source list keeps its width when the window resizes
    def splitView_constrainMinCoordinate_ofSubviewAt_(self, split, proposed, index):
        return 160

    def splitView_constrainMaxCoordinate_ofSubviewAt_(self, split, proposed, index):
        return 320

    def splitView_resizeSubviewsWithOldSize_(self, split, old):
        side, pages = split.subviews()
        size = split.frame().size
        sw = side.frame().size.width
        side.setFrame_(NSMakeRect(0, 0, sw, size.height))
        pages.setFrame_(NSMakeRect(sw + 1, 0, max(0, size.width - sw - 1), size.height))

    # ---- toolbar ------------------------------------------------------------------------------------
    TOOLBAR = ["nav", "transport", NSToolbarFlexibleSpaceItemIdentifier, "lcd", NSToolbarFlexibleSpaceItemIdentifier,
               "search"]

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return self.TOOLBAR

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return self.TOOLBAR

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(self, toolbar, ident, flag):
        item = NSToolbarItem.alloc().initWithItemIdentifier_(ident)
        if ident in ("nav", "transport"):
            parts = [("back", u"Back", 28), ("forward", u"Forward", 28)] if ident == "nav" else \
                [("prev", u"Previous Song", 32), ("play", u"Play", 36), ("next", u"Next Song", 32)]
            seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(0, 0, sum(p[2] for p in parts) + 8, 25))
            seg.setSegmentStyle_(NSSegmentStyleTexturedRounded)
            seg.cell().setTrackingMode_(NSSegmentSwitchTrackingMomentary)
            seg.setSegmentCount_(len(parts))
            for i, (glyph, tip, width) in enumerate(parts):
                seg.setImage_forSegment_(glyphs.image(glyph, 11 if ident == "nav" else 13), i)
                seg.setWidth_forSegment_(width, i)
                seg.cell().setToolTip_forSegment_(tip, i)
            seg.setTarget_(self)
            seg.setAction_("navClicked:" if ident == "nav" else "transportClicked:")
            setattr(self, ident + "Control", seg)
            view, label = seg, (u"Back/Forward" if ident == "nav" else u"Controls")
        elif ident == "lcd":
            view = ToolbarLCDView.alloc().initWithFrame_(NSMakeRect(0, 0, 380, 35))
            view.onClick = lambda: self.app.showDeck_(None)
            view.onLink = self.app.followLink
            view.setToolTip_(u"Show the cassette deck")
            self.lcd = view
            label = u"Now Playing"
        elif ident == "search":
            field = NSSearchField.alloc().initWithFrame_(NSMakeRect(0, 0, 210, 22))
            field.cell().setPlaceholderString_(u"Search Spotify")
            field.cell().setSendsWholeSearchString_(True)
            field.setTarget_(self)
            field.setAction_("search:")
            self.searchField = field
            view, label = field, u"Search"
        else:
            return None
        item.setView_(view)
        item.setLabel_(label)
        item.setPaletteLabel_(label)
        item.setMinSize_(view.frame().size)
        item.setMaxSize_(view.frame().size)
        return item

    def navClicked_(self, sender):
        self.goBack() if sender.selectedSegment() == 0 else self.goForward()

    def transportClicked_(self, sender):
        [self.app.previous_, self.app.playPause_, self.app.next_][sender.selectedSegment()](None)

    def search_(self, sender):
        text = sender.stringValue().strip()
        if text:
            self.go(("search", text))

    # ---- now playing ----------------------------------------------------------------------------------
    def showState(self, state, progress):
        item = (state or {}).get("item")
        uri = item.get("uri") if item else None
        if hasattr(self, "lcd"):
            if item:
                names = u", ".join(a.get("name") for a in item.get("artists") or [] if a.get("name"))
                album = (item.get("album") or {}).get("name")
                self.lcd.line1 = item.get("name") or u""
                self.lcd.line2 = u"%s — %s" % (names, album) if album else names
            else:
                self.lcd.line1, self.lcd.line2, self.lcd.p = u"Kassett", u"Nothing playing", 0
            self.lcd.setNeedsDisplay_(True)
        if hasattr(self, "transportControl"):
            playing = bool(state and state.get("is_playing") and item)
            if getattr(self, "shows_pause", None) != playing:
                self.shows_pause = playing
                self.transportControl.setImage_forSegment_(glyphs.image("pause" if playing else "play", 13), 1)
        if uri != self.playing_uri:
            self.playing_uri = uri
            self.list.refreshPlaying()
            self.canvas.setNeedsDisplay_(True)

    def setLinks(self, links):
        if hasattr(self, "lcd"):
            self.lcd.setLinks(links)

    def showProgress(self, progress, duration):
        if hasattr(self, "lcd"):
            self.lcd.p = float(progress) / duration if duration else 0
            self.lcd.setNeedsDisplay_(True)

    # ---- the source list ----------------------------------------------------------------------------
    def reload(self):
        """Start over: after launch, login or logout."""
        self.client = self.app.libraryClient()
        self.history, self.index = [], -1
        self.playlists, self.liked_total, self.me_id = [], None, None
        self.rebuildSources()
        if not (self.client and self.client.logged_in):
            self.rebuildSources()
            self.showMessage(u"Not logged in", u"Log in with your Spotify Premium account to see your library.", True)
            self.setStatus(u"")
            return
        self.go(("liked",))
        self.loadSources()

    def loadSources(self):
        client = self.client

        def work():
            me = client.me() or {}
            liked = client.saved_tracks(0)
            playlists, offset = [], 0
            while True:
                page = client.my_playlists(offset) or {}
                playlists += [slim_playlist(p, me.get("id")) for p in page.get("items") or [] if p]
                offset += spotify.PAGE
                if not page.get("next") or offset >= 500:
                    break
            return me.get("id"), (liked or {}).get("total"), playlists

        def done(result, error):
            if error:
                self.flashError(error)
                return
            self.me_id, self.liked_total, self.playlists = result
            self.rebuildSources()
            if self.debug == "playlist" and self.playlists:
                self.debug = None
                self.go(("playlist", self.playlists[0]["id"]))
        cocoa.in_background(work, done)

    def rebuildSources(self):
        def row(title, glyph, key, badge=u""):
            return NSMutableDictionary.dictionaryWithDictionary_(
                {"kind": "source", "title": title, "glyph": glyph, "key": key, "badge": badge})
        lib = NSMutableDictionary.dictionaryWithDictionary_({"kind": "group", "title": u"LIBRARY"})
        badge = unicode(self.liked_total) if self.liked_total else u""
        lib_rows = [row(u"Liked Songs", "heart", "liked", badge), row(u"Albums", "disc", "albums"),
                    row(u"Artists", "person", "artists")]
        groups = [(lib, lib_rows)]
        if self.playlists:
            pl = NSMutableDictionary.dictionaryWithDictionary_({"kind": "group", "title": u"PLAYLISTS"})
            groups.append((pl, [row(p["name"], "playlist", "playlist:" + p["id"]) for p in self.playlists]))
        self.groups = groups
        self.syncing = True
        self.outline.reloadData()
        for g, _ in groups:
            self.outline.expandItem_(g)
        self.selectSource()
        self.syncing = False

    def sourceKey(self, loc):
        if not loc:
            return None
        return loc[0] if loc[0] in ("liked", "albums", "artists") else ("playlist:" + loc[1] if loc[0] == "playlist" else None)

    def selectSource(self):
        key = self.sourceKey(self.location())
        self.syncing = True
        for _, rows in self.groups:
            for r in rows:
                if r["key"] == key:
                    i = self.outline.rowForItem_(r)
                    self.outline.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(i), False)
                    self.syncing = False
                    return
        self.outline.deselectAll_(None)
        self.syncing = False

    def outlineView_numberOfChildrenOfItem_(self, ov, item):
        if item is None:
            return len(self.groups)
        for g, rows in self.groups:
            if item == g:
                return len(rows)
        return 0

    def outlineView_child_ofItem_(self, ov, index, item):
        if item is None:
            return self.groups[index][0]
        for g, rows in self.groups:
            if item == g:
                return rows[index]
        return None

    def outlineView_isItemExpandable_(self, ov, item):
        return item is not None and item["kind"] == "group"

    def outlineView_isGroupItem_(self, ov, item):
        return item["kind"] == "group"

    def outlineView_shouldSelectItem_(self, ov, item):
        return item["kind"] != "group"

    def outlineView_shouldShowOutlineCellForItem_(self, ov, item):
        return False

    def outlineView_heightOfRowByItem_(self, ov, item):
        return 22

    def outlineView_dataCellForTableColumn_item_(self, ov, col, item):
        if col is None or item["kind"] == "group":
            return None
        return self.sourceCell

    def outlineView_objectValueForTableColumn_byItem_(self, ov, col, item):
        return item["title"] if item["kind"] == "group" else item

    def outlineViewSelectionDidChange_(self, note):
        if getattr(self, "syncing", False):
            return
        item = self.outline.itemAtRow_(self.outline.selectedRow())
        if item is None:
            return
        key = item["key"]
        self.go(("playlist", key.split(":", 1)[1]) if key.startswith("playlist:") else (key,))

    # ---- navigation ---------------------------------------------------------------------------------
    def location(self):
        return self.history[self.index] if 0 <= self.index < len(self.history) else None

    def go(self, loc, push=True, came_from=None):
        came_from = came_from or self.location()
        tapes = ("albums", "artist", "search")
        if loc and loc[0] == "album" and came_from and came_from[0] in tapes:
            self.transition = "flip"            # turn the tape over to read its track list
        elif came_from and came_from[0] == "album" and loc and loc[0] in tapes:
            self.transition = "flipback"
        else:
            self.transition = "fade"
        if push and loc != self.location():
            del self.history[self.index + 1:]
            self.history.append(loc)
            self.index = len(self.history) - 1
        self.updateNav()
        self.selectSource()
        self.open(loc)

    def goBack(self):
        if self.index > 0:
            came_from = self.location()
            self.index -= 1
            self.go(self.history[self.index], False, came_from)

    def goForward(self):
        if self.index < len(self.history) - 1:
            came_from = self.location()
            self.index += 1
            self.go(self.history[self.index], False, came_from)

    def updateNav(self):
        if hasattr(self, "navControl"):
            self.navControl.setEnabled_forSegment_(self.index > 0, 0)
            self.navControl.setEnabled_forSegment_(self.index < len(self.history) - 1, 1)

    def showPage(self, page):
        """Switch views with a short crossfade, or flip the pane over when opening a tape. Both work
        on snapshots, so nothing underneath redraws while they run (the Core 2 Duo stays smooth)."""
        pages = (self.gridPage, self.list.view, self.canvasPage, self.message)
        old = [p for p in pages if not p.isHidden()]
        moving = old and old[0] is not page and self.window.isVisible()
        transition, self.transition = getattr(self, "transition", "fade"), "fade"
        effect = self.flip if transition in ("flip", "flipback") else self.fade
        if moving:
            effect.direction = -1 if transition == "flipback" else 1
            effect.start(snapshot(old[0]))
        for p in pages:
            p.setHidden_(p is not page)
        self.followButton.setHidden_(True)
        if moving:
            effect.target = page
            effect.performSelector_withObject_afterDelay_("begin:", None, 0)

    def showMessage(self, title, text, login=False):
        self.message.title, self.message.text = title, text
        self.loginButton.setHidden_(not login)
        self.loginButton.setTitle_(u"Log In Again…" if login == "again" else u"Log In to Spotify…")
        self.loginButton.setAction_("logInAgain:" if login == "again" else "logIn:")
        self.message.setNeedsDisplay_(True)
        self.showPage(self.message)

    def setStatus(self, text, busy=False):
        self.status.setStringValue_(text or u"")
        if busy:
            self.spinner.startAnimation_(None)
        else:
            self.spinner.stopAnimation_(None)

    def flashError(self, error):
        if getattr(error, "reason", None) == "NOT_ALLOWLISTED":
            self.app.notAllowlisted()
        self.setStatus(u"⚠ %s" % error)

    def fetch(self, work, done, status=u"Loading…"):
        """Run work() in the background for the current view; drop the answer if the view changed."""
        self.serial += 1
        serial = self.serial
        self.more = None
        self.setStatus(status, True)

        def finish(result, error):
            if serial != self.serial:
                return
            self.setStatus(u"")
            if error:
                self.flashError(error)
                if getattr(error, "reason", None) == "SCOPE":
                    self.showMessage(u"Kassett needs to ask Spotify again",
                                     u"Your login is from an older Kassett that didn’t ask to read your library. "
                                     u"Log in again and allow it.", "again")
                else:
                    self.showMessage(u"Spotify didn’t answer", u"%s" % error)
                return
            done(result)
        cocoa.in_background(work, finish)

    def loadMore(self):
        if self.more and not self.loading_more:
            self.loading_more = True
            more, self.more = self.more, None
            serial = self.serial
            self.spinner.startAnimation_(None)

            def finish(result, error):
                self.loading_more = False
                self.spinner.stopAnimation_(None)
                if serial == self.serial and not error:
                    result()
            cocoa.in_background(more, finish)

    def open(self, loc):
        if not (self.client and self.client.logged_in):
            return
        kind = loc[0]
        getattr(self, "open_" + kind)(*loc[1:])

    # ---- Liked Songs, playlists, albums -------------------------------------------------------------
    def openList(self, kind, source, first_page, total, header, saved=None, next_offset=None, fetch_page=None,
                 album=None):
        self.list.show(kind, source, first_page, total, header, saved)
        self.showPage(self.list.view)
        self.window.makeFirstResponder_(self.list.table)
        uri, self.reveal_uri = getattr(self, "reveal_uri", None), None
        rows = [i for i, r in enumerate(self.list.rows) if uri and r.get("uri") == uri]
        if rows:       # opened from the playing song: pick it in the list
            self.list.table.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(rows[0]), False)
            self.list.table.scrollRowToVisible_(rows[0])
        self.listStatus()
        self.queueMore(next_offset, fetch_page, total, album)

    def queueMore(self, offset, fetch_page, total, album=None):
        if fetch_page is None or offset is None or offset >= total:
            self.more = None
            return

        def work():
            page = fetch_page(offset) or {}
            rows = [slim_track(t, album) for t in spotify.items_of(page)]

            def apply():
                self.list.append(rows, page.get("total") or total)
                self.listStatus()
                self.queueMore(offset + spotify.PAGE, fetch_page, page.get("total") or total, album)
            return apply
        self.more = work

    def listStatus(self):
        self.setStatus(songs_and_time(self.list.rows, self.list.total))

    def open_liked(self):
        client = self.client

        def work():
            page = client.saved_tracks(0) or {}
            return [slim_track(t) for t in spotify.items_of(page)], page.get("total") or 0

        def done(result):
            rows, total = result
            self.liked_total = total
            header = (u"PLAYLIST", u"Liked Songs", u"%s · the newest first" % paint.plural(total, u"song"),
                      u"Everything you hearted in Spotify, on any device.")
            self.openList("liked", None, rows, total, header, None, spotify.PAGE, client.saved_tracks)
            if not rows:
                self.list.setNotice(u"You haven’t liked any songs yet. Right-click a song and choose "
                                    u"Add to Liked Songs.")
        self.fetch(work, done)

    def open_playlist(self, playlist_id):
        client, me_id = self.client, self.me_id

        def work():
            p = client.playlist(playlist_id) or {}
            info = slim_playlist(p, me_id or (client.me() or {}).get("id"))
            paging = spotify.playlist_items_paging(p)
            rows = [slim_track(t) for t in spotify.items_of(paging)] if isinstance(paging, dict) and \
                paging.get("items") is not None else None
            return info, rows, (paging or {}).get("total") or info["total"]

        def done(result):
            info, rows, total = result
            meta = u"%s · %s" % (info["owner"], paint.plural(total, u"song")) if total else info["owner"]
            header = (u"PLAYLIST", info["name"], meta, info["description"])
            if rows is None:
                self.openList("playlist", info, [], total, header)
                self.list.setNotice(u"Spotify only lists the songs in playlists you made or collaborate on. "
                                    u"You can still play this one.")
                self.setStatus(paint.plural(total, u"song") if total else u"")
                return
            self.openList("playlist", info, rows, total, header, None, len(rows),
                          lambda offset: client.playlist_items(playlist_id, offset))
            if not rows:
                self.list.setNotice(u"This playlist is empty.")
        self.fetch(work, done)

    def open_album(self, album_id):
        client = self.client

        def work():
            a = client.album(album_id) or {}
            info = slim_album(a)
            paging = a.get("tracks") or {}
            rows = [slim_track(t, a) for t in spotify.items_of(paging)]
            while paging.get("next") and len(rows) < 500:     # every song, so the sides can be worked out
                paging = client.album_tracks(album_id, len(rows)) or {}
                page = [slim_track(t, a) for t in spotify.items_of(paging)]
                if not page:
                    break
                rows += page
            saved = client.library_contains([info["uri"]])
            return info, rows, len(rows), bool(saved and saved[0])

        def done(result):
            info, rows, total, saved = result
            minutes = u", " + paint.total_time(sum(r["duration"] for r in rows))
            meta = u" · ".join(x for x in (info["artist"], info["year"], paint.plural(total, u"song") + minutes) if x)
            self.openList("album", info, side_rows(rows), total, (u"ALBUM", info["name"], meta, u""), saved)
        self.fetch(work, done)

    def toggleSaved(self, source, button):
        if not source:
            return
        saved = button.title().startswith(u"✓")
        client = self.client

        def done(_, error):
            if error:
                self.flashError(error)
                return
            button.setTitle_(self.list.saveTitle(not saved))
            frame = button.frame()
            frame.size.width = pill_width(button.title(), False)
            button.setFrame_(frame)
            self.setStatus(u"Removed “%s” from your library." % source["name"] if saved
                           else u"Saved “%s” to your library." % source["name"])
        cocoa.in_background(lambda: (client.unsave if saved else client.save)([source["uri"]]), done)

    def playRows(self, kind, source, rows, row, shuffle=None):
        """Play from `row` (or from the top) in the list's own context when Spotify has one."""
        if kind == "liked":
            context = "spotify:user:%s:collection" % self.me_id if self.me_id else None
        else:
            context = (source or {}).get("uri")
        uris = [r["uri"] for r in rows if r["playable"]]
        if row is None:
            if rows and not shuffle:
                self.app.showPending(rows[0])
            self.app.playFrom(context, None, uris[:100], 0, shuffle if shuffle else False)
            return
        r = rows[row]
        self.app.showPending(r)
        start = uris.index(r["uri"]) if r["uri"] in uris else 0
        self.app.playFrom(context, r["uri"], uris[start:start + 100], 0, None)

    def playSongs(self, songs, i):
        self.app.showPending(songs[i])
        self.app.playFrom(None, None, [t["uri"] for t in songs[i:]], 0, None)

    # ---- right-click on a song ----------------------------------------------------------------------
    def trackMenu(self, t, play, in_liked=False):
        menu = NSMenu.alloc().initWithTitle_(u"Song")
        menu.setAutoenablesItems_(False)
        self.menu_track, self.menu_play = t, play

        def add(title, action, enabled=True):
            it = menu.addItemWithTitle_action_keyEquivalent_(title, action, "")
            it.setTarget_(self)
            it.setEnabled_(enabled)
        add(u"Play", "menuPlay:", t["playable"])
        add(u"Add to Up Next", "menuQueue:", t["playable"])
        menu.addItem_(NSMenuItem.separatorItem())
        add(u"Go to Album", "menuAlbum:", bool(t.get("album_id")))
        add(u"Go to Artist", "menuArtist:", bool(t["artists"] and t["artists"][0][0]))
        menu.addItem_(NSMenuItem.separatorItem())
        if in_liked:
            add(u"Remove from Liked Songs", "menuUnlike:")
        else:
            add(u"Add to Liked Songs", "menuLike:")
        return menu

    def menuPlay_(self, sender):
        self.menu_play()

    def menuQueue_(self, sender):
        t = self.menu_track
        self.app.addToQueue(t["uri"], t["name"])
        self.setStatus(u"Added “%s” to Up Next." % t["name"])

    def menuAlbum_(self, sender):
        self.go(("album", self.menu_track["album_id"]))

    def menuArtist_(self, sender):
        self.go(("artist", self.menu_track["artists"][0][0]))

    def menuLike_(self, sender):
        t = self.menu_track
        cocoa.in_background(lambda: self.client.save([t["uri"]]), lambda _, e: self.flashError(e) if e else
                            self.setStatus(u"Added “%s” to Liked Songs." % t["name"]))

    def menuUnlike_(self, sender):
        t = self.menu_track

        def done(_, error):
            if error:
                return self.flashError(error)
            if t in self.list.rows:
                self.list.rows.remove(t)
                self.list.total -= 1
                self.list.table.reloadData()
                self.listStatus()
        cocoa.in_background(lambda: self.client.unsave([t["uri"]]), done)

    # ---- album and artist grids ---------------------------------------------------------------------
    def open_albums(self):
        self.openGrid("albums")

    def open_artists(self):
        self.openGrid("artists")

    def openGrid(self, kind):
        client = self.client
        self.grid_kind = kind
        self.gridBar.title = u"Albums" if kind == "albums" else u"Artists you follow"
        self.gridBar.count = u""
        self.sortPopup.setHidden_(kind != "albums")
        self.gridBar.setNeedsDisplay_(True)

        def page_of(cursor):
            if kind == "albums":
                page = client.saved_albums(cursor or 0) or {}
                return ([slim_album(a) for a in spotify.items_of(page)], page.get("total") or 0,
                        (cursor or 0) + spotify.PAGE if page.get("next") else None)
            page = client.followed_artists(cursor)
            return ([slim_artist(a) for a in page.get("items") or [] if a], page.get("total") or 0,
                    (page.get("cursors") or {}).get("after") if page.get("next") else None)

        def done(result):
            items, total, cursor = result
            self.grid, self.grid_total = items, total
            self.showPage(self.gridPage)
            self.renderGrid(True)
            self.queueGridPage(page_of, cursor)
            if self.debug in ("album", "artist") and items:
                target, self.debug = self.debug, None
                self.go((target, items[0]["id"]))
        self.fetch(lambda: page_of(None), done)

    def queueGridPage(self, page_of, cursor):
        if cursor is None:
            self.more = None
            if self.grid_sort:
                self.renderGrid(False)
            return

        def work():
            items, total, after = page_of(cursor)

            def apply():
                self.grid.extend(items)
                self.grid_total = total
                self.renderGrid(False)
                self.queueGridPage(page_of, after)
            return apply
        self.more = work
        if self.grid_sort:   # sorting needs everything: keep loading
            self.loadMore()

    def sortChanged_(self, sender):
        self.grid_sort = SORTS[sender.indexOfSelectedItem()][1]
        if self.grid_sort and self.more:
            self.loadMore()
        self.renderGrid(True)

    def renderGrid(self, top):
        items = list(self.grid)
        if self.grid_kind == "artists":
            items.sort(key=lambda a: a["name"].lower())
        elif self.grid_sort:
            items.sort(key=lambda a: (a.get(self.grid_sort) or u"").lower(), reverse=self.grid_sort == "year")
        noun = u"album" if self.grid_kind == "albums" else u"artist"
        self.gridBar.count = paint.plural(self.grid_total, noun) if self.grid_kind == "artists" else u""
        self.gridBar.setNeedsDisplay_(True)
        self.setStatus(paint.plural(self.grid_total, noun))
        canvas = self.gridCanvas
        round_ = self.grid_kind == "artists"
        canvas.builder = lambda width: self.gridItems(width, items, round_)
        canvas.nearEnd = self.loadMore
        canvas.rebuild()
        if top:
            canvas.scrollToTop()
        if getattr(self, "bounce", None) == "albums-bounce":
            self.bounce = None
            clip = canvas.superview()
            clip.setBoundsOrigin_(NSMakePoint(0, canvas.frame().size.height - clip.bounds().size.height + 90))
        if not items:
            self.showMessage(u"No albums yet" if not round_ else u"No artists yet",
                             u"Albums you save in Spotify show up here." if not round_ else
                             u"Artists you follow in Spotify show up here.")

    def gridItems(self, width, items, round_):
        pad, gap = 24, 22
        cols = max(2, int((width - 2 * pad + gap) // (130 + gap)))
        cw = (width - 2 * pad - (cols - 1) * gap) / float(cols)
        out = []
        canvas = self.gridCanvas
        for i, it in enumerate(items):
            r, c = divmod(i, cols)
            if round_:
                d = min(118, cw)
                cell_h = d + 30
                rect = NSMakeRect(pad + c * (cw + gap), 22 + r * (cell_h + 22), cw, cell_h)
                out.append({"rect": rect, "data": it, "draw": lambda e, s, d=d: draw_artist_cell(e, d, canvas),
                            "click": lambda e: self.go(("artist", e["data"]["id"])), "cache": circle_key})
        rows = (len(items) + cols - 1) // cols
        if round_:
            canvas.backdrop = canvas.top_fill = canvas.bottom_fill = None
            return out, 20 + rows * (min(118, cw) + 30 + 22) + 20
        return self.shelfItems(width, items)

    def shelfItems(self, width, items):
        """Albums as tapes standing on walnut shelves."""
        out, height = self.shelf(self.gridCanvas, width, items, 0, 2)
        self.gridCanvas.backdrop = draw_wall
        self.gridCanvas.top_fill = self.gridCanvas.bottom_fill = draw_wall
        return out, height

    def shelf(self, canvas, width, items, top, min_rows):
        """Shelf boards and tapes from `top` down; returns the items and where the shelf ends."""
        pad, gap = 28, 24
        cols = max(2, int((width - 2 * pad + gap) // (100 + gap)))
        cw = (width - 2 * pad - (cols - 1) * gap) / float(cols)
        ch = cw * CASE_RATIO
        row_h = 26 + ch + 40
        out = []
        rows = max(min_rows, (len(items) + cols - 1) // cols)
        for r in range(rows):
            board_y = top + 26 + r * row_h + ch - 2
            out.append({"rect": NSMakeRect(0, board_y, width, 34), "draw": lambda e, s, by=board_y: draw_board(width, by)})
        for i, it in enumerate(items):
            r, c = divmod(i, cols)
            rect = NSMakeRect(pad + c * (cw + gap), top + 26 + r * row_h, cw, ch)
            out.append({"rect": rect, "data": it, "click": lambda e: self.go(("album", e["data"]["id"])),
                        "menu": lambda e: self.albumMenu(e["data"]), "cache": case_key,
                        "draw": lambda e, s: draw_case(e["rect"], canvas, e["data"]["image"], e["data"]["name"],
                                                       e["data"]["artist"], e["data"]["year"])})
        return out, top + 26 + rows * row_h + 10

    def albumMenu(self, album):
        menu = NSMenu.alloc().initWithTitle_(u"Album")
        self.menu_album = album
        for title, action in ((u"Play", "menuPlayAlbum:"), (u"Open", "menuOpenAlbum:")):
            menu.addItemWithTitle_action_keyEquivalent_(title, action, "").setTarget_(self)
        return menu

    def menuPlayAlbum_(self, sender):
        self.app.playFrom(self.menu_album["uri"], None, [], 0, False)

    def menuOpenAlbum_(self, sender):
        self.go(("album", self.menu_album["id"]))

    # ---- the artist page ----------------------------------------------------------------------------
    def open_artist(self, artist_id):
        client = self.client

        def work():
            a = client.artist(artist_id) or {}
            info = slim_artist(a)
            try:   # the page still opens if one of its parts fails
                songs = [slim_track(t) for t in client.artist_songs(a)] if a.get("name") else []
            except spotify.SpotifyError:
                songs = []
            try:
                albums = [slim_album(x) for x in (client.artist_albums(artist_id) or {}).get("items") or [] if x]
            except spotify.SpotifyError:
                albums = []
            try:
                following = bool((client.library_contains([info["uri"]]) or [False])[0])
            except spotify.SpotifyError:
                following = None
            return info, songs, albums, following

        def done(result):
            info, songs, albums, following = result
            self.artist = {"info": info, "songs": songs, "albums": albums, "following": following, "more": False}
            self.renderArtist(True)
            self.setStatus(u"%s · %s" % (info["name"], paint.plural(len(albums), u"album")))
        self.fetch(work, done)

    def renderArtist(self, top):
        self.showPage(self.canvasPage)
        self.canvas.backdrop = None
        a = self.artist
        self.canvas.builder = lambda width: self.artistItems(width, a)
        self.canvas.nearEnd = None
        self.canvas.rebuild()
        if top:
            self.canvas.scrollToTop()
        if getattr(self, "bounce", None) == "artist-bounce":
            self.bounce = None
            self.canvas.superview().setBoundsOrigin_(NSMakePoint(0, -90))
        name_w = paint.text_width(a["info"]["name"], paint.font("Helvetica-Bold", 44, True), -0.8)
        f = a["following"]
        self.followButton.setHidden_(f is None)
        title = u"✓ Following" if f else u"Follow"
        bw = paint.text_width(title, paint.ui(11, True)) + 28
        x = min(26 + name_w + 16, self.canvas.frame().size.width - bw - 20)
        self.followButton.setTitle_(title)
        self.followButton.setFrame_(NSMakeRect(x, ARTIST_HEAD - 20 - 26, bw, 22))

    def toggleFollow_(self, sender):
        a = self.artist
        following = a["following"]
        client = self.client

        def done(_, error):
            if error:
                return self.flashError(error)
            a["following"] = not following
            self.renderArtist(False)
        cocoa.in_background(lambda: (client.unsave if following else client.save)([a["info"]["uri"]]), done)

    def artistItems(self, width, a):
        """The header, then the popular songs across the page in up to two columns of five, then the
        albums and singles standing on a shelf that runs the full width, so the page stays balanced."""
        canvas, info = self.canvas, a["info"]
        items = [{"rect": NSMakeRect(0, 0, width, ARTIST_HEAD), "draw": lambda e, s: draw_artist_header(e, info, canvas)}]
        y0 = ARTIST_HEAD + 16
        inner = width - 52
        items.append({"rect": NSMakeRect(26, y0, inner, 22), "draw": lambda e, s: draw_section(e, u"Popular")})
        songs = a["songs"][:10]
        cols = 2 if len(songs) > 5 and inner >= 640 else 1
        col_w = (inner - 26 * (cols - 1)) / float(cols)
        per_col = (len(songs) + cols - 1) // cols if cols > 1 else len(songs)
        for i, t in enumerate(songs):
            c, r = divmod(i, per_col) if cols > 1 else (0, i)
            rect = NSMakeRect(26 + c * (col_w + 26), y0 + 22 + r * 34, col_w, 34)
            items.append(self.songItem(rect, t, i, lambda i=i: self.playSongs(songs, i),
                                       show_album=True))
        y = y0 + 22 + per_col * 34
        if not songs:
            items.append({"rect": NSMakeRect(26, y + 8, inner, 20),
                          "draw": lambda e, s: paint.text(u"Spotify found no songs for this artist.", e["rect"],
                                                          paint.ui(12), "#6b6b6b")})
            y += 30
        y += 22
        items.append({"rect": NSMakeRect(26, y, inner, 22), "draw": lambda e, s: draw_section(
            e, u"Albums and Singles" if a["albums"] else u"No albums on Spotify")})
        wall_top = y + 30
        shelf, end = self.shelf(canvas, width, a["albums"], wall_top, 1)
        for it in shelf:
            if "data" in it:
                it["draw"] = lambda e, s: draw_album_cell(e, canvas)
        items += shelf
        canvas.backdrop = lambda rect: (paint.fill(rect, "#ffffff"), draw_wall(
            NSIntersectionRect(rect, NSMakeRect(0, wall_top, width, 1e6))))
        canvas.top_fill = lambda rect: draw_artist_backdrop(rect, width, info, canvas)
        canvas.bottom_fill = draw_wall
        return items, end

    def songItem(self, rect, t, n, play, show_album=False):
        canvas = self.canvas
        return {"rect": rect, "data": t, "selectable": True,
                "draw": lambda e, s: draw_song_row(e, t, n, s, canvas, show_album, t["uri"] == self.playing_uri),
                "double": lambda e: play(), "menu": lambda e: self.trackMenu(t, play)}

    # ---- search -------------------------------------------------------------------------------------
    def open_search(self, text):
        client = self.client
        self.searchField.setStringValue_(text)

        def work():
            found = client.search(text)
            return ([slim_track(t) for t in (found.get("tracks") or {}).get("items") or [] if t],
                    [slim_artist(a) for a in (found.get("artists") or {}).get("items") or [] if a],
                    [slim_album(a) for a in (found.get("albums") or {}).get("items") or [] if a])

        def done(result):
            songs, artists, albums = result
            self.found = (text, songs, artists, albums)
            self.showPage(self.canvasPage)
            self.canvas.backdrop = self.canvas.top_fill = self.canvas.bottom_fill = None
            self.canvas.builder = lambda width: self.searchItems(width)
            self.canvas.nearEnd = None
            self.canvas.rebuild()
            self.canvas.scrollToTop()
            self.setStatus(u"%s, %s, %s" % (paint.plural(len(songs), u"song"), paint.plural(len(artists), u"artist"),
                                            paint.plural(len(albums), u"album")))
        self.fetch(work, done, u"Searching Spotify…")

    def searchItems(self, width):
        text, songs, artists, albums = self.found
        canvas = self.canvas
        items = []
        heading = u"Results for “%s”" % text
        items.append({"rect": NSMakeRect(24, 16, width - 48, 26), "draw": lambda e, s: paint.text(
            heading, e["rect"], paint.font("Helvetica-Bold", 20, True), "#1d1d1d")})
        if not (songs or artists or albums):
            items.append({"rect": NSMakeRect(24, 54, width - 48, 20), "draw": lambda e, s: paint.text(
                u"Spotify found nothing for that. Check the spelling, or try fewer words.", e["rect"], paint.ui(12), "#6b6b6b")})
            return items, 100
        y = 56
        top_artist = artists and artists[0]["name"].lower() == text.lower()
        top = ("artist", artists[0]) if top_artist else (("song", songs[0]) if songs else
                                                          (("artist", artists[0]) if artists else ("album", albums[0])))
        card = NSMakeRect(24, y, 250, 176)

        def open_top(e):
            kind, obj = top
            if kind == "song" and obj.get("album_id"):
                self.go(("album", obj["album_id"]))
            elif kind != "song":
                self.go((kind, obj["id"]))
        items.append({"rect": card, "draw": lambda e, s: draw_top_card(e, top, canvas), "click": open_top})

        def play_top(e):
            kind, obj = top
            if kind == "song":
                self.playSongs(songs, 0)
            else:
                self.app.playFrom(obj["uri"], None, [], 0, None)
        items.append({"rect": NSMakeRect(24 + 14 + 92 + 12, y + 14 + 14 + 8 + 92 - 24, 74, 24),
                      "draw": lambda e, s: draw_pill(e["rect"], u"▶  Play", True), "click": play_top})
        sx = 24 + 250 + 22
        sw = width - sx - 24
        items.append({"rect": NSMakeRect(sx, y, sw, 22), "draw": lambda e, s: draw_section(e, u"Songs")})
        for i, t in enumerate(songs[:4]):
            items.append(self.songItem(NSMakeRect(sx, y + 22 + i * 34, sw, 34), t, None,
                                       lambda i=i: self.playSongs(songs, i)))
        y += 176 + 18
        if artists:
            items.append({"rect": NSMakeRect(24, y, width - 48, 22), "draw": lambda e, s: draw_section(e, u"Artists")})
            fit = max(1, int((width - 48 + 26) // (72 + 26)))
            for i, a in enumerate(artists[:fit]):
                rect = NSMakeRect(24 + i * (72 + 26) - 8, y + 32, 88, 98)
                items.append({"rect": rect, "data": a, "draw": lambda e, s: draw_artist_cell(e, 72, canvas, small=True),
                              "click": lambda e: self.go(("artist", e["data"]["id"])), "cache": circle_key})
            y += 32 + 98 + 10
        if albums:
            items.append({"rect": NSMakeRect(24, y, width - 48, 22), "draw": lambda e, s: draw_section(e, u"Albums")})
            fit = max(1, int((width - 48 + 20) // (104 + 20)))
            for i, alb in enumerate(albums[:fit]):
                rect = NSMakeRect(24 + i * (104 + 20), y + 32, 96, 96 * CASE_RATIO)
                items.append({"rect": rect, "data": alb, "draw": lambda e, s: draw_album_cell(e, canvas),
                              "click": lambda e: self.go(("album", e["data"]["id"])),
                              "menu": lambda e: self.albumMenu(e["data"]), "cache": case_key})
            y += 32 + 96 * CASE_RATIO + 14
        return items, y + 10

    # ---- a scripted benchmark (DebugOpenView bench, with DebugPerf on) ----------------------------------
    def bench(self):
        """Scroll the shelf, Liked Songs and the artists on their own and log how long each step takes
        to draw, so lag can be measured without anyone at the Mac."""
        self.go(("albums",))
        self.performSelector_withObject_afterDelay_("benchShelf:", None, 10.0)

    def benchScroll(self, scroll, name, step, steps):
        import perf
        clip, times = scroll.contentView(), []
        for i in list(range(steps)) + list(reversed(range(steps))):
            clip.scrollToPoint_(NSMakePoint(0, i * step))
            scroll.reflectScrolledClipView_(clip)
            start = time.time()
            self.window.displayIfNeeded()
            times.append((time.time() - start) * 1000)
        down, up = sorted(times[:steps]), sorted(times[steps:])
        for label, t in ((u"first pass", down), (u"second pass", up)):
            perf.mark(u"bench %s, %s: %d steps of %d px, median %.1f ms, 90%% %.1f ms, worst %.1f ms" % (
                name, label, len(t), step, t[len(t) // 2], t[int(len(t) * 0.9)], t[-1]))

    def benchShelf_(self, _):
        import perf
        self.benchScroll(self.gridCanvas.enclosingScrollView(), u"albums shelf", 40, 60)
        start = time.time()
        snapshot(self.gridPage)
        perf.mark(u"bench snapshot of the shelf page (used by fades and flips): %.0f ms" % ((time.time() - start) * 1000))
        self.go(("liked",))
        self.performSelector_withObject_afterDelay_("benchLiked:", None, 6.0)

    def benchLiked_(self, _):
        self.benchScroll(self.list.scroll, u"Liked Songs", 40, 60)
        self.go(("artists",))
        self.performSelector_withObject_afterDelay_("benchArtists:", None, 8.0)

    def benchArtists_(self, _):
        import perf
        self.benchScroll(self.gridCanvas.enclosingScrollView(), u"artists", 30, 60)
        perf.mark(u"bench done")

    # ---- hidden hook ---------------------------------------------------------------------------------
    def debugOpen(self, view):
        if view.startswith("album-search:") or view.startswith("artist-search:"):
            kind, text = view.split(":", 1)
            kind = kind.split("-")[0]
            client = self.client

            def work():   # open the first album or artist Spotify finds for the text
                found = (client.search(text, kind).get(kind + "s") or {}).get("items") or []
                return found[0]["id"] if found else None
            cocoa.in_background(work, lambda found, error: found and self.go((kind, found)))
            return
        if view in ("artist-bounce", "albums-bounce"):
            self.bounce = view
            view = view.split("-")[0]
        if view.startswith("search:"):
            self.go(("search", view[7:]))
        elif view in ("liked", "albums", "artists"):
            self.go((view,))
        elif view == "playlist":
            self.debug = "playlist"
            if self.playlists:
                self.debug = None
                self.go(("playlist", self.playlists[0]["id"]))
        elif view in ("album", "artist"):
            self.debug = view
            self.go(("albums",) if view == "album" else ("artists",))


def snapshot(view):
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    img = NSImage.alloc().initWithSize_(view.bounds().size)
    img.addRepresentation_(rep)
    return img


class FadeView(NSView):
    DURATION = 0.2

    def initWithFrame_(self, frame):
        self = super(FadeView, self).initWithFrame_(frame)
        if self:
            self.old, self.new, self.t, self.target, self.timer, self.started = None, None, 0.0, None, None, 0
        return self

    def isOpaque(self):
        return True

    def start(self, old):
        self.old, self.new, self.t = old, None, 0.0
        self.setHidden_(False)
        self.setNeedsDisplay_(True)

    def begin_(self, _):
        if self.target is None:
            return self.finish()
        self.new = snapshot(self.target)
        self.started = time.time()
        if self.timer is None:
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / 30.0, self, "tick:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def tick_(self, timer):
        self.t = min(1.0, (time.time() - self.started) / self.DURATION)
        self.setNeedsDisplay_(True)
        if self.t >= 1.0:
            self.finish()

    def finish(self):
        if self.timer:
            self.timer.invalidate()
            self.timer = None
        self.old = self.new = self.target = None
        self.setHidden_(True)

    def drawRect_(self, rect):
        if self.old is not None:
            self.old.drawInRect_fromRect_operation_fraction_(self.bounds(), NSZeroRect, NSCompositeCopy, 1.0)
        if self.new is not None:
            self.new.drawInRect_fromRect_operation_fraction_(self.bounds(), NSZeroRect, NSCompositeSourceOver,
                                                             self.t * self.t * (3 - 2 * self.t))


_linen = {}


def linen(size):
    """Lion's dark linen, which shows behind the pane while it turns over."""
    if "tile" not in _linen:
        tile = NSImage.alloc().initWithSize_(NSMakeSize(96, 96))
        tile.lockFocus()
        paint.fill(NSMakeRect(0, 0, 96, 96), "#2e3034")
        rnd = random.Random(5)
        for i in range(96):
            paint.fill(NSMakeRect(0, i, 96, 1), white(1, rnd.uniform(0, 0.035)) if i % 2 else white(0, rnd.uniform(0.02, 0.08)))
            paint.fill(NSMakeRect(i, 0, 1, 96), white(1, rnd.uniform(0, 0.03)) if i % 2 else white(0, rnd.uniform(0.02, 0.07)))
        tile.unlockFocus()
        _linen["tile"] = NSColor.colorWithPatternImage_(tile)
    img = NSImage.alloc().initWithSize_(size)
    img.lockFocus()
    _linen["tile"].set()
    NSBezierPath.fillRect_(NSMakeRect(0, 0, size.width, size.height))
    NSGradient.alloc().initWithStartingColor_endingColor_(white(0, 0), white(0, 0.45)).drawInRect_relativeCenterPosition_(
        NSMakeRect(0, 0, size.width, size.height), NSMakePoint(0, 0))
    img.unlockFocus()
    return img


class FlipView(NSView):
    """Turns the pane over like a Dashboard widget: the old view on the front of a card, the new one
    on its back, rotated by Core Animation on the GPU over Lion's linen."""
    DURATION = 0.6

    def initWithFrame_(self, frame):
        self = super(FlipView, self).initWithFrame_(frame)
        if self:
            self.setLayer_(CALayer.layer())
            self.setWantsLayer_(True)
            self.setHidden_(True)
            self.old, self.target, self.direction, self.card = None, None, 1, None
        return self

    def hitTest_(self, point):
        return None if self.isHidden() else self      # no clicks reach the views while it turns

    def start(self, old):
        b = self.bounds()
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        root = self.layer()
        root.setSublayers_([])
        root.setContents_(linen(b.size))      # on the root, so the turning card can't dip behind it
        perspective = CATransform3DMakeRotation(0, 0, 1, 0)
        perspective.m34 = -1.0 / 1600
        root.setSublayerTransform_(perspective)
        card = CATransformLayer.layer()
        card.setFrame_(((0, 0), (b.size.width, b.size.height)))
        front = CALayer.layer()
        front.setFrame_(((0, 0), (b.size.width, b.size.height)))
        front.setContents_(old)
        front.setDoubleSided_(False)
        card.addSublayer_(front)
        root.addSublayer_(card)
        CATransaction.commit()
        self.card = card
        self.setHidden_(False)

    def begin_(self, _):
        if self.target is None or self.card is None:
            return self.finish_(None)
        b = self.bounds()
        # `defaults write page.zepto.kassett DebugAnimationScale 10` slows the flip down to check it.
        self.DURATION = 0.6 * (NSUserDefaults.standardUserDefaults().floatForKey_("DebugAnimationScale") or 1)
        CATransaction.begin()
        CATransaction.setDisableActions_(True)
        back = CALayer.layer()
        back.setFrame_(((0, 0), (b.size.width, b.size.height)))
        back.setContents_(snapshot(self.target))
        back.setDoubleSided_(False)
        back.setTransform_(CATransform3DMakeRotation(math.pi, 0, 1, 0))
        self.card.addSublayer_(back)
        angle = math.pi * self.direction
        CATransaction.commit()
        ease = CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseInEaseOut)
        turn = CABasicAnimation.animationWithKeyPath_("transform.rotation.y")
        turn.setFromValue_(0.0)
        turn.setToValue_(angle)
        turn.setDuration_(self.DURATION)
        turn.setTimingFunction_(ease)
        # The card's own transform stays as it is (a half turn as the model value decomposes ambiguously
        # and would play backwards); the animation holds its end until the card is thrown away.
        turn.setRemovedOnCompletion_(False)
        turn.setFillMode_("forwards")
        self.card.addAnimation_forKey_(turn, "turn")
        self.performSelector_withObject_afterDelay_("finish:", None, self.DURATION + 0.02)

    def finish_(self, _):
        self.setHidden_(True)
        self.layer().setSublayers_([])
        self.layer().setContents_(None)
        self.card = self.target = None


class GridBar(LibraryFlipped):
    def initWithFrame_(self, frame):
        self = super(GridBar, self).initWithFrame_(frame)
        if self:
            self.title, self.count = u"Albums", u""
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        paint.fill(b, "#fafafa", "#e6e6e6")
        paint.fill(NSMakeRect(0, b.size.height - 1, b.size.width, 1), "#bdbdbd")
        paint.text(self.title, NSMakeRect(16, 7, b.size.width / 2, 17), paint.ui(13, True), "#1d1d1d")
        if self.count:
            paint.text(self.count, NSMakeRect(b.size.width - 216, 9, 200, 15), paint.ui(11), "#555555", NSRightTextAlignment)
        else:
            paint.text(u"Sort by", NSMakeRect(b.size.width - 216, 9, 60, 15), paint.ui(11), "#555555", NSRightTextAlignment)


# ---- drawing the canvas items -------------------------------------------------------------------------
def draw_section(e, title):
    r = e["rect"]
    paint.text(title, NSMakeRect(r.origin.x, r.origin.y, r.size.width, 17), paint.ui(13, True), "#1d1d1d")
    paint.fill(NSMakeRect(r.origin.x, r.origin.y + r.size.height - 1, r.size.width, 1), "#dcdcdc")


def draw_album_cell(e, canvas, year=False):
    a = e["data"]
    draw_case(e["rect"], canvas, a["image"], a["name"], a["artist"], a["year"])


def draw_artist_cell(e, d, canvas, small=False):
    r, a = e["rect"], e["data"]
    circle = NSMakeRect(r.origin.x + (r.size.width - d) / 2.0, r.origin.y, d, d)
    draw_cover(circle, a["image"], a["name"], canvas, round_=True)
    paint.text(a["name"], NSMakeRect(r.origin.x, r.origin.y + d + 7, r.size.width, 15), paint.ui(11, True), "#1d1d1d",
               NSCenterTextAlignment)


def draw_song_row(e, t, n, selected, canvas, show_album, playing):
    r = e["rect"]
    x, y, w = r.origin.x, r.origin.y, r.size.width
    if selected:
        paint.fill(r, "#5b8fdc", "#3570cf")
    else:
        paint.fill(NSMakeRect(x, y + 33, w, 1), "#ededed")
    fg = white(1) if selected else hexc("#1d1d1d")
    gray = white(1, 0.85) if selected else hexc("#5f5f5f")
    left = x
    if n is not None:
        if playing:
            glyphs.draw_at("now_playing", x, y + 11, white(1) if selected else hexc("#2f6fd1"))
        else:
            paint.text(unicode(n + 1), NSMakeRect(x, y + 10, 14, 15), paint.ui(12), gray, NSRightTextAlignment)
        left = x + 24
    draw_cover(NSMakeRect(left, y + 4, 26, 26), t["image"], t["album"] or t["name"], canvas, caption=False,
               shadow=False, small=True)
    tx = left + 36
    side = 150 if show_album else min(190, w * 0.35)
    paint.text(t["name"], NSMakeRect(tx, y + 9, w - (tx - x) - side - 50, 16), paint.ui(12), fg)
    paint.text(t["album"] if show_album else artist_line(t), NSMakeRect(x + w - side - 44, y + 9, side, 16), paint.ui(12), gray)
    paint.text(paint.fmt(t["duration"]), NSMakeRect(x + w - 40, y + 9, 36, 16), paint.ui(12), gray, NSRightTextAlignment)


def draw_artist_backdrop(area, width, info, canvas):
    """The header's brown wash and the artist's photo, laid out for the header band but drawn
    wherever `area` is, so above the page (when scrolling bounces) the picture simply carries on."""
    base = NSMakeRect(0, 0, width, ARTIST_HEAD)
    img = art.shared().image(info.get("big"), lambda: canvas.setNeedsDisplayInRect_(base))
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath.clipRect_(area)
    paint.gradient(("#7a5532", 0), ("#3a2414", 0.6), ("#1e130b", 1)).drawFromPoint_toPoint_options_(
        NSMakePoint(0, -ARTIST_HEAD * 0.4), NSMakePoint(width * 0.6, ARTIST_HEAD * 1.4),
        NSGradientDrawsBeforeStartingLocation | NSGradientDrawsAfterEndingLocation)
    if img is not None and img.size().width and img.size().height:
        photo = NSMakeRect(width * 0.45, 0, width * 0.55, ARTIST_HEAD)
        size = img.size()
        scale = max(photo.size.width / size.width, photo.size.height / size.height)
        whole = NSMakeRect(photo.origin.x + (photo.size.width - size.width * scale) / 2.0,
                           (ARTIST_HEAD - size.height * scale) / 2.0, size.width * scale, size.height * scale)
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath.clipRect_(NSMakeRect(photo.origin.x, -1e5, photo.size.width, 2e5))
        img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            whole, NSZeroRect, NSCompositeSourceOver, 0.9, True, {NSImageHintInterpolation: NSImageInterpolationHigh})
        NSGraphicsContext.restoreGraphicsState()
        paint.fill(NSMakeRect(photo.origin.x, area.origin.y, photo.size.width, area.size.height),
                   ("#3a2414", 0), (hexc("#3a2414", 0.0), 0.6), angle=0)
        paint.fill(NSIntersectionRect(area, base), white(0, 0.0), white(0, 0.35)) if NSIntersectsRect(area, base) else None
    else:
        NSGradient.alloc().initWithStartingColor_endingColor_(hexc("#ffd696", 0.45), hexc("#ffd696", 0)) \
            .drawInRect_relativeCenterPosition_(base, NSMakePoint(0.5, -0.4))
    NSGraphicsContext.restoreGraphicsState()


def draw_artist_header(e, info, canvas):
    r = e["rect"]
    draw_artist_backdrop(r, r.size.width, info, canvas)
    paint.fill(NSMakeRect(0, r.size.height - 1, r.size.width, 1), white(0, 0.4))
    paint.text(u"ARTIST", NSMakeRect(26, r.size.height - 20 - 44 - 22, 200, 14), paint.ui(10, True), white(1, 0.85), kern=1)
    paint.text(info["name"], NSMakeRect(26, r.size.height - 20 - 48, r.size.width - 200, 52),
               paint.font("Helvetica-Bold", 44, True), white(1), kern=-0.8, sh=paint.shadow(2, 6, white(0, 0.5)))


def draw_top_card(e, top, canvas):
    r = e["rect"]
    shape = paint.rounded(NSInsetRect(r, 0.5, 0.5), 6)
    paint.fill(shape, "#f7f7f7", "#e9e9e9")
    paint.stroke(shape, "#d0d0d0", 1)
    x, y = r.origin.x + 14, r.origin.y + 14
    paint.text(u"TOP RESULT", NSMakeRect(x, y, 200, 14), paint.ui(10, True), "#5f5f5f", kern=0.8)
    kind, obj = top
    cover = NSMakeRect(x, y + 22, 92, 92)
    if kind == "artist":
        draw_cover(cover, obj["image"], obj["name"], canvas, round_=True)
        line = u"Artist"
    elif kind == "song":
        draw_cover(cover, obj.get("big"), obj["album"] or obj["name"], canvas, caption=False)
        line = u"Song · " + artist_line(obj)
    else:
        draw_cover(cover, obj["image"], obj["name"], canvas)
        line = u"Album · " + obj["artist"]
    paint.text(obj["name"], NSMakeRect(x, y + 124, r.size.width - 28, 19), paint.ui(15, True), "#1d1d1d")
    paint.text(line, NSMakeRect(x, y + 143, r.size.width - 28, 15), paint.ui(11), "#555555")
