# -*- coding: utf-8 -*-
"""Convert Ghost's post HTML back to the Markdown dialect in lionkit.markdown (Python 2.7).

Text, headings, lists, quotes, code, links and image cards become Markdown. Anything else
(HTML cards, bookmarks, galleries, tables...) is kept verbatim inside
<!--kg-card-begin: html--> ... <!--kg-card-end: html--> so it survives a round trip. So is any
block whose Markdown wouldn't render back to the same HTML: every block is checked.
"""
import re
from htmlentitydefs import name2codepoint
from HTMLParser import HTMLParser

from lionkit import markdown

# Bump whenever the same HTML would convert to different Markdown: Planchette re-pulls posts it
# converted with an older version (unless they have unsaved edits).
VERSION = 4

# Attributes the site adds by itself when it renders a post, so losing them changes nothing.
GENERATED = {"img": ("loading", "srcset", "sizes"), "h1": ("id",), "h2": ("id",), "h3": ("id",),
             "h4": ("id",), "h5": ("id",), "h6": ("id",)}
BREAK = u"\x01"
INLINE = {"strong", "b", "em", "i", "a", "span", "code", "s", "u", "mark", "sup", "sub"}

VOID = {"img", "br", "hr", "meta", "input", "source", "link", "col", "area", "wbr", "embed", "param"}
HTML_CARD = re.compile(r"(<!--kg-card-begin: html-->.*?<!--kg-card-end: html-->)", re.S)


class Node(object):
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def cls(self):
        return self.attrs.get("class") or ""


class _Builder(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.root = Node("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_entityref(self, name):
        self.handle_data(unichr(name2codepoint[name]) if name in name2codepoint else u"&%s;" % name)

    def handle_charref(self, ref):
        self.handle_data(unichr(int(ref[1:], 16) if ref[:1] in "xX" else int(ref)))


def parse(html):
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root


def _attrs_html(node):
    return u"".join(u' %s="%s"' % (k, (v or u"").replace(u'"', u"&quot;")) for k, v in node.attrs.items())


def to_html(node):
    """Serialize a node back to HTML (for cards we keep verbatim)."""
    if not isinstance(node, Node):
        return node.replace(u"&", u"&amp;").replace(u"<", u"&lt;").replace(u">", u"&gt;")
    inner = u"".join(to_html(c) for c in node.children)
    if node.tag in VOID:
        return u"<%s%s>" % (node.tag, _attrs_html(node))
    return u"<%s%s>%s</%s>" % (node.tag, _attrs_html(node), inner, node.tag)


def text_of(node):
    if not isinstance(node, Node):
        return node
    return u"".join(text_of(c) for c in node.children)


def _escape(text):
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text)


def _wrap(before, text, after):
    """Wrap text in Markdown markers, keeping edge spaces outside them: <b>Ariana </b>had -> **Ariana** had."""
    core = text.strip()
    if not core:
        return text
    lead = u" " if text[:1].isspace() else u""
    trail = u" " if text[-1:].isspace() else u""
    return lead + before + core + after + trail


def inline(nodes):
    out = []
    for n in nodes:
        if not isinstance(n, Node):
            out.append(_escape(re.sub(r"\s+", u" ", n)))
            continue
        t = n.tag
        if t in ("strong", "b"):
            out.append(_wrap(u"**", inline(n.children), u"**"))
        elif t in ("em", "i"):
            out.append(_wrap(u"*", inline(n.children), u"*"))
        elif t == "code":
            out.append(u"`%s`" % text_of(n))
        elif t == "a":
            out.append(_wrap(u"[", inline(n.children), u"](%s)" % n.attrs.get("href", u"")))
        elif t == "img":
            out.append(u"![%s](%s)" % (n.attrs.get("alt", u""), n.attrs.get("src", u"")))
        elif t == "br":
            out.append(BREAK)
        else:  # span, s, u, mark... keep the text
            out.append(inline(n.children))
    return u"".join(out)


def _card(node):
    return u"<!--kg-card-begin: html-->\n%s\n<!--kg-card-end: html-->" % to_html(node)


def block(node):
    if not isinstance(node, Node):
        text = node.strip()
        return _escape(text) if text else u""
    t, cls = node.tag, node.cls()
    if t == "p":
        return inline(node.children).strip().replace(BREAK, u"\\\n")
    if re.match(r"^h[1-6]$", t):
        return u"%s %s" % (u"#" * int(t[1]), inline(node.children).strip().replace(BREAK, u" "))
    if t in ("ul", "ol"):
        items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
        return u"\n".join(u"%s %s" % (u"%d." % (i + 1) if t == "ol" else u"-",
                                       inline(li.children).strip().replace(BREAK, u" "))
                          for i, li in enumerate(items))
    if t == "blockquote":
        return u"> " + inline(node.children).strip().replace(BREAK, u"\\\n> ")
    if t == "pre":
        code = node.children[0] if node.children and isinstance(node.children[0], Node) else node
        lang = re.search(r"language-(\S+)", code.cls() if isinstance(code, Node) else u"")
        return u"```%s\n%s\n```" % (lang.group(1) if lang else u"", text_of(code).rstrip(u"\n"))
    if t == "hr":
        return u"---"
    if t == "figure" and "kg-image-card" in cls:
        img = next((c for c in node.children if isinstance(c, Node) and c.tag == "img"), None)
        cap = next((c for c in node.children if isinstance(c, Node) and c.tag == "figcaption"), None)
        if img is not None:
            caption = _escape(re.sub(r"\s+", u" ", text_of(cap)).strip()).replace(u'"', u'\\"') if cap else u""
            title = u' "%s"' % caption if caption else u""
            return u"![%s](%s%s)" % (img.attrs.get("alt", u""), img.attrs.get("src", u""), title)
    if t == "img":
        return u"![%s](%s)" % (node.attrs.get("alt", u""), node.attrs.get("src", u""))
    if t in ("div", "section", "article") and "kg-card" not in cls:
        return u"\n\n".join(b for b in (block(c) for c in node.children) if b)
    return _card(node)  # tables, embeds, bookmarks, callouts, galleries...


def _canon(node):
    """A comparable form of a node: whitespace collapsed, attribute order and attributes the site
    generates ignored, Ghost's <span style="white-space: pre-wrap;"> wrappers unwrapped, and a
    space just inside bold, italic or a link treated like one just outside it (it looks the same)."""
    if not isinstance(node, Node):
        return re.sub(r"\s+", u" ", node)
    kids = []
    for child in node.children:
        if isinstance(child, Node) and child.tag == "span" and child.attrs == {"style": "white-space: pre-wrap;"}:
            kids.extend(_canon(c) for c in child.children)
        elif isinstance(child, Node) and child.tag in INLINE and child.tag != "code":
            text = text_of(child)
            kids.extend([u" "] if text[:1].isspace() else [])
            kids.append(_canon(child))
            kids.extend([u" "] if text[-1:].isspace() else [])
        else:
            kids.append(_canon(child))
    merged = []
    for k in kids:
        if not isinstance(k, tuple) and merged and not isinstance(merged[-1], tuple):
            merged[-1] = re.sub(r"\s+", u" ", merged[-1] + k)
        else:
            merged.append(k)
    if merged and not isinstance(merged[0], tuple):
        merged[0] = merged[0].lstrip()
    if merged and not isinstance(merged[-1], tuple):
        merged[-1] = merged[-1].rstrip()
    skip = GENERATED.get(node.tag, ())
    return (node.tag, tuple(sorted((k, v) for k, v in node.attrs.items() if k not in skip)),
            tuple(m for m in merged if m != u""))


def same_html(a, b):
    """True when two HTML fragments render the same once the site has done its part."""
    canon = lambda html: tuple(c for c in (_canon(c) for c in parse(html).children) if c != u" " and c != u"")
    return canon(a) == canon(b)


def image_sizes(node, images):
    """Record the width and height of every image under node, by src."""
    if isinstance(node, Node):
        if node.tag == "img" and node.attrs.get("src") and node.attrs.get("width"):
            images[node.attrs["src"]] = {"width": node.attrs["width"], "height": node.attrs.get("height")}
        for child in node.children:
            image_sizes(child, images)


def convert(html, images=None):
    """Markdown for a post's HTML. Pass a dict as `images` to collect image sizes (by src) for
    markdown.to_html. A block that wouldn't come back the same is kept as an HTML card."""
    images = {} if images is None else images
    parts = []
    for segment in HTML_CARD.split(html or u""):
        if HTML_CARD.match(segment):
            parts.append(segment.strip())
            continue
        for child in parse(segment).children:
            image_sizes(child, images)
            b = block(child)
            if b and not same_html(to_html(child), markdown.to_html(b, images)):
                b = _card(child)
            if b:
                parts.append(b)
    return u"\n\n".join(parts) + u"\n"
