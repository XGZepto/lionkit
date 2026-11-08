# -*- coding: utf-8 -*-
"""Kassett icon (until the cassette icon lands): a glossy iTunes-10-style green disc with a play symbol and remote waves."""
from AppKit import *  # noqa: F401,F403


def c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def render(path, size):
    s = size / 512.0
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocus()
    disc_rect = NSMakeRect(40 * s, 40 * s, 432 * s, 432 * s)
    disc = NSBezierPath.bezierPathWithOvalInRect_(disc_rect)
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -10 * s))
    shadow.setShadowBlurRadius_(18 * s)
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.5))
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    c(20, 120, 60).set()
    disc.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient.alloc().initWithStartingColor_endingColor_(c(110, 220, 120), c(18, 110, 52)).drawInBezierPath_angle_(disc, -90)
    rim = NSBezierPath.bezierPathWithOvalInRect_(NSInsetRect(disc_rect, 6 * s, 6 * s))
    rim.setLineWidth_(4 * s)
    c(255, 255, 255, 0.35).set()
    rim.stroke()

    play = NSBezierPath.bezierPath()
    play.moveToPoint_(NSMakePoint(196 * s, 168 * s))
    play.lineToPoint_(NSMakePoint(196 * s, 344 * s))
    play.lineToPoint_(NSMakePoint(334 * s, 256 * s))
    play.closePath()
    c(255, 255, 255).set()
    play.fill()

    for i, radius in enumerate((70, 110)):
        arc = NSBezierPath.bezierPath()
        arc.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(NSMakePoint(330 * s, 256 * s), radius * s, -38, 38)
        arc.setLineWidth_(16 * s)
        arc.setLineCapStyle_(NSRoundLineCapStyle)
        c(255, 255, 255, 0.85 - i * 0.3).set()
        arc.stroke()

    gloss = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(86 * s, 250 * s, 340 * s, 200 * s))
    NSGradient.alloc().initWithStartingColor_endingColor_(c(255, 255, 255, 0.55), c(255, 255, 255, 0.0)).drawInBezierPath_angle_(gloss, -90)
    img.unlockFocus()
    rep = NSBitmapImageRep.alloc().initWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)
