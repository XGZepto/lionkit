# -*- coding: utf-8 -*-
"""Planchette icon: a wooden planchette resting on a stitched leather notebook (drawn with AppKit)."""
from AppKit import *  # noqa: F401,F403


def c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def render(path, size):
    s = size / 512.0
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocus()
    cover = NSMakeRect(56 * s, 28 * s, 400 * s, 456 * s)
    shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(cover, 36 * s, 36 * s)

    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -10 * s))
    shadow.setShadowBlurRadius_(18 * s)
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.5))
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    c(90, 52, 28).set()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSGradient.alloc().initWithStartingColor_endingColor_(c(150, 92, 52), c(92, 52, 26)).drawInBezierPath_angle_(shape, -90)

    stitch = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSInsetRect(cover, 20 * s, 20 * s), 22 * s, 22 * s)
    stitch.setLineWidth_(5 * s)
    stitch.setLineDash_count_phase_([16 * s, 11 * s], 2, 0)
    c(238, 214, 160).set()
    stitch.stroke()

    # The planchette: a heart-shaped walnut pointer, tip up, with a brass-ringed glass window.
    def pt(x, y):
        return NSMakePoint(x * s, y * s)

    heart = NSBezierPath.bezierPath()
    heart.moveToPoint_(pt(256, 420))
    heart.curveToPoint_controlPoint1_controlPoint2_(pt(384, 214), pt(316, 364), pt(384, 300))
    heart.curveToPoint_controlPoint1_controlPoint2_(pt(256, 150), pt(384, 112), pt(284, 110))
    heart.curveToPoint_controlPoint1_controlPoint2_(pt(128, 214), pt(228, 110), pt(128, 112))
    heart.curveToPoint_controlPoint1_controlPoint2_(pt(256, 420), pt(128, 300), pt(196, 364))
    heart.closePath()
    NSGraphicsContext.saveGraphicsState()
    shadow.setShadowOffset_(NSMakeSize(0, -8 * s))
    shadow.setShadowBlurRadius_(14 * s)
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.55))
    shadow.set()
    c(196, 140, 78).set()
    heart.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient.alloc().initWithStartingColor_endingColor_(c(232, 186, 122), c(160, 102, 50)).drawInBezierPath_angle_(heart, -90)
    grain = NSBezierPath.bezierPath()
    for i in range(7):
        y = 170 + i * 34
        grain.moveToPoint_(pt(150, y))
        grain.curveToPoint_controlPoint1_controlPoint2_(pt(362, y + 6), pt(220, y + 14), pt(300, y - 10))
    NSGraphicsContext.saveGraphicsState()
    heart.addClip()
    c(120, 72, 32, 0.22).set()
    grain.setLineWidth_(3 * s)
    grain.stroke()
    NSGradient.alloc().initWithStartingColor_endingColor_(c(255, 255, 255, 0.28), c(255, 255, 255, 0.0)).drawInRect_angle_(
        NSMakeRect(120 * s, 300 * s, 272 * s, 130 * s), -90)
    NSGraphicsContext.restoreGraphicsState()
    c(98, 56, 22).set()
    heart.setLineWidth_(5 * s)
    heart.stroke()

    ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(204 * s, 248 * s, 104 * s, 104 * s))
    NSGradient.alloc().initWithStartingColor_endingColor_(c(246, 214, 128), c(160, 112, 36)).drawInBezierPath_angle_(ring, -60)
    glass = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(218 * s, 262 * s, 76 * s, 76 * s))
    NSGradient.alloc().initWithStartingColor_endingColor_(c(250, 244, 228), c(214, 196, 160)).drawInBezierPath_angle_(glass, -90)
    shine = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(230 * s, 302 * s, 40 * s, 24 * s))
    c(255, 255, 255, 0.75).set()
    shine.fill()
    img.unlockFocus()
    rep = NSBitmapImageRep.alloc().initWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)
