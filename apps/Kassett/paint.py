# -*- coding: utf-8 -*-
"""Drawing helpers for Kassett's custom views: colors, gradients, shadows, text and images.

Kassett's views are flipped (origin at the top left, like the HTML mockups in design/kassett),
so a gradient drawn at angle 90 runs from the top down, like CSS's `180deg`."""
from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403

_gradients = {}
_fonts = {}


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, a)


def white(w, a=1.0):
    return NSColor.colorWithCalibratedWhite_alpha_(w, a)


def gradient(*stops):
    """gradient("#fbfbfb", "#cdcdcd") or gradient(("#e2632e", 0), ("#efa13a", .5), ...)."""
    key = repr(stops)
    g = _gradients.get(key)
    if g is None:
        if stops and isinstance(stops[0], tuple):
            colors = [hexc(c) if isinstance(c, basestring) else c for c, _ in stops]
            locations = [float(l) for _, l in stops]
        else:
            colors = [hexc(c) if isinstance(c, basestring) else c for c in stops]
            locations = [i / float(len(colors) - 1) for i in range(len(colors))]
        g = NSGradient.alloc().initWithColors_atLocations_colorSpace_(
            colors, locations, NSColorSpace.genericRGBColorSpace())
        _gradients[key] = g
    return g


def fill(shape, *stops, **kw):
    """Fill a rect or path with a color or a vertical gradient (angle= to change it)."""
    if len(stops) == 1 and not isinstance(stops[0], tuple):
        c = stops[0]
        (hexc(c) if isinstance(c, basestring) else c).set()
        if isinstance(shape, NSBezierPath):
            shape.fill()
        else:
            NSBezierPath.fillRect_(shape)
        return
    g = gradient(*stops)
    angle = kw.get("angle", 90)
    if isinstance(shape, NSBezierPath):
        g.drawInBezierPath_angle_(shape, angle)
    else:
        g.drawInRect_angle_(shape, angle)


def stroke(path, color, width=1.0):
    (hexc(color) if isinstance(color, basestring) else color).set()
    path.setLineWidth_(width)
    path.stroke()


def rounded(rect, radius):
    return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)


def corners(rect, tl, tr, br, bl):
    """A rect with its own radius per corner (in a flipped view: top-left, top-right, ...)."""
    x, y, w, h = rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(x + tl, y))
    p.lineToPoint_(NSMakePoint(x + w - tr, y))
    if tr:
        p.appendBezierPathWithArcFromPoint_toPoint_radius_(NSMakePoint(x + w, y), NSMakePoint(x + w, y + tr), tr)
    p.lineToPoint_(NSMakePoint(x + w, y + h - br))
    if br:
        p.appendBezierPathWithArcFromPoint_toPoint_radius_(NSMakePoint(x + w, y + h), NSMakePoint(x + w - br, y + h), br)
    p.lineToPoint_(NSMakePoint(x + bl, y + h))
    if bl:
        p.appendBezierPathWithArcFromPoint_toPoint_radius_(NSMakePoint(x, y + h), NSMakePoint(x, y + h - bl), bl)
    p.lineToPoint_(NSMakePoint(x, y + tl))
    if tl:
        p.appendBezierPathWithArcFromPoint_toPoint_radius_(NSMakePoint(x, y), NSMakePoint(x + tl, y), tl)
    p.closePath()
    return p


def oval(cx, cy, r):
    return NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))


def shadow(dy, blur, color, dx=0):
    """An NSShadow; dy > 0 moves it down the screen (shadow offsets ignore flipping)."""
    s = NSShadow.alloc().init()
    s.setShadowOffset_(NSMakeSize(dx, -dy))
    s.setShadowBlurRadius_(blur)
    s.setShadowColor_(hexc(color) if isinstance(color, basestring) else color)
    return s


def with_shadow(s, draw):
    NSGraphicsContext.saveGraphicsState()
    s.set()
    draw()
    NSGraphicsContext.restoreGraphicsState()


def inner_shadow(path, dy, blur, color):
    """CSS `inset 0 dy blur color`: darken the inside of `path` along its edges."""
    NSGraphicsContext.saveGraphicsState()
    path.addClip()
    ring = NSBezierPath.bezierPathWithRect_(NSInsetRect(path.bounds(), -blur * 3 - 4, -blur * 3 - 4))
    ring.appendBezierPath_(path)
    ring.setWindingRule_(NSEvenOddWindingRule)
    shadow(dy, blur, color).set()
    white(0, 1).set()
    ring.fill()
    NSGraphicsContext.restoreGraphicsState()


def clipped(path, draw):
    NSGraphicsContext.saveGraphicsState()
    path.addClip()
    draw()
    NSGraphicsContext.restoreGraphicsState()


def font(name, size, bold=False):
    key = (name, size, bold)
    f = _fonts.get(key)
    if f is None:
        f = NSFont.fontWithName_size_(name, size) if name else None
        if f is None:
            f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        _fonts[key] = f
    return f


def ui(size, bold=False):
    return font("LucidaGrande-Bold" if bold else "LucidaGrande", size, bold)


def attrs(f, color, align=NSLeftTextAlignment, kern=None, sh=None, truncate=True):
    para = NSMutableParagraphStyle.alloc().init()
    para.setAlignment_(align)
    para.setLineBreakMode_(NSLineBreakByTruncatingTail if truncate else NSLineBreakByWordWrapping)
    a = {NSFontAttributeName: f, NSParagraphStyleAttributeName: para,
         NSForegroundColorAttributeName: hexc(color) if isinstance(color, basestring) else color}
    if kern:
        a[NSKernAttributeName] = kern
    if sh is not None:
        a[NSShadowAttributeName] = sh
    return a


def text(s, rect, f, color, align=NSLeftTextAlignment, kern=None, sh=None, truncate=True):
    """Draw one line (or wrapped lines with truncate=False) inside rect."""
    NSAttributedString.alloc().initWithString_attributes_(s or u"", attrs(f, color, align, kern, sh, truncate)) \
        .drawWithRect_options_(rect, NSStringDrawingUsesLineFragmentOrigin | NSStringDrawingTruncatesLastVisibleLine)


def text_width(s, f, kern=None):
    a = {NSFontAttributeName: f}
    if kern:
        a[NSKernAttributeName] = kern
    return NSAttributedString.alloc().initWithString_attributes_(s or u"", a).size().width


def text_height(s, f, width):
    a = NSAttributedString.alloc().initWithString_attributes_(s or u"", attrs(f, "#000000", truncate=False))
    return a.boundingRectWithSize_options_(NSMakeSize(width, 1e5), NSStringDrawingUsesLineFragmentOrigin).size.height


def engraved():
    """The 1 px white shadow under dark text on light chrome."""
    return shadow(1, 0, white(1, 0.75))


def image(img, rect, fraction=1.0, fill_rect=True):
    """Draw img into rect, cropping to fill it (fill_rect) or letterboxing; respects flipped views."""
    if img is None:
        return
    size = img.size()
    if not size.width or not size.height:
        return
    src = NSMakeRect(0, 0, size.width, size.height)
    if fill_rect:
        scale = max(rect.size.width / size.width, rect.size.height / size.height)
        w, h = rect.size.width / scale, rect.size.height / scale
        src = NSMakeRect((size.width - w) / 2.0, (size.height - h) / 2.0, w, h)
    img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        rect, src, NSCompositeSourceOver, fraction, True, {NSImageHintInterpolation: NSImageInterpolationHigh})


def fmt(ms):
    s = max(0, int((ms or 0) / 1000))
    return u"%d:%02d" % (s // 60, s % 60)


def total_time(ms):
    """iTunes-style totals for the bottom bar: 44 minutes, 16.9 hours, 2.1 days."""
    minutes = (ms or 0) / 60000.0
    if minutes < 1:
        return u"%d seconds" % int((ms or 0) / 1000)
    if minutes < 90:
        return u"1 minute" if int(round(minutes)) == 1 else u"%d minutes" % int(round(minutes))
    hours = minutes / 60
    if hours < 48:
        return u"%.1f hours" % hours
    return u"%.1f days" % (hours / 24)


def plural(n, one, many=None):
    return u"%d %s" % (n, one if n == 1 else (many or one + u"s"))
