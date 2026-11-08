# -*- coding: utf-8 -*-
"""Kassett's glyphs, transcribed from the SVGs in design/kassett. Each is drawn in its own
view box (y down, like SVG) and scaled into whatever rect it's given, in any color."""
import math

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403


def _poly(*pts):
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(*pts[0]))
    for pt in pts[1:]:
        p.lineToPoint_(NSMakePoint(*pt))
    p.closePath()
    return p


def _rect(x, y, w, h, r=0):
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), r, r)


def _circle(cx, cy, r):
    return NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))


def _line(*pts):
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(*pts[0]))
    for pt in pts[1:]:
        p.lineToPoint_(NSMakePoint(*pt))
    return p


def _fill(p):
    p.fill()


def _stroke(width, p):
    p.setLineWidth_(width)
    p.setLineCapStyle_(NSButtLineCapStyle)
    p.setLineJoinStyle_(NSRoundLineJoinStyle)
    p.stroke()


def _heart():
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(8, 14))
    p.lineToPoint_(NSMakePoint(2.2, 8.3))
    r = math.hypot(5.8, 4.7) / 2
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(NSMakePoint(5.1, 5.95), r, 141, 321, False)
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(NSMakePoint(10.9, 5.95), r, 219, 399, False)
    p.closePath()
    p.fill()


def _disc():
    p = _circle(8, 8, 6.8)
    p.appendBezierPath_(_circle(8, 8, 2))
    p.setWindingRule_(NSEvenOddWindingRule)
    p.fill()


def _person():
    _circle(8, 5, 3.2).fill()
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(1.8, 15))
    p.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(8, 9.2), NSMakePoint(2.4, 10.8), NSMakePoint(5, 9.2))
    p.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(14.2, 15), NSMakePoint(11, 9.2), NSMakePoint(13.6, 10.8))
    p.closePath()
    p.fill()


def _playlist():
    for r in ((1, 2, 8, 1.8), (1, 6, 8, 1.8), (1, 10, 5, 1.8)):
        _rect(*r).fill()
    _stroke(1.6, _line((12, 2), (12, 10.5)))
    _circle(10.6, 11.4, 2.2).fill()
    _stroke(1.6, _line((12, 2.6), (15, 4)))


def _now_playing():
    _poly((1, 4), (4, 4), (8, 1), (8, 11), (4, 8), (1, 8)).fill()
    wave = NSBezierPath.bezierPath()
    wave.moveToPoint_(NSMakePoint(10, 3.5))
    wave.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(10, 8.5), NSMakePoint(11.4, 5), NSMakePoint(11.4, 7))
    _stroke(1.4, wave)


def _airplay():
    _stroke(1.6, _line((5.5, 12.5), (2.5, 12.5), (2.5, 1.5), (15.5, 1.5), (15.5, 12.5), (12.5, 12.5)))
    _poly((4.5, 16.5), (13.5, 16.5), (9, 10.5)).fill()


def _expand():
    _stroke(1.4, _line((1, 5), (1, 1), (5, 1)))
    _stroke(1.4, _line((7, 11), (11, 11), (11, 7)))
    _stroke(1.4, _line((1, 1), (5, 5)))
    _stroke(1.4, _line((11, 11), (7, 7)))


def _shrink():
    _stroke(1.4, _line((1.5, 5), (5, 5), (5, 1.5)))
    _stroke(1.4, _line((7, 10.5), (7, 7), (10.5, 7)))
    _stroke(1.4, _line((1, 1), (5, 5)))
    _stroke(1.4, _line((11, 11), (7, 7)))


GLYPHS = {
    "prev": ((22, 14), lambda: (_rect(1, 1, 2.5, 12).fill(), _poly((12, 1), (4, 7), (12, 13)).fill(),
                               _poly((21, 1), (13, 7), (21, 13)).fill())),
    "rew": ((20, 14), lambda: (_poly((10, 1), (1, 7), (10, 13)).fill(), _poly((19, 1), (10, 7), (19, 13)).fill())),
    "play": ((14, 16), lambda: _poly((1, 1), (13, 8), (1, 15)).fill()),
    "pause": ((12, 14), lambda: (_rect(1, 1, 3.5, 12).fill(), _rect(7.5, 1, 3.5, 12).fill())),
    "ff": ((20, 14), lambda: (_poly((1, 1), (10, 7), (1, 13)).fill(), _poly((10, 1), (19, 7), (10, 13)).fill())),
    "next": ((22, 14), lambda: (_poly((1, 1), (9, 7), (1, 13)).fill(), _poly((10, 1), (18, 7), (10, 13)).fill(),
                               _rect(18.5, 1, 2.5, 12).fill())),
    "eject": ((16, 15), lambda: (_poly((8, 1), (15, 9), (1, 9)).fill(), _rect(1, 11, 14, 3).fill())),
    "queue": ((14, 12), lambda: [_rect(x, y, w, 2).fill() for y in (1, 5, 9) for x, w in ((0, 2), (4, 10))]),
    "airplay": ((18, 17), _airplay),
    "speaker": ((18, 18), lambda: (_stroke(1.5, _rect(4.5, 1.5, 9, 15, 1.6)), _stroke(1.3, _circle(9, 11, 2.6)),
                                  _circle(9, 5, 1).fill())),
    "phone": ((18, 18), lambda: (_stroke(1.5, _rect(5.5, 1.5, 7, 15, 1.6)), _circle(9, 13.7, 0.9).fill())),
    "computer": ((18, 18), lambda: (_stroke(1.5, _rect(3.5, 3.5, 11, 8, 1)), _rect(1, 13, 16, 2, 1).fill())),
    "tv": ((18, 18), lambda: (_stroke(1.5, _rect(1.5, 2.5, 15, 10, 1.2)), _rect(5.5, 14.5, 7, 1.7, 0.8).fill())),
    "car": ((18, 18), lambda: (_stroke(1.5, _rect(2, 7, 14, 6, 2)), _stroke(1.4, _line((4.5, 7), (6, 3.5), (12, 3.5), (13.5, 7))),
                              _circle(5.5, 14.2, 1.6).fill(), _circle(12.5, 14.2, 1.6).fill())),
    "now_playing": ((14, 12), _now_playing),
    "heart": ((16, 15), _heart),
    "disc": ((16, 16), _disc),
    "person": ((16, 16), _person),
    "playlist": ((16, 15), _playlist),
    "back": ((8, 11), lambda: _stroke(1.8, _line((7, 1), (2, 5.5), (7, 10)))),
    "forward": ((8, 11), lambda: _stroke(1.8, _line((1, 1), (6, 5.5), (1, 10)))),
    "expand": ((12, 12), _expand),
    "shrink": ((12, 12), _shrink),
}

DEVICE_GLYPHS = {"Computer": "computer", "Smartphone": "phone", "Tablet": "phone", "TV": "tv", "CastVideo": "tv",
                 "STB": "tv", "Automobile": "car"}


def device_glyph(kind):
    return DEVICE_GLYPHS.get(kind, "speaker")


def size(name):
    return GLYPHS[name][0]


def draw(name, rect, color):
    """Draw glyph `name` scaled to fit rect (keeping its proportions), centered."""
    (vw, vh), body = GLYPHS[name]
    scale = min(rect.size.width / float(vw), rect.size.height / float(vh))
    x = rect.origin.x + (rect.size.width - vw * scale) / 2.0
    y = rect.origin.y + (rect.size.height - vh * scale) / 2.0
    flipped = NSGraphicsContext.currentContext().isFlipped()
    t = NSAffineTransform.transform()
    if flipped:
        t.translateXBy_yBy_(x, y)
        t.scaleXBy_yBy_(scale, scale)
    else:
        t.translateXBy_yBy_(x, y + vh * scale)
        t.scaleXBy_yBy_(scale, -scale)
    NSGraphicsContext.saveGraphicsState()
    t.concat()
    color.set()
    body()
    NSGraphicsContext.restoreGraphicsState()


def draw_at(name, x, y, color, scale=1.0):
    """Draw at the view box's natural size (times scale) with its top left at x, y."""
    (vw, vh), _ = GLYPHS[name]
    draw(name, NSMakeRect(x, y, vw * scale, vh * scale), color)


_images = {}


def image(name, side=16, template=True, color=None):
    key = (name, side, template, color is not None and color.description())
    img = _images.get(key)
    if img is None:
        img = NSImage.alloc().initWithSize_(NSMakeSize(side, side))
        img.lockFocus()
        draw(name, NSMakeRect(0, 0, side, side), color or NSColor.blackColor())
        img.unlockFocus()
        img.setTemplate_(template)
        _images[key] = img
    return img
