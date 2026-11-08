#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Pack a release .app into a drag-to-Applications disk image and a zip (runs ON the Mac).

usage: make_dmg.py <App.app> <output dir>       (tools/package.sh runs it for you)

Writes <App>-<version>.dmg and <App>-<version>.zip. The disk image holds the app, a link to
/Applications, a "Read Me First" document and a background picture that shows what to do.

Finder normally lays out such a window and saves it in the volume's .DS_Store, but that would
put a window and a disk icon on the screen of whoever is using the Mac. This script writes the
.DS_Store itself (the format dmgbuild uses) and makes the background's alias with the Alias
Manager, so the rw image is only ever mounted hidden (-nobrowse) and Finder isn't involved.
"""
import ctypes
import os
import plistlib
import random
import shutil
import struct
import subprocess
import sys
import tempfile

from AppKit import *  # noqa: F401,F403 (PyObjC convention)
from Foundation import *  # noqa: F401,F403

WIDTH, HEIGHT = 600, 440          # the background, and the window's content area
ICON_SIZE = 112
TITLE_BAR = 22
APP_AT, APPLICATIONS_AT, README_AT = (160, 190), (440, 190), (300, 340)  # icon centres, top-left origin
README = u"Read Me First.rtf"

ABOUT = {
    "page.zepto.kassett": [
        u"Kassett is a remote for Spotify Connect on Mac OS X Lion. It doesn’t play music itself. "
        u"Instead, it shows what’s playing on your phone, a speaker or another computer, and it "
        u"lets you control that playback or move it to another device. Controlling playback needs a "
        u"Spotify Premium account.",
        u"Kassett isn’t made by Spotify or affiliated with it.",
    ],
    "page.zepto.planchette": [
        u"Planchette is a Markdown editor for blogs that run on Ghost. It keeps your posts in sync with "
        u"your site in both directions, shows a live preview while you write, and has an inspector for "
        u"each post’s URL slug, excerpt, tags and feature image.",
        u"Planchette isn’t made by the Ghost Foundation or affiliated with it.",
    ],
}

GENERAL = [
    u"To install %(name)s, drag it onto the Applications folder in this window. After that you can "
    u"eject the disk image and move it to the Trash.",
    u"I don’t have an Apple Developer ID, so Lion can’t tell who made %(name)s and won’t "
    u"open it with a double-click the first time. To open it anyway, hold down the Control key and "
    u"click %(name)s in your Applications folder, choose Open from the menu, and then click Open in "
    u"the dialog that follows. You only need to do this once. After that, %(name)s opens like any "
    u"other app.",
    u"The first time it starts, %(name)s copies the Python program that comes with Lion into its own "
    u"folder. That copy is what lets the menu bar and the Dock show the name %(name)s. If you open "
    u"%(name)s straight from this disk image, it can’t make the copy, so it still works but "
    u"calls itself Python until you install it.",
    u"%(name)s carries its own copy of curl and OpenSSL 3, because Lion’s built-in networking "
    u"can’t connect securely to most websites anymore. It doesn’t install anything else on "
    u"your Mac. To remove it, drag %(name)s from the Applications folder to the Trash. If something "
    u"goes wrong, the file %(log)s in your home folder usually says why.",
]


def color(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


# ---- the background picture ------------------------------------------------------------------
def noise_tile(size=64):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    rnd = random.Random(7)  # the same grain on every build
    for y in range(size):
        for x in range(size):
            v = rnd.random()
            rep.setColor_atX_y_(NSColor.colorWithCalibratedWhite_alpha_(v, 0.045), x, y)
    tile = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    tile.addRepresentation_(rep)
    return tile


def arrow(x0, x1, y, shaft=16, head_width=46, head_length=36):
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(x0, y + shaft / 2.0))
    p.lineToPoint_(NSMakePoint(x1 - head_length, y + shaft / 2.0))
    p.lineToPoint_(NSMakePoint(x1 - head_length, y + head_width / 2.0))
    p.lineToPoint_(NSMakePoint(x1, y))
    p.lineToPoint_(NSMakePoint(x1 - head_length, y - head_width / 2.0))
    p.lineToPoint_(NSMakePoint(x1 - head_length, y - shaft / 2.0))
    p.lineToPoint_(NSMakePoint(x0, y - shaft / 2.0))
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(NSMakePoint(x0, y), shaft / 2.0, 270, 90, True)
    p.closePath()
    p.setLineJoinStyle_(NSRoundLineJoinStyle)
    return p


def engraved(text, size, rgb):
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -1))
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(1, 0.9))
    return NSAttributedString.alloc().initWithString_attributes_(text, {
        NSFontAttributeName: NSFont.fontWithName_size_("Lucida Grande", size),
        NSForegroundColorAttributeName: color(*rgb),
        NSShadowAttributeName: shadow,
    })


def draw_background(path, name):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, WIDTH, HEIGHT, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    bounds = NSMakeRect(0, 0, WIDTH, HEIGHT)

    # Brushed-paper light gray: a soft top-lit gradient with a fine grain.
    NSGradient.alloc().initWithStartingColor_endingColor_(color(246, 246, 246), color(218, 219, 221)).drawInRect_angle_(bounds, -90)
    NSColor.colorWithPatternImage_(noise_tile()).set()
    NSBezierPath.fillRect_(bounds)
    NSColor.colorWithCalibratedWhite_alpha_(1, 0.6).set()
    NSRectFillUsingOperation(NSMakeRect(0, HEIGHT - 1, WIDTH, 1), NSCompositeSourceOver)
    # A soft pool of light behind the icons.
    glow = NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.colorWithCalibratedWhite_alpha_(1, 0.75), NSColor.colorWithCalibratedWhite_alpha_(1, 0))
    NSGraphicsContext.saveGraphicsState()
    squash = NSAffineTransform.transform()
    squash.translateXBy_yBy_(WIDTH / 2.0, HEIGHT - APP_AT[1])
    squash.scaleXBy_yBy_(1.0, 0.5)
    squash.concat()
    glow.drawFromCenter_radius_toCenter_radius_options_(NSZeroPoint, 0, NSZeroPoint, 280, 0)
    NSGraphicsContext.restoreGraphicsState()

    # The instruction across the top.
    text = engraved(u"To install %s, drag it onto the Applications folder." % name, 15, (96, 99, 104))
    size = text.size()
    text.drawAtPoint_(NSMakePoint(round((WIDTH - size.width) / 2), HEIGHT - 44 - size.height / 2))

    # An arrow pressed into the surface, from the app to the Applications folder.
    y = HEIGHT - APP_AT[1]
    shape = arrow(APP_AT[0] + ICON_SIZE / 2 + 26, APPLICATIONS_AT[0] - ICON_SIZE / 2 - 22, y)
    NSGraphicsContext.saveGraphicsState()
    transform = NSAffineTransform.transform()
    transform.translateXBy_yBy_(0, -1)
    highlight = transform.transformBezierPath_(shape)
    NSColor.colorWithCalibratedWhite_alpha_(1, 0.85).set()
    highlight.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient.alloc().initWithStartingColor_endingColor_(color(150, 153, 158), color(184, 187, 191)).drawInBezierPath_angle_(shape, -90)
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    inner = NSBezierPath.bezierPathWithRect_(NSInsetRect(shape.bounds(), -20, -20))
    inner.appendBezierPath_(shape)
    inner.setWindingRule_(NSEvenOddWindingRule)
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -1.5))
    shadow.setShadowBlurRadius_(2.5)
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.45))
    shadow.set()
    NSColor.blackColor().set()
    inner.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)


# ---- the Read Me -------------------------------------------------------------------------------
def write_readme(path, info):
    name = info["CFBundleName"]
    words = {"name": name, "log": "Library/Logs/%s.log" % info["CFBundleExecutable"]}
    paragraphs = ABOUT.get(info["CFBundleIdentifier"], [])[:1] + [p % words for p in GENERAL] + \
        ABOUT.get(info["CFBundleIdentifier"], [])[1:]
    style = NSMutableParagraphStyle.alloc().init()
    style.setParagraphSpacing_(9)
    style.setLineSpacing_(1.5)
    body = {NSFontAttributeName: NSFont.fontWithName_size_("Lucida Grande", 13), NSParagraphStyleAttributeName: style}
    title = {NSFontAttributeName: NSFont.fontWithName_size_("Lucida Grande Bold", 18), NSParagraphStyleAttributeName: style}
    doc = NSMutableAttributedString.alloc().init()
    doc.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(
        u"%s %s\n" % (name, info["CFBundleShortVersionString"]), title))
    doc.appendAttributedString_(NSAttributedString.alloc().initWithString_attributes_(u"\n".join(paragraphs) + u"\n", body))
    rtf = doc.RTFFromRange_documentAttributes_(NSMakeRange(0, doc.length()), {
        NSViewSizeDocumentAttribute: NSValue.valueWithSize_(NSMakeSize(560, 560))})
    rtf.writeToFile_atomically_(path, True)


# ---- .DS_Store ---------------------------------------------------------------------------------
def ds_record(filename, code, kind, value):
    name = filename.encode("utf-16-be")
    head = struct.pack(">I", len(name) // 2) + name + code + kind
    if kind == "blob":
        return head + struct.pack(">I", len(value)) + value
    if kind == "long":
        return head + struct.pack(">I", value)
    if kind == "type":
        return head + value
    raise ValueError(kind)


def ds_store(records):
    """A .DS_Store holding the records in one B-tree leaf.

    The file is a buddy allocator whose offsets count from byte 4: the 32-byte header at 0, the
    B-tree header ("DSDB") at 32, the allocator's own block at 2048 and the leaf node at 4096.
    """
    records = sorted(records, key=lambda r: (r[0].lower(), r[1]))
    node = struct.pack(">II", 0, len(records)) + "".join(ds_record(*r) for r in records)
    if len(node) > 4096:
        raise ValueError(".DS_Store records don't fit in one node")
    blocks = [(2048, 11), (32, 5), (4096, 12)]  # block 0 is the allocator, 1 the DSDB, 2 the leaf
    free = dict((n, [1 << n]) for n in range(5, 31))  # what's left after the header took 0..32
    for offset, log2 in blocks:
        free[log2].remove(offset)
    root = struct.pack(">II", len(blocks), 0)
    root += "".join(struct.pack(">I", offset | log2) for offset, log2 in blocks)
    root += "\0" * 4 * (256 - len(blocks))
    root += struct.pack(">IB4sI", 1, 4, "DSDB", 1)
    for n in range(32):
        offsets = free.get(n, [])
        root += struct.pack(">I", len(offsets)) + "".join(struct.pack(">I", o) for o in offsets)
    space = bytearray(8192)
    space[0:32] = struct.pack(">4sIII16s", "Bud1", 2048, 2048, 2048,
                              "\x00\x00\x10\x0c\x00\x00\x00\x87\x00\x00\x20\x0b\x00\x00\x00\x00")
    space[32:52] = struct.pack(">IIIII", 2, 0, len(records), 1, 4096)
    space[2048:2048 + len(root)] = root
    space[4096:4096 + len(node)] = node
    return struct.pack(">I", 1) + str(space)


def binary_plist(obj):
    data, error = NSPropertyListSerialization.dataWithPropertyList_format_options_error_(
        obj, NSPropertyListBinaryFormat_v1_0, 0, None)
    if data is None:
        raise ValueError(error)
    return data.bytes().tobytes()


def alias(path):
    """A classic Alias Manager record for path, which is how Lion's Finder finds the background."""
    cs = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
    cs.FSPathMakeRef.restype = ctypes.c_int32
    cs.FSNewAlias.restype = ctypes.c_int16
    cs.GetHandleSize.restype = ctypes.c_long
    cs.GetHandleSize.argtypes = [ctypes.c_void_p]
    cs.DisposeHandle.argtypes = [ctypes.c_void_p]
    ref = ctypes.create_string_buffer(80)  # FSRef
    if cs.FSPathMakeRef(path.encode("utf-8"), ref, None):
        raise OSError("FSPathMakeRef failed for %s" % path)
    handle = ctypes.c_void_p()
    if cs.FSNewAlias(None, ref, ctypes.byref(handle)):
        raise OSError("FSNewAlias failed for %s" % path)
    try:
        data = ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p)).contents.value
        return ctypes.string_at(data, cs.GetHandleSize(handle))
    finally:
        cs.DisposeHandle(handle)


def window_store(volume, app_file):
    background = alias(os.path.join(volume, ".background", "background.png"))
    x = (1440 - WIDTH) // 2
    y = (900 - HEIGHT - TITLE_BAR) // 2
    bwsp = {
        "WindowBounds": "{{%d, %d}, {%d, %d}}" % (x, y, WIDTH, HEIGHT + TITLE_BAR),
        "ShowSidebar": False, "ContainerShowSidebar": False, "SidebarWidth": 0,
        "ShowToolbar": False, "ShowStatusBar": False, "ShowPathbar": False,
        "ShowTabView": False, "PreviewPaneVisibility": False,
    }
    icvp = {
        "viewOptionsVersion": 1, "arrangeBy": "none", "iconSize": float(ICON_SIZE), "textSize": 12.0,
        "labelOnBottom": True, "showItemInfo": False, "showIconPreview": True, "gridSpacing": 100.0,
        "gridOffsetX": 0.0, "gridOffsetY": 0.0, "scrollPositionX": 0.0, "scrollPositionY": 0.0,
        "backgroundType": 2, "backgroundColorRed": 1.0, "backgroundColorGreen": 1.0, "backgroundColorBlue": 1.0,
        "backgroundImageAlias": NSData.dataWithBytes_length_(background, len(background)),
    }

    def iloc(pos):
        return struct.pack(">IIII", pos[0], pos[1], 0xffffffff, 0xffff0000)

    return ds_store([
        (u".", "bwsp", "blob", binary_plist(bwsp)),
        (u".", "icvp", "blob", binary_plist(icvp)),
        (u".", "vSrn", "long", 1),
        (u".", "vstl", "type", "icnv"),
        (app_file, "Iloc", "blob", iloc(APP_AT)),
        (u"Applications", "Iloc", "blob", iloc(APPLICATIONS_AT)),
        (README, "Iloc", "blob", iloc(README_AT)),
    ])


# ---- the image ---------------------------------------------------------------------------------
def hdiutil(*args):
    return subprocess.check_output(["hdiutil"] + list(args))


def make(app, out_dir):
    app = os.path.abspath(app.rstrip("/"))
    info = plistlib.readPlist(os.path.join(app, "Contents", "Info.plist"))
    name, version = info["CFBundleName"], info["CFBundleShortVersionString"]
    base = "%s-%s" % (info["CFBundleExecutable"], version)
    volname = ("%s %s" % (name, version)).encode("utf-8")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    dmg, zip_ = os.path.join(out_dir, base + ".dmg"), os.path.join(out_dir, base + ".zip")
    work = tempfile.mkdtemp(prefix="lk-dmg-")
    device = None
    try:
        stage = os.path.join(work, "stage")
        os.makedirs(os.path.join(stage, ".background"))
        subprocess.check_call(["ditto", app, os.path.join(stage, os.path.basename(app))])
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        draw_background(os.path.join(stage, ".background", "background.png"), name)
        write_readme(os.path.join(stage, README), info)
        icns = os.path.join(app, "Contents", "Resources", "AppIcon.icns")
        if os.path.exists(icns):
            shutil.copy(icns, os.path.join(stage, ".VolumeIcon.icns"))

        size_kb = int(subprocess.check_output(["du", "-sk", stage]).split()[0]) + 4096
        rw = os.path.join(work, "rw.dmg")
        hdiutil("create", "-quiet", "-srcfolder", stage, "-volname", volname, "-fs", "HFS+",
                "-format", "UDRW", "-size", "%dk" % size_kb, rw)
        attached = plistlib.readPlistFromString(hdiutil(
            "attach", rw, "-readwrite", "-noverify", "-noautoopen", "-nobrowse", "-plist"))
        for entity in attached["system-entities"]:
            if entity.get("mount-point"):
                volume, device = entity["mount-point"], entity["dev-entry"]
        with open(os.path.join(volume, ".DS_Store"), "wb") as f:
            f.write(window_store(volume, os.path.basename(app).decode("utf-8")))
        if os.path.exists(os.path.join(volume, ".VolumeIcon.icns")):
            # kHasCustomIcon on the volume's root folder, so the disk shows the app's icon
            subprocess.call(["xattr", "-wx", "com.apple.FinderInfo", "00" * 8 + "0400" + "00" * 22, volume])
        shutil.rmtree(os.path.join(volume, ".Trashes"), ignore_errors=True)
        subprocess.call(["sync"])
        hdiutil("detach", "-quiet", device)
        device = None
        if os.path.exists(dmg):
            os.remove(dmg)
        hdiutil("convert", "-quiet", rw, "-format", "UDZO", "-imagekey", "zlib-level=9", "-o", dmg)
        if os.path.exists(zip_):
            os.remove(zip_)
        subprocess.check_call(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, zip_])
    finally:
        if device:
            subprocess.call(["hdiutil", "detach", "-quiet", "-force", device])
        shutil.rmtree(work, ignore_errors=True)
    print(dmg)
    print(zip_)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    make(sys.argv[1], sys.argv[2])
