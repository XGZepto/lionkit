# -*- coding: utf-8 -*-
"""The cassette deck (Now Playing) and the mini player.

Everything is drawn in flipped views so the coordinates read like design/kassett/Main.dc.html.
The reels turn the way real tape does: the tape moves at a constant speed, so the reel with less
tape on it spins faster, and the packs grow by area rather than by diameter."""
import math
import time

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403

import art
import glyphs
import paint
from paint import hexc, white

FPS = 24.0
REEL_SPEED = 150.0 * 37.5      # degrees per second times radius: a 75 px pack turns once in 2.4 s
WHIRR = 0.45                   # seconds a seek or skip takes to wind the tape
HUB, FULL = 20.0, 55.0         # radius of an empty and a full tape pack, px
SHELLS = {"black": ("#414146", "#222226"), "smoke": ("#6d737b", "#3b4047"), "white": ("#f2efe8", "#d5d0c3")}
INK = hexc("#26337f")
DECK_W, DECK_H, BAR = 780, 448, 30


def pack_radii(p):
    """Supply and take-up pack radii when a fraction p of the tape has played."""
    p = max(0.0, min(1.0, p))
    area = FULL * FULL - HUB * HUB
    return math.sqrt(HUB * HUB + area * (1 - p)), math.sqrt(HUB * HUB + area * p)


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def label_fonts(size=22):
    return (paint.font("MarkerFelt-Wide", size), paint.font("Noteworthy-Light", round(size * 0.68)))


def flipped_image(w, h, draw):
    img = NSImage.alloc().initWithSize_(NSMakeSize(w, h))
    img.lockFocusFlipped_(True)
    draw()
    img.unlockFocus()
    return img


def draw_part(img, rect, op=NSCompositeSourceOver):
    """Draw the part of a cached image under `rect` of a flipped view (image space isn't flipped)."""
    h = img.size().height
    src = NSMakeRect(rect.origin.x, h - rect.origin.y - rect.size.height, rect.size.width, rect.size.height)
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(rect, src, op, 1.0, True, None)


class FlippedView(NSView):
    def isFlipped(self):
        return True


# ---- the deck's brushed-aluminium panel -------------------------------------------------------------
def draw_brushed(w, h, top_line=True):
    paint.fill(NSMakeRect(0, 0, w, h), "#e0e0e0", "#b7b7b7")
    for y in range(0, int(h), 7):
        paint.fill(NSMakeRect(0, y, w, 3), white(0, 0.025))
        paint.fill(NSMakeRect(0, y + 3, w, 4), white(1, 0.05))
    for y in range(0, int(h), 4):
        paint.fill(NSMakeRect(0, y, w, 1), white(1, 0.12))
        paint.fill(NSMakeRect(0, y + 1, w, 1), white(0, 0.04))
    if top_line:
        paint.fill(NSMakeRect(0, 0, w, 1), "#9c9c9c")
        paint.fill(NSMakeRect(0, 1, w, 1), white(1, 0.8))


STRIP = NSMakeRect(22, 330, 736, 104)     # the recessed control strip
INDEX = NSMakeRect(490, 32, 268, 284)     # the dark window that holds the J-card and the counter
LEDS = {"green": "#5fe04a", "amber": "#ffb12e"}


def draw_recess(r, radius, top, bottom, depth=0.85):
    """A window cut into the faceplate: light catches its lower edge, the inside is dark and deep."""
    paint.fill(paint.rounded(NSOffsetRect(r, 0, 1), radius), white(1, 0.8))
    shape = paint.rounded(r, radius)
    paint.fill(shape, top, bottom)
    paint.inner_shadow(shape, 3, 8, white(0, depth))
    paint.stroke(paint.rounded(NSInsetRect(r, 0.5, 0.5), radius - 0.5), white(0, 0.55))
    return shape


def draw_strip(r):
    paint.fill(paint.rounded(NSOffsetRect(r, 0, 1), 8), white(1, 0.75))
    shape = paint.rounded(r, 8)
    paint.fill(shape, "#cbcbcb", "#b3b3b3")

    def brushing():
        for y in range(int(r.origin.y), int(r.origin.y + r.size.height), 3):
            paint.fill(NSMakeRect(r.origin.x, y, r.size.width, 1), white(1, 0.10))
    paint.clipped(shape, brushing)
    paint.inner_shadow(shape, 1, 3, white(0, 0.35))


def draw_slot(r):
    paint.fill(paint.corners(NSOffsetRect(r, 0, 1), 2, 2, 6, 6), white(1, 0.7))
    shape = paint.corners(r, 2, 2, 6, 6)
    paint.fill(shape, "#141517")
    paint.inner_shadow(shape, 2, 3, white(0, 0.9))


def draw_led(cx, cy, name):
    """A small indicator light: green, amber, or None for off."""
    lamp = paint.oval(cx, cy, 3.2)
    if name is None:
        paint.fill(paint.oval(cx, cy + 0.6, 3.2), white(1, 0.6))
        paint.fill(lamp, "#3b2f25")
        paint.inner_shadow(lamp, 1, 1, white(0, 0.6))
        return
    color = hexc(LEDS[name])
    paint.with_shadow(paint.shadow(0, 6, color), lambda: paint.fill(lamp, color))
    NSGradient.alloc().initWithStartingColor_endingColor_(white(1, 0.95), color).drawInBezierPath_relativeCenterPosition_(
        lamp, NSMakePoint(-0.25, -0.35))


class DeckView(FlippedView):
    def initWithFrame_(self, frame):
        self = super(DeckView, self).initWithFrame_(frame)
        if self:
            self.bg = None
            self.onKey = None
            self.labels = []          # (text, rect, led name or None) printed above the controls
            self.slots = []
            self.leds = {}
            self.controlsShown = True
        return self

    def isOpaque(self):
        return True

    def mouseDownCanMoveWindow(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def keyDown_(self, event):
        if not (self.onKey and self.onKey(event)):
            super(DeckView, self).keyDown_(event)

    def setLed(self, led, name):
        if self.leds.get(led) != name:
            self.leds[led] = name
            for text, r, which in self.labels:
                if which == led:
                    self.setNeedsDisplayInRect_(NSInsetRect(r, -14, -8))

    def drawRect_(self, rect):
        b = self.bounds()
        if self.bg is None:
            self.bg = flipped_image(b.size.width, b.size.height, self.drawPanel)
        draw_part(self.bg, rect, NSCompositeCopy)
        if not self.controlsShown:
            return
        for r in self.slots:
            if NSIntersectsRect(rect, NSInsetRect(r, -2, -2)):
                draw_slot(r)
        f = paint.font("Helvetica-Bold", 7.5, True)
        for text, r, led in self.labels:
            if not NSIntersectsRect(rect, NSInsetRect(r, -14, -8)):
                continue
            paint.text(text, r, f, "#474747", NSCenterTextAlignment, kern=1.3, sh=paint.engraved())
            if led:
                tw = paint.text_width(text, f, 1.3)
                draw_led(r.origin.x + (r.size.width - tw) / 2.0 - 8, r.origin.y + 4.5, self.leds.get(led))

    def drawPanel(self):
        w, h = self.bounds().size.width, self.bounds().size.height
        draw_brushed(w, h)
        paint.text(u"KASSETT", NSMakeRect(26, 10, 200, 16), paint.font("Helvetica-Bold", 12, True), "#3c3c3c",
                   kern=4, sh=paint.engraved())
        paint.text(u"STEREO CASSETTE DECK", NSMakeRect(w - 26 - 300, 12, 300, 12), paint.font("Helvetica-Bold", 8, True),
                   "#5c5c5c", NSRightTextAlignment, kern=2.2, sh=paint.engraved())
        draw_recess(INDEX, 10, "#17181b", "#26282c")
        draw_strip(STRIP)


# ---- the cassette in its well ------------------------------------------------------------------------
class CassetteView(FlippedView):
    """452 x 286: the dark well, the cassette shell, its label, the window and the reels."""
    WELL = NSMakeRect(0, 0, 452, 284)
    SHELL = (26, 16)
    HUBS = ((171, 127), (281, 127))

    def initWithFrame_(self, frame):
        self = super(CassetteView, self).initWithFrame_(frame)
        if self:
            self.title, self.subtitle = u"Kassett", u""
            self.shell = "black"
            self.p = 0.0
            self.angles = [0.0, 37.0]
            self.bg, self.bg_key, self.overlay = None, None, None
        return self

    def mouseDownCanMoveWindow(self):
        return True

    def setLabel(self, title, subtitle):
        if (title, subtitle) != (self.title, self.subtitle):
            self.title, self.subtitle = title, subtitle
            self.setNeedsDisplay_(True)

    def setProgress(self, p):
        self.p = max(0.0, min(1.0, p))
        if self.key() != self.bg_key:
            self.setNeedsDisplay_(True)

    def key(self):
        left, right = pack_radii(self.p)
        return (self.title, self.subtitle, self.shell, int(left * 2), int(right * 2))

    def turn(self, degrees_at_mid):
        """Advance the reels as if `degrees_at_mid` had turned a mid-sized pack."""
        left, right = pack_radii(self.p)
        self.angles[0] = (self.angles[0] + degrees_at_mid * 37.5 / left) % 360
        self.angles[1] = (self.angles[1] + degrees_at_mid * 37.5 / right) % 360
        for cx, cy in self.HUBS:
            self.setNeedsDisplayInRect_(NSMakeRect(cx - 21, cy - 21, 42, 42))

    def drawRect_(self, rect):
        if self.bg is None or self.key() != self.bg_key:
            self.bg_key = self.key()
            self.bg = flipped_image(452, 286, self.drawBody)
        if self.overlay is None:
            self.overlay = flipped_image(452, 286, self.drawGlass)
        draw_part(self.bg, rect)
        for (cx, cy), angle in zip(self.HUBS, self.angles):
            if NSIntersectsRect(rect, NSMakeRect(cx - 21, cy - 21, 42, 42)):
                draw_hub(cx, cy, angle)
        draw_part(self.overlay, rect)

    def drawBody(self):
        paint.fill(paint.rounded(NSOffsetRect(self.WELL, 0, 1), 10), white(1, 0.85))
        paint.fill(paint.rounded(self.WELL, 10), "#f6f6f6", "#9b9b9b")          # the chrome door frame
        paint.stroke(paint.rounded(NSInsetRect(self.WELL, 0.5, 0.5), 9.5), white(0, 0.38))
        bay = paint.rounded(NSInsetRect(self.WELL, 4, 4), 7)
        paint.fill(bay, "#121315", "#222428")
        paint.inner_shadow(bay, 3, 10, white(0, 0.9))

        sx, sy = self.SHELL
        top, bottom = SHELLS.get(self.shell, SHELLS["black"])
        shell = paint.rounded(NSMakeRect(sx, sy, 400, 252), 12)
        paint.with_shadow(paint.shadow(3, 10, white(0, 0.7)), lambda: paint.fill(shell, bottom))
        paint.fill(shell, top, bottom)
        paint.inner_shadow(shell, -2, 4, white(0, 0.35))
        paint.clipped(shell, lambda: paint.fill(NSMakeRect(sx + 6, sy, 388, 1), white(1, 0.22)))
        for x, y in ((9, 9), (381, 9), (9, 233), (381, 233)):
            draw_screw(sx + x + 5, sy + y + 5, 5)
        draw_head_opening(sx + 72, sy + 196)
        draw_label(sx + 22, sy + 16, self.title, self.subtitle, self.p)

    def drawGlass(self):
        """The smoked acrylic door: a light tint, a reflection across it and a pull notch at the top."""
        sx, sy = self.SHELL
        win = NSMakeRect(sx + 22 + 68, sy + 16 + 64, 220, 62)
        paint.clipped(paint.rounded(win, 8), lambda: paint.fill(
            NSMakeRect(win.origin.x, win.origin.y, 220, 26), white(1, 0.16), white(1, 0)))
        inner = NSInsetRect(self.WELL, 4, 4)
        door = paint.rounded(inner, 7)
        paint.fill(door, white(0, 0.10))
        paint.clipped(door, lambda: paint.gradient(
            (white(1, 0.18), 0), (white(1, 0.05), 0.34), (white(1, 0), 0.35), (white(1, 0.035), 0.6),
            (white(1, 0), 0.78)).drawInRect_angle_(inner, 62))
        paint.stroke(paint.rounded(NSInsetRect(inner, 1, 1), 6), white(1, 0.10), 1)
        notch = paint.corners(NSMakeRect(196, 4, 60, 6), 0, 0, 3, 3)
        paint.fill(paint.corners(NSMakeRect(196, 5, 60, 6), 0, 0, 3, 3), white(1, 0.12))
        paint.fill(notch, "#0a0a0b")


def draw_screw(cx, cy, r):
    head = paint.oval(cx, cy, r)
    paint.fill(head, white(0, 0.5))
    inner = paint.oval(cx, cy, r - 1)
    NSGradient.alloc().initWithStartingColor_endingColor_(hexc("#f4f4f4"), hexc("#8d8d8d")).drawInBezierPath_relativeCenterPosition_(
        inner, NSMakePoint(-0.2, -0.3))
    slot = NSBezierPath.bezierPath()
    slot.moveToPoint_(NSMakePoint(cx - r * 0.55, cy + r * 0.3))
    slot.lineToPoint_(NSMakePoint(cx + r * 0.55, cy - r * 0.3))
    paint.stroke(slot, white(0, 0.45), 1.2)


def draw_head_opening(x, y):
    """The trapezoid at the bottom of the shell where the tape meets the head."""
    t = NSBezierPath.bezierPath()
    t.moveToPoint_(NSMakePoint(x + 23, y))
    t.lineToPoint_(NSMakePoint(x + 233, y))
    t.lineToPoint_(NSMakePoint(x + 256, y + 56))
    t.lineToPoint_(NSMakePoint(x, y + 56))
    t.closePath()
    paint.fill(t, white(0, 0.18), white(0, 0.3))
    paint.fill(NSMakeRect(x + 23, y, 210, 1), white(1, 0.07))
    cx = x + (256 - 140) / 2.0
    holes = [("o", 11), ("r", 14), ("r", 14), ("o", 11)]
    for kind, w in holes:
        if kind == "o":
            shape = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx, y + 22.5, 11, 11))
        else:
            shape = paint.rounded(NSMakeRect(cx, y + 23, 14, 10), 2)
        sb = shape.copy()
        tr = NSAffineTransform.transform()
        tr.translateXBy_yBy_(0, 1)
        sb.transformUsingAffineTransform_(tr)
        paint.fill(sb, white(1, 0.15))
        paint.fill(shape, "#0c0c0d")
        paint.inner_shadow(shape, 1, 2, white(0, 0.9))
        cx += w + 30


def draw_label(x, y, title, subtitle, p):
    """The paper label: ruled lines, side A, the handwriting, the reel window and the stripes."""
    lab = NSMakeRect(x, y, 356, 162)
    shape = paint.rounded(lab, 5)
    paint.with_shadow(paint.shadow(1, 2, white(0, 0.5)), lambda: paint.fill(shape, "#ece2c6"))
    paint.fill(shape, "#f6efdb", "#ece2c6")

    def body():
        rule = hexc("#466eaa", 0.28)
        paint.fill(NSMakeRect(x, y + 30, 356, 1), rule)
        paint.fill(NSMakeRect(x, y + 54, 356, 1), rule)
        side = paint.rounded(NSMakeRect(x + 13, y + 9, 24, 24), 3.5)
        paint.stroke(side, "#2d2d2d", 2)
        paint.text(u"A", NSMakeRect(x + 12, y + 9, 26, 24), paint.font("Helvetica-Bold", 20, True), "#2d2d2d",
                   NSCenterTextAlignment)
        big, small = label_fonts()
        # Write on the ruled lines: baselines sit just above them, like handwriting on paper.
        paint.text(title, NSMakeRect(x + 50, y + 28.5 - big.ascender(), 292, 30), big, INK)
        paint.text(subtitle, NSMakeRect(x + 52, y + 52.5 - small.ascender(), 290, 26), small, INK)
        stamp = paint.font("Helvetica-Bold", 10, True)
        brown = "#6b5f48"
        paint.text(u"C60", NSMakeRect(x + 300, y + 70, 44, 12), stamp, brown, kern=1)
        paint.text(u"NR", NSMakeRect(x + 14, y + 74, 24, 12), stamp, brown, kern=1)
        paint.stroke(NSBezierPath.bezierPathWithRect_(NSMakeRect(x + 34.5, y + 75.5, 7, 7)), brown, 1.2)
        for i, c in enumerate(("#e2632e", "#efa13a", "#e8d39e")):
            paint.fill(NSMakeRect(x, y + 132 + 10 * i, 356, 10), c)
        draw_window(x + 68, y + 64, p)

    paint.clipped(shape, body)


def draw_window(x, y, p):
    win = NSMakeRect(x, y, 220, 62)
    paint.fill(paint.rounded(NSInsetRect(win, -2, -2), 10), "#d9cfb4")
    shape = paint.rounded(win, 8)
    paint.fill(shape, "#3a322d", "#1e1916")

    def packs():
        for cx, r in zip((x + 55, x + 165), pack_radii(p)):
            draw_pack(cx, y + 31, r)
    paint.clipped(shape, packs)
    paint.inner_shadow(shape, 2, 5, white(0, 0.8))


_packs = {}


def draw_pack(cx, cy, r):
    """A pack of brown tape: fine concentric windings and a soft sheen."""
    key = int(r * 2)
    img = _packs.get(key)
    if img is None:
        d = key + 2

        def body():
            c = d / 2.0
            paint.fill(paint.oval(c, c, r), "#4a2f1b")
            ring = hexc("#5d3d25")
            rr = r - 0.5
            while rr > HUB - 2:
                paint.stroke(paint.oval(c, c, rr), ring, 1)
                rr -= 2
            sheen = paint.oval(c, c, r)
            NSGradient.alloc().initWithStartingColor_endingColor_(white(1, 0.10), white(1, 0)).drawInBezierPath_relativeCenterPosition_(
                sheen, NSMakePoint(-0.35, -0.45))
            paint.stroke(paint.oval(c, c, r - 0.5), white(0, 0.35), 1)
        img = flipped_image(d, d, body)
        if len(_packs) > 40:
            _packs.clear()
        _packs[key] = img
    s = img.size()
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(cx - s.width / 2.0, cy - s.height / 2.0, s.width, s.height),
        NSZeroRect, NSCompositeSourceOver, 1.0, True, None)


def draw_hub(cx, cy, angle, r=17.0):
    """The white take-up hub with six teeth, turned counterclockwise by angle degrees."""
    NSGraphicsContext.saveGraphicsState()
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(cx, cy)
    t.rotateByDegrees_(-angle)
    t.concat()
    disc = paint.oval(0, 0, r)
    paint.with_shadow(paint.shadow(1, 2, white(0, 0.45)), lambda: paint.fill(disc, "#f3efe6"))
    NSGradient.alloc().initWithStartingColor_endingColor_(hexc("#fbf8f1"), hexc("#e2dbcc")).drawInBezierPath_relativeCenterPosition_(
        disc, NSMakePoint(-0.3, -0.4))
    paint.stroke(paint.oval(0, 0, r - 0.5), "#b9b1a0", 1)
    hole = paint.oval(0, 0, r / 2.0)
    paint.fill(hole, "#241e1a")
    tooth = hexc("#f3efe6")
    for i in range(6):
        NSGraphicsContext.saveGraphicsState()
        rot = NSAffineTransform.transform()
        rot.rotateByDegrees_(60 * i)
        rot.concat()
        paint.fill(NSMakeRect(-1, -r / 2.0, 2, 4), tooth)
        NSGraphicsContext.restoreGraphicsState()
    for dy in (-r * 0.79, r * 0.79):
        paint.fill(paint.oval(0, dy, 1.6), "#cfc6b3")
    NSGraphicsContext.restoreGraphicsState()


# ---- the J-card: the album cover in the case --------------------------------------------------------
class JCardView(FlippedView):
    CARD = NSMakeRect(6, 3, 176, 176)

    def initWithFrame_(self, frame):
        self = super(JCardView, self).initWithFrame_(frame)
        if self:
            self.image, self.name, self.blank = None, u"", True
        return self

    def mouseDownCanMoveWindow(self):
        return True

    def setArt(self, img, name, blank):
        self.image, self.name, self.blank = img, name, blank
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        c = self.CARD
        paint.with_shadow(paint.shadow(3, 8, white(0, 0.75)), lambda: paint.fill(c, "#2a2620"))
        if self.blank:
            draw_blank_card(c)
        elif self.image is not None:
            paint.image(self.image, c)
        else:
            art.draw_placeholder(c, self.name, (self.name or u"").upper(), caption_size=21)
        paint.clipped(NSBezierPath.bezierPathWithRect_(c), lambda: paint.gradient(
            (white(1, 0.22), 0), (white(1, 0), 0.45)).drawInRect_angle_(c, 70))
        paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(c, -0.5, -0.5)), white(1, 0.14), 1)


def draw_blank_card(c):
    """An unused J-card insert: cream paper, ruled lines, the printed tape type."""
    paint.fill(c, "#f6efdb", "#ebe0c2")
    x, y, w, h = c.origin.x, c.origin.y, c.size.width, c.size.height
    paint.fill(NSMakeRect(x, y + 34, w, 1.5), hexc("#c0392b", 0.35))
    for ly in range(int(y + 56), int(y + h - 30), 18):
        paint.fill(NSMakeRect(x + 12, ly, w - 24, 1), hexc("#466eaa", 0.28))
    paint.fill(NSMakeRect(x, y + h - 20, w, 20), "#e2632e")
    paint.fill(NSMakeRect(x, y + h - 26, w, 6), "#efa13a")
    f = paint.font("Helvetica-Bold", 8, True)
    paint.text(u"TYPE I · NORMAL POSITION", NSMakeRect(x, y + h - 16, w, 12), f, "#fff6e6",
               NSCenterTextAlignment, kern=1.2)
    paint.text(u"KASSETT", NSMakeRect(x + 12, y + 14, w - 24, 14), f, "#6b5f48", kern=2)


# ---- the tape counter --------------------------------------------------------------------------------
class CounterView(FlippedView):
    ROLL = 0.22

    def initWithFrame_(self, frame):
        self = super(CounterView, self).initWithFrame_(frame)
        if self:
            self.digits = u"0000"
            self.rolls = {}
            self.remaining = u""
        return self

    def mouseDownCanMoveWindow(self):
        return True

    def setTime(self, elapsed_ms, remaining_ms):
        s = max(0, int(elapsed_ms / 1000))
        m = min(99, s // 60)
        digits = u"%02d%02d" % (m, s % 60 if s // 60 < 100 else 59)
        now = time.time()
        for i, (old, new) in enumerate(zip(self.digits, digits)):
            if old != new:
                self.rolls[i] = (old, now)
        self.digits = digits
        text = u"−%s remaining" % paint.fmt(remaining_ms) if remaining_ms is not None else u""
        if text != self.remaining:
            self.remaining = text
        self.setNeedsDisplay_(True)

    def rolling(self):
        now = time.time()
        for i, (_, start) in list(self.rolls.items()):
            if now - start > self.ROLL:
                del self.rolls[i]
        return bool(self.rolls)

    def drawRect_(self, rect):
        w = self.bounds().size.width
        bx = (w - 118) / 2.0
        paint.fill(paint.rounded(NSMakeRect(bx, 2, 118, 46), 6), "#606266", "#2a2b2e")    # metal surround
        paint.stroke(paint.rounded(NSMakeRect(bx + 0.5, 2.5, 117, 45), 5.5), white(1, 0.14))
        bezel = paint.rounded(NSMakeRect(bx + 4, 6, 110, 38), 4)
        paint.fill(bezel, "#0d0e10")
        paint.inner_shadow(bezel, 2, 4, white(0, 0.9))
        digit_font = paint.font("Helvetica-Bold", 22, True)
        now = time.time()
        base = bx + 4
        for i, x in enumerate((7, 29, 61, 83)):
            self.drawWheel(NSMakeRect(base + x, 10, 20, 30), i, digit_font, now)
        paint.text(u":", NSMakeRect(base + 51, 11, 8, 26), paint.font("Helvetica-Bold", 20, True), "#c9c4b8",
                   NSCenterTextAlignment)
        paint.text(self.remaining, NSMakeRect(0, 56, w, 15), paint.ui(11), "#c4c4c4", NSCenterTextAlignment,
                   sh=paint.shadow(-1, 0, white(0, 0.7)))

    def drawWheel(self, wheel, i, f, now):
        shape = paint.rounded(wheel, 2)
        paint.fill(shape, ("#3a3a3d", 0), ("#151517", 0.3), ("#151517", 0.7), ("#3a3a3d", 1))
        new = self.digits[i]
        roll = self.rolls.get(i)

        def digits():
            ink = "#f5f2ea"
            box = lambda dy: NSMakeRect(wheel.origin.x, wheel.origin.y + 3 + dy, 20, 26)
            if roll and now - roll[1] < self.ROLL:
                off = ease((now - roll[1]) / self.ROLL) * 30
                paint.text(roll[0], box(-off), f, ink, NSCenterTextAlignment)
                paint.text(new, box(30 - off), f, ink, NSCenterTextAlignment)
            else:
                paint.text(new, box(0), f, ink, NSCenterTextAlignment)
            paint.fill(NSMakeRect(wheel.origin.x, wheel.origin.y, 20, 7), white(0, 0.45), white(0, 0))
            paint.fill(NSMakeRect(wheel.origin.x, wheel.origin.y + 23, 20, 7), white(0, 0), white(0, 0.45))
        paint.clipped(shape, digits)


# ---- the tape position: a tuner-style dial ------------------------------------------------------------
class DialView(FlippedView):
    """Minutes printed along a dark dial with an orange needle at the playing position. Drag to seek."""
    PAD = 14

    def initWithFrame_(self, frame):
        self = super(DialView, self).initWithFrame_(frame)
        if self:
            self.p, self.elapsed, self.total, self.duration = 0.0, u"0:00", u"0:00", 0
            self.dragging, self.enabled = False, False
            self.onSeek = None
        return self

    def mouseDownCanMoveWindow(self):
        return False

    def setValues(self, p, elapsed, total, enabled):
        if not self.dragging:
            self.p, self.elapsed = p, elapsed
        self.total, self.enabled = total, enabled
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        w, h = self.bounds().size.width, self.bounds().size.height - 1
        glass = draw_recess(NSMakeRect(0, 0, w, h), 5, "#141518", "#25272c", 0.9)
        x0, x1 = self.PAD, w - self.PAD
        secs = self.duration / 1000.0 if self.duration else 240.0
        major = 60.0 if secs <= 8 * 60 else (120.0 if secs <= 16 * 60 else 300.0)
        dim = 1.0 if self.duration else 0.45
        base = 42
        paint.fill(NSMakeRect(x0, base, x1 - x0, 1), white(1, 0.45 * dim))
        num = paint.font("Helvetica-Bold", 8, True)
        steps = int(secs // (major / 4)) + 1
        for i in range(steps):
            x = round(x0 + (x1 - x0) * (i * major / 4) / secs) - 0.5
            if i % 4 == 0:
                paint.fill(NSMakeRect(x, base - 9, 1, 9), white(1, 0.8 * dim))
                paint.text(u"%d" % int(i * major / 4 / 60), NSMakeRect(x - 10, base - 22, 21, 10), num,
                           white(1, 0.7 * dim), NSCenterTextAlignment)
            else:
                paint.fill(NSMakeRect(x, base - 4, 1, 4), white(1, 0.4 * dim))
        paint.text(u"MIN", NSMakeRect(x1 - 40, h - 16, 40, 10), paint.font("Helvetica-Bold", 7, True), white(1, 0.35),
                   NSRightTextAlignment, kern=1)
        if self.duration:
            nx = x0 + (x1 - x0) * self.p
            color = hexc("#ff6a2b", 1.0 if self.enabled else 0.45)
            paint.with_shadow(paint.shadow(0, 5, hexc("#ff5a1a", 0.9 if self.enabled else 0.3)),
                              lambda: paint.fill(NSMakeRect(nx - 1, 7, 2, h - 14), color))
        paint.clipped(glass, lambda: paint.fill(NSMakeRect(0, 0, w, h / 2.0), white(1, 0.08), white(1, 0)))

    def fraction(self, event):
        x = self.convertPoint_fromView_(event.locationInWindow(), None).x
        return max(0.0, min(1.0, (x - self.PAD) / float(self.bounds().size.width - 2 * self.PAD)))

    def mouseDown_(self, event):
        if not (self.enabled and self.duration):
            return
        self.dragging = True
        self.p = self.fraction(event)
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        if self.dragging:
            self.p = self.fraction(event)
            self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        if self.dragging:
            self.dragging = False
            self.p = self.fraction(event)
            if self.onSeek:
                self.onSeek(self.p)


# ---- piano keys --------------------------------------------------------------------------------------
class KeyButton(NSButton):
    def isFlipped(self):
        return True

    def mouseDownCanMoveWindow(self):
        return False


class KeyCell(NSButtonCell):
    """An aluminium piano key that comes out of a slot in the control strip. `latched` keeps it down
    (PLAY while playing, PAUSE while paused); the others go down only while pressed."""

    def drawWithFrame_inView_(self, frame, view):
        down = getattr(self, "latched", False) or self.isHighlighted()
        w, face = frame.size.width, 64
        y = 3 if down else 0
        body = NSMakeRect(0, y, w, face)
        shape = paint.corners(body, 0, 0, 3, 3)
        lip = 6 if down else 10          # the angled front edge you push
        if not down:
            paint.fill(paint.corners(NSOffsetRect(body, 0, 1), 0, 0, 3, 3), white(0, 0.55))
        paint.fill(shape, *(("#d9d9d9", "#bcbcbc") if down else ("#f8f8f8", "#d2d2d2")))

        def detail():
            paint.fill(NSMakeRect(0, y + face - lip, w, lip), *(("#a8a8a8", "#8a8a8a") if down else ("#c4c4c4", "#949494")))
            paint.fill(NSMakeRect(0, y + face - lip, w, 1), white(1, 0.6))
            paint.fill(NSMakeRect(0, y, w, 1), white(1, 0.5 if down else 0.95))
            paint.fill(NSMakeRect(0, y, 1, face), white(1, 0.5))
            paint.fill(NSMakeRect(w - 1, y, 1, face), white(0, 0.14))
        paint.clipped(shape, detail)
        if down:
            paint.inner_shadow(shape, 3, 4, white(0, 0.4))
        name = getattr(self, "glyph", "play")
        gw, gh = glyphs.size(name)
        scale = 0.85
        gx, gy = (w - gw * scale) / 2.0, y + (face - lip - gh * scale) / 2.0
        alpha = 1.0 if self.isEnabled() else 0.35
        glyphs.draw(name, NSMakeRect(gx, gy + 1, gw * scale, gh * scale), white(1, 0.85 * alpha))
        glyphs.draw(name, NSMakeRect(gx, gy, gw * scale, gh * scale), hexc("#474747", alpha))


def make_key(parent, frame, glyph, caption, target, action):
    key = KeyButton.alloc().initWithFrame_(frame)
    cell = KeyCell.alloc().init()
    cell.glyph, cell.caption, cell.latched = glyph, caption, False
    cell.setButtonType_(NSMomentaryChangeButton)
    key.setCell_(cell)
    key.setTarget_(target)
    key.setAction_(action)
    key.setToolTip_({"PREV": u"Previous song", "REW": u"Back 15 seconds", "PLAY": u"Play", "PAUSE": u"Pause",
                     "FF": u"Forward 15 seconds", "NEXT": u"Next song", "LIBRARY": u"Open the library"}.get(caption))
    parent.addSubview_(key)
    return key


# ---- the volume knob ---------------------------------------------------------------------------------
class KnobView(FlippedView):
    """74 px spun-aluminium knob. Drag up or down, or scroll, to change the volume."""

    def initWithFrame_(self, frame):
        self = super(KnobView, self).initWithFrame_(frame)
        if self:
            self.volume, self.enabled = 50, False
            self.face = None
            self.start = None
            self.onChange = None   # onChange(volume, final)
        return self

    def mouseDownCanMoveWindow(self):
        return False

    def setVolume(self, v, enabled):
        if self.start is None:
            self.volume = max(0, min(100, int(v)))
        self.enabled = enabled
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        cx, cy, r = self.bounds().size.width / 2.0, 46.0, 30.0
        on = 1.0 if self.enabled else 0.5

        def at(deg, radius):
            a = math.radians(deg)
            return NSMakePoint(cx + radius * math.sin(a), cy - radius * math.cos(a))
        for i in range(11):                       # the scale printed on the strip, 0 to 10
            deg = -135 + 27 * i
            r0, r1, width = (33.5, 41, 1.6) if i % 5 == 0 else (34.5, 39, 1.1)
            for dy, color in ((1, white(1, 0.7)), (0, hexc("#454545", on))):
                tick = NSBezierPath.bezierPath()
                p0, p1 = at(deg, r0), at(deg, r1)
                tick.moveToPoint_(NSMakePoint(p0.x, p0.y + dy))
                tick.lineToPoint_(NSMakePoint(p1.x, p1.y + dy))
                paint.stroke(tick, color, width)
        small = paint.font("Helvetica-Bold", 7, True)
        for text, deg in ((u"0", -135), (u"10", 135)):
            p = at(deg, 47)
            paint.text(text, NSMakeRect(p.x - 8, p.y - 5, 16, 10), small, hexc("#4a4a4a", on), NSCenterTextAlignment,
                       sh=paint.engraved())
        if self.enabled:
            paint.text(u"%d" % self.volume, NSMakeRect(cx - 12, cy + 33, 24, 10), small, "#4a4a4a",
                       NSCenterTextAlignment, sh=paint.engraved())
        body = paint.oval(cx, cy, r)
        paint.with_shadow(paint.shadow(3, 5, white(0, 0.55)), lambda: paint.fill(body, "#9a9a9a"))
        paint.fill(body, "#f3f3f3", "#8c8c8c")

        def knurl():
            for i in range(84):
                deg = i * 360 / 84.0
                line = NSBezierPath.bezierPath()
                line.moveToPoint_(at(deg, r - 4))
                line.lineToPoint_(at(deg, r))
                paint.stroke(line, white(1, 0.45) if i % 2 else white(0, 0.22), 1)
        paint.clipped(body, knurl)
        if self.face is None:
            self.face = flipped_image(66, 66, draw_knob_face)
        self.face.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            NSMakeRect(cx - 25.5, cy - 25.5, 51, 51), NSZeroRect, NSCompositeSourceOver, 1.0, True, None)
        paint.stroke(paint.oval(cx, cy, 25.5), white(0, 0.28), 1)
        notch = NSBezierPath.bezierPath()
        notch.moveToPoint_(at(-135 + 270 * self.volume / 100.0, 11))
        notch.lineToPoint_(at(-135 + 270 * self.volume / 100.0, 22))
        notch.setLineCapStyle_(NSRoundLineCapStyle)
        hl = notch.copy()
        tr = NSAffineTransform.transform()
        tr.translateXBy_yBy_(0, 1)
        hl.transformUsingAffineTransform_(tr)
        paint.stroke(hl, white(1, 0.7), 2.4)
        paint.stroke(notch, hexc("#2f2f2f", on), 2.4)

    def change(self, v, final):
        v = max(0, min(100, int(round(v))))
        changed = v != self.volume
        self.volume = v
        self.setNeedsDisplay_(True)
        if self.onChange and (changed or final):
            self.onChange(v, final)

    def mouseDown_(self, event):
        if self.enabled:
            self.start = (event.locationInWindow().y, self.volume)

    def mouseDragged_(self, event):
        if self.start:
            y0, v0 = self.start
            self.change(v0 + (event.locationInWindow().y - y0) * 0.6, False)

    def mouseUp_(self, event):
        if self.start:
            self.start = None
            self.change(self.volume, True)

    def scrollWheel_(self, event):
        if self.enabled and event.deltaY():
            self.change(self.volume + event.deltaY() * 2, True)


def draw_knob_face():
    """Spun metal: a conic sweep of light and dark with faint machining rings."""
    c, r = 33.0, 33.0
    stops = [(0, 0xef), (.12, 0xb2), (.25, 0xf7), (.38, 0xa8), (.5, 0xed), (.62, 0xb0), (.75, 0xf5), (.88, 0xa9), (1, 0xef)]

    def shade(t):
        for (t0, v0), (t1, v1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return 0xef
    face = paint.oval(c, c, r)

    def body():
        steps = 120
        for i in range(steps):
            a0 = 360.0 * i / steps - 90
            wedge = NSBezierPath.bezierPath()
            wedge.moveToPoint_(NSMakePoint(c, c))
            wedge.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(NSMakePoint(c, c), r + 1, a0, a0 + 360.0 / steps + 0.6)
            wedge.closePath()
            white(shade((i + 0.5) / steps) / 255.0).set()
            wedge.fill()
        rr = r - 1.5
        while rr > 2:
            paint.stroke(paint.oval(c, c, rr), white(1 if int(rr) % 2 else 0, 0.05), 0.8)
            rr -= 1.5
    paint.clipped(face, body)
    paint.stroke(paint.oval(c, c, r - 0.5), white(1, 0.5), 1)


# ---- the bottom bar ----------------------------------------------------------------------------------
class GlyphView(NSView):
    """A small engraved glyph for the bottom bar (the device that's playing)."""

    def initWithFrame_(self, frame):
        self = super(GlyphView, self).initWithFrame_(frame)
        if self:
            self.glyph = "speaker"
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        glyphs.draw(self.glyph, NSOffsetRect(b, 0, -1), white(1, 0.6))
        glyphs.draw(self.glyph, b, hexc("#3d3d3d"))


class BarButton(NSButton):
    def isFlipped(self):
        return True

    def mouseDownCanMoveWindow(self):
        return False


class BarCell(NSButtonCell):
    """The small glossy bottom-bar buttons (Up Next, AirPlay), like iTunes 10's."""

    def drawWithFrame_inView_(self, frame, view):
        r = NSMakeRect(1, 0, frame.size.width - 2, frame.size.height - 2)
        paint.fill(paint.rounded(NSOffsetRect(r, 0, 1), 4), white(1, 0.4))
        paint.fill(paint.rounded(r, 4), "#7b7b7b")
        inner = paint.rounded(NSInsetRect(r, 1, 1), 3)
        if self.isHighlighted() or getattr(self, "lit", False):
            paint.fill(inner, "#bdbdbd", "#a6a6a6")
        else:
            paint.fill(inner, "#f6f6f6", "#cfcfcf")
            paint.clipped(inner, lambda: paint.fill(NSMakeRect(0, 1, frame.size.width, 1), white(1)))
        name = getattr(self, "glyph", "queue")
        gw, gh = glyphs.size(name)
        scale = 14.0 / max(gw, gh) if max(gw, gh) > 14 else 1.0
        gr = NSMakeRect(r.origin.x + (r.size.width - gw * scale) / 2.0, r.origin.y + (r.size.height - gh * scale) / 2.0,
                        gw * scale, gh * scale)
        glyphs.draw(name, gr, hexc("#3d3d3d", 1 if self.isEnabled() else 0.4))


def make_bar_button(parent, frame, glyph, tip, target, action):
    b = BarButton.alloc().initWithFrame_(frame)
    cell = BarCell.alloc().init()
    cell.glyph = glyph
    cell.setButtonType_(NSMomentaryChangeButton)
    b.setCell_(cell)
    b.setToolTip_(tip)
    b.setTarget_(target)
    b.setAction_(action)
    parent.addSubview_(b)
    return b


def bar_label(frame):
    label = NSTextField.alloc().initWithFrame_(frame)
    label.setBezeled_(False)
    label.setDrawsBackground_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    label.setFont_(NSFont.systemFontOfSize_(11))
    label.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    label.cell().setBackgroundStyle_(NSBackgroundStyleRaised)
    return label


# ---- the deck window ---------------------------------------------------------------------------------
class Deck(NSObject):
    """Owns the Now Playing window. `app` is the AppDelegate, which does the talking to Spotify."""

    def initWithApp_(self, app):
        self = super(Deck, self).init()
        if self is None:
            return None
        self.app = app
        self.timer = None
        self.last_frame = time.time()
        self.playing = False
        self.p_target = 0.0
        self.whirr = None          # (from_p, to_p, start) while the tape winds after a seek or skip
        self.build()
        return self

    def build(self):
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, DECK_W, DECK_H + BAR),
            NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSTexturedBackgroundWindowMask,
            NSBackingStoreBuffered, False)
        w.setTitle_(u"Kassett")
        w.setContentBorderThickness_forEdge_(BAR, NSMinYEdge)
        w.setAutorecalculatesContentBorderThickness_forEdge_(False, NSMinYEdge)
        w.setFrameAutosaveName_("KassettDeck")
        if not w.setFrameUsingName_("KassettDeck"):
            w.center()
        w.setDelegate_(self)
        content = w.contentView()

        deck = DeckView.alloc().initWithFrame_(NSMakeRect(0, BAR, DECK_W, DECK_H))
        deck.onKey = self.app.handleKey
        content.addSubview_(deck)
        self.view = deck
        self.cassette = CassetteView.alloc().initWithFrame_(NSMakeRect(22, 32, 452, 286))
        deck.addSubview_(self.cassette)
        self.jcard = JCardView.alloc().initWithFrame_(NSMakeRect(530, 43, 188, 190))
        deck.addSubview_(self.jcard)
        self.counter = CounterView.alloc().initWithFrame_(NSMakeRect(490, 230, 268, 74))
        deck.addSubview_(self.counter)

        # The control strip: keys in two slots, the tape position dial and the volume knob, each with
        # its name printed above it like on a real deck.
        top = STRIP.origin.y + 26
        deck.slots = [NSMakeRect(32, top - 4, 52, 72), NSMakeRect(100, top - 4, 330, 72)]
        labels = []
        self.libraryKey = make_key(deck, NSMakeRect(36, top, 44, 67), "eject", u"LIBRARY", self.app, "showLibrary:")
        labels.append((u"LIBRARY", NSMakeRect(28, STRIP.origin.y + 8, 60, 10), None))
        self.keys = {}
        x = 104
        for glyph, caption, action, led in (("prev", u"PREV", "previous:", None), ("rew", u"REW", "rewind:", None),
                                            ("play", u"PLAY", "play:", "play"), ("pause", u"PAUSE", "pause:", "pause"),
                                            ("ff", u"FF", "fastForward:", None), ("next", u"NEXT", "next:", None)):
            self.keys[caption] = make_key(deck, NSMakeRect(x, top, 52, 67), glyph, caption, self.app, action)
            labels.append((caption, NSMakeRect(x - 6, STRIP.origin.y + 8, 64, 10), led))
            x += 54
        self.progress = DialView.alloc().initWithFrame_(NSMakeRect(448, top, 180, 66))
        self.progress.onSeek = self.app.seekToFraction
        deck.addSubview_(self.progress)
        labels.append((u"TAPE POSITION", NSMakeRect(448, STRIP.origin.y + 8, 180, 10), None))
        self.knob = KnobView.alloc().initWithFrame_(NSMakeRect(642, STRIP.origin.y + 14, 96, 90))
        self.knob.onChange = self.app.volumeChanged
        deck.addSubview_(self.knob)
        labels.append((u"VOLUME", NSMakeRect(642, STRIP.origin.y + 8, 96, 10), None))
        deck.labels = labels

        self.login = NSButton.alloc().initWithFrame_(NSMakeRect(STRIP.origin.x + STRIP.size.width / 2 - 100,
                                                                STRIP.origin.y + 18, 200, 32))
        self.login.setBezelStyle_(NSRoundedBezelStyle)
        self.login.setTitle_(u"Log In to Spotify\u2026")
        self.login.setTarget_(self.app)
        self.login.setAction_("logIn:")
        deck.addSubview_(self.login)
        self.loginNote = NSTextField.alloc().initWithFrame_(NSMakeRect(60, STRIP.origin.y + 56, DECK_W - 120, 34))
        for f in (self.loginNote,):
            f.setBezeled_(False)
            f.setDrawsBackground_(False)
            f.setEditable_(False)
            f.setSelectable_(False)
            f.setAlignment_(NSCenterTextAlignment)
            f.setFont_(NSFont.systemFontOfSize_(11))
            f.setTextColor_(hexc("#3f3f3f"))
            f.cell().setBackgroundStyle_(NSBackgroundStyleRaised)
        self.loginNote.setStringValue_(u"Kassett plays Spotify on your phone, speakers and computers. "
                                       u"Controlling playback needs a Spotify Premium account.")
        deck.addSubview_(self.loginNote)

        self.deviceGlyph = GlyphView.alloc().initWithFrame_(NSMakeRect(10, 8, 14, 14))
        content.addSubview_(self.deviceGlyph)
        self.status = bar_label(NSMakeRect(28, 6, DECK_W - 120, 17))
        content.addSubview_(self.status)
        self.upNextButton = make_bar_button(content, NSMakeRect(DECK_W - 10 - 32 - 8 - 34, 4, 34, 23), "queue",
                                            u"Up Next", self.app, "showUpNext:")
        self.airplayButton = make_bar_button(content, NSMakeRect(DECK_W - 10 - 34, 4, 34, 23), "airplay",
                                             u"Choose where Spotify plays", self.app, "chooseDevice:")
        self.window = w

    # ---- showing state ------------------------------------------------------------------------------
    def showLoggedIn(self, logged_in):
        for v in [self.libraryKey, self.knob, self.progress, self.upNextButton, self.airplayButton] + self.keys.values():
            v.setHidden_(not logged_in)
        self.view.controlsShown = logged_in
        self.view.setNeedsDisplay_(True)
        for v in (self.login, self.loginNote):
            v.setHidden_(logged_in)

    def setTape(self, title, subtitle):
        self.cassette.setLabel(title, subtitle)

    def setArt(self, img, name, blank):
        self.jcard.setArt(img, name, blank)

    def setStatus(self, text, glyph=None):
        self.status.setStringValue_(text)
        self.deviceGlyph.setHidden_(glyph is None)
        if glyph:
            self.deviceGlyph.glyph = glyph
            self.deviceGlyph.setNeedsDisplay_(True)
        x = 28 if glyph else 10
        self.status.setFrame_(NSMakeRect(x, 6, DECK_W - 100 - x, 17))

    def setPlaying(self, playing, has_track, controllable=True):
        """controllable is False when Spotify won't take commands for the device that's playing."""
        self.playing, self.controllable = playing, controllable
        self.keys[u"PLAY"].cell().latched = playing
        self.keys[u"PAUSE"].cell().latched = has_track and not playing
        for k in self.keys.values():
            k.setEnabled_(controllable and (has_track or k is self.keys[u"PLAY"]))
            k.setNeedsDisplay_(True)
        self.view.setLed("play", "green" if playing else None)
        self.view.setLed("pause", "amber" if has_track and not playing else None)
        self.ensureTimer()

    def setPosition(self, progress_ms, duration_ms, jumped):
        p = float(progress_ms) / duration_ms if duration_ms else 0.0
        if jumped and abs(p - self.cassette.p) > 0.01 and self.window.isVisible():
            self.whirr = (self.cassette.p, p, time.time())
        elif self.whirr is None:
            self.cassette.setProgress(p)
        self.p_target = p
        self.counter.setTime(progress_ms, duration_ms - progress_ms if duration_ms else None)
        self.progress.duration = duration_ms
        self.progress.setValues(p, paint.fmt(progress_ms), paint.fmt(duration_ms),
                                bool(duration_ms) and getattr(self, "controllable", True))
        self.ensureTimer()

    def setVolume(self, volume, enabled):
        self.knob.setVolume(volume if volume is not None else 50,
                            enabled and volume is not None and getattr(self, "controllable", True))

    # ---- animation ----------------------------------------------------------------------------------
    def animating(self):
        return self.window.isVisible() and not self.window.isMiniaturized() and \
            (self.playing or self.whirr is not None or self.counter.rolling())

    def ensureTimer(self):
        if self.animating() and self.timer is None:
            self.last_frame = time.time()
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / FPS, self, "frame:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def frame_(self, timer):
        now = time.time()
        dt, self.last_frame = min(0.2, now - self.last_frame), now
        if self.whirr:
            start_p, end_p, start = self.whirr
            t = (now - start) / WHIRR
            if t >= 1:
                self.whirr = None
                self.cassette.setProgress(self.p_target)
            else:
                self.cassette.setProgress(start_p + (end_p - start_p) * ease(t))
                self.cassette.turn((7 if end_p > start_p else -7) * 150 * dt)
        elif self.playing:
            self.cassette.turn(150 * dt)
        if self.counter.rolling() or self.counter.rolls:
            self.counter.setNeedsDisplay_(True)
        if not self.animating():
            self.timer.invalidate()
            self.timer = None

    def windowDidMiniaturize_(self, note):
        self.ensureTimer()

    def windowDidDeminiaturize_(self, note):
        self.ensureTimer()

    def windowWillClose_(self, note):
        if self.timer:
            self.timer.invalidate()
            self.timer = None


# ---- the mini player ---------------------------------------------------------------------------------
class MiniView(FlippedView):
    def initWithFrame_(self, frame):
        self = super(MiniView, self).initWithFrame_(frame)
        if self:
            self.title, self.artist, self.p, self.has_track = u"Kassett", u"", 0.0, False
            self.angle = 0.0
            self.bg = None
        return self

    def isOpaque(self):
        return True

    def mouseDownCanMoveWindow(self):
        return True

    def drawRect_(self, rect):
        b = self.bounds()
        if self.bg is None:
            self.bg = flipped_image(b.size.width, b.size.height, lambda: draw_brushed(b.size.width, b.size.height))
        draw_part(self.bg, rect, NSCompositeCopy)
        draw_mini_cassette(12, 16, self.angle)
        x, w = 120, b.size.width - 120 - 160
        big = paint.font("MarkerFelt-Wide", 17)
        paint.text(self.title, NSMakeRect(x, 21, w, 22), big, INK)
        paint.text(self.artist, NSMakeRect(x, 42, w, 20), paint.font("Noteworthy-Bold", 12), "#3a3a3a")
        track = NSMakeRect(x, 66, w, 4)
        paint.fill(paint.rounded(NSOffsetRect(track, 0, 1), 2), white(1, 0.8))
        shape = paint.rounded(track, 2)
        paint.fill(shape, "#939393")
        paint.inner_shadow(shape, 1, 1, white(0, 0.5))
        if self.has_track:
            paint.fill(paint.rounded(NSMakeRect(x, 66, max(4, w * self.p), 4), 2), "#2f2f32")


def draw_mini_cassette(x, y, angle):
    shell = paint.rounded(NSMakeRect(x, y, 96, 62), 5)
    paint.with_shadow(paint.shadow(1, 3, white(0, 0.6)), lambda: paint.fill(shell, "#222226"))
    paint.fill(shell, "#414146", "#222226")
    paint.clipped(shell, lambda: paint.fill(NSMakeRect(x + 4, y, 88, 1), white(1, 0.2)))
    lab = paint.rounded(NSMakeRect(x + 6, y + 5, 84, 40), 3)

    def label():
        paint.fill(NSMakeRect(x + 6, y + 5, 84, 40), "#f6efdb", "#ece2c6")
        paint.fill(NSMakeRect(x + 6, y + 37, 84, 4), "#e2632e")
        paint.fill(NSMakeRect(x + 6, y + 41, 84, 4), "#efa13a")
    paint.clipped(lab, label)
    win = paint.rounded(NSMakeRect(x + 20, y + 14, 56, 20), 4)
    paint.fill(win, "#241e1a")
    paint.inner_shadow(win, 1, 2, white(0, 0.8))
    for cx in (x + 33, x + 63):
        NSGraphicsContext.saveGraphicsState()
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(cx, y + 24)
        t.rotateByDegrees_(-angle)
        t.concat()
        paint.fill(paint.oval(0, 0, 7), "#f3efe6")
        paint.fill(paint.oval(0, 0, 3.5), "#241e1a")
        for i in range(3):
            NSGraphicsContext.saveGraphicsState()
            rot = NSAffineTransform.transform()
            rot.rotateByDegrees_(120 * i)
            rot.concat()
            paint.fill(NSMakeRect(-0.8, -3.6, 1.6, 2.2), "#f3efe6")
            NSGraphicsContext.restoreGraphicsState()
        NSGraphicsContext.restoreGraphicsState()


class SegmentCell(NSButtonCell):
    """One part of a textured segmented control drawn like the mockup's (left, middle or right)."""

    def drawWithFrame_inView_(self, frame, view):
        part = getattr(self, "part", "middle")
        r = NSMakeRect(0, 0, frame.size.width, frame.size.height - 1)
        rad = {"left": (4, 0, 0, 4), "right": (0, 4, 4, 0), "middle": (0, 0, 0, 0), "single": (4, 4, 4, 4)}[part]
        outline = paint.corners(r, *rad)
        paint.fill(paint.corners(NSOffsetRect(r, 0, 1), *rad), white(1, 0.5))
        paint.fill(outline, "#7b7b7b")
        inner_r = NSMakeRect(1 if part in ("left", "single") else 0, 1,
                             r.size.width - (1 if part in ("left", "single") else 0) - 1, r.size.height - 2)
        inner = paint.corners(inner_r, *[max(0, v - 1) for v in rad])
        if self.isHighlighted():
            paint.fill(inner, "#bdbdbd", "#a8a8a8")
        else:
            paint.fill(inner, "#f6f6f6", "#cfcfcf")
            paint.clipped(inner, lambda: paint.fill(NSMakeRect(0, 1, r.size.width, 1), white(1, 0.9)))
        name = getattr(self, "glyph", "play")
        gw, gh = glyphs.size(name)
        scale = getattr(self, "scale", 1.0)
        glyphs.draw(name, NSMakeRect((r.size.width - gw * scale) / 2.0, (r.size.height - gh * scale) / 2.0,
                                     gw * scale, gh * scale), hexc("#333333", 1 if self.isEnabled() else 0.4))


def make_segment(parent, frame, glyph, part, scale, tip, target, action):
    b = KeyButton.alloc().initWithFrame_(frame)
    cell = SegmentCell.alloc().init()
    cell.glyph, cell.part, cell.scale = glyph, part, scale
    cell.setButtonType_(NSMomentaryChangeButton)
    b.setCell_(cell)
    b.setToolTip_(tip)
    b.setTarget_(target)
    b.setAction_(action)
    parent.addSubview_(b)
    return b


class Mini(NSObject):
    def initWithApp_(self, app):
        self = super(Mini, self).init()
        if self is None:
            return None
        self.app = app
        self.timer = None
        self.playing = False
        p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 460, 94), NSTitledWindowMask | NSClosableWindowMask | NSUtilityWindowMask,
            NSBackingStoreBuffered, False)
        p.setTitle_(u"Kassett")
        p.setFloatingPanel_(False)
        p.setHidesOnDeactivate_(False)
        p.setBecomesKeyOnlyIfNeeded_(True)
        p.setFrameAutosaveName_("KassettMini")
        if not p.setFrameUsingName_("KassettMini"):
            p.center()
        p.setDelegate_(self)
        self.view = MiniView.alloc().initWithFrame_(p.contentView().bounds())
        p.contentView().addSubview_(self.view)
        y = (94 - 24) / 2
        self.prevButton = make_segment(self.view, NSMakeRect(300, y, 33, 25), "prev", "left", 0.64,
                                       u"Previous song", app, "previous:")
        self.playButton = make_segment(self.view, NSMakeRect(333, y, 36, 25), "play", "middle", 0.75,
                                       u"Play or pause", app, "playPause:")
        self.nextButton = make_segment(self.view, NSMakeRect(369, y, 32, 25), "next", "right", 0.64,
                                       u"Next song", app, "next:")
        self.expandButton = make_segment(self.view, NSMakeRect(420, y, 28, 25), "expand", "single", 1.0,
                                         u"Show the cassette deck", app, "showDeck:")
        self.window = p
        return self

    def show(self, title, artist, p, playing, has_track):
        v = self.view
        v.title, v.artist, v.p, v.has_track = title, artist, p, has_track
        v.setNeedsDisplay_(True)
        self.playing = playing
        self.playButton.cell().glyph = "pause" if playing else "play"
        self.playButton.setNeedsDisplay_(True)
        controllable = getattr(self.app, "controllable", True)
        for b in (self.prevButton, self.nextButton):
            b.setEnabled_(has_track and controllable)
        self.playButton.setEnabled_(controllable)
        if playing and self.timer is None and self.window.isVisible():
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / FPS, self, "frame:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def frame_(self, timer):
        if not (self.playing and self.window.isVisible()):
            self.timer.invalidate()
            self.timer = None
            return
        self.view.angle = (self.view.angle + 360 / FPS / 1.6) % 360
        self.view.setNeedsDisplayInRect_(NSMakeRect(12, 16, 96, 62))

    def windowWillClose_(self, note):
        self.app.miniClosed()
