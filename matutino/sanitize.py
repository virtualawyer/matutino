"""Allowlist HTML cleaner that emits well-formed XHTML.

Everything that goes into a story -- feed content and extracted article
bodies alike -- passes through clean(). The output is served on our own
origin and zipped into EPUBs, so it has to be both safe (no script, no
handlers, no javascript: links) and valid XML (every tag closed, no
control characters).
"""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

KEEP = {"p", "br", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "em",
        "strong", "a", "img", "figure", "figcaption", "pre", "code", "hr",
        "table", "thead", "tbody", "tr", "th", "td", "sup", "sub", "small"}
RENAME = {"h1": "h2", "h5": "h4", "h6": "h4", "b": "strong", "i": "em",
          "cite": "em", "q": "em"}
# Containers whose whole content goes. Void tags (input, embed, source...)
# must not be listed: they never close, so the skip depth would never unwind.
DROP = {"script", "style", "iframe", "object", "noscript", "form", "button",
        "select", "textarea", "svg", "math", "video", "audio", "canvas",
        "template", "head", "title", "nav", "aside", "footer", "header",
        "dialog", "map"}
VOID = {"br", "hr", "img"}
BLOCK = {"p", "h2", "h3", "h4", "ul", "ol", "blockquote", "figure", "pre",
         "table", "hr"}
PIXEL = re.compile(r"feedburner|feedsportal|doubleclick|pixel|tracking|"
                   r"/beacon|stats\.wordpress|gravatar\.com/avatar", re.I)
BAD_XML = re.compile(u"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def xml_text(s):
    return html.escape(BAD_XML.sub("", s), quote=False)


def xml_attr(s):
    return html.escape(BAD_XML.sub("", s), quote=True)


def _url(value, base):
    v = (value or "").strip()
    if not v or v.startswith("data:"):
        return None
    try:
        v = urljoin(base or "", v)
    except ValueError:
        return None
    return v if v.lower().startswith(("http://", "https://")) else None


class _Cleaner(HTMLParser):
    def __init__(self, base):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.base = base
        self.out = []
        self.stack = []
        self.skip = 0          # depth inside a DROP element
        self.images = []

    def _close_to(self, tag):
        while self.stack:
            t = self.stack.pop()
            self.out.append("</%s>" % t)
            if t == tag:
                return

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag in DROP:
                self.skip += 1
            return
        if tag in DROP:
            self.skip = 1
            return
        tag = RENAME.get(tag, tag)
        if tag not in KEEP:
            return
        a = dict((k, v or "") for k, v in attrs)
        if tag in BLOCK and "p" in self.stack:
            self._close_to("p")
        if tag == "li" and self.stack and self.stack[-1] == "li":
            self._close_to("li")
        if tag == "a":
            if "a" in self.stack:
                return
            href = a.get("href", "")
            url = _url(href, self.base) if not href.startswith("mailto:") else href
            self.out.append('<a href="%s">' % xml_attr(url) if url else "<a>")
        elif tag == "img":
            src = None
            for key in ("src", "data-src", "data-lazy-src", "data-original"):
                src = _url(a.get(key), self.base)
                if src:
                    break
            if not src and a.get("srcset"):
                src = _url(a["srcset"].split(",")[0].split()[0], self.base)
            if not src or PIXEL.search(src):
                return
            if a.get("width", "").strip() in ("0", "1", "2") or \
                    a.get("height", "").strip() in ("0", "1", "2"):
                return
            self.images.append(src)
            title = a.get("title", "").strip()
            self.out.append('<img src="%s" alt="%s"%s/>'
                            % (xml_attr(src), xml_attr(a.get("alt", "")),
                               ' title="%s"' % xml_attr(title) if title else ""))
            return
        elif tag in VOID:
            self.out.append("<%s/>" % tag)
            return
        elif tag in ("td", "th"):
            span = "".join(' %s="%s"' % (k, a[k]) for k in ("colspan", "rowspan")
                           if a.get(k, "").isdigit())
            self.out.append("<%s%s>" % (tag, span))
        else:
            self.out.append("<%s>" % tag)
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if self.skip or tag in DROP:
            return
        self.handle_starttag(tag, attrs)
        tag = RENAME.get(tag, tag)
        if tag not in VOID and self.stack and self.stack[-1] == tag:
            self._close_to(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if tag in DROP:
                self.skip -= 1
            return
        tag = RENAME.get(tag, tag)
        if tag in self.stack:
            self._close_to(tag)

    def handle_data(self, data):
        if not self.skip:
            self.out.append(xml_text(data))

    def result(self):
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        s = "".join(self.out)
        s = re.sub(r"<(p|li|em|strong|a|h[234]|figcaption)>(\s|<br/>)*</\1>", "", s)
        s = re.sub(r"(<br/>\s*){3,}", "<br/><br/>", s)
        return s.strip()


def clean(markup, base=None):
    """Return (xhtml, [absolute image urls in document order])."""
    c = _Cleaner(base)
    try:
        c.feed(markup or "")
        c.close()
    except Exception:
        pass
    return c.result(), c.images


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def text(markup):
    """Plain text of a fragment, whitespace collapsed."""
    s = TAG.sub(" ", markup or "")
    return WS.sub(" ", html.unescape(s)).strip()


def excerpt(s, limit=260):
    s = WS.sub(" ", s or "").strip()
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"
