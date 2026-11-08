# -*- coding: utf-8 -*-
"""Convert Ghost's post HTML back to the Markdown dialect in lionkit.markdown (Python 2.7).

Text, headings, lists, quotes, code, links and image cards become Markdown. Anything else
(HTML cards, bookmarks, galleries, tables...) is kept verbatim inside
<!--kg-card-begin: html--> ... <!--kg-card-end: html--> so it survives a round trip.
"""
import re
from htmlentitydefs import name2codepoint
from HTMLParser import HTMLParser

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
            out.append(u" ")
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
        return inline(node.children).strip()
    if re.match(r"^h[1-6]$", t):
        return u"%s %s" % (u"#" * int(t[1]), inline(node.children).strip())
    if t in ("ul", "ol"):
        items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
        return u"\n".join(u"%s %s" % (u"%d." % (i + 1) if t == "ol" else u"-", inline(li.children).strip())
                          for i, li in enumerate(items))
    if t == "blockquote":
        return u"> " + inline(node.children).strip()
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
            caption = re.sub(r"\s+", u" ", text_of(cap)).strip().replace(u'"', u"”") if cap else u""
            title = u' "%s"' % caption if caption else u""
            return u"![%s](%s%s)" % (img.attrs.get("alt", u""), img.attrs.get("src", u""), title)
    if t == "img":
        return u"![%s](%s)" % (node.attrs.get("alt", u""), node.attrs.get("src", u""))
    if t in ("div", "section", "article") and "kg-card" not in cls:
        return u"\n\n".join(b for b in (block(c) for c in node.children) if b)
    return _card(node)  # tables, embeds, bookmarks, callouts, galleries...


def convert(html):
    parts = []
    for segment in HTML_CARD.split(html or u""):
        if HTML_CARD.match(segment):
            parts.append(segment.strip())
            continue
        for child in parse(segment).children:
            b = block(child)
            if b:
                parts.append(b)
    return u"\n\n".join(parts) + u"\n"
