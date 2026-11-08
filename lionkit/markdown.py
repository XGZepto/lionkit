# -*- coding: utf-8 -*-
"""A small Markdown -> HTML converter (Python 2.7), tuned for Ghost posts.

Supports: <!--kg-card-begin: html--> blocks (passed through), \\-escapes, # headings, paragraphs, **bold**, *italic*, `code`, [links](url), fenced ``` code blocks,
> quotes, - / 1. lists, --- rules, and images on their own line:  ![alt](src "caption")
which become Ghost image cards (<figure> with <figcaption>).
"""
import cgi
import re

_IMG_LINE = re.compile(r'^!\[([^\]]*)\]\((\S+?)(?:\s+"([^"]*)")?\)\s*$')
_INLINE_IMG = re.compile(r'!\[([^\]]*)\]\((\S+?)\)')
_LINK = re.compile(r'\[([^\]]+)\]\((\S+?)\)')
_BOLD = re.compile(r'\*\*(.+?)\*\*')
_ITALIC = re.compile(r'(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)|(?<![\w])_(?!\s)(.+?)(?<!\s)_(?![\w])')


def esc(s):
    return cgi.escape(s, quote=True)


def inline(text):
    # Pull out code spans first so nothing inside them gets formatted.
    codes = []

    def keep_code(m):
        codes.append("<code>%s</code>" % esc(m.group(1)))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", keep_code, text)
    # Backslash escapes (\* \_ \` \[ \] \\) become literal characters.
    text = re.sub(r"\\([\\`*_\[\]])", lambda m: (codes.append(esc(m.group(1))), "\x00%d\x00" % (len(codes) - 1))[1], text)
    text = esc(text)
    text = _INLINE_IMG.sub(lambda m: '<img src="%s" alt="%s">' % (m.group(2), m.group(1)), text)
    text = _LINK.sub(lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(lambda m: "<em>%s</em>" % (m.group(1) or m.group(2)), text)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], text)


def image_srcs(md):
    """All image sources referenced in the document (for uploading local files)."""
    return [m.group(2) for m in _INLINE_IMG.finditer(md)]


def to_html(md):
    lines = md.replace("\r\n", "\n").split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(l.strip() for l in para)))
            del para[:]

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("<!--kg-card-begin: html-->"):
            flush()
            raw = []
            while i < len(lines):
                raw.append(lines[i])
                if "<!--kg-card-end: html-->" in lines[i]:
                    break
                i += 1
            out.append("\n".join(raw))  # Ghost HTML card: pass through verbatim
        elif stripped.startswith("```"):
            flush()
            lang = stripped[3:].strip()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            cls = ' class="language-%s"' % esc(lang) if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, esc("\n".join(code))))
        elif not stripped:
            flush()
        elif re.match(r"^#{1,6}\s", stripped):
            flush()
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (level, inline(stripped[level:].strip()), level))
        elif re.match(r"^(-{3,}|\*{3,})$", stripped):
            flush()
            out.append("<hr>")
        elif _IMG_LINE.match(stripped):
            flush()
            alt, src, caption = _IMG_LINE.match(stripped).groups()
            cap = "<figcaption>%s</figcaption>" % inline(caption) if caption else ""
            out.append('<figure class="kg-card kg-image-card%s"><img src="%s" class="kg-image" alt="%s">%s</figure>'
                       % (" kg-card-hascaption" if caption else "", src, esc(alt), cap))
        elif stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote><p>%s</p></blockquote>" % inline(" ".join(quote)))
            continue
        elif re.match(r"^([-*+]|\d+\.)\s", stripped):
            flush()
            ordered = bool(re.match(r"^\d+\.", stripped))
            items = []
            while i < len(lines) and re.match(r"^([-*+]|\d+\.)\s", lines[i].strip()):
                items.append(inline(re.sub(r"^([-*+]|\d+\.)\s+", "", lines[i].strip())))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % it for it in items), tag))
            continue
        else:
            para.append(line)
        i += 1
    flush()
    return "\n".join(out)
