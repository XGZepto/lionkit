# -*- coding: utf-8 -*-
"""Kassett's icon: the player's black cassette with its orange-banded label, tilted, with its edge
showing and a soft shadow, drawn with the same code as the cassette in the app."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(os.path.dirname(HERE))]   # the app's modules and lionkit

from AppKit import *  # noqa: F401,F403

import deck
import paint


def render(path, size):
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocusFlipped_(True)
    s = size / 512.0
    t = NSAffineTransform.transform()
    t.scaleBy_(s)
    t.translateXBy_yBy_(256, 262)
    t.rotateByDegrees_(-9)
    t.scaleBy_(0.98)
    t.translateXBy_yBy_(-200, -126)
    t.concat()
    shell = paint.rounded(NSMakeRect(0, 0, 400, 252), 12)
    edge = paint.rounded(NSMakeRect(0, 12, 400, 252), 12)          # the cassette's thickness, below its face
    paint.with_shadow(paint.shadow(14, 22, paint.white(0, 0.55)), lambda: paint.fill(edge, "#141416"))
    paint.fill(edge, "#2c2c30", "#0e0e10")
    deck.draw_cassette(0, 0, "black", u"Kassett", u"Side A — my favorite songs", 0.42)
    for (hx, hy), angle in zip(deck.HUB_XY, (14, 47)):
        deck.draw_hub(hx, hy, angle)
    paint.clipped(shell, lambda: paint.gradient((paint.white(1, 0.30), 0), (paint.white(1, 0.06), 0.45),
                                                (paint.white(1, 0), 0.46)).drawInRect_angle_(NSMakeRect(0, 0, 400, 252), 65))
    img.unlockFocus()
    rep = NSBitmapImageRep.alloc().initWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)
