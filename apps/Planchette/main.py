# -*- coding: utf-8 -*-
"""Planchette: a Lion-native Markdown editor for blogs that run on Ghost.

Post list with sorting and search, two-way sync with conflict detection, a status header,
a HUD inspector for slug / excerpt / tags / feature image, Markdown syntax highlighting,
and a live preview that scrolls with the editor.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AppKit import *  # noqa: F401,F403 (PyObjC convention)
from Foundation import *  # noqa: F401,F403
from PyObjCTools import AppHelper
from WebKit import WebView

from lionkit import cocoa, ghost, html2md, http, icons, keychain, markdown

APP_NAME = "Planchette"
SUPPORT = os.path.expanduser("~/Library/Application Support/Planchette")
POSTS_DIR = os.path.join(SUPPORT, "posts")
MEDIA_DIR = os.path.join(SUPPORT, "media")
IMAGE_CACHE = os.path.join(SUPPORT, "image-cache")
DWEBP = os.path.expanduser("~/Library/LionKit/bin/lk-dwebp")
KEYCHAIN_SERVICE = "Planchette"
BAR = 26
SIDEBAR_WIDTH = 240
COLUMN = 660            # max width of the writing column
EXCERPT_MAX = 300
GROUPS = [("new", u"ON THIS MAC"), ("draft", u"DRAFTS"), ("scheduled", u"SCHEDULED"), ("published", u"PUBLISHED")]
STATUS_NAMES = {"new": u"Local", "draft": u"Draft", "scheduled": u"Scheduled", "published": u"Published"}
SORTS = [(u"Last Edited", "edited"), (u"Publish Date", "published"), (u"Title", "title")]


def rgb(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r / 255.0, g / 255.0, b / 255.0, a)


PAPER, INK, FAINT = rgb(252, 249, 241), rgb(43, 38, 34), rgb(170, 158, 142)
ACCENT, CODE_BG, QUOTE = rgb(150, 82, 36), rgb(241, 233, 216), rgb(110, 100, 90)
STATUS_COLORS = {"new": rgb(140, 140, 140), "draft": rgb(226, 150, 30), "scheduled": rgb(60, 120, 205),
                 "published": rgb(60, 160, 75)}

PREVIEW_SHELL = u"""<html><head><meta charset="utf-8"><style>
body { font: 17px/1.65 Georgia, serif; color: #2b2622; background: #fcf9f1; margin: 0; }
#page { max-width: 640px; margin: 0 auto; padding: 30px 34px 90px; }
h1.title { font: 34px/1.2 'Hoefler Text', Georgia, serif; margin: 0 0 6px; }
.meta { font: 12px 'Lucida Grande', sans-serif; color: #a3968a; margin-bottom: 26px; }
.feature { width: 100%; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,.25); margin-bottom: 26px; }
h2, h3 { font-family: 'Hoefler Text', Georgia, serif; margin-top: 32px; }
img { max-width: 100%; border-radius: 3px; box-shadow: 0 1px 5px rgba(0,0,0,.25); }
figure { margin: 26px 0; }
figcaption { font-size: 13px; color: #7a6f64; text-align: center; margin-top: 7px; font-style: italic; }
pre { background: #2b2622; color: #f3ead8; padding: 12px 14px; border-radius: 6px; overflow-x: auto;
      box-shadow: inset 0 1px 3px rgba(0,0,0,.5); }
code { font: 13px Menlo, monospace; background: #efe6d3; padding: 1px 4px; border-radius: 3px; }
pre code { background: none; padding: 0; color: inherit; }
blockquote { border-left: 3px solid #c9b99a; margin-left: 0; padding-left: 16px; color: #5c534a; font-style: italic; }
table { border-collapse: collapse; font-size: 14px; margin: 16px 0; width: 100%; }
td, th { border: 1px solid #ddd2bd; padding: 5px 9px; text-align: left; }
th { background: #f1e9d8; }
a { color: #8a4b22; }
.empty { color: #b3a898; font-style: italic; }
</style><script>
function setContent(title, meta, feature, body) {
  document.getElementById('t').innerText = title;
  document.getElementById('m').innerText = meta;
  var f = document.getElementById('f');
  if (feature) { f.src = feature; f.style.display = 'block'; } else { f.style.display = 'none'; }
  document.getElementById('c').innerHTML = body;
}
function scrollToRatio(r) {
  var max = document.body.scrollHeight - window.innerHeight;
  window.scrollTo(0, Math.max(0, max) * r);
}
</script></head><body><div id="page"><h1 class="title" id="t"></h1><div class="meta" id="m"></div>
<img class="feature" id="f" style="display:none"><div id="c"></div></div></body></html>"""


# ---- storage: one JSON file per post; Markdown is the source of truth while editing ------------
def ensure_dirs():
    for d in (SUPPORT, POSTS_DIR, MEDIA_DIR, IMAGE_CACHE):
        if not os.path.isdir(d):
            os.makedirs(d)


def doc_path(key):
    return os.path.join(POSTS_DIR, "%s.json" % key)


def load_doc(key):
    try:
        return json.load(open(doc_path(key)))
    except (IOError, ValueError):
        return None


def save_doc(doc):
    doc["local_edited"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = doc_path(doc["key"]) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f)
    os.rename(tmp, doc_path(doc["key"]))


def local_docs():
    docs = {}
    for p in glob.glob(os.path.join(POSTS_DIR, "*.json")):
        try:
            d = json.load(open(p))
            docs[d["key"]] = d
        except (ValueError, KeyError):
            pass
    return docs


def new_doc():
    return {"key": "local-%s" % uuid.uuid4().hex[:12], "id": None, "title": u"", "markdown": u"",
            "status": "new", "base_updated_at": None, "dirty": True, "uploads": {}, "saved_at": None,
            "slug": u"", "excerpt": u"", "tags": [], "feature_image": None}


def short_date(iso):
    try:
        t = time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return unicode(time.strftime("%b %d, %Y", t)).replace(u" 0", u" ")
    except (TypeError, ValueError):
        return u""


# ---- images: local media, WebP conversion and a cache of remote images for the preview -------
def import_media(path):
    """Copy an image into the media folder under a short, readable name; return 'media:<name>'."""
    base, ext = os.path.splitext(os.path.basename(path))
    name = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:40] or "image"
    candidate, n = name + ext.lower(), 2
    while os.path.exists(os.path.join(MEDIA_DIR, candidate)):
        candidate, n = "%s-%d%s" % (name, n, ext.lower()), n + 1
    shutil.copyfile(path, os.path.join(MEDIA_DIR, candidate))
    return u"media:" + candidate


def media_path(src):
    """Local file path for 'media:' and 'file://' references, else None."""
    if src.startswith("media:"):
        return os.path.join(MEDIA_DIR, src[6:])
    if src.startswith("file://"):
        return NSURL.URLWithString_(src).path()
    return None


def viewable(path):
    """Lion's WebKit can't show WebP; return a PNG copy for those."""
    if not path.lower().endswith(".webp"):
        return path
    png = os.path.join(IMAGE_CACHE, hashlib.sha1(path.encode("utf-8")).hexdigest() + ".png")
    if not os.path.exists(png):
        subprocess.call([DWEBP, path, "-o", png], stdout=open(os.devnull, "w"), stderr=subprocess.STDOUT)
    return png if os.path.exists(png) else path


# ---- Markdown syntax highlighting -----------------------------------------------------------------
def _fonts():
    fm = NSFontManager.sharedFontManager()
    base = NSFont.fontWithName_size_("Georgia", 16)
    head = NSFont.fontWithName_size_("Hoefler Text", 16) or base
    return {
        "base": base,
        "bold": fm.convertFont_toHaveTrait_(base, NSBoldFontMask),
        "italic": fm.convertFont_toHaveTrait_(base, NSItalicFontMask),
        "mono": NSFont.fontWithName_size_("Menlo", 13.5),
        "small": NSFont.fontWithName_size_("Georgia", 13),
        "h1": fm.convertFont_toHaveTrait_(NSFont.fontWithName_size_(head.fontName(), 27), NSBoldFontMask),
        "h2": fm.convertFont_toHaveTrait_(NSFont.fontWithName_size_(head.fontName(), 22), NSBoldFontMask),
        "h3": fm.convertFont_toHaveTrait_(NSFont.fontWithName_size_(head.fontName(), 19), NSBoldFontMask),
    }


_STYLE = {"code": []}
_RULES = [
    ("heading", re.compile(r"^(#{1,6})[ \t]+.*$", re.M)),
    ("fence", re.compile(r"^```.*?(?:^```[ \t]*$|\Z)", re.M | re.S)),
    ("card", re.compile(r"^<!--kg-card-begin: html-->.*?(?:<!--kg-card-end: html-->|\Z)", re.M | re.S)),
    ("image", re.compile(r"^!\[.*$", re.M)),
    ("quote", re.compile(r"^>.*$", re.M)),
    ("list", re.compile(r"^[ \t]*(?:[-*+]|\d+\.)(?=[ \t])", re.M)),
    ("code", re.compile(r"`[^`\n]+`")),
    ("bold", re.compile(r"\*\*[^*\n]+\*\*")),
    ("italic", re.compile(r"(?<![*\w])\*(?!\s)[^*\n]+?(?<!\s)\*(?!\*)")),
    ("link", re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")),
]


def highlight(storage):
    if "fonts" not in _STYLE:
        _STYLE["fonts"] = _fonts()
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineHeightMultiple_(1.22)
        para.setParagraphSpacing_(3)
        _STYLE["para"] = para
    f, text = _STYLE["fonts"], storage.string()
    storage.beginEditing()
    storage.setAttributes_range_({NSFontAttributeName: f["base"], NSForegroundColorAttributeName: INK,
                                  NSParagraphStyleAttributeName: _STYLE["para"]}, NSMakeRange(0, len(text)))

    def attr(start, end, font=None, color=None, bg=None):
        rng = NSMakeRange(start, end - start)
        if font is not None:
            storage.addAttribute_value_range_(NSFontAttributeName, font, rng)
        if color is not None:
            storage.addAttribute_value_range_(NSForegroundColorAttributeName, color, rng)
        if bg is not None:
            storage.addAttribute_value_range_(NSBackgroundColorAttributeName, bg, rng)

    code = []
    for kind, rx in _RULES:
        for m in rx.finditer(text):
            s, e = m.span()
            if kind in ("fence", "card", "code"):
                code.append((s, e))
            if kind == "heading":
                level = len(m.group(1))
                attr(s, e, font=f["h1" if level == 1 else "h2" if level == 2 else "h3"])
                attr(s, s + level, color=FAINT)
            elif kind in ("fence", "card"):
                attr(s, e, font=f["mono"], color=QUOTE if kind == "fence" else FAINT, bg=CODE_BG)
            elif kind == "image":
                attr(s, e, font=f["small"], color=FAINT)
            elif kind == "quote":
                attr(s, e, font=f["italic"], color=QUOTE)
            elif kind == "list":
                attr(s, e, font=f["bold"], color=ACCENT)
            elif kind == "code":
                attr(s, e, font=f["mono"], bg=CODE_BG)
            elif kind == "bold":
                attr(s, e, font=f["bold"])
                attr(s, s + 2, color=FAINT)
                attr(e - 2, e, color=FAINT)
            elif kind == "italic":
                attr(s, e, font=f["italic"])
            elif kind == "link":
                attr(s, e, color=FAINT)
                attr(m.start(1), m.end(1), color=ACCENT)
    storage.endEditing()
    _STYLE["code"] = code


def in_code(rng):
    start, end = rng.location, rng.location + rng.length
    return any(s <= start and end <= e for s, e in _STYLE["code"])


# ---- custom drawing --------------------------------------------------------------------------------
def draw_pill(rect, color, text):
    """A glossy 2011-style capsule with white caps text."""
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, rect.size.height / 2, rect.size.height / 2)
    top = color.blendedColorWithFraction_ofColor_(0.35, NSColor.whiteColor())
    NSGradient.alloc().initWithStartingColor_endingColor_(top, color).drawInBezierPath_angle_(path, -90)
    color.shadowWithLevel_(0.25).set()
    path.setLineWidth_(1)
    path.stroke()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_(NSMakeSize(0, -1))
    shadow.setShadowColor_(NSColor.colorWithCalibratedWhite_alpha_(0, 0.35))
    shadow.setShadowBlurRadius_(0)
    attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(9.5), NSForegroundColorAttributeName: NSColor.whiteColor(),
             NSShadowAttributeName: shadow, NSKernAttributeName: 0.6}
    label = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    size = label.size()
    label.drawAtPoint_(NSMakePoint(rect.origin.x + (rect.size.width - size.width) / 2,
                                   rect.origin.y + (rect.size.height - size.height) / 2))


def pill_width(text):
    attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(9.5), NSKernAttributeName: 0.6}
    return NSAttributedString.alloc().initWithString_attributes_(text, attrs).size().width + 16


class PaperView(NSView):
    def drawRect_(self, rect):
        PAPER.set()
        NSRectFill(rect)


class StatusStrip(NSView):
    """The post's state above the title: a status pill plus what's saved where."""

    def initWithFrame_(self, frame):
        self = super(StatusStrip, self).initWithFrame_(frame)
        if self:
            self.status, self.detail = "new", u""
        return self

    def drawRect_(self, rect):
        PAPER.set()
        NSRectFill(rect)
        label = STATUS_NAMES.get(self.status, u"Post").upper()
        w = pill_width(label)
        draw_pill(NSMakeRect(0, 5, w, 16), STATUS_COLORS.get(self.status, FAINT), label)
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(11), NSForegroundColorAttributeName: QUOTE}
        NSAttributedString.alloc().initWithString_attributes_(self.detail, attrs).drawAtPoint_(NSMakePoint(w + 9, 6))


class PostCell(NSTextFieldCell):
    """Sidebar row: status dot, title, a date line and an 'EDITED' pill for unsaved changes."""

    def drawInteriorWithFrame_inView_(self, frame, view):
        item = self.objectValue()
        if not hasattr(item, "objectForKey_"):
            return super(PostCell, self).drawInteriorWithFrame_inView_(frame, view)
        dark = self.backgroundStyle() == NSBackgroundStyleDark
        x, y, w = frame.origin.x, frame.origin.y, frame.size.width
        dot = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x + 2, y + 8, 8, 8))
        color = STATUS_COLORS.get(item["status"], FAINT)
        NSGradient.alloc().initWithStartingColor_endingColor_(
            color.blendedColorWithFraction_ofColor_(0.4, NSColor.whiteColor()), color).drawInBezierPath_angle_(dot, 90)
        para = NSMutableParagraphStyle.alloc().init()
        para.setLineBreakMode_(NSLineBreakByTruncatingTail)
        badge = 0
        if item["dirty"]:
            badge = pill_width(u"EDITED")
            draw_pill(NSMakeRect(x + w - badge - 2, y + 4, badge, 14), rgb(214, 120, 40), u"EDITED")
        title_attrs = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(12) if dark else NSFont.systemFontOfSize_(12),
                       NSForegroundColorAttributeName: NSColor.whiteColor() if dark else NSColor.blackColor(),
                       NSParagraphStyleAttributeName: para}
        NSAttributedString.alloc().initWithString_attributes_(item["title"], title_attrs).drawInRect_(
            NSMakeRect(x + 16, y + 3, w - 18 - badge - 4, 16))
        sub_attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(10.5), NSParagraphStyleAttributeName: para,
                     NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1, 0.85) if dark
                     else NSColor.grayColor()}
        NSAttributedString.alloc().initWithString_attributes_(item["sub"], sub_attrs).drawInRect_(
            NSMakeRect(x + 16, y + 19, w - 18, 14))


def hud_label(view, text, frame, size=11, color=None):
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if color is None else NSFont.systemFontOfSize_(size))
    f.setTextColor_(color or NSColor.colorWithCalibratedWhite_alpha_(0.85, 1))
    f.setStringValue_(text)
    view.addSubview_(f)
    return f


class AppDelegate(NSObject):

    # ---- launch ------------------------------------------------------------------------------------
    def applicationDidFinishLaunching_(self, note):
        self.defaults = NSUserDefaults.standardUserDefaults()
        ensure_dirs()
        self.doc = None
        self.remote = []
        self.site_tags = []
        self.groups = []
        self.busy = False
        self.loading_doc = False
        self.preview_ready = False
        self.fetching_images = set()
        self.search = u""
        cocoa.build_main_menu(
            APP_NAME, self,
            file_items=[(u"New Post", "newPost:", "n"), None,
                        (u"Save Draft", "save:", "s"),
                        (u"Publish…", "publishOrUnpublish:", "p", NSCommandKeyMask | NSShiftKeyMask),
                        None, (u"Insert Image…", "insertImage:", "i", NSCommandKeyMask | NSShiftKeyMask),
                        (u"Open in Browser", "openInBrowser:", "o"), None,
                        (u"Discard Changes and Reload from Site…", "revertToRemote:", ""),
                        (u"Delete Draft…", "deleteDraft:", "")],
            view_items=[(u"Show Inspector", "toggleInspector:", "i", NSCommandKeyMask | NSAlternateKeyMask),
                        (u"Hide Preview", "togglePreview:", "p", NSCommandKeyMask | NSAlternateKeyMask), None,
                        (u"Refresh Post List", "refresh:", "r")])
        view_menu = NSApp.mainMenu().itemWithTitle_("View").submenu()
        view_menu.addItem_(NSMenuItem.separatorItem())
        sort_item = view_menu.addItemWithTitle_action_keyEquivalent_(u"Sort Posts By", None, "")
        sort_menu = NSMenu.alloc().initWithTitle_(u"Sort Posts By")
        for i, (title, _) in enumerate(SORTS):
            it = sort_menu.addItemWithTitle_action_keyEquivalent_(title, "sortBy:", "")
            it.setTag_(i)
            it.setTarget_(self)
        sort_item.setSubmenu_(sort_menu)

        self.buildWindow()
        self.buildInspector()
        self.window.makeKeyAndOrderFront_(None)
        self.layoutPanes()
        self.rebuildSidebar()
        last = self.defaults.stringForKey_("lastKey")
        self.showDoc((load_doc(last) if last else None) or self.createDoc())
        self.refresh_(None)

    # ---- window ------------------------------------------------------------------------------------
    def buildWindow(self):
        mask = (NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask |
                NSResizableWindowMask | NSTexturedBackgroundWindowMask)
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 1240, 740), mask, NSBackingStoreBuffered, False)
        w.setMinSize_(NSMakeSize(860, 460))
        w.setContentBorderThickness_forEdge_(BAR, NSMinYEdge)
        w.setFrameAutosaveName_("PlanchetteMain")
        if not w.setFrameUsingName_("PlanchetteMain"):
            w.center()
        self.window = w
        content = w.contentView()
        cw, ch = content.frame().size.width, content.frame().size.height

        toolbar = NSToolbar.alloc().initWithIdentifier_("PlanchetteToolbar")
        toolbar.setDelegate_(self)
        toolbar.setDisplayMode_(NSToolbarDisplayModeIconOnly)
        toolbar.setAllowsUserCustomization_(False)
        w.setToolbar_(toolbar)

        outer = NSSplitView.alloc().initWithFrame_(NSMakeRect(0, BAR, cw, ch - BAR))
        outer.setVertical_(True)
        outer.setDividerStyle_(NSSplitViewDividerStyleThin)
        outer.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.outer = outer

        sidebar = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, SIDEBAR_WIDTH, ch - BAR))
        sidebar.setHasVerticalScroller_(True)
        sidebar.setBorderType_(NSNoBorder)
        ov = NSOutlineView.alloc().initWithFrame_(sidebar.bounds())
        col = NSTableColumn.alloc().initWithIdentifier_("post")
        col.setWidth_(SIDEBAR_WIDTH - 16)
        ov.addTableColumn_(col)
        ov.setOutlineTableColumn_(col)
        ov.setHeaderView_(None)
        ov.setSelectionHighlightStyle_(NSTableViewSelectionHighlightStyleSourceList)
        ov.setColumnAutoresizingStyle_(NSTableViewUniformColumnAutoresizingStyle)
        ov.setIndentationPerLevel_(2)
        ov.setDataSource_(self)
        ov.setDelegate_(self)
        menu = NSMenu.alloc().initWithTitle_(u"Post")
        for title, sel in ((u"Open in Browser", "rowOpenInBrowser:"), (u"Discard Local Changes…", "rowDiscard:"),
                           (u"Delete Draft…", "rowDelete:")):
            menu.addItemWithTitle_action_keyEquivalent_(title, sel, "").setTarget_(self)
        ov.setMenu_(menu)
        sidebar.setDocumentView_(ov)
        self.outline = ov
        self.postCell = PostCell.alloc().init()

        inner = NSSplitView.alloc().initWithFrame_(NSMakeRect(0, 0, cw - SIDEBAR_WIDTH - 1, ch - BAR))
        inner.setVertical_(True)
        inner.setDividerStyle_(NSSplitViewDividerStyleThin)
        self.inner = inner

        editor = PaperView.alloc().initWithFrame_(NSMakeRect(0, 0, 500, ch - BAR))
        eh, ew = editor.frame().size.height, editor.frame().size.width
        self.strip = StatusStrip.alloc().initWithFrame_(NSMakeRect(32, eh - 40, ew - 64, 26))
        self.strip.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        editor.addSubview_(self.strip)
        title = NSTextField.alloc().initWithFrame_(NSMakeRect(30, eh - 84, ew - 60, 40))
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setFocusRingType_(NSFocusRingTypeNone)
        title.setFont_(NSFont.fontWithName_size_("Hoefler Text", 30) or NSFont.systemFontOfSize_(26))
        title.setTextColor_(INK)
        title.cell().setPlaceholderString_(u"Title")
        title.cell().setScrollable_(True)
        title.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        title.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        title.setDelegate_(self)
        editor.addSubview_(title)
        self.titleField = title
        rule = NSBox.alloc().initWithFrame_(NSMakeRect(32, eh - 94, ew - 64, 1))
        rule.setBoxType_(NSBoxSeparator)
        rule.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
        editor.addSubview_(rule)
        self.rule = rule

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, ew, eh - 98))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSNoBorder)
        scroll.setDrawsBackground_(False)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        size = scroll.contentSize()
        tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, size.width, size.height))
        tv.setMinSize_(NSMakeSize(0, size.height))
        tv.setMaxSize_(NSMakeSize(1e7, 1e7))
        tv.setVerticallyResizable_(True)
        tv.setHorizontallyResizable_(False)
        tv.setAutoresizingMask_(NSViewWidthSizable)
        tv.textContainer().setContainerSize_(NSMakeSize(size.width, 1e7))
        tv.textContainer().setWidthTracksTextView_(True)
        tv.setRichText_(False)
        tv.setAllowsUndo_(True)
        tv.setFont_(NSFont.fontWithName_size_("Georgia", 16))
        tv.setTextColor_(INK)
        tv.setBackgroundColor_(PAPER)
        tv.setInsertionPointColor_(ACCENT)
        tv.setSelectedTextAttributes_({NSBackgroundColorAttributeName: rgb(240, 214, 170)})
        tv.setAutomaticQuoteSubstitutionEnabled_(False)
        tv.setAutomaticDashSubstitutionEnabled_(False)
        tv.setContinuousSpellCheckingEnabled_(True)
        tv.setDelegate_(self)
        scroll.setDocumentView_(tv)
        editor.addSubview_(scroll)
        self.textView, self.editorScroll, self.editorPane = tv, scroll, editor
        clip = scroll.contentView()
        clip.setPostsBoundsChangedNotifications_(True)
        clip.setPostsFrameChangedNotifications_(True)
        nc = NSNotificationCenter.defaultCenter()
        nc.addObserver_selector_name_object_(self, "editorScrolled:", NSViewBoundsDidChangeNotification, clip)
        nc.addObserver_selector_name_object_(self, "editorResized:", NSViewFrameDidChangeNotification, clip)

        preview = WebView.alloc().initWithFrame_frameName_groupName_(NSMakeRect(0, 0, 420, ch - BAR), None, None)
        preview.setFrameLoadDelegate_(self)
        preview.mainFrame().loadHTMLString_baseURL_(PREVIEW_SHELL, NSURL.fileURLWithPath_(SUPPORT + "/"))
        self.preview = preview

        inner.addSubview_(editor)
        inner.addSubview_(preview)
        outer.addSubview_(sidebar)
        outer.addSubview_(inner)
        content.addSubview_(outer)

        self.spinner = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(10, 5, 16, 16))
        self.spinner.setStyle_(NSProgressIndicatorSpinningStyle)
        self.spinner.setControlSize_(NSSmallControlSize)
        self.spinner.setDisplayedWhenStopped_(False)
        content.addSubview_(self.spinner)
        self.status = self.barLabel(NSMakeRect(30, 4, cw - 240, 17), NSLeftTextAlignment)
        self.status.setAutoresizingMask_(NSViewWidthSizable)
        self.words = self.barLabel(NSMakeRect(cw - 220, 4, 208, 17), NSRightTextAlignment)
        self.words.setAutoresizingMask_(NSViewMinXMargin)
        content.addSubview_(self.status)
        content.addSubview_(self.words)

    def layoutPanes(self):
        size = self.outer.frame().size
        sidebar, inner = self.outer.subviews()
        sidebar.setFrame_(NSMakeRect(0, 0, SIDEBAR_WIDTH, size.height))
        inner.setFrame_(NSMakeRect(SIDEBAR_WIDTH + 1, 0, size.width - SIDEBAR_WIDTH - 1, size.height))
        self.outer.adjustSubviews()
        self.layoutEditor()

    def layoutEditor(self):
        size = self.inner.frame().size
        editor, preview = self.inner.subviews()
        if preview.isHidden():
            editor.setFrame_(NSMakeRect(0, 0, size.width, size.height))
        else:
            left = int(size.width * 0.52)
            editor.setFrame_(NSMakeRect(0, 0, left, size.height))
            preview.setFrame_(NSMakeRect(left + 1, 0, size.width - left - 1, size.height))
        self.inner.adjustSubviews()
        self.editorResized_(None)

    def editorResized_(self, note):
        """Keep the text in a centered column of readable width, aligned with the title."""
        width = self.editorPane.frame().size.width
        height = self.editorPane.frame().size.height
        margin = max(34, (width - COLUMN) / 2.0)
        self.textView.setTextContainerInset_(NSMakeSize(margin - 6, 12))
        for view, y, h, dx in ((self.strip, height - 40, 26, 0), (self.titleField, height - 84, 40, -2),
                               (self.rule, height - 94, 1, 0)):
            view.setFrame_(NSMakeRect(margin + dx, y, width - 2 * margin, h))

    def barLabel(self, frame, align):
        label = NSTextField.alloc().initWithFrame_(frame)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setAlignment_(align)
        label.setFont_(NSFont.systemFontOfSize_(11))
        label.cell().setBackgroundStyle_(NSBackgroundStyleRaised)
        return label

    # ---- toolbar: textured buttons with template glyphs, like Lion's Mail -----------------------------
    TOOLBAR = ["compose", "refresh", NSToolbarSpaceItemIdentifier, "view", NSToolbarFlexibleSpaceItemIdentifier,
               "search", "browser", "primary", "secondary"]

    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return self.TOOLBAR

    def toolbarDefaultItemIdentifiers_(self, toolbar):
        return self.TOOLBAR

    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(self, toolbar, ident, flag):
        item = NSToolbarItem.alloc().initWithItemIdentifier_(ident)
        if ident == "view":
            seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(0, 0, 112, 25))
            seg.setSegmentStyle_(NSSegmentStyleTexturedRounded)
            seg.cell().setTrackingMode_(NSSegmentSwitchTrackingMomentary)
            seg.setSegmentCount_(3)
            for i, (glyph, tip) in enumerate((("photo", u"Insert Image"), ("eye", u"Preview"), ("info", u"Inspector"))):
                seg.setImage_forSegment_(icons.template(glyph), i)
                seg.setWidth_forSegment_(34, i)
                seg.cell().setToolTip_forSegment_(tip, i)
            seg.setTarget_(self)
            seg.setAction_("viewSegment:")
            view, label = seg, u"View"
        elif ident == "search":
            field = NSSearchField.alloc().initWithFrame_(NSMakeRect(0, 0, 170, 22))
            field.cell().setPlaceholderString_(u"Search posts")
            field.setTarget_(self)
            field.setAction_("searchPosts:")
            self.searchField = field
            view, label = field, u"Search"
        else:
            spec = {"compose": (u"New Post", "newPost:", "compose", None),
                    "refresh": (u"Refresh", "refresh:", "refresh", None),
                    "browser": (u"Open in Browser", "openInBrowser:", "globe", None),
                    "primary": (u"Save Draft", "save:", None, 96),
                    "secondary": (u"Publish…", "publishOrUnpublish:", None, 92)}.get(ident)
            if not spec:
                return None
            label, action, glyph, width = spec
            button = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, width or 36, 25))
            button.setBezelStyle_(NSTexturedRoundedBezelStyle)
            if glyph:
                button.setImage_(icons.template(glyph))
                button.setImagePosition_(NSImageOnly)
                button.setToolTip_(label)
            else:
                button.setTitle_(label)
            button.setTarget_(self)
            button.setAction_(action)
            setattr(self, ident + "Button", button)
            view = button
        item.setView_(view)
        item.setLabel_(label)
        item.setPaletteLabel_(label)
        item.setMinSize_(view.frame().size)
        item.setMaxSize_(view.frame().size)
        return item

    def viewSegment_(self, sender):
        segment = sender.selectedSegment()
        if segment == 0:
            self.insertImage_(sender)
        elif segment == 1:
            self.togglePreview_(sender)
        else:
            self.toggleInspector_(sender)

    # ---- what can be done right now ---------------------------------------------------------------------
    def canDo(self, action):
        d = self.doc or {}
        if self.busy and action in ("save:", "publishOrUnpublish:", "revertToRemote:", "refresh:", "deleteDraft:"):
            return False
        return bool({
            "save:": d.get("dirty") or not d.get("id"),
            "revertToRemote:": d.get("id"),
            "openInBrowser:": d.get("id"),
            "deleteDraft:": not d.get("id"),
        }.get(action, True))

    def validateMenuItem_(self, item):
        action = item.action()
        if action == "sortBy:":
            item.setState_(NSOnState if SORTS[item.tag()][1] == self.sortKey() else NSOffState)
            return True
        if action == "toggleInspector:":
            item.setTitle_(u"Hide Inspector" if self.inspector.isVisible() else u"Show Inspector")
        elif action == "togglePreview:":
            item.setTitle_(u"Show Preview" if self.preview.isHidden() else u"Hide Preview")
        elif action == "publishOrUnpublish:":
            item.setTitle_(self.secondaryButton.title())
        elif action == "save:":
            item.setTitle_(self.primaryButton.title())
        elif action in ("rowOpenInBrowser:", "rowDiscard:", "rowDelete:"):
            row = self.clickedItem()
            if row is None:
                return False
            local = load_doc(row["key"]) or {}
            remote = not row["key"].startswith("local-")
            return bool({"rowOpenInBrowser:": remote, "rowDiscard:": remote and local.get("dirty"),
                         "rowDelete:": not remote}[action])
        return self.canDo(action)

    # ---- sidebar ----------------------------------------------------------------------------------------
    def sortKey(self):
        return self.defaults.stringForKey_("sortBy") or "edited"

    def sortBy_(self, sender):
        self.defaults.setObject_forKey_(SORTS[sender.tag()][1], "sortBy")
        self.rebuildSidebar()

    def searchPosts_(self, sender):
        self.search = sender.stringValue().strip().lower()
        self.rebuildSidebar()

    def rebuildSidebar(self):
        local = local_docs()
        rows = dict((s, []) for s, _ in GROUPS)
        for d in local.values():
            if not d.get("id"):
                rows["new"].append({"key": d["key"], "title": d.get("title") or u"Untitled", "status": "new",
                                    "sub": u"Only on this Mac", "dirty": False,
                                    "edited": d.get("local_edited") or u"", "published": u""})
        for p in self.remote:
            cached = local.get(p["id"]) or {}
            status = p["status"] if p["status"] in rows else "draft"
            dirty = bool(cached.get("dirty"))
            when = p.get("published_at") if status in ("published", "scheduled") else p.get("updated_at")
            prefix = {"draft": u"Edited ", "scheduled": u"Scheduled for "}.get(status, u"")
            rows[status].append({"key": p["id"], "status": status, "dirty": dirty,
                                 "title": (cached.get("title") if dirty else p.get("title")) or u"Untitled",
                                 "sub": prefix + short_date(when),
                                 "edited": p.get("updated_at") or u"", "published": p.get("published_at") or u""})
        sort = self.sortKey()
        self.groups = []
        for status, label in GROUPS:
            items = [r for r in rows[status] if not self.search or self.search in r["title"].lower()]
            if sort == "title":
                items.sort(key=lambda r: r["title"].lower())
            else:
                field = "published" if sort == "published" else "edited"
                items.sort(key=lambda r: r[field] or r["edited"], reverse=True)
            if items:
                group = NSMutableDictionary.dictionaryWithDictionary_(
                    {"kind": "group", "title": u"%s  %d" % (label, len(items))})
                self.groups.append((group, [NSMutableDictionary.dictionaryWithDictionary_(dict(r, kind="post"))
                                            for r in items]))
        self.loading_doc = True
        self.outline.reloadData()
        for group, _ in self.groups:
            self.outline.expandItem_(group)
        self.selectCurrentInSidebar()
        self.loading_doc = False

    def selectCurrentInSidebar(self):
        if not self.doc:
            return
        for group, items in self.groups:
            for item in items:
                if item["key"] == self.doc["key"]:
                    row = self.outline.rowForItem_(item)
                    if row >= 0:
                        self.outline.selectRowIndexes_byExtendingSelection_(NSIndexSet.indexSetWithIndex_(row), False)
                        self.outline.scrollRowToVisible_(row)
                    return
        self.outline.deselectAll_(None)

    def outlineView_numberOfChildrenOfItem_(self, ov, item):
        if item is None:
            return len(self.groups)
        for group, items in self.groups:
            if item == group:
                return len(items)
        return 0

    def outlineView_child_ofItem_(self, ov, index, item):
        if item is None:
            return self.groups[index][0]
        for group, items in self.groups:
            if item == group:
                return items[index]
        return None

    def outlineView_isItemExpandable_(self, ov, item):
        return item is not None and item["kind"] == "group"

    def outlineView_isGroupItem_(self, ov, item):
        return item["kind"] == "group"

    def outlineView_shouldSelectItem_(self, ov, item):
        return item["kind"] != "group"

    def outlineView_heightOfRowByItem_(self, ov, item):
        return 22 if item["kind"] == "group" else 38

    def outlineView_dataCellForTableColumn_item_(self, ov, col, item):
        if col is None or item["kind"] == "group":
            return None
        return self.postCell

    def outlineView_objectValueForTableColumn_byItem_(self, ov, col, item):
        return item["title"] if item["kind"] == "group" else item

    def outlineViewSelectionDidChange_(self, note):
        if self.loading_doc:
            return
        item = self.outline.itemAtRow_(self.outline.selectedRow())
        if item is None or item["kind"] == "group" or (self.doc and item["key"] == self.doc["key"]):
            return
        self.openKey(item["key"])

    def clickedItem(self):
        row = self.outline.clickedRow()
        item = self.outline.itemAtRow_(row) if row >= 0 else None
        return item if item is not None and item["kind"] == "post" else None

    def rowOpenInBrowser_(self, sender):
        item = self.clickedItem()
        if item is not None:
            url = ghost.Ghost(self.site(), "").editor_url(item["key"])
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))

    def rowDiscard_(self, sender):
        item = self.clickedItem()
        if item is not None and self.confirm(u"Discard your changes to “%s”?" % item["title"],
                                             u"It will be reloaded from %s." % self.siteName(), u"Discard Changes"):
            os.remove(doc_path(item["key"]))
            if self.doc and self.doc["key"] == item["key"]:
                self.pull(item["key"])
            self.rebuildSidebar()

    def rowDelete_(self, sender):
        item = self.clickedItem()
        if item is not None:
            self.deleteLocal(item["key"], item["title"])

    # ---- opening posts (pull) ------------------------------------------------------------------------
    def remoteSummary(self, post_id):
        return next((p for p in self.remote if p["id"] == post_id), None)

    def openKey(self, key):
        cached = load_doc(key)
        summary = self.remoteSummary(key)
        if summary is None:
            if cached:
                self.showDoc(cached)
            return
        if cached and cached.get("base_updated_at") == summary["updated_at"]:
            self.showDoc(cached)
            return
        if cached and cached.get("dirty"):
            alert = NSAlert.alloc().init()
            alert.setMessageText_(u"“%s” changed on the site" % (summary.get("title") or u"Untitled"))
            alert.setInformativeText_(u"It was edited on %s since you last opened it here, and you also "
                                      u"have unsaved changes in Planchette." % self.siteName())
            alert.addButtonWithTitle_(u"Keep My Changes")
            alert.addButtonWithTitle_(u"Use the Site’s Version")
            if alert.runModal() == NSAlertFirstButtonReturn:
                cached["base_updated_at"] = summary["updated_at"]
                save_doc(cached)
                self.showDoc(cached)
                return
        self.pull(key)

    def pull(self, post_id):
        g = self.ghostClient(False)
        if not g:
            return
        self.setBusy_(u"Loading from %s…" % self.siteName())

        def work():
            p = g.get_post(post_id, html=True)
            return {"key": p["id"], "id": p["id"], "title": p.get("title") or u"",
                    "markdown": html2md.convert(p.get("html") or u""), "status": p["status"],
                    "base_updated_at": p["updated_at"], "url": p.get("url"), "dirty": False, "uploads": {},
                    "saved_at": None, "slug": p.get("slug") or u"", "excerpt": p.get("custom_excerpt") or u"",
                    "tags": [t["name"] for t in p.get("tags") or []], "feature_image": p.get("feature_image")}

        def done(doc, error):
            self.setIdle()
            if error:
                self.setStatus_(u"Couldn’t load the post: %s" % error)
                return
            save_doc(doc)
            self.showDoc(doc)
            self.rebuildSidebar()

        cocoa.in_background(work, done)

    def showDoc(self, doc):
        for k, v in new_doc().items():
            if k != "key":
                doc.setdefault(k, v)
        self.doc = doc
        self.loading_doc = True
        self.titleField.setStringValue_(doc.get("title") or u"")
        self.textView.setString_(doc.get("markdown") or u"")
        highlight(self.textView.textStorage())
        self.textView.scrollRangeToVisible_(NSMakeRange(0, 0))
        self.loadInspector()
        self.loading_doc = False
        self.defaults.setObject_forKey_(doc["key"], "lastKey")
        self.updatePreview_(None)
        self.updateState()
        self.selectCurrentInSidebar()
        self.window.makeFirstResponder_(self.textView if doc.get("title") else self.titleField)

    def createDoc(self):
        doc = new_doc()
        save_doc(doc)
        return doc

    # ---- editing -----------------------------------------------------------------------------------------
    def textDidChange_(self, note):
        if note.object() == self.excerptView:
            self.inspectorEdited()
            return
        self.edited()
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(self, "rehighlight:", None)
        self.performSelector_withObject_afterDelay_("rehighlight:", None, 0.0)

    def rehighlight_(self, _):
        highlight(self.textView.textStorage())

    def textView_shouldSetSpellingState_range_(self, tv, value, rng):
        return 0 if in_code(rng) else value

    def controlTextDidChange_(self, note):
        if note.object() in (self.slugField, self.tagsField):
            self.inspectorEdited()
        elif note.object() == self.titleField:
            self.edited()

    def controlTextDidEndEditing_(self, note):
        if note.object() == self.tagsField:
            self.inspectorEdited()

    def edited(self):
        if self.loading_doc or not self.doc:
            return
        was_dirty = self.doc.get("dirty")
        self.doc["title"] = self.titleField.stringValue()
        self.doc["markdown"] = self.textView.string()
        self.markDirty(was_dirty)

    def markDirty(self, was_dirty):
        self.doc["dirty"] = True
        save_doc(self.doc)
        self.updateState()
        if not was_dirty:
            self.rebuildSidebar()
        NSObject.cancelPreviousPerformRequestsWithTarget_selector_object_(self, "updatePreview:", None)
        self.performSelector_withObject_afterDelay_("updatePreview:", None, 0.3)

    def siteName(self):
        return self.site().replace("https://", "").replace("http://", "") or u"your blog"

    def updateState(self):
        """Status pill + detail, window title and close-button dot, toolbar labels, bar text."""
        d = self.doc
        status = d.get("status") or "new"
        live = status in ("published", "scheduled")
        self.window.setTitle_(d.get("title") or u"Untitled")
        self.window.setDocumentEdited_(bool(d.get("dirty")))
        if not d.get("id"):
            detail = u"Only on this Mac — Save Draft puts it on %s" % self.siteName()
        elif d.get("dirty"):
            detail = u"Unsaved changes" + (u" — readers see the old version until you Update" if live else u"")
        else:
            detail = u"In sync with %s" % self.siteName() + (u" · saved %s" % d["saved_at"] if d.get("saved_at") else u"")
        if d.get("slug") and d.get("id"):
            detail += u"   /%s/" % d["slug"]
        self.strip.status, self.strip.detail = status, detail
        self.strip.setNeedsDisplay_(True)
        self.primaryButton.setTitle_(u"Update" if live else u"Save Draft")
        self.secondaryButton.setTitle_(u"Unpublish…" if live else u"Publish…")
        self.primaryButton.setEnabled_(self.canDo("save:"))
        self.secondaryButton.setEnabled_(not self.busy)
        self.browserButton.setEnabled_(bool(d.get("id")))
        if not self.busy:
            self.setStatus_(u"")
        words = len((d.get("markdown") or u"").split())
        self.words.setStringValue_(u"%d word%s · %d min read" % (words, u"" if words == 1 else u"s",
                                                                    max(1, int(round(words / 220.0)))))

    def setStatus_(self, text):
        self.status.setStringValue_(text)

    def setBusy_(self, text):
        self.busy = True
        self.spinner.startAnimation_(None)
        self.updateState()
        self.setStatus_(text)

    def setIdle(self):
        self.busy = False
        self.spinner.stopAnimation_(None)
        self.updateState()

    # ---- preview -------------------------------------------------------------------------------------------
    def webView_didFinishLoadForFrame_(self, webview, frame):
        if frame == webview.mainFrame():
            self.preview_ready = True
            self.updatePreview_(None)

    def imageURL(self, src):
        local = media_path(src)
        if local:
            return NSURL.fileURLWithPath_(viewable(local)).absoluteString() if os.path.exists(local) else src
        if src.startswith("http"):
            return self.remoteImage(src)
        return src

    def updatePreview_(self, _):
        if not self.preview_ready or not self.doc:
            return
        d = self.doc
        body = markdown.to_html(d.get("markdown") or u"") or u'<p class="empty">Start writing on the left…</p>'
        body = re.sub(r'src="([^"]+)"', lambda m: u'src="%s"' % self.imageURL(m.group(1)), body)
        meta = u" · ".join(x for x in (STATUS_NAMES.get(d.get("status"), u""), u", ".join(d.get("tags") or [])) if x)
        feature = self.imageURL(d["feature_image"]) if d.get("feature_image") else u""
        js = u"setContent(%s, %s, %s, %s); scrollToRatio(%f);" % (
            json.dumps(d.get("title") or u"Untitled"), json.dumps(meta), json.dumps(feature), json.dumps(body),
            self.editorScrollRatio())
        self.preview.stringByEvaluatingJavaScriptFromString_(js)

    def editorScrollRatio(self):
        visible = self.editorScroll.contentView().documentVisibleRect()
        total = self.textView.frame().size.height - visible.size.height
        return max(0.0, min(1.0, visible.origin.y / total)) if total > 0 else 0.0

    def editorScrolled_(self, note):
        if self.preview_ready:
            self.preview.stringByEvaluatingJavaScriptFromString_(u"scrollToRatio(%f);" % self.editorScrollRatio())

    def remoteImage(self, url):
        """Lion's WebKit can't fetch HTTPS (or decode WebP); use a LionKit-downloaded copy instead."""
        ext = os.path.splitext(url.split("?")[0])[1][:5] or ".img"
        path = os.path.join(IMAGE_CACHE, hashlib.sha1(url.encode("utf-8")).hexdigest() + ext)
        if os.path.exists(path):
            return NSURL.fileURLWithPath_(viewable(path)).absoluteString()
        if url not in self.fetching_images:
            self.fetching_images.add(url)

            def fetch():
                http.request("GET", url, output_path=path, timeout=60)
                viewable(path)

            def done(_, error):
                self.fetching_images.discard(url)
                if not error:
                    self.updatePreview_(None)
                    if self.doc and self.doc.get("feature_image") == url:
                        self.loadInspector()

            cocoa.in_background(fetch, done)
        return url

    # ---- inspector (HUD panel) -------------------------------------------------------------------------
    def buildInspector(self):
        p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 300, 470),
            NSTitledWindowMask | NSClosableWindowMask | NSUtilityWindowMask | NSHUDWindowMask,
            NSBackingStoreBuffered, False)
        p.setTitle_(u"Post Info")
        p.setFloatingPanel_(True)
        p.setHidesOnDeactivate_(True)
        v = p.contentView()
        gray = NSColor.colorWithCalibratedWhite_alpha_(0.6, 1)
        hud_label(v, u"URL SLUG", NSMakeRect(14, 438, 270, 15))
        self.slugField = NSTextField.alloc().initWithFrame_(NSMakeRect(16, 412, 268, 22))
        self.slugField.cell().setPlaceholderString_(u"generated from the title")
        self.slugField.setDelegate_(self)
        v.addSubview_(self.slugField)
        self.urlLabel = hud_label(v, u"", NSMakeRect(14, 392, 270, 15), 10.5, gray)

        hud_label(v, u"EXCERPT", NSMakeRect(14, 362, 200, 15))
        self.excerptCount = hud_label(v, u"", NSMakeRect(214, 362, 70, 15), 10.5, gray)
        self.excerptCount.setAlignment_(NSRightTextAlignment)
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(16, 272, 268, 86))
        scroll.setBorderType_(NSBezelBorder)
        scroll.setHasVerticalScroller_(True)
        ex = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 262, 86))
        ex.setFont_(NSFont.systemFontOfSize_(12))
        ex.setRichText_(False)
        ex.setAllowsUndo_(True)
        ex.textContainer().setWidthTracksTextView_(True)
        ex.setDelegate_(self)
        scroll.setDocumentView_(ex)
        v.addSubview_(scroll)
        self.excerptView = ex

        hud_label(v, u"TAGS", NSMakeRect(14, 244, 270, 15))
        tags = NSTokenField.alloc().initWithFrame_(NSMakeRect(16, 196, 268, 44))
        tags.setDelegate_(self)
        tags.cell().setPlaceholderString_(u"Type a tag and press Return")
        v.addSubview_(tags)
        self.tagsField = tags

        hud_label(v, u"FEATURE IMAGE", NSMakeRect(14, 170, 270, 15))
        well = NSImageView.alloc().initWithFrame_(NSMakeRect(16, 44, 268, 122))
        well.setImageFrameStyle_(NSImageFrameGrayBezel)
        well.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        v.addSubview_(well)
        self.featureWell = well
        for title, x, action in ((u"Choose…", 16, "chooseFeature:"), (u"Remove", 112, "removeFeature:")):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(x, 10, 90, 26))
            b.setBezelStyle_(NSRoundRectBezelStyle)
            b.setTitle_(title)
            b.setTarget_(self)
            b.setAction_(action)
            v.addSubview_(b)
        self.inspector = p

    def tokenField_completionsForSubstring_indexOfToken_indexOfSelectedItem_(self, field, sub, index, selected):
        return [t for t in self.site_tags if t.lower().startswith(sub.lower())]

    def loadInspector(self):
        d = self.doc
        self.slugField.setStringValue_(d.get("slug") or u"")
        self.excerptView.setString_(d.get("excerpt") or u"")
        self.tagsField.setObjectValue_(d.get("tags") or [])
        self.updateInspectorLabels()
        self.featureWell.setImage_(None)
        if d.get("feature_image"):
            url = self.imageURL(d["feature_image"])
            if url.startswith("file://"):
                self.featureWell.setImage_(NSImage.alloc().initWithContentsOfURL_(NSURL.URLWithString_(url)))

    def updateInspectorLabels(self):
        d = self.doc
        n = len(d.get("excerpt") or u"")
        self.excerptCount.setStringValue_(u"%d / %d" % (n, EXCERPT_MAX))
        self.excerptCount.setTextColor_(rgb(255, 120, 90) if n > EXCERPT_MAX else NSColor.colorWithCalibratedWhite_alpha_(0.6, 1))
        self.urlLabel.setStringValue_(u"%s/%s/" % (self.siteName(), d.get("slug") or u"(from title)"))

    def inspectorEdited(self):
        if self.loading_doc or not self.doc:
            return
        was_dirty = self.doc.get("dirty")
        self.doc["slug"] = self.slugField.stringValue().strip()
        self.doc["excerpt"] = self.excerptView.string()
        self.doc["tags"] = [unicode(t).strip() for t in (self.tagsField.objectValue() or []) if unicode(t).strip()]
        self.updateInspectorLabels()
        self.markDirty(was_dirty)

    def toggleInspector_(self, sender):
        if self.inspector.isVisible():
            self.inspector.orderOut_(None)
        else:
            frame = self.window.frame()
            self.inspector.setFrameTopLeftPoint_(NSMakePoint(frame.origin.x + frame.size.width - 320,
                                                             frame.origin.y + frame.size.height - 90))
            self.inspector.orderFront_(None)

    def chooseFeature_(self, sender):
        paths = self.pickImage(False)
        if paths:
            was_dirty = self.doc.get("dirty")
            self.doc["feature_image"] = import_media(paths[0])
            self.loadInspector()
            self.markDirty(was_dirty)

    def removeFeature_(self, sender):
        if self.doc.get("feature_image"):
            was_dirty = self.doc.get("dirty")
            self.doc["feature_image"] = None
            self.loadInspector()
            self.markDirty(was_dirty)

    # ---- actions ---------------------------------------------------------------------------------------
    def newPost_(self, sender):
        self.showDoc(self.createDoc())
        self.rebuildSidebar()

    def pickImage(self, multiple):
        panel = NSOpenPanel.openPanel()
        panel.setAllowsMultipleSelection_(multiple)
        panel.setAllowedFileTypes_(["jpg", "jpeg", "png", "gif", "webp"])
        pb = os.path.expanduser("~/Pictures/Photo Booth Library/Pictures")
        if os.path.isdir(pb):
            panel.setDirectoryURL_(NSURL.fileURLWithPath_(pb))
        if panel.runModal() != NSFileHandlingPanelOKButton:
            return []
        return [u.path() for u in panel.URLs()]

    def insertImage_(self, sender):
        refs = [import_media(p) for p in self.pickImage(True)]
        if refs:
            self.textView.insertText_(u"".join(u'\n![](%s "Caption")\n' % r for r in refs))

    def togglePreview_(self, sender):
        self.preview.setHidden_(not self.preview.isHidden())
        self.layoutEditor()

    def openInBrowser_(self, sender):
        if self.doc and self.doc.get("id"):
            url = ghost.Ghost(self.site(), "").editor_url(self.doc["id"])
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))

    def refresh_(self, sender):
        g = self.ghostClient(sender is not None)
        if not g:
            self.setStatus_(u"Add your blog and its Admin API key in Preferences to see your posts.")
            return
        self.setBusy_(u"Checking %s…" % self.siteName())

        def work():
            return g.list_posts(), g.tag_names()

        def done(result, error):
            self.setIdle()
            if error:
                self.setStatus_(u"Couldn’t load posts: %s" % error)
                return
            self.remote, self.site_tags = result
            self.rebuildSidebar()
            if self.doc and self.doc.get("id") and not self.doc.get("dirty"):
                summary = self.remoteSummary(self.doc["id"])
                if summary and summary["updated_at"] != self.doc.get("base_updated_at"):
                    self.pull(self.doc["id"])

        cocoa.in_background(work, done)

    def deleteDraft_(self, sender):
        if self.doc and not self.doc.get("id"):
            self.deleteLocal(self.doc["key"], self.doc.get("title") or u"Untitled")

    def deleteLocal(self, key, title):
        if not self.confirm(u"Delete “%s”?" % title,
                            u"This draft only exists on this Mac, so it can’t be recovered.", u"Delete"):
            return
        if os.path.exists(doc_path(key)):
            os.remove(doc_path(key))
        if self.doc and self.doc["key"] == key:
            others = list(local_docs().values())
            self.showDoc(others[0] if others else self.createDoc())
        self.rebuildSidebar()

    def save_(self, sender):
        self.push(None, False, False)

    def publishOrUnpublish_(self, sender):
        title = self.doc.get("title") or u"Untitled"
        if self.doc.get("status") in ("published", "scheduled"):
            if self.confirm(u"Unpublish “%s”?" % title,
                            u"It becomes a draft again and disappears from %s." % self.siteName(), u"Unpublish"):
                self.push("draft", False, True)
        elif self.confirm(u"Publish “%s”?" % title,
                          u"It goes live on %s right away. It won’t be emailed to subscribers." % self.siteName(),
                          u"Publish"):
            self.push("published", False, True)

    def revertToRemote_(self, sender):
        if self.doc.get("dirty") and not self.confirm(
                u"Discard your changes?", u"Planchette will reload this post from %s." % self.siteName(),
                u"Discard Changes"):
            return
        self.pull(self.doc["id"])

    def confirm(self, message, info, ok_title):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.setInformativeText_(info)
        alert.addButtonWithTitle_(ok_title)
        alert.addButtonWithTitle_(u"Cancel")
        return alert.runModal() == NSAlertFirstButtonReturn

    def push(self, status, overwrite, confirmed):  # called positionally (PyObjC selector)
        doc = self.doc
        if doc.get("status") == "published" and not confirmed and not self.confirm(
                u"Update the live post?", u"“%s” is published. Updating changes what readers see on %s now."
                % (doc.get("title") or u"Untitled", self.siteName()), u"Update"):
            return
        if len(doc.get("excerpt") or u"") > EXCERPT_MAX:
            self.setStatus_(u"The excerpt is longer than %d characters; shorten it in the Inspector." % EXCERPT_MAX)
            return
        g = self.ghostClient(True)
        if not g:
            return
        snapshot = json.loads(json.dumps(doc))
        self.setBusy_(u"Saving to %s…" % self.siteName())

        def upload(src, uploads):
            if src not in uploads:
                uploads[src] = g.upload_image(media_path(src))
            return uploads[src]

        def work():
            uploads = snapshot.setdefault("uploads", {})
            text = snapshot.get("markdown") or u""
            for src in markdown.image_srcs(text):
                if media_path(src):
                    text = text.replace(src, upload(src, uploads))
            fields = {"title": snapshot.get("title") or u"Untitled", "html": markdown.to_html(text),
                      "custom_excerpt": snapshot.get("excerpt") or None,
                      "tags": [{"name": t} for t in snapshot.get("tags") or []]}
            if snapshot.get("slug"):
                fields["slug"] = snapshot["slug"]
            feature = snapshot.get("feature_image")
            fields["feature_image"] = upload(feature, uploads) if feature and media_path(feature) else feature
            if status:
                fields["status"] = status
            if not snapshot.get("id"):
                fields.setdefault("status", "draft")
                return g.create_post(fields), uploads
            base = g.get_post(snapshot["id"])["updated_at"] if overwrite else snapshot["base_updated_at"]
            return g.update_post(snapshot["id"], fields, base), uploads

        def done(result, error):
            self.setIdle()
            if isinstance(error, ghost.GhostConflict):
                alert = NSAlert.alloc().init()
                alert.setMessageText_(u"This post changed on %s" % self.siteName())
                alert.setInformativeText_(u"Someone edited it on the site after you opened it here. "
                                          u"Replace the site’s version with yours, or load theirs?")
                alert.addButtonWithTitle_(u"Replace with Mine")
                alert.addButtonWithTitle_(u"Load the Site’s Version")
                alert.addButtonWithTitle_(u"Cancel")
                choice = alert.runModal()
                if choice == NSAlertFirstButtonReturn:
                    self.push(status, True, True)
                elif choice == NSAlertSecondButtonReturn:
                    self.pull(snapshot["id"])
                return
            if error:
                self.setStatus_(u"Couldn’t save: %s" % error)
                return
            post, uploads = result
            old_key = doc["key"]
            doc.update({"id": post["id"], "key": post["id"], "status": post["status"], "url": post.get("url"),
                        "slug": post.get("slug") or u"", "base_updated_at": post["updated_at"], "uploads": uploads,
                        "saved_at": time.strftime("%H:%M")})
            doc["dirty"] = any(doc.get(k) != snapshot.get(k)
                               for k in ("markdown", "title", "excerpt", "tags", "feature_image"))
            save_doc(doc)
            if old_key != doc["key"] and os.path.exists(doc_path(old_key)):
                os.remove(doc_path(old_key))
            self.defaults.setObject_forKey_(doc["key"], "lastKey")
            self.loadInspector()
            self.updateState()
            self.setStatus_({"published": u"Published ✓", "draft": u"Saved as a draft ✓"}
                            .get(post["status"], u"Saved ✓"))
            self.refresh_(None)

        cocoa.in_background(work, done)

    # ---- Ghost connection & preferences --------------------------------------------------------------
    def site(self):
        return self.defaults.stringForKey_("site") or u""

    def ghostClient(self, prompt):
        if not self.site():
            if prompt:
                self.showPreferences_(None)
            return None
        try:
            key = keychain.get(KEYCHAIN_SERVICE, self.site())
        except OSError as e:
            self.setStatus_(u"Couldn’t read the keychain: %s" % e)
            return None
        if not key:
            if prompt:
                self.setStatus_(u"Add your Ghost Admin API key in Preferences first.")
                self.showPreferences_(None)
            return None
        return ghost.Ghost(self.site(), key)

    def showPreferences_(self, sender):
        if not getattr(self, "prefs", None):
            p = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 480, 236), NSTitledWindowMask | NSClosableWindowMask, NSBackingStoreBuffered, False)
            p.setTitle_(u"Planchette Preferences")
            v = p.contentView()
            self.prefLabel(v, u"Ghost site:", 186)
            self.siteField = NSTextField.alloc().initWithFrame_(NSMakeRect(140, 182, 316, 24))
            self.siteField.cell().setPlaceholderString_(u"https://yourblog.com")
            v.addSubview_(self.siteField)
            self.prefLabel(v, u"Admin API key:", 148)
            self.keyField = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(140, 144, 316, 24))
            v.addSubview_(self.keyField)
            help_ = self.prefText(v, NSMakeRect(140, 70, 316, 66))
            help_.setTextColor_(NSColor.grayColor())
            help_.setStringValue_(u"In Ghost Admin: Settings → Integrations → Add custom integration, "
                                  u"then copy its Admin API key. It’s stored in your login keychain.")
            self.prefStatus = self.prefText(v, NSMakeRect(20, 22, 320, 20))
            save = NSButton.alloc().initWithFrame_(NSMakeRect(356, 14, 106, 32))
            save.setTitle_(u"Save")
            save.setBezelStyle_(NSRoundedBezelStyle)
            save.setKeyEquivalent_(u"\r")
            save.setTarget_(self)
            save.setAction_("savePreferences:")
            v.addSubview_(save)
            self.prefs = p
        self.siteField.setStringValue_(self.site())
        try:
            has_key = keychain.get(KEYCHAIN_SERVICE, self.site())
        except OSError:
            has_key = None
        self.keyField.setStringValue_(u"")
        self.keyField.cell().setPlaceholderString_(u"saved in keychain" if has_key else u"id:secret")
        self.prefStatus.setStringValue_(u"")
        self.prefs.center()
        self.prefs.makeKeyAndOrderFront_(None)

    def prefLabel(self, view, text, y):
        label = self.prefText(view, NSMakeRect(10, y, 124, 17))
        label.setAlignment_(NSRightTextAlignment)
        label.setFont_(NSFont.systemFontOfSize_(13))
        label.setStringValue_(text)

    def prefText(self, view, frame):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setFont_(NSFont.systemFontOfSize_(11))
        view.addSubview_(f)
        return f

    def savePreferences_(self, sender):
        site = self.siteField.stringValue().strip().rstrip("/")
        if not site:
            self.prefStatus.setStringValue_(u"Enter your blog\u2019s address first.")
            return
        if not site.startswith("http"):
            site = "https://" + site
        self.defaults.setObject_forKey_(site, "site")
        key = self.keyField.stringValue().strip()
        try:
            if key:
                if ":" not in key:
                    self.prefStatus.setStringValue_(u"That doesn’t look like an Admin API key (id:secret).")
                    return
                keychain.set(KEYCHAIN_SERVICE, site, key)
                self.keyField.setStringValue_(u"")
            key = keychain.get(KEYCHAIN_SERVICE, site)
        except OSError as e:
            self.prefStatus.setStringValue_(u"Keychain error: %s" % e)
            return
        if not key:
            self.prefStatus.setStringValue_(u"Saved. Add an Admin API key to connect.")
            return
        self.prefStatus.setStringValue_(u"Checking…")

        def done(info, error):
            if error:
                self.prefStatus.setStringValue_(u"Couldn’t connect: %s" % error)
            else:
                self.prefStatus.setStringValue_(u"✓ Connected to %s" % info.get("title", site))
                self.refresh_(None)

        cocoa.in_background(lambda: ghost.Ghost(site, key).site_info(), done)

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True


if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()
