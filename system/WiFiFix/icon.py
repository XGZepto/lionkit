# -*- coding: utf-8 -*-
"""WiFiFix icon: a brass key whose bow is the Wi-Fi fan, cut through the metal, lying at an angle.

The key's outline is drawn once as a white silhouette (fills and round-jointed strokes give the
rounded bow, cleared shapes cut the slots and the bitting); the brass face, its thickness, the
bevels and the shadow are all made from that silhouette."""
from AppKit import *  # noqa: F401,F403

ANGLE = 34.0  # the key points down to the right


def c(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


def canvas(size, draw):
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocus()
    draw()
    img.unlockFocus()
    return img


def place(size):
    """Key coordinates: the fan's apex at the origin, the shaft along +x, about 430 units long."""
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(size * 0.5, size * 0.53)
    t.rotateByDegrees_(-ANGLE)
    t.scaleBy_(size / 512.0 * 0.9)
    t.translateXBy_yBy_(-112, 0)
    t.concat()


def arc_stroke(radius, a0, a1, width):
    p = NSBezierPath.bezierPath()
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(NSMakePoint(0, 0), radius, a0, a1)
    p.setLineWidth_(width)
    p.setLineCapStyle_(NSRoundLineCapStyle)
    return p


def silhouette(size):
    def draw():
        place(size)
        NSColor.whiteColor().set()
        bow = NSBezierPath.bezierPath()
        bow.moveToPoint_(NSMakePoint(0, 0))
        bow.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(NSMakePoint(0, 0), 132, 142, 218)
        bow.closePath()
        bow.fill()
        bow.setLineWidth_(36)
        bow.setLineJoinStyle_(NSRoundLineJoinStyle)
        bow.stroke()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(-40, -40, 80, 80)).fill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(20, -34, 26, 68), 6, 6).fill()  # shoulder
        shaft = NSBezierPath.bezierPath()
        shaft.moveToPoint_(NSMakePoint(30, 23))
        shaft.lineToPoint_(NSMakePoint(352, 23))
        shaft.lineToPoint_(NSMakePoint(372, 4))
        shaft.lineToPoint_(NSMakePoint(372, -10))
        shaft.lineToPoint_(NSMakePoint(30, -10))
        shaft.closePath()
        shaft.fill()
        # bitting: the teeth hang below the shaft
        teeth = NSBezierPath.bezierPath()
        teeth.moveToPoint_(NSMakePoint(176, -10))
        for x, depth in ((190, 44), (214, 30), (238, 48), (262, 26), (286, 42), (312, 22), (336, 34)):
            teeth.lineToPoint_(NSMakePoint(x - 6, -depth))
            teeth.lineToPoint_(NSMakePoint(x + 6, -depth))
        teeth.lineToPoint_(NSMakePoint(350, -10))
        teeth.closePath()
        teeth.fill()

        NSGraphicsContext.currentContext().setCompositingOperation_(NSCompositeClear)
        arc_stroke(54, 151, 209, 20).stroke()
        arc_stroke(100, 147, 213, 20).stroke()
    return canvas(size, draw)


def tinted(img, color, size):
    def draw():
        img.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeSourceOver, 1.0)
        color.set()
        NSRectFillUsingOperation(NSMakeRect(0, 0, size, size), NSCompositeSourceAtop)
    return canvas(size, draw)


def minus(img, other, dx, dy, size):
    """img with `other`, shifted by (dx, dy), cut away: leaves a rim along one side of the shape."""
    def draw():
        img.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeSourceOver, 1.0)
        other.drawAtPoint_fromRect_operation_fraction_(NSMakePoint(dx, dy), NSZeroRect, NSCompositeDestinationOut, 1.0)
    return canvas(size, draw)


def render(path, size):
    s = size / 512.0
    sil = silhouette(size)

    def face_draw():
        brass = NSGradient.alloc().initWithColors_([
            c(255, 246, 196), c(242, 206, 112), c(204, 150, 48), c(248, 222, 140), c(184, 128, 36), c(128, 84, 20)])
        brass.drawInRect_angle_(NSMakeRect(0, 0, size, size), -90 - ANGLE * 0.6)
        sil.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeDestinationIn, 1.0)
    face = canvas(size, face_draw)
    side = tinted(sil, c(122, 82, 20), size)
    light_rim = minus(tinted(sil, c(255, 252, 230), size), sil, 0, -2.5 * s, size)
    dark_rim = minus(tinted(sil, c(92, 58, 10), size), sil, 0, 2.0 * s, size)

    def draw():
        NSGraphicsContext.saveGraphicsState()
        shadow = NSShadow.alloc().init()
        shadow.setShadowOffset_(NSMakeSize(0, -12 * s))
        shadow.setShadowBlurRadius_(16 * s)
        shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.5))
        shadow.set()
        side.drawAtPoint_fromRect_operation_fraction_(NSMakePoint(0, -9 * s), NSZeroRect, NSCompositeSourceOver, 1.0)
        NSGraphicsContext.restoreGraphicsState()
        for dy in (-3, -6):  # the cut edge, a little lighter towards the face
            side.drawAtPoint_fromRect_operation_fraction_(NSMakePoint(0, dy * s), NSZeroRect, NSCompositeSourceOver, 1.0)
        face.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeSourceOver, 1.0)
        light_rim.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeSourceOver, 0.9)
        dark_rim.drawAtPoint_fromRect_operation_fraction_(NSZeroPoint, NSZeroRect, NSCompositeSourceOver, 0.55)

        # the keyway groove along the shaft, and a stamped ring around the fan's dot
        NSGraphicsContext.saveGraphicsState()
        place(size)
        groove = NSBezierPath.bezierPath()
        groove.moveToPoint_(NSMakePoint(64, 6))
        groove.lineToPoint_(NSMakePoint(336, 6))
        groove.setLineWidth_(7)
        groove.setLineCapStyle_(NSRoundLineCapStyle)
        c(128, 86, 22, 0.85).set()
        groove.stroke()
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(0, -4)
        groove.transformUsingAffineTransform_(t)
        groove.setLineWidth_(2.5)
        c(255, 246, 200, 0.8).set()
        groove.stroke()
        ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(-24, -24, 48, 48))
        ring.setLineWidth_(3)
        c(128, 86, 22, 0.6).set()
        ring.stroke()
        NSGraphicsContext.restoreGraphicsState()
    img = canvas(size, draw)
    rep = NSBitmapImageRep.alloc().initWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)


if __name__ == "__main__":
    import sys
    render(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 512)
