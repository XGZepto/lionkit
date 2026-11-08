# -*- coding: utf-8 -*-
"""Album, artist and playlist artwork: small JPEGs cached on disk, a few kept in memory.

Spotify serves covers at 640, 300 and 64 px. Kassett only ever downloads the 300 and 64 px
versions, keeps them in ~/Library/Caches/Kassett/Artwork, and holds a bounded number of decoded
images in memory, because the Mac has 2 GB of RAM."""
import collections
import hashlib
import os
import Queue
import threading
import zlib

from AppKit import *  # noqa: F401,F403
from Foundation import *  # noqa: F401,F403

from lionkit import cocoa, http
import paint

CACHE = os.path.expanduser("~/Library/Caches/Kassett/Artwork")
KEEP_FILES = 1500        # trimmed back to this at launch
WORKERS = 3
MEMORY = {"small": 160, "large": 36}   # decoded images kept per size class

# Stand-ins for missing covers, from the mockups' palette.
PLACEHOLDERS = [("#f0c25a", "#d27a33", "#8f3b1f", "#fff8ec"), ("#c9b48f", "#6f5a3c", None, "#fffaf0"),
                ("#9db8a3", "#3f5f52", None, "#f7fff9"), ("#d8d2c4", "#7a7466", None, "#2b2925"),
                ("#4f6f8f", "#1f2f43", None, "#eef4fb"), ("#6a4e9b", "#e07a5f", None, "#fff6f0"),
                ("#ff9b3d", "#e2571e", None, "#fffaf2"), ("#5b4a3a", "#2b211a", None, "#f3e9dc"),
                ("#b9b4a5", "#5e6b73", None, "#1e2326"), ("#2c3e50", "#8e44ad", None, "#f5ecff"),
                ("#9fb7c9", "#4c6276", None, "#f4f8fb"), ("#e9a8a0", "#8d4a5c", None, "#fff4f2"),
                ("#74b072", "#2e6a3b", None, "#f2fff0"), ("#8ecae6", "#219ebc", None, "#f2fbff")]


def best_url(images, side):
    """The smallest image at least `side` px wide (Spotify lists them largest first)."""
    images = [i for i in images or [] if i and i.get("url")]
    if not images:
        return None
    sized = [i for i in images if i.get("width")]
    if not sized:
        return images[0]["url"]
    sized.sort(key=lambda i: i["width"])
    for i in sized:
        if i["width"] >= side:
            return i["url"]
    return sized[-1]["url"]


def small(images):
    return best_url(images, 64)


def large(images):
    return best_url(images, 300)


def path_for(url):
    return os.path.join(CACHE, hashlib.sha1(url).hexdigest() + ".jpg")


def placeholder(name):
    return PLACEHOLDERS[zlib.crc32((name or u"").encode("utf-8")) % len(PLACEHOLDERS)]


def draw_placeholder(rect, name, caption=None, round_=False, caption_size=13):
    """A cover-sized gradient with the title printed on it, like the mockups' stand-in art."""
    c1, c2, c3, ink = placeholder(name)
    stops = (c1, c2, c3) if c3 else (c1, c2)
    shape = NSBezierPath.bezierPathWithOvalInRect_(rect) if round_ else NSBezierPath.bezierPathWithRect_(rect)
    paint.fill(shape, *stops, angle=45)
    if caption:
        pad = max(6, rect.size.width * 0.07)
        f = paint.font("Helvetica-Bold", caption_size, True)
        h = paint.text_height(caption, f, rect.size.width - 2 * pad)
        h = min(h, rect.size.height - 2 * pad)
        paint.text(caption, NSMakeRect(rect.origin.x + pad, rect.origin.y + rect.size.height - pad - h,
                                       rect.size.width - 2 * pad, h), f, ink, truncate=False)


def initials(name):
    words = [w for w in (name or u"").replace(u"&", u" ").split() if w.lower() not in (u"the", u"and")]
    return u"".join(w[0].upper() for w in words[:2] if w[0].isalnum()) or u"♫"


class ArtCache(object):
    def __init__(self):
        self.memory = {"small": collections.OrderedDict(), "large": collections.OrderedDict()}
        self.waiting = {}
        self.jobs = Queue.Queue()
        if not os.path.isdir(CACHE):
            os.makedirs(CACHE)
        for _ in range(WORKERS):
            t = threading.Thread(target=self._worker)
            t.daemon = True
            t.start()
        cocoa.in_background(self._trim)

    def image(self, url, done=None, size_class="large"):
        """The NSImage for url if it's cached; otherwise None, and done() runs on the main thread
        once it has been downloaded."""
        if not url:
            return None
        mem = self.memory[size_class]
        img = mem.pop(url, None)
        if img is None:
            path = path_for(url)
            if os.path.exists(path):
                img = NSImage.alloc().initWithContentsOfFile_(path)
            if img is None:
                if done is not None:
                    self.fetch(url, done)
                return None
        mem[url] = img
        while len(mem) > MEMORY[size_class]:
            mem.popitem(last=False)
        return img

    def fetch(self, url, done):
        if url in self.waiting:
            self.waiting[url].append(done)
            return
        self.waiting[url] = [done]
        self.jobs.put(url)

    def _worker(self):
        while True:
            url = self.jobs.get()
            path = path_for(url)
            try:
                if not os.path.exists(path):
                    tmp = path + ".part"
                    r = http.request("GET", url, output_path=tmp, timeout=20)
                    if r.ok:
                        os.rename(tmp, path)
                    elif os.path.exists(tmp):
                        os.remove(tmp)
            except Exception:
                pass
            pool = NSAutoreleasePool.alloc().init()
            cocoa.on_main(lambda url=url: self._finished(url))
            del pool

    def _finished(self, url):
        for done in self.waiting.pop(url, []):
            try:
                done()
            except Exception as e:
                print("artwork callback failed: %s" % e)

    def _trim(self):
        files = [os.path.join(CACHE, f) for f in os.listdir(CACHE)]
        if len(files) <= KEEP_FILES:
            return
        files.sort(key=lambda p: os.path.getmtime(p))
        for p in files[:len(files) - KEEP_FILES]:
            try:
                os.remove(p)
            except OSError:
                pass


cache = None


def shared():
    global cache
    if cache is None:
        cache = ArtCache()
    return cache
