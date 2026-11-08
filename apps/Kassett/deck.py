# -*- coding: utf-8 -*-
"""The cassette deck (Now Playing) and the mini player.

Everything is drawn in flipped views so the coordinates read like design/kassett/Main.dc.html.
The reels turn the way real tape does: the tape moves at a constant speed, so the reel with less
tape on it spins faster, and the packs grow by area rather than by diameter."""
import math
import random
import time

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403
from Quartz import CABasicAnimation, CACurrentMediaTime, CALayer

import art
import glyphs
import paint
from paint import hexc, white

FPS = 30.0
WHIRR = 0.45                   # seconds a seek or skip takes to wind the tape
# A compact cassette drawn to scale: 100.4 x 63.8 mm at about 4 px per mm (IEC 60094).
MM = 400 / 100.4
HUB, FULL = 8.5 * MM, 20.5 * MM    # radius of a bare hub and of a full C60 pack, px
TAPE_SPEED = 47.6 * MM             # 4.76 cm/s of tape, px per second
WHIRR_SPEED = 2.5                  # winding looks this many times faster (more would strobe at 30 fps)
SHELLS = {"black": ("#414146", "#222226"), "smoke": ("#6d737b", "#3b4047"), "white": ("#f2efe8", "#d5d0c3"),
          "clear": None}
INK = hexc("#26337f")
DECK_W, DECK_H, BAR = 600, 418, 30
STRIP_X = 488        # where the silver key strip starts, like the side of a 1979 Walkman


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


def brushing(rect, seed, light=0.07, dark=0.05, count=500):
    """Streaks of brushed metal: many short, faint horizontal scratches of random length."""
    rnd = random.Random(seed)
    x0, y0, w, h = rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
    for y in range(int(h)):
        paint.fill(NSMakeRect(x0, y0 + y, w, 1), white(1, rnd.uniform(0, light * 0.6)))
    for _ in range(count):
        length = rnd.uniform(30, w * 0.8)
        x = rnd.uniform(-length / 2, w)
        y = rnd.randint(0, int(h) - 1)
        paint.fill(NSMakeRect(x0 + x, y0 + y, length, 1),
                   white(1, rnd.uniform(0.02, light)) if rnd.random() < 0.6 else white(0, rnd.uniform(0.01, dark)))


def chrome_text(text, rect, font, kern):
    """Text like a chrome nameplate: a mirrored gradient with a horizon line, a dark edge and a shadow."""
    w, h = int(rect.size.width), int(rect.size.height)
    letters = flipped_image(w, h, lambda: paint.text(text, NSMakeRect(0, 0, w, h), font, white(1), kern=kern))
    shine = flipped_image(w, h, lambda: paint.fill(NSMakeRect(0, 0, w, h), ("#ffffff", 0), ("#dfe6ee", 0.3),
                                                        ("#a3b2c3", 0.5), ("#55687d", 0.53), ("#9fb0c2", 0.75),
                                                        ("#eef2f6", 1)))
    letters.lockFocusFlipped_(True)
    shine.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(0, 0, w, h), NSZeroRect, NSCompositeSourceIn, 1.0, True, None)
    letters.unlockFocus()
    for dy, alpha in ((1, 0.7), (-1, 0.45)):      # a dark rim below and above, as if pressed into the body
        paint.with_shadow(paint.shadow(dy, 0, white(0, alpha)), lambda: letters.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
            rect, NSZeroRect, NSCompositeSourceOver, 1.0, True, None))
    paint.with_shadow(paint.shadow(2, 3, white(0, 0.35)), lambda: letters.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        rect, NSZeroRect, NSCompositeSourceOver, 1.0, True, None))


def groove(r, radius):
    """The seam where a part sits in the body: dark inside edge, light outside edge."""
    paint.stroke(paint.rounded(NSInsetRect(r, -1.5, -1.5), radius + 1.5), white(0, 0.35), 1)
    paint.stroke(paint.rounded(NSOffsetRect(NSInsetRect(r, -2.5, -2.5), 0, 1), radius + 2.5), white(1, 0.22), 1)


def draw_body(w, h, strip_x=STRIP_X, full=True):
    """Blue anodised aluminium, brushed, with light catching its top, and a silver strip on the right."""
    STRIP_X = strip_x
    body = NSMakeRect(0, 0, STRIP_X, h)
    paint.fill(body, ("#86b5e6", 0), ("#5f93cf", 0.16), ("#4a7ebd", 0.45), ("#3d6dab", 0.8), ("#335f99", 1))
    brushing(body, 7, 0.08, 0.06, 700)
    paint.fill(NSMakeRect(0, 0, STRIP_X, h * 0.4), white(1, 0.10), white(1, 0))

    strip = NSMakeRect(STRIP_X, 0, w - STRIP_X, h)
    paint.fill(strip, ("#c9c9c9", 0), ("#f7f7f7", 0.3), ("#e6e6e6", 0.55), ("#bdbdbd", 1), angle=0)
    brushing(strip, 11, 0.25, 0.08, 260)
    paint.fill(NSMakeRect(STRIP_X - 2, 0, 1, h), white(0, 0.18))
    paint.fill(NSMakeRect(STRIP_X - 1, 0, 1, h), white(0, 0.45))
    paint.fill(NSMakeRect(STRIP_X, 0, 1, h), white(1, 0.9))
    paint.fill(NSMakeRect(0, 0, w, 1), white(0, 0.5))
    paint.fill(NSMakeRect(0, 1, w, 1), white(1, 0.45))
    paint.fill(NSMakeRect(0, h - 1, w, 1), white(0, 0.3))
    if not full:
        return
    chrome_text(u"KASSETT", NSMakeRect(16, 10, 200, 40), paint.font("Futura-CondensedExtraBold", 31, True), 2.5)
    paint.text(u"STEREO CASSETTE PLAYER", NSMakeRect(STRIP_X - 18 - 260, 29, 260, 12),
               paint.font("Helvetica-Bold", 8, True), white(1, 0.85), NSRightTextAlignment, kern=2.2,
               sh=paint.shadow(-1, 0, white(0, 0.3)))
    groove(NSMakeRect(18, 56, 452, 284), 10)
    groove(NSMakeRect(18.5, 354.5, 451, 49), 6)


class DeckView(FlippedView):
    def initWithFrame_(self, frame):
        self = super(DeckView, self).initWithFrame_(frame)
        if self:
            self.bg = None
            self.onKey = None
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

    def drawRect_(self, rect):
        b = self.bounds()
        if self.bg is None:
            self.bg = flipped_image(b.size.width, b.size.height, lambda: draw_body(b.size.width, b.size.height))
        draw_part(self.bg, rect, NSCompositeCopy)


# ---- the cassette, drawn from the real thing --------------------------------------------------------
# Shell coordinates: the 400 x 252 px shell, origin at its top left.
HUB_XY = ((200 - 21.25 * MM, 115.0), (200 + 21.25 * MM, 115.0))      # reel spindles are 42.5 mm apart
ROLLERS, ROLLER_R = ((46.0, 225.0), (354.0, 225.0)), 2.3 * MM          # white guide rollers in the corners
PINS, PIN_R = ((104.0, 229.0), (296.0, 229.0)), 1.1 * MM               # steel guide pins
TAPE_Y = 225.0 + 2.3 * MM                                              # the tape's run along the bottom
CAPSTAN = (270.0, TAPE_Y - 4)                                          # the player's capstan, through the right hole
LABEL = NSMakeRect(22, 16, 356, 166)
WINDOW = NSMakeRect(77, 79, 246, 72)                                   # the label's window, around both hubs
SCREWS = ((14, 14), (386, 14), (14, 238), (386, 238), (200, 189))


class CassetteView(FlippedView):
    """452 x 286: the bay behind the smoked door, the cassette, and the player's head, capstan and
    pinch roller. Reels turn at tape speed / pack radius, so the emptier reel spins faster."""
    WELL = NSMakeRect(0, 0, 452, 284)
    SHELL = (26, 16)

    def initWithFrame_(self, frame):
        self = super(CassetteView, self).initWithFrame_(frame)
        if self:
            self.title, self.subtitle = u"Kassett", u""
            self.shell = "clear"
            self.p = 0.0
            self.angles = [0.0, 37.0]
            self.engage, self.engaged = 0.0, False     # how far the head and pinch roller have moved in
            self.bg, self.bg_key = None, None
            self.coarse = False                        # redraw the packs less often while winding fast
            self.reels = ReelView.alloc().initWithFrame_(self.bounds())
            self.addSubview_(self.reels)
            self.reels.setUp(self.hubs(), flipped_image(452, 286, self.drawGlass))
        return self

    def mouseDownCanMoveWindow(self):
        return True

    def hubs(self):
        sx, sy = self.SHELL
        return [(sx + x, sy + y) for x, y in HUB_XY]

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
        step = 6.0 if self.coarse else 1.0
        return (self.title, self.subtitle, self.shell, int(left * 2 / step), int(right * 2 / step))

    def spin(self, speed):
        """Turn the reels at `speed` times play speed (0 stops them, negative rewinds): the tape
        moves at 4.76 cm/s, so each reel turns at that speed divided by its pack's radius."""
        left, right = pack_radii(self.p)
        self.reels.setSpeeds([TAPE_SPEED * speed / left, TAPE_SPEED * speed / right])

    def setEngaged(self, engaged):
        self.engaged = engaged

    def mechanismMoving(self):
        return abs(self.engage - (1.0 if self.engaged else 0.0)) > 0.001

    def stepMechanism(self, dt):
        target = 1.0 if self.engaged else 0.0
        if abs(self.engage - target) <= 0.001:
            return
        step = dt / 0.22                       # the head takes about a fifth of a second to come up
        self.engage = min(target, self.engage + step) if target > self.engage else max(target, self.engage - step)
        sx, sy = self.SHELL
        self.setNeedsDisplayInRect_(NSMakeRect(sx + 160, sy + 205, 140, 50))

    def drawRect_(self, rect):
        if self.bg is None or self.key() != self.bg_key:
            self.bg_key = self.key()
            self.bg = flipped_image(452, 286, self.drawBody)
        draw_part(self.bg, rect)
        sx, sy = self.SHELL
        if NSIntersectsRect(rect, NSMakeRect(sx + 160, sy + 205, 140, 50)):
            draw_mechanism(sx, sy, ease(self.engage), self.shell == "clear")

    def drawBody(self):
        paint.fill(paint.rounded(NSOffsetRect(self.WELL, 0, 1), 10), white(1, 0.85))
        paint.fill(paint.rounded(self.WELL, 10), "#f6f6f6", "#9b9b9b")          # the chrome door frame
        paint.stroke(paint.rounded(NSInsetRect(self.WELL, 0.5, 0.5), 9.5), white(0, 0.38))
        bay = paint.rounded(NSInsetRect(self.WELL, 4, 4), 7)
        paint.fill(bay, "#121315", "#222428")
        paint.inner_shadow(bay, 3, 10, white(0, 0.9))
        sx, sy = self.SHELL
        draw_cassette(sx, sy, self.shell, self.title, self.subtitle, self.p)
        for cx, cy in self.hubs():          # the hubs' shadows on the tape; the hubs are layers on top
            paint.with_shadow(paint.shadow(1, 3, white(0, 0.6)), lambda: paint.fill(paint.oval(cx, cy, HUB - 1), "#3a2a1e"))

    def drawGlass(self):
        """The window in the label, the smoked door in front, and a pull notch at the top."""
        sx, sy = self.SHELL
        win = NSOffsetRect(WINDOW, sx, sy)
        paint.clipped(paint.rounded(win, 10), lambda: paint.fill(
            NSMakeRect(win.origin.x, win.origin.y, win.size.width, 30), white(1, 0.22), white(1, 0)))
        inner = NSInsetRect(self.WELL, 4, 4)
        door = paint.rounded(inner, 7)
        paint.fill(door, white(0, 0.08))
        paint.clipped(door, lambda: paint.gradient(
            (white(1, 0.16), 0), (white(1, 0.04), 0.34), (white(1, 0), 0.35), (white(1, 0.03), 0.6),
            (white(1, 0), 0.78)).drawInRect_angle_(inner, 62))
        paint.stroke(paint.rounded(NSInsetRect(inner, 1, 1), 6), white(1, 0.10), 1)
        paint.fill(paint.corners(NSMakeRect(196, 5, 60, 6), 0, 0, 3, 3), white(1, 0.12))
        paint.fill(paint.corners(NSMakeRect(196, 4, 60, 6), 0, 0, 3, 3), "#0a0a0b")


def tangent(c1, r1, c2, r2, side):
    """Where a belt round two circles touches them, on the left (side -1) or right (side 1)."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    theta = math.atan2(dy, dx)
    alpha = math.acos(max(-1.0, min(1.0, (r1 - r2) / d)))
    best = None
    for a in (theta + alpha, theta - alpha):
        p1 = (c1[0] + r1 * math.cos(a), c1[1] + r1 * math.sin(a))
        p2 = (c2[0] + r2 * math.cos(a), c2[1] + r2 * math.sin(a))
        if best is None or (p1[0] - best[0][0]) * side > 0:
            best = (p1, p2, a)
    return best


def tape_path(sx, sy, p):
    """The tape: off the supply pack's left side, round the left roller, along the bottom past the
    head, round the right roller and up onto the take-up pack's right side."""
    left_r, right_r = pack_radii(p)
    (h1, h2), (r1, r2) = HUB_XY, ROLLERS
    a1, b1, ang1 = tangent(h1, left_r, r1, ROLLER_R, -1)
    a2, b2, ang2 = tangent(h2, right_r, r2, ROLLER_R, 1)
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(NSMakePoint(sx + a1[0], sy + a1[1]))
    path.lineToPoint_(NSMakePoint(sx + b1[0], sy + b1[1]))
    path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        NSMakePoint(sx + r1[0], sy + r1[1]), ROLLER_R, math.degrees(ang1), 90, True)
    path.lineToPoint_(NSMakePoint(sx + r2[0], sy + TAPE_Y))
    path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        NSMakePoint(sx + r2[0], sy + r2[1]), ROLLER_R, 90, math.degrees(ang2), True)
    path.lineToPoint_(NSMakePoint(sx + a2[0], sy + a2[1]))
    return path


def draw_cassette(sx, sy, kind, title, subtitle, p):
    shell_r = NSMakeRect(sx, sy, 400, 252)
    shell = paint.rounded(shell_r, 12)
    clear = SHELLS.get(kind, SHELLS["black"]) is None
    win = NSOffsetRect(WINDOW, sx, sy)
    if clear:
        paint.with_shadow(paint.shadow(3, 10, white(0, 0.6)), lambda: paint.fill(shell, white(0, 0.4)))
    else:
        top, bottom = SHELLS[kind]
        paint.with_shadow(paint.shadow(3, 10, white(0, 0.7)), lambda: paint.fill(shell, bottom))
        paint.fill(shell, top, bottom)

    def insides():
        for (hx, hy), r in zip(HUB_XY, pack_radii(p)):
            draw_pack(sx + hx, sy + hy, r)
        if clear:
            paint.stroke(tape_path(sx, sy, p), "#3e2716", 1.8)
            for rx, ry in ROLLERS:                                   # nylon rollers on steel axles
                paint.fill(paint.oval(sx + rx, sy + ry, ROLLER_R), "#f4f1ea", "#cfc8b8")
                paint.stroke(paint.oval(sx + rx, sy + ry, ROLLER_R - 0.5), white(0, 0.3), 1)
                paint.fill(paint.oval(sx + rx, sy + ry, 2.2), "#8a8a8a")
            for px, py in PINS:
                paint.fill(paint.oval(sx + px, sy + py, PIN_R), "#f2f2f2", "#7c7c7c")
            pad_x, pad_y = sx + 193, sy + TAPE_Y - 6.5                 # felt pressure pad on a bronze leaf spring
            spring = NSBezierPath.bezierPath()
            spring.moveToPoint_(NSMakePoint(pad_x - 16, pad_y - 6))
            spring.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(pad_x + 30, pad_y - 6),
                                                              NSMakePoint(pad_x + 2, pad_y + 1), NSMakePoint(pad_x + 12, pad_y + 1))
            paint.stroke(spring, "#b48a3c", 1.2)
            paint.fill(NSMakeRect(pad_x, pad_y, 14, 5), "#e6e0d2", "#bdb5a3")
    paint.clipped(shell if clear else paint.rounded(win, 10), insides)

    if clear:   # the front of the see-through shell
        paint.fill(shell, white(1, 0.15), white(1, 0.06))
        paint.stroke(paint.rounded(NSInsetRect(shell_r, 0.5, 0.5), 11.5), white(1, 0.4), 1)
        paint.stroke(paint.rounded(NSInsetRect(shell_r, 5.5, 5.5), 7), white(1, 0.1), 1)
        paint.clipped(shell, lambda: paint.fill(NSMakeRect(sx + 8, sy + 1, 384, 1), white(1, 0.55)))
    else:
        paint.inner_shadow(shell, -2, 4, white(0, 0.35))
        paint.clipped(shell, lambda: paint.fill(NSMakeRect(sx + 6, sy, 388, 1), white(1, 0.22)))
    for x, y in SCREWS:
        draw_screw(sx + x, sy + y, 5)
    draw_head_ramp(sx + 72, sy + 196, clear)
    draw_label(sx, sy, title, subtitle)


def draw_screw(cx, cy, r):
    """A Phillips screw head, sunk into the shell."""
    paint.fill(paint.oval(cx, cy, r + 0.8), white(0, 0.35))
    head = paint.oval(cx, cy, r)
    NSGradient.alloc().initWithStartingColor_endingColor_(hexc("#f6f6f6"), hexc("#8a8a8a")).drawInBezierPath_relativeCenterPosition_(
        head, NSMakePoint(-0.25, -0.35))
    for dx, dy in ((r * 0.6, 0), (0, r * 0.6)):
        line = NSBezierPath.bezierPath()
        line.moveToPoint_(NSMakePoint(cx - dx, cy - dy))
        line.lineToPoint_(NSMakePoint(cx + dx, cy + dy))
        paint.stroke(line, white(0, 0.5), 1.3)


def draw_head_ramp(x, y, clear):
    """The thick part of the shell along the bottom: two capstan holes and two locating holes."""
    t = NSBezierPath.bezierPath()
    t.moveToPoint_(NSMakePoint(x + 23, y))
    t.lineToPoint_(NSMakePoint(x + 233, y))
    t.lineToPoint_(NSMakePoint(x + 256, y + 56))
    t.lineToPoint_(NSMakePoint(x, y + 56))
    t.closePath()
    if clear:
        paint.fill(t, white(1, 0.10), white(1, 0.04))
        paint.stroke(t, white(1, 0.25), 1)
    else:
        paint.fill(t, white(0, 0.18), white(0, 0.3))
        paint.fill(NSMakeRect(x + 23, y, 210, 1), white(1, 0.07))
    hy = y + 33
    for cx in (x + 58, x + 198):                                     # capstan holes
        paint.fill(paint.oval(cx, hy + 0.8, 6), white(1, 0.18))
        hole = paint.oval(cx, hy, 6)
        if not clear:
            paint.fill(hole, "#0c0c0d")
        paint.inner_shadow(hole, 1, 2, white(0, 0.8))
    for hx in (x + 100, x + 144):                                    # locating holes
        hole = paint.rounded(NSMakeRect(hx, hy - 5, 12, 10), 2)
        paint.fill(hole, white(0, 0.55 if clear else 1))
        paint.inner_shadow(hole, 1, 2, white(0, 0.9))


def draw_mechanism(sx, sy, engage, clear):
    """The player's own parts at the bottom of the cassette: the steel capstan through the right
    capstan hole, the rubber pinch roller that presses the tape against it, and the tape head.
    engage runs from 0 (stopped, everything pulled back 7 px) to 1 (playing, touching the tape)."""
    back = (1 - engage) * 7

    def parts():
        roller_y = sy + TAPE_Y + 1.5 + 18 + back
        roller = paint.oval(sx + CAPSTAN[0], roller_y, 18)
        paint.fill(roller, "#2a2a2c", "#0f0f10")
        paint.stroke(paint.oval(sx + CAPSTAN[0], roller_y, 17), white(1, 0.10), 1)
        paint.fill(paint.oval(sx + CAPSTAN[0], roller_y, 4), "#d8d8d8", "#7a7a7a")
        head = NSMakeRect(sx + 183, sy + TAPE_Y + back, 34, 24)
        paint.fill(paint.rounded(head, 3), ("#f8f8f8", 0), ("#b9b9b9", 0.35), ("#e9e9e9", 0.6), ("#8c8c8c", 1), angle=0)
        paint.fill(NSMakeRect(head.origin.x + 16.5, head.origin.y, 1, 8), white(0, 0.6))       # the head gap
        paint.stroke(paint.rounded(NSInsetRect(head, 0.5, 0.5), 2.5), white(0, 0.35), 1)
        paint.fill(paint.oval(sx + CAPSTAN[0], sy + CAPSTAN[1], 4), "#fafafa", "#7a7a7a")      # the capstan
        paint.stroke(paint.oval(sx + CAPSTAN[0], sy + CAPSTAN[1], 3.5), white(0, 0.4), 1)
    if clear:
        paint.clipped(paint.rounded(NSMakeRect(sx, sy, 400, 252), 12), parts)
    else:
        paint.clipped(paint.oval(sx + CAPSTAN[0], sy + 229, 6), parts)


def draw_label(sx, sy, title, subtitle):
    """The label: an index area with the handwritten title, an orange band round the window with the
    side letter, and a printed strip with the tape's brand and type. The window is a hole in it."""
    x, y = sx + LABEL.origin.x, sy + LABEL.origin.y
    lab = NSOffsetRect(LABEL, sx, sy)
    win = paint.rounded(NSOffsetRect(WINDOW, sx, sy), 10)
    shape = paint.rounded(lab, 5)
    shape.appendBezierPath_(win)
    shape.setWindingRule_(NSEvenOddWindingRule)
    paint.with_shadow(paint.shadow(1, 2, white(0, 0.45)), lambda: paint.fill(shape, "#ece8dd"))
    paint.fill(shape, "#fbf9f3", "#efebe1")

    def body():
        rule = hexc("#466eaa", 0.30)
        tiny = paint.font("Helvetica-Bold", 6.5, True)
        paint.text(u"INDEX", NSMakeRect(x + 12, y + 20, 40, 9), tiny, "#7d8aa0", kern=1)
        paint.fill(NSMakeRect(x + 46, y + 28, 298, 1), rule)
        paint.fill(NSMakeRect(x + 12, y + 50, 332, 1), rule)
        big, small = label_fonts()
        paint.text(title, NSMakeRect(x + 50, y + 26.5 - big.ascender(), 292, 30), big, INK)
        paint.text(subtitle, NSMakeRect(x + 16, y + 48.5 - small.ascender(), 326, 26), small, INK)
        paint.fill(NSMakeRect(x, y + 56, 356, 86), "#ee7a36", "#df5f22")
        paint.fill(NSMakeRect(x, y + 56, 356, 1), white(0, 0.12))
        paint.text(u"A", NSMakeRect(x + 15, y + 78, 34, 30), paint.font("Helvetica-Bold", 26, True), white(1, 0.95))
        paint.text(u"SIDE", NSMakeRect(x + 14, y + 108, 40, 9), tiny, white(1, 0.85), kern=1.2)
        paint.text(u"60", NSMakeRect(x + 304, y + 80, 44, 24), paint.font("Helvetica-Bold", 22, True), white(1, 0.95),
                   NSRightTextAlignment)
        paint.text(u"MIN", NSMakeRect(x + 304, y + 106, 44, 9), tiny, white(1, 0.85), NSRightTextAlignment, kern=1.2)
        paint.text(u"KASSETT", NSMakeRect(x + 14, y + 144, 140, 14), paint.font("Helvetica-Bold", 11, True), "#1f1f1f", kern=1.5)
        paint.text(u"TYPE I (NORMAL) POSITION", NSMakeRect(x + 14, y + 156, 160, 9), tiny, "#555555", kern=0.6)
        arrow = NSBezierPath.bezierPath()
        ax, ay = x + 170, y + 154
        for i, (px, py) in enumerate(((0, -2), (16, -2), (16, -5.5), (24, 0), (16, 5.5), (16, 2), (0, 2))):
            (arrow.lineToPoint_ if i else arrow.moveToPoint_)(NSMakePoint(ax + px, ay + py))
        arrow.closePath()
        paint.fill(arrow, "#df5f22")
        paint.text(u"C60", NSMakeRect(x + 280, y + 145, 64, 18), paint.font("Helvetica-Bold", 14, True), "#1f1f1f",
                   NSRightTextAlignment)
    paint.clipped(shape, body)
    paint.inner_shadow(win, 1, 2, white(0, 0.6))      # the label's thickness at the window's edge
    paint.stroke(win, white(0, 0.3), 1)


_packs = {}


def draw_pack(cx, cy, r):
    """A pack of brown tape seen edge-on: fine windings, a sheen, a darker rim."""
    key = int(r * 2)
    img = _packs.get(key)
    if img is None:
        d = key + 2

        def body():
            c = d / 2.0
            paint.fill(paint.oval(c, c, r), "#4a2f1b")
            ring = hexc("#5a3b23")
            rr = r - 0.5
            while rr > HUB:
                paint.stroke(paint.oval(c, c, rr), ring, 0.8)
                rr -= 1.6
            sheen = paint.oval(c, c, r)
            NSGradient.alloc().initWithStartingColor_endingColor_(white(1, 0.12), white(1, 0)).drawInBezierPath_relativeCenterPosition_(
                sheen, NSMakePoint(-0.35, -0.45))
            paint.stroke(paint.oval(c, c, r - 0.5), white(0, 0.4), 1)
        img = flipped_image(d, d, body)
        if len(_packs) > 60:
            _packs.clear()
        _packs[key] = img
    sz = img.size()
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(cx - sz.width / 2.0, cy - sz.height / 2.0, sz.width, sz.height),
        NSZeroRect, NSCompositeSourceOver, 1.0, True, None)


def draw_hub(cx, cy, angle):
    """A white hub with its tape clamp and six teeth, and the player's three-spline spindle in it,
    turned counterclockwise by `angle` degrees (both turn together). Unlit: hub_light() lights it."""
    r = HUB
    NSGraphicsContext.saveGraphicsState()
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(cx, cy)
    t.rotateByDegrees_(-angle)
    t.concat()
    ring = paint.oval(0, 0, r)
    paint.fill(ring, "#eee8da")
    paint.stroke(paint.oval(0, 0, r - 0.5), "#a99f8b", 1)
    paint.stroke(paint.oval(0, 0, r - 4.5), white(1, 0.7), 1)
    paint.stroke(paint.oval(0, 0, r - 5.5), white(0, 0.08), 1)
    clamp = NSMakeRect(-5, -r + 0.5, 10, 6)                       # where the tape's leader is clamped
    paint.fill(clamp, "#e3dccd")
    paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(clamp, 0.5, 0.5)), white(0, 0.25), 1)
    for i in range(6):                                            # holes through the hub's web
        NSGraphicsContext.saveGraphicsState()
        rot = NSAffineTransform.transform()
        rot.rotateByDegrees_(60 * i + 30)
        rot.concat()
        paint.fill(paint.oval(0, -(r * 0.62), 2.6), "#2a221c")
        NSGraphicsContext.restoreGraphicsState()
    hole = paint.oval(0, 0, 14.5)
    paint.fill(hole, "#16120f")
    paint.inner_shadow(hole, 1, 2, white(0, 0.7))
    tooth = hexc("#ece6d9")
    for i in range(6):
        NSGraphicsContext.saveGraphicsState()
        rot = NSAffineTransform.transform()
        rot.rotateByDegrees_(60 * i)
        rot.concat()
        paint.fill(paint.corners(NSMakeRect(-1.8, -14.8, 3.6, 4.4), 0, 0, 1, 1), tooth)
        NSGraphicsContext.restoreGraphicsState()
    shaft = paint.oval(0, 0, 8)                                   # the player's spindle, engaged in the teeth
    paint.fill(shaft, "#e4e4e4", "#8d8d8d")
    for i in range(3):
        NSGraphicsContext.saveGraphicsState()
        rot = NSAffineTransform.transform()
        rot.rotateByDegrees_(120 * i + 30)
        rot.concat()
        paint.fill(NSMakeRect(-1.6, -12.4, 3.2, 5.4), "#bfbfbf", "#8a8a8a")
        NSGraphicsContext.restoreGraphicsState()
    paint.fill(paint.oval(0, 0, 3), "#6a6a6a")
    paint.fill(paint.oval(-0.8, -0.8, 1.1), white(1, 0.6))
    NSGraphicsContext.restoreGraphicsState()


HUB_BOX = int(2 * HUB + 4)


def hub_image():
    c = HUB_BOX / 2.0
    return flipped_image(HUB_BOX, HUB_BOX, lambda: draw_hub(c, c, 0))


def hub_light():
    """Light from above on the hub, which stays put while the hub turns under it."""
    def body():
        c = HUB_BOX / 2.0
        ring = paint.oval(c, c, HUB)
        NSGradient.alloc().initWithStartingColor_endingColor_(white(1, 0.55), white(1, 0)).drawInBezierPath_relativeCenterPosition_(
            ring, NSMakePoint(-0.35, -0.45))
        paint.clipped(ring, lambda: paint.fill(NSMakeRect(0, c, HUB_BOX, c), white(0, 0), white(0, 0.14)))
    return flipped_image(HUB_BOX, HUB_BOX, body)


class ReelView(NSView):
    """The two hubs as Core Animation layers. The GPU turns them; Python only sets each one's speed
    when it changes (play, pause, a seek, or a pack growing a little), so playing costs no CPU."""

    def initWithFrame_(self, frame):
        self = super(ReelView, self).initWithFrame_(frame)
        if self:
            root = CALayer.layer()
            root.setGeometryFlipped_(True)
            self.setLayer_(root)
            self.setWantsLayer_(True)
            self.hubs, self.speeds = [], []
            self.glass = None
        return self

    def hitTest_(self, point):
        return None          # clicks and window drags go to the cassette underneath

    def setUp(self, centers, glass):
        root = self.layer()
        image, light = hub_image(), hub_light()
        for cx, cy in centers:
            hub = CALayer.layer()
            hub.setBounds_(((0, 0), (HUB_BOX, HUB_BOX)))
            hub.setPosition_((cx, cy))
            hub.setContents_(image)
            spin = CABasicAnimation.animationWithKeyPath_("transform.rotation.z")
            spin.setFromValue_(0.0)
            spin.setToValue_(-2 * math.pi)       # counterclockwise on screen, like tape going left to right
            spin.setDuration_(1.0)
            spin.setRepeatCount_(1e9)
            hub.addAnimation_forKey_(spin, "spin")
            hub.setSpeed_(0.0)
            hub.setTimeOffset_(1e5 + len(self.hubs) * 0.37)   # room to run backwards when rewinding
            root.addSublayer_(hub)
            lit = CALayer.layer()
            lit.setBounds_(((0, 0), (HUB_BOX, HUB_BOX)))
            lit.setPosition_((cx, cy))
            lit.setContents_(light)
            root.addSublayer_(lit)
            self.hubs.append(hub)
            self.speeds.append(0.0)
        self.glass = CALayer.layer()
        self.glass.setFrame_(((0, 0), (self.bounds().size.width, self.bounds().size.height)))
        self.glass.setContents_(glass)
        root.addSublayer_(self.glass)

    def setSpeeds(self, radians_per_second):
        """Change each hub's speed without a jump in where it is."""
        now = CACurrentMediaTime()
        for i, (hub, w) in enumerate(zip(self.hubs, radians_per_second)):
            turns = w / (2 * math.pi)
            if abs(turns - self.speeds[i]) < 0.002:
                continue
            local = hub.convertTime_fromLayer_(now, None)
            hub.setTimeOffset_(local)
            hub.setBeginTime_(now)
            hub.setSpeed_(turns)
            self.speeds[i] = turns


# ---- piano keys --------------------------------------------------------------------------------------
class KeyButton(NSButton):
    def isFlipped(self):
        return True

    def mouseDownCanMoveWindow(self):
        return False


class KeyCell(NSButtonCell):
    """A glossy plastic key on the silver strip, lit the way Lion's Aqua buttons are. `accent` makes it
    candy orange (play while playing)."""

    def drawWithFrame_inView_(self, frame, view):
        down = self.isHighlighted()
        accent = getattr(self, "accent", False)
        w = frame.size.width
        r = NSMakeRect(2, 1 + (1 if down else 0), w - 4, frame.size.height - 6)
        radius = min(9.0, r.size.height * 0.2)
        shape = paint.rounded(r, radius)
        paint.with_shadow(paint.shadow(1 if down else 3, 2 if down else 4, white(0, 0.5)),
                          lambda: paint.fill(shape, "#888888"))
        if accent:
            body = (("#f08a2c", 0), ("#e2690f", 0.5), ("#f39a3c", 1)) if down else \
                (("#ffb04a", 0), ("#f7861d", 0.5), ("#e8700f", 0.51), ("#ffb35c", 1))
            rim, glow = hexc("#a9530a"), hexc("#ffd59a", 0.55)
        else:
            body = (("#d9d9d9", 0), ("#c4c4c4", 0.5), ("#d6d6d6", 1)) if down else \
                (("#ffffff", 0), ("#ececec", 0.5), ("#dcdcdc", 0.51), ("#f6f6f6", 1))
            rim, glow = white(0, 0.42), white(1, 0.7)
        paint.fill(shape, *body)

        def light():
            gloss = paint.rounded(NSMakeRect(r.origin.x + 3, r.origin.y + 2, r.size.width - 6, r.size.height * 0.48),
                                  max(2.0, radius - 2))
            paint.fill(gloss, white(1, 0.75 if not down else 0.35), white(1, 0.12))
            paint.fill(NSMakeRect(r.origin.x, r.origin.y + r.size.height - 10, r.size.width, 10), white(1, 0), glow)
        paint.clipped(shape, light)
        paint.stroke(paint.rounded(NSInsetRect(r, 0.5, 0.5), radius - 0.5), rim, 1)
        paint.stroke(paint.rounded(NSInsetRect(r, 1.5, 1.5), radius - 1.5), white(1, 0.35 if accent else 0.6), 1)
        if down:
            paint.inner_shadow(shape, 2, 4, white(0, 0.35))
        name = getattr(self, "glyph", "play")
        gw, gh = glyphs.size(name)
        k = 1.0 if r.size.height > 40 else 0.72
        alpha = 1.0 if self.isEnabled() else 0.35
        gx, gy = r.origin.x + (r.size.width - gw * k) / 2.0, r.origin.y + (r.size.height - gh * k) / 2.0
        if accent:
            glyphs.draw_at(name, gx, gy - 1, white(0, 0.3 * alpha), k)
            glyphs.draw_at(name, gx, gy, white(1, alpha), k)
        else:
            glyphs.draw_at(name, gx, gy + 1, white(1, 0.95 * alpha), k)
            glyphs.draw_at(name, gx, gy, hexc("#3d3d3d", alpha), k)


def make_key(parent, frame, glyph, tip, target, action):
    key = KeyButton.alloc().initWithFrame_(frame)
    cell = KeyCell.alloc().init()
    cell.glyph, cell.accent = glyph, False
    cell.setButtonType_(NSMomentaryChangeButton)
    key.setCell_(cell)
    key.setTarget_(target)
    key.setAction_(action)
    key.setToolTip_(tip)
    parent.addSubview_(key)
    return key


# ---- the volume wheel ----------------------------------------------------------------------------------
class WheelView(FlippedView):
    """A ridged thumb wheel in a slot, like a Walkman's. Drag it, or scroll over it."""

    def initWithFrame_(self, frame):
        self = super(WheelView, self).initWithFrame_(frame)
        if self:
            self.volume, self.enabled = 50, False
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
        w = self.bounds().size.width
        f = paint.font("Helvetica-Bold", 7.5, True)
        ink = hexc("#4d4d4d", 1 if self.enabled else 0.45)
        paint.text(u"VOLUME", NSMakeRect(2, 0, 60, 10), f, ink, kern=1.3, sh=paint.engraved())
        if self.enabled:
            paint.text(u"%d" % self.volume, NSMakeRect(w - 32, 0, 30, 10), f, ink, NSRightTextAlignment, sh=paint.engraved())
        slot_r = NSMakeRect(0, 15, w, 28)
        paint.fill(paint.rounded(NSOffsetRect(slot_r, 0, 1), 6), white(1, 0.8))
        slot = paint.rounded(slot_r, 6)
        paint.fill(slot, "#232325")
        paint.inner_shadow(slot, 2, 3, white(0, 0.9))
        drum = NSMakeRect(4, 19, w - 8, 20)

        def ridges():
            paint.fill(drum, ("#4a4a4c", 0), ("#d6d6d6", 0.45), ("#bdbdbd", 0.6), ("#3c3c3e", 1))
            cx, radius = drum.origin.x + drum.size.width / 2.0, drum.size.width / 2.0
            phase = self.volume * 2.0
            for i in range(-30, 31):
                angle = (i * 6 + phase % 6) * math.pi / 180 * 1.5
                if abs(angle) >= math.pi / 2:
                    continue
                x = cx + radius * math.sin(angle)
                lit = 0.5 * math.cos(angle)
                paint.fill(NSMakeRect(x, drum.origin.y, 1, drum.size.height), white(0, 0.35 * lit + 0.1))
                paint.fill(NSMakeRect(x + 1, drum.origin.y, 1, drum.size.height), white(1, 0.5 * lit))
            paint.fill(NSMakeRect(drum.origin.x, drum.origin.y, 12, drum.size.height), white(0, 0.45), white(0, 0), angle=0)
            paint.fill(NSMakeRect(drum.origin.x + drum.size.width - 12, drum.origin.y, 12, drum.size.height),
                       white(0, 0), white(0, 0.45), angle=0)
        paint.clipped(paint.rounded(drum, 3), ridges)

    def change(self, v, final):
        v = max(0, min(100, int(round(v))))
        changed = v != self.volume
        self.volume = v
        self.setNeedsDisplay_(True)
        if self.onChange and (changed or final):
            self.onChange(v, final)

    def mouseDown_(self, event):
        if self.enabled:
            p = event.locationInWindow()
            self.start = (p.x, p.y, self.volume)

    def mouseDragged_(self, event):
        if self.start:
            x0, y0, v0 = self.start
            p = event.locationInWindow()
            self.change(v0 + (p.x - x0) * 0.5 + (p.y - y0) * 0.5, False)

    def mouseUp_(self, event):
        if self.start:
            self.start = None
            self.change(self.volume, True)

    def scrollWheel_(self, event):
        if self.enabled and (event.deltaY() or event.deltaX()):
            self.change(self.volume + (event.deltaY() - event.deltaX()) * 2, True)


# ---- the LCD under the cassette ----------------------------------------------------------------------
class LCDView(FlippedView):
    """iTunes 10's status display: the cover, title, artist and times. Click or drag along it to seek."""

    def initWithFrame_(self, frame):
        self = super(LCDView, self).initWithFrame_(frame)
        if self:
            self.line1, self.line2 = u"Kassett", u""
            self.art, self.name = None, u""
            self.p, self.elapsed, self.remaining = 0.0, u"", u""
            self.enabled, self.dragging, self.onSeek = False, False, None
        return self

    def mouseDownCanMoveWindow(self):
        return False

    def drawRect_(self, rect):
        w, h = self.bounds().size.width, self.bounds().size.height - 1
        r = NSMakeRect(0.5, 0.5, w - 1, h - 1)
        paint.fill(paint.rounded(NSOffsetRect(r, 0, 1), 6), white(1, 0.3))
        shape = paint.rounded(r, 6)
        paint.fill(shape, "#f7f9ee", "#d6dcc6")
        paint.inner_shadow(shape, 1, 3, white(0, 0.25))
        paint.clipped(shape, lambda: paint.fill(NSMakeRect(0, 0, w, h * 0.45), white(1, 0.35), white(1, 0.05)))
        paint.stroke(shape, "#4d5144", 1)
        cover = NSMakeRect(8, 7, 36, 36)
        if self.art is not None:
            paint.image(self.art, cover)
        elif self.name:
            art.draw_placeholder(cover, self.name)
        else:
            paint.fill(cover, white(0, 0.08))
        paint.stroke(NSBezierPath.bezierPathWithRect_(NSInsetRect(cover, -0.5, -0.5)), white(0, 0.3), 1)
        tx, tw = 54, w - 54 - 70
        paint.text(self.line1, NSMakeRect(tx, 6, tw, 16), paint.ui(12, True), "#282a24")
        paint.text(self.line2, NSMakeRect(tx, 21, tw, 15), paint.ui(11), "#464840")
        paint.text(self.remaining, NSMakeRect(w - 64, 7, 54, 15), paint.ui(11, True), "#282a24", NSRightTextAlignment)
        paint.text(self.elapsed, NSMakeRect(w - 64, 21, 54, 15), paint.ui(10), "#464840", NSRightTextAlignment)
        if self.elapsed:
            track = NSMakeRect(tx, 39, w - tx - 12, 3)
            paint.fill(paint.rounded(track, 1.5), white(0, 0.16))
            paint.fill(paint.rounded(NSMakeRect(tx, 39, max(3, track.size.width * self.p), 3), 1.5), "#3c4036")

    def fraction(self, event):
        x = self.convertPoint_fromView_(event.locationInWindow(), None).x
        return max(0.0, min(1.0, (x - 54) / float(self.bounds().size.width - 54 - 12)))

    def mouseDown_(self, event):
        if self.enabled and self.elapsed:
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
            if self.onSeek:
                self.onSeek(self.fraction(event))


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
        self.cassette = CassetteView.alloc().initWithFrame_(NSMakeRect(18, 56, 452, 286))
        deck.addSubview_(self.cassette)
        self.lcd = LCDView.alloc().initWithFrame_(NSMakeRect(18, 354, 452, 51))
        self.lcd.onSeek = self.app.seekToFraction
        deck.addSubview_(self.lcd)

        # Four big keys down the silver strip, lined up with the cassette window, and the volume wheel
        # lined up with the LCD.
        kx = STRIP_X + (DECK_W - STRIP_X - 84) / 2.0
        self.playKey = make_key(deck, NSMakeRect(kx, 54, 84, 64), "play", u"Play or pause", self.app, "playPause:")
        self.nextKey = make_key(deck, NSMakeRect(kx, 129, 84, 64), "next", u"Next song", self.app, "next:")
        self.prevKey = make_key(deck, NSMakeRect(kx, 204, 84, 64), "prev", u"Previous song", self.app, "previous:")
        self.libraryKey = make_key(deck, NSMakeRect(kx, 279, 84, 64), "eject", u"Open the library", self.app,
                                   "showLibrary:")
        self.keys = {u"PLAY": self.playKey, u"NEXT": self.nextKey, u"PREV": self.prevKey}
        self.wheel = WheelView.alloc().initWithFrame_(NSMakeRect(kx, 357, 84, 46))
        self.wheel.onChange = self.app.volumeChanged
        deck.addSubview_(self.wheel)

        self.login = NSButton.alloc().initWithFrame_(NSMakeRect(18 + 452 - 112, 362, 104, 32))
        self.login.setBezelStyle_(NSRoundedBezelStyle)
        self.login.setTitle_(u"Log In\u2026")
        self.login.setTarget_(self.app)
        self.login.setAction_("logIn:")
        deck.addSubview_(self.login)

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
        for v in (self.upNextButton, self.airplayButton):
            v.setHidden_(not logged_in)
        self.login.setHidden_(logged_in)
        if not logged_in:
            for k in self.keys.values():
                k.setEnabled_(False)
            self.wheel.setVolume(50, False)

    def setTape(self, title, subtitle):
        self.cassette.setLabel(title, subtitle)
        self.lcd.line1, self.lcd.line2 = title, subtitle
        self.lcd.setNeedsDisplay_(True)

    def setArt(self, img, name, blank):
        self.lcd.art, self.lcd.name = img, (u"" if blank else name)
        self.lcd.setNeedsDisplay_(True)

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
        self.cassette.setEngaged(playing)
        if self.whirr is None:
            self.cassette.spin(1.0 if playing else 0.0)
        cell = self.playKey.cell()
        cell.glyph, cell.accent = ("pause" if playing else "play"), playing
        self.playKey.setToolTip_(u"Pause" if playing else u"Play")
        self.playKey.setEnabled_(controllable)
        for k in (self.nextKey, self.prevKey):
            k.setEnabled_(controllable and has_track)
        for k in self.keys.values():
            k.setNeedsDisplay_(True)
        self.ensureTimer()

    def setPosition(self, progress_ms, duration_ms, jumped):
        p = float(progress_ms) / duration_ms if duration_ms else 0.0
        if jumped and abs(p - self.cassette.p) > 0.01 and self.window.isVisible():
            self.whirr = (self.cassette.p, p, time.time())
            self.cassette.coarse = True
            self.cassette.spin(WHIRR_SPEED if p > self.cassette.p else -WHIRR_SPEED)
        elif self.whirr is None:
            self.cassette.setProgress(p)
            self.cassette.spin(1.0 if self.playing else 0.0)
        self.p_target = p
        lcd = self.lcd
        if not lcd.dragging:
            lcd.p = p
        lcd.elapsed = paint.fmt(progress_ms) if duration_ms else u""
        lcd.remaining = u"\u2212" + paint.fmt(duration_ms - progress_ms) if duration_ms else u""
        lcd.enabled = bool(duration_ms) and getattr(self, "controllable", True)
        lcd.setNeedsDisplay_(True)
        self.ensureTimer()

    def setVolume(self, volume, enabled):
        self.wheel.setVolume(volume if volume is not None else 50,
                             enabled and volume is not None and getattr(self, "controllable", True))

    # ---- animation ----------------------------------------------------------------------------------
    def animating(self):
        return self.window.isVisible() and not self.window.isMiniaturized() and \
            (self.whirr is not None or self.cassette.mechanismMoving())

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
                self.cassette.coarse = False
                self.cassette.setProgress(self.p_target)
                self.cassette.spin(1.0 if self.playing else 0.0)
            else:
                self.cassette.setProgress(start_p + (end_p - start_p) * ease(t))
        self.cassette.stepMechanism(dt)
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
MINI_STRIP = 286


class MiniView(FlippedView):
    """The player shrunk to a strip: the same blue body and silver key strip, a small cassette."""

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
            self.bg = flipped_image(b.size.width, b.size.height,
                                    lambda: draw_body(b.size.width, b.size.height, MINI_STRIP, False))
        draw_part(self.bg, rect, NSCompositeCopy)
        draw_mini_cassette(12, 16, self.angle)
        x, w = 122, MINI_STRIP - 122 - 14
        sh = paint.shadow(-1, 0, white(0, 0.35))
        paint.text(self.title, NSMakeRect(x, 22, w, 18), paint.ui(13, True), white(1), sh=sh)
        paint.text(self.artist, NSMakeRect(x, 40, w, 16), paint.ui(11), white(1, 0.85), sh=sh)
        track = NSMakeRect(x, 64, w, 5)
        paint.fill(paint.rounded(NSOffsetRect(track, 0, 1), 2.5), white(1, 0.25))
        shape = paint.rounded(track, 2.5)
        paint.fill(shape, white(0, 0.35))
        paint.inner_shadow(shape, 1, 1, white(0, 0.5))
        if self.has_track:
            paint.fill(paint.rounded(NSMakeRect(x, 64, max(5, w * self.p), 5), 2.5), "#f6f6f6", "#c9c9c9")


def draw_mini_cassette(x, y, angle):
    """The big cassette's look at 96 x 62: the label's index area, the orange band and two hubs."""
    shell = paint.rounded(NSMakeRect(x, y, 96, 62), 5)
    paint.with_shadow(paint.shadow(1, 3, white(0, 0.6)), lambda: paint.fill(shell, "#222226"))
    paint.fill(shell, "#414146", "#222226")
    paint.clipped(shell, lambda: paint.fill(NSMakeRect(x + 4, y, 88, 1), white(1, 0.2)))
    lab = paint.rounded(NSMakeRect(x + 6, y + 5, 84, 42), 3)

    def label():
        paint.fill(NSMakeRect(x + 6, y + 5, 84, 42), "#fbf9f3", "#efebe1")
        paint.fill(NSMakeRect(x + 10, y + 12, 76, 0.8), hexc("#466eaa", 0.35))
        paint.fill(NSMakeRect(x + 6, y + 16, 84, 24), "#ee7a36", "#df5f22")
    paint.clipped(lab, label)
    win = paint.rounded(NSMakeRect(x + 22, y + 18, 52, 20), 5)
    paint.fill(win, "#2b1d14")
    paint.inner_shadow(win, 1, 2, white(0, 0.8))
    for cx in (x + 34, x + 62):
        NSGraphicsContext.saveGraphicsState()
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(cx, y + 28)
        t.rotateByDegrees_(-angle)
        t.concat()
        paint.fill(paint.oval(0, 0, 7.5), "#f1ece0")
        paint.fill(paint.oval(0, 0, 3.4), "#1a1410")
        for i in range(6):
            NSGraphicsContext.saveGraphicsState()
            rot = NSAffineTransform.transform()
            rot.rotateByDegrees_(60 * i)
            rot.concat()
            paint.fill(NSMakeRect(-0.6, -3.4, 1.2, 1.4), "#f1ece0")
            NSGraphicsContext.restoreGraphicsState()
        NSGraphicsContext.restoreGraphicsState()
    for sx_, sy_ in ((x + 4, y + 4), (x + 92, y + 4), (x + 4, y + 58), (x + 92, y + 58)):
        paint.fill(paint.oval(sx_, sy_, 1.6), "#9a9a9a")


class Mini(NSObject):
    def initWithApp_(self, app):
        self = super(Mini, self).init()
        if self is None:
            return None
        self.app = app
        self.timer = None
        self.playing = False
        p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, MINI_STRIP + 190, 94), NSTitledWindowMask | NSClosableWindowMask | NSUtilityWindowMask,
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
        x, y = MINI_STRIP + 12, 26
        self.prevButton = make_key(self.view, NSMakeRect(x, y, 40, 42), "prev", u"Previous song", app, "previous:")
        self.playButton = make_key(self.view, NSMakeRect(x + 42, y, 44, 42), "play", u"Play or pause", app, "playPause:")
        self.nextButton = make_key(self.view, NSMakeRect(x + 88, y, 40, 42), "next", u"Next song", app, "next:")
        self.expandButton = make_key(self.view, NSMakeRect(x + 134, y + 6, 30, 30), "expand",
                                     u"Show the cassette player", app, "showDeck:")
        self.window = p
        return self

    def show(self, title, artist, p, playing, has_track):
        v = self.view
        v.title, v.artist, v.p, v.has_track = title, artist, p, has_track
        v.setNeedsDisplay_(True)
        self.playing = playing
        self.playButton.cell().glyph = "pause" if playing else "play"
        self.playButton.cell().accent = playing
        self.playButton.setNeedsDisplay_(True)
        controllable = getattr(self.app, "controllable", True)
        for b in (self.prevButton, self.nextButton):
            b.setEnabled_(has_track and controllable)
        self.playButton.setEnabled_(controllable)
        if playing and self.timer is None and self.window.isVisible():
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(1 / 12.0, self, "frame:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def frame_(self, timer):
        if not (self.playing and self.window.isVisible()):
            self.timer.invalidate()
            self.timer = None
            return
        self.view.angle = (self.view.angle + 360 / 12.0 / 1.6) % 360
        self.view.setNeedsDisplayInRect_(NSMakeRect(12, 16, 96, 62))

    def windowWillClose_(self, note):
        self.app.miniClosed()
