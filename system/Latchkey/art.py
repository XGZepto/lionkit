# -*- coding: utf-8 -*-
"""Latchkey's small pictures: the menu bar key, and the lock, signal fan and status lights in the menu.

The menu bar glyph is a key whose bow is the Wi-Fi fan, so it reads differently from Lion's own
Wi-Fi menu next to it. Lion's menu extras are near-black with a 1 px white emboss below, and pure
white while their menu is open; status items don't get that treatment for free, so both variants
are drawn here."""
from AppKit import (NSBezierPath, NSColor, NSGradient, NSGraphicsContext, NSImage, NSMakePoint,
                    NSMakeRect, NSMakeSize, NSShadow, NSInsetRect, NSCompositeSourceOver)

INK = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.82)
INK_OFF = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.22)
WHITE = NSColor.whiteColor()
WHITE_OFF = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.38)


def rgb(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def band(center, r0, r1, a0, a1):
    """A slice of a ring between radii r0 and r1, angles a0..a1 (degrees); r0 = 0 gives a wedge."""
    p = NSBezierPath.bezierPath()
    if r0 <= 0:
        p.moveToPoint_(center)
        p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(center, r1, a0, a1)
    else:
        p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(center, r1, a0, a1)
        p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(center, r0, a1, a0, True)
    p.closePath()
    return p


def _image(w, h, draw):
    img = NSImage.alloc().initWithSize_(NSMakeSize(w, h))
    img.lockFocus()
    draw()
    img.unlockFocus()
    return img


# ---- menu bar ----------------------------------------------------------------------------------
BAR_W, BAR_H = 24, 18
# The fan opens to the left from the point where the key's shaft starts.
FAN_CENTER = NSMakePoint(10.5, 9.0)
FAN_BANDS = ((0, 2.6), (3.6, 5.9), (6.9, 9.4))


def _key_parts():
    """(fan bands from the tip outwards, shaft with its teeth) as paths."""
    bands = [band(FAN_CENTER, r0, r1, 136, 224) for r0, r1 in FAN_BANDS]
    shaft = NSBezierPath.bezierPath()
    shaft.appendBezierPathWithRect_(NSMakeRect(10.0, 8.0, 12.5, 2.0))
    shaft.appendBezierPathWithRect_(NSMakeRect(17.0, 5.0, 1.6, 3.0))
    shaft.appendBezierPathWithRect_(NSMakeRect(20.4, 5.5, 1.6, 2.5))
    return bands, shaft


def menubar_glyph(lit, highlighted=False, dim=False):
    """The key. `lit` is how many fan bands are dark (0-3); `dim` greys out the whole key (Wi-Fi off)."""
    on, off = (WHITE, WHITE_OFF) if highlighted else (INK, INK_OFF)
    if dim:
        on = off

    def draw():
        bands, shaft = _key_parts()
        NSGraphicsContext.saveGraphicsState()
        if not highlighted:
            emboss = NSShadow.alloc().init()
            emboss.setShadowOffset_(NSMakeSize(0, -1))
            emboss.setShadowBlurRadius_(0)
            emboss.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.55))
            emboss.set()
        on.set()
        shaft.fill()
        for i, p in enumerate(bands):
            (on if i < lit else off).set()
            p.fill()
        NSGraphicsContext.restoreGraphicsState()
    return _image(BAR_W, BAR_H, draw)


# ---- menu rows ---------------------------------------------------------------------------------
def signal_fan(level, highlighted=False, enabled=True):
    """Lion's upright Wi-Fi fan for a network row: `level` of 4 segments dark."""
    if highlighted:
        on, off = WHITE, WHITE_OFF
    elif enabled:
        on, off = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.78), NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.2)
    else:
        on = off = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.2)

    def draw():
        c = NSMakePoint(8.0, 1.0)
        for i, (r0, r1) in enumerate(((0, 3.0), (4.1, 6.6), (7.7, 10.2), (11.3, 13.4))):
            (on if i < level else off).set()
            band(c, r0, r1, 47, 133).fill()
    return _image(16, 12, draw)


def lock(highlighted=False, enabled=True):
    color = WHITE if highlighted else NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.7 if enabled else 0.25)

    def draw():
        color.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(0.5, 0.5, 8, 6), 1, 1).fill()
        shackle = NSBezierPath.bezierPath()
        shackle.moveToPoint_(NSMakePoint(2.25, 6.5))
        shackle.lineToPoint_(NSMakePoint(2.25, 8.0))
        shackle.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(NSMakePoint(4.5, 8.0), 2.25, 180, 0, True)
        shackle.lineToPoint_(NSMakePoint(6.75, 6.5))
        shackle.setLineWidth_(1.5)
        shackle.stroke()
    return _image(9, 11, draw)


# Glossy "gumdrop" lights, like the ones in Lion's Network preferences.
LIGHTS = {
    "green": (rgb(120, 214, 104), rgb(60, 160, 75), rgb(36, 112, 46)),
    "amber": (rgb(255, 214, 110), rgb(226, 150, 30), rgb(160, 98, 12)),
    "orange": (rgb(250, 160, 100), rgb(214, 120, 40), rgb(150, 74, 20)),
    "gray": (rgb(214, 214, 214), rgb(140, 140, 140), rgb(98, 98, 98)),
}


def status_light(name, size=11):
    top, bottom, rim = LIGHTS[name]

    def draw():
        r = NSMakeRect(0.5, 1.0, size - 1, size - 1)
        NSGraphicsContext.saveGraphicsState()
        sh = NSShadow.alloc().init()
        sh.setShadowOffset_(NSMakeSize(0, -0.5))
        sh.setShadowBlurRadius_(1.0)
        sh.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.35))
        sh.set()
        rim.set()
        NSBezierPath.bezierPathWithOvalInRect_(r).fill()
        NSGraphicsContext.restoreGraphicsState()
        inner = NSBezierPath.bezierPathWithOvalInRect_(NSInsetRect(r, 0.75, 0.75))
        NSGradient.alloc().initWithStartingColor_endingColor_(top, bottom).drawInBezierPath_angle_(inner, -90)
        w = r.size.width
        gloss = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(r.origin.x + w * 0.2, r.origin.y + w * 0.5, w * 0.6, w * 0.42))
        NSGradient.alloc().initWithStartingColor_endingColor_(
            NSColor.colorWithCalibratedWhite_alpha_(1, 0.85), NSColor.colorWithCalibratedWhite_alpha_(1, 0.1)
        ).drawInBezierPath_angle_(gloss, -90)
    return _image(size, size + 1, draw)


def draw_image(img, x, y, fraction=1.0):
    img.drawAtPoint_fromRect_operation_fraction_(NSMakePoint(x, y), NSMakeRect(0, 0, 0, 0), NSCompositeSourceOver, fraction)
