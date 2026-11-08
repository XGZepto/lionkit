# -*- coding: utf-8 -*-
"""Monochrome template glyphs for Lion toolbars, drawn with NSBezierPath.

Template images are drawn in black on transparent; AppKit tints and embosses them to match
Lion's textured buttons (like Mail's or Preview's toolbar)."""
import math

from AppKit import (NSBezierPath, NSColor, NSImage, NSMakePoint, NSMakeRect, NSMakeSize,
                    NSRoundLineCapStyle, NSRoundLineJoinStyle)

SIZE = 18.0


def _stroke(path, width=1.6):
    path.setLineWidth_(width)
    path.setLineCapStyle_(NSRoundLineCapStyle)
    path.setLineJoinStyle_(NSRoundLineJoinStyle)
    path.stroke()


def _compose():
    page = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(2.5, 2.5, 11, 13), 1.5, 1.5)
    _stroke(page)
    pen = NSBezierPath.bezierPath()
    pen.moveToPoint_(NSMakePoint(8, 7))
    pen.lineToPoint_(NSMakePoint(16, 15))
    _stroke(pen, 2.4)
    tip = NSBezierPath.bezierPath()
    tip.moveToPoint_(NSMakePoint(6.6, 5.6))
    tip.lineToPoint_(NSMakePoint(8.8, 6.4))
    tip.lineToPoint_(NSMakePoint(7.4, 7.8))
    tip.closePath()
    tip.fill()


def _refresh():
    arc = NSBezierPath.bezierPath()
    arc.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(NSMakePoint(9, 9), 6, 60, 360)
    _stroke(arc, 1.8)
    head = NSBezierPath.bezierPath()
    head.moveToPoint_(NSMakePoint(15, 6.2))
    head.lineToPoint_(NSMakePoint(17.4, 10.4))
    head.lineToPoint_(NSMakePoint(12.4, 10.4))
    head.closePath()
    head.fill()


def _photo():
    frame = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(1.5, 3.5, 15, 11), 1.5, 1.5)
    _stroke(frame)
    hills = NSBezierPath.bezierPath()
    hills.moveToPoint_(NSMakePoint(3, 5))
    hills.lineToPoint_(NSMakePoint(7, 10))
    hills.lineToPoint_(NSMakePoint(10, 7))
    hills.lineToPoint_(NSMakePoint(12, 9))
    hills.lineToPoint_(NSMakePoint(15, 5))
    hills.closePath()
    hills.fill()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(11.5, 10, 2.6, 2.6)).fill()


def _eye():
    lens = NSBezierPath.bezierPath()
    lens.moveToPoint_(NSMakePoint(1.5, 9))
    lens.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(16.5, 9), NSMakePoint(5, 15), NSMakePoint(13, 15))
    lens.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(1.5, 9), NSMakePoint(13, 3), NSMakePoint(5, 3))
    lens.closePath()
    _stroke(lens)
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(6.2, 6.2, 5.6, 5.6)).fill()


def _info():
    _stroke(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(2, 2, 14, 14)))
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(8, 11.2, 2, 2)).fill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(8.1, 4.5, 1.8, 5.5), 0.6, 0.6).fill()


def _globe():
    _stroke(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(2, 2, 14, 14)))
    _stroke(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(6, 2, 6, 14)), 1.2)
    for y in (6.5, 11.5):
        line = NSBezierPath.bezierPath()
        inset = 2.6
        line.moveToPoint_(NSMakePoint(2 + inset, y))
        line.lineToPoint_(NSMakePoint(16 - inset, y))
        _stroke(line, 1.2)


def _upload():
    cloud = NSBezierPath.bezierPath()
    cloud.appendBezierPathWithOvalInRect_(NSMakeRect(1.5, 4, 7, 7))
    cloud.appendBezierPathWithOvalInRect_(NSMakeRect(5, 6, 9, 9))
    cloud.appendBezierPathWithOvalInRect_(NSMakeRect(10, 4, 7, 7))
    cloud.appendBezierPathWithRect_(NSMakeRect(5, 4, 9, 4))
    cloud.fill()
    NSColor.clearColor().set()


def _airplay():
    screen = NSBezierPath.bezierPath()
    screen.moveToPoint_(NSMakePoint(5.5, 5.5))
    screen.lineToPoint_(NSMakePoint(2.5, 5.5))
    screen.lineToPoint_(NSMakePoint(2.5, 15.5))
    screen.lineToPoint_(NSMakePoint(15.5, 15.5))
    screen.lineToPoint_(NSMakePoint(15.5, 5.5))
    screen.lineToPoint_(NSMakePoint(12.5, 5.5))
    _stroke(screen)
    tri = NSBezierPath.bezierPath()
    tri.moveToPoint_(NSMakePoint(4.5, 1.5))
    tri.lineToPoint_(NSMakePoint(13.5, 1.5))
    tri.lineToPoint_(NSMakePoint(9, 7.5))
    tri.closePath()
    tri.fill()


def _computer():
    _stroke(NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(3.5, 6.5, 11, 8), 1, 1))
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(1, 3, 16, 2), 1, 1).fill()


def _phone():
    _stroke(NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(5.5, 1.5, 7, 15), 1.6, 1.6))
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(8.1, 2.8, 1.8, 1.8)).fill()


def _speaker():
    _stroke(NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(4.5, 1.5, 9, 15), 1.6, 1.6))
    _stroke(NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(6.5, 3.5, 5, 5)), 1.4)
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(8, 11.5, 2, 2)).fill()


DRAWERS = {"compose": _compose, "refresh": _refresh, "photo": _photo, "eye": _eye,
           "info": _info, "globe": _globe, "upload": _upload, "airplay": _airplay,
           "computer": _computer, "phone": _phone, "speaker": _speaker}
_cache = {}


def template(name):
    if name not in _cache:
        img = NSImage.alloc().initWithSize_(NSMakeSize(SIZE, SIZE))
        img.lockFocus()
        NSColor.blackColor().set()
        DRAWERS[name]()
        img.unlockFocus()
        img.setTemplate_(True)
        _cache[name] = img
    return _cache[name]
