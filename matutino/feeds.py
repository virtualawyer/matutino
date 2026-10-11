"""Feed parsing (RSS 2.0, RSS 1.0/RDF, Atom), feed discovery, paste parsing.

ElementTree is strict, and real feeds are not: undeclared HTML entities
(&nbsp;) and bare ampersands are common. parse() retries once after
repairing those before giving up.
"""

import calendar
import html
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_tz, mktime_tz
from html.entities import name2codepoint
from urllib.parse import urljoin, urlsplit

from . import fetch
from .sanitize import text, BAD_XML


class FeedError(Exception):
    pass


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _ns(tag):
    return tag[1:].split("}", 1)[0] if isinstance(tag, str) and tag.startswith("{") else ""


def _inner(el):
    """Text of an element; xhtml children serialized back to markup."""
    if el is None:
        return ""
    if len(el):
        parts = [el.text or ""]
        for child in el:
            s = ET.tostring(child, encoding="unicode")
            parts.append(re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", re.sub(r"<(/?)\w+:", r"<\1", s)))
        return "".join(parts)
    return el.text or ""


ISO = re.compile(r"(\d{4})-(\d\d)-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d)(?:\.\d+)?)?)?"
                 r"\s*(Z|[+-]\d\d:?\d\d)?", re.I)


def parse_date(s):
    """Epoch seconds from RFC 822 or ISO 8601, or None."""
    s = (s or "").strip()
    if not s:
        return None
    t = parsedate_tz(s)
    if t:
        try:
            return float(mktime_tz(t))
        except (OverflowError, ValueError):
            return None
    m = ISO.match(s)
    if not m:
        return None
    y, mo, d, hh, mm, ss, tz = m.groups()
    try:
        ts = calendar.timegm((int(y), int(mo), int(d), int(hh or 0), int(mm or 0),
                              int(ss or 0), 0, 0, 0))
    except (ValueError, OverflowError):
        return None
    if tz and tz.upper() != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        ts -= sign * (int(digits[:2]) * 3600 + int(digits[2:4]) * 60)
    return float(ts)


XML_ENTS = {"amp", "lt", "gt", "quot", "apos"}


def _repair(data):
    s = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    s = re.sub(r"^\s*<\?xml[^>]*\?>", "", s.lstrip("\ufeff \r\n\t"))
    s = BAD_XML.sub("", s)

    def ent(m):
        name = m.group(1)
        if name in XML_ENTS:
            return m.group(0)
        cp = name2codepoint.get(name)
        return "&#%d;" % cp if cp else "&amp;" + name + ";"
    s = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", ent, s)
    s = re.sub(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#\d+|#x[0-9A-Fa-f]+);)", "&amp;", s)
    # A tag that lost its ">" before CDATA: <content:encoded<![CDATA[ (jpl.nasa.gov)
    s = re.sub(r"<([A-Za-z_][\w:.-]*)<!\[CDATA\[", r"<\1><![CDATA[", s)
    # Attributes run together, "a"b="c" (science.nasa.gov); inside tags only.
    s = re.sub(r"<[A-Za-z_][^<>]*>",
               lambda m: re.sub(r'"(?=[A-Za-z_][\w:.-]*=["\'])', '" ', m.group(0)), s)
    return s


def _root(data):
    if isinstance(data, bytes):
        data = data.lstrip(b"\xef\xbb\xbf \r\n\t")
    if re.search(rb"<!ENTITY" if isinstance(data, bytes) else r"<!ENTITY", data):
        raise FeedError("feed declares entities; refused")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        try:
            return ET.fromstring(_repair(data))
        except ET.ParseError as e:
            raise FeedError("not a readable feed (%s)" % str(e)[:60])


def _image_of(el):
    """Best image URL attached to an item element (media, enclosure)."""
    best = None
    for c in el.iter():
        name = _local(c.tag)
        if name == "content" and _ns(c.tag).startswith("http://search.yahoo.com/mrss"):
            url = c.get("url")
            medium = (c.get("medium") or "").lower()
            typ = (c.get("type") or "").lower()
            if url and (medium == "image" or typ.startswith("image/") or
                        (not medium and not typ and re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", url, re.I))):
                return url
        elif name == "thumbnail" and c.get("url") and not best:
            best = c.get("url")
        elif name == "enclosure" and (c.get("type") or "").lower().startswith("image/"):
            return c.get("url")
        elif name == "link" and c.get("rel") == "enclosure" and \
                (c.get("type") or "").lower().startswith("image/"):
            return c.get("href")
        elif name == "image" and c.get("href") and not best:  # itunes:image
            best = c.get("href")
    return best


def parse(data, base_url=""):
    """Parse feed bytes into {"title", "items": [...]} or raise FeedError."""
    root = _root(data)
    kind = _local(root.tag)
    if kind not in ("rss", "feed", "rdf"):
        raise FeedError("not a feed (got <%s>)" % kind)
    title = ""
    for el in root.iter():
        if _local(el.tag) == "title":
            title = text(_inner(el))
            break
    items = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("item", "entry"):
            continue
        it = {"title": "", "link": "", "guid": "", "published": None, "author": "",
              "summary": "", "content": "", "image": _image_of(el)}
        for c in el:
            n = _local(c.tag)
            ns = _ns(c.tag)
            if n == "title":
                it["title"] = text(_inner(c))
            elif n == "link":
                href = c.get("href")
                if href is not None:
                    if c.get("rel", "alternate") == "alternate" and not it["link"]:
                        it["link"] = href
                elif (c.text or "").strip():
                    it["link"] = c.text.strip()
            elif n in ("guid", "id"):
                it["guid"] = (c.text or "").strip()
            elif n in ("pubdate", "published", "issued", "date") or \
                    (n == "updated" and not it["published"]) or \
                    (n == "modified" and not it["published"]):
                it["published"] = parse_date(c.text) or it["published"]
            elif n in ("creator", "author"):
                name_el = [g for g in c if _local(g.tag) == "name"]
                who = (name_el[0].text if name_el else c.text) or ""
                m = re.search(r"\(([^)]+)\)", who)
                it["author"] = text(m.group(1) if m else who)
            elif n in ("description", "summary"):
                # ElementTree has already decoded escaped markup; unescaping
                # again would turn a literal "&lt;" in the text into a tag.
                it["summary"] = _inner(c)
            elif n == "encoded" or (n == "content" and not ns.startswith("http://search.yahoo.com")):
                it["content"] = _inner(c)
        if it["link"]:
            it["link"] = urljoin(base_url, it["link"])
        if it["image"]:
            it["image"] = urljoin(it["link"] or base_url, it["image"])
        if not it["guid"]:
            it["guid"] = it["link"] or it["title"]
        if it["title"] or it["link"]:
            if not it["title"]:
                it["title"] = text(it["summary"])[:90] or it["link"]
            items.append(it)
    return {"title": title, "items": items}


FEED_TYPES = {"application/rss+xml", "application/atom+xml", "application/rdf+xml",
              "application/xml", "text/xml", "application/x-rss+xml"}


def looks_like_feed(ctype, body):
    head = body[:2500].lstrip().lower()
    if b"<html" in head:
        return False
    return b"<rss" in head or b"<feed" in head or b"<rdf:rdf" in head or ctype in FEED_TYPES


def short_title(t):
    """'The Tico Times | Costa Rica News | Travel' -> 'The Tico Times'."""
    head = re.split(r"\s+[|\u2013\u2014\u00b7-]\s+", t or "")[0].strip()
    return (head if len(head) >= 3 else (t or "").strip())[:80]


ALT = re.compile(r"<link\b[^>]*>", re.I)


def find_alternates(page, base):
    out = []
    for tag in ALT.findall(page):
        low = tag.lower()
        if "alternate" in low and ("rss+xml" in low or "atom+xml" in low):
            m = re.search(r'href\s*=\s*["\']([^"\']+)["\']', tag, re.I)
            if m:
                out.append(urljoin(base, html.unescape(m.group(1))))
    return out


def discover(url):
    """Resolve a pasted address to (feed_url, feed_title) or raise FeedError.

    A page address works too: its <link rel="alternate"> feed is used, then
    a few common feed paths are tried.
    """
    try:
        final, ctype, body = fetch.get(url, max_bytes=6000000)
    except fetch.FetchError as e:
        raise FeedError(str(e))
    if looks_like_feed(ctype, body):
        return final, short_title(parse(body, final)["title"])
    page = body.decode("utf-8", "replace")
    p = urlsplit(final)
    root = "%s://%s" % (p.scheme, p.netloc)
    candidates = find_alternates(page, final) + [
        root + s for s in ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml")]
    seen = set()
    for cand in candidates:
        if cand in seen or len(seen) >= 6:
            continue
        seen.add(cand)
        try:
            f2, c2, b2 = fetch.get(cand, max_bytes=6000000)
            if looks_like_feed(c2, b2):
                return f2, short_title(parse(b2, f2)["title"])
        except (fetch.FetchError, FeedError):
            continue
    raise FeedError("no feed found at that address")


URL = re.compile(r"""https?://[^\s'"<>|]+""", re.I)
BARE = re.compile(r"""(?<![\w@/.])((?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s'"<>|]*)?)""", re.I)
# "# World" names a section; a longer "#" line with sentence punctuation is a
# comment, and so is a "#" line holding an address (a feed switched off).
HASH_SECTION = re.compile(r"^#+\s*([^.,;:!?()]{1,40}?)\s*$")
SECTION = [HASH_SECTION,
           re.compile(r"^\[\s*(.+?)\s*\]$"),
           re.compile(r"""^\(?\s*['"]([^'"]{1,60})['"]\s*[:,]\s*[\[(]?\s*$"""),
           re.compile(r"^([^:/\[\](){}=]{1,60}):$")]
HEADLINES = re.compile(r"\b(feed|headlines?|summary|summaries)\b", re.I)


def parse_paste(textblock, section="", mode="full"):
    """Turn pasted text into [{"section","name","url","mode"}].

    Accepts one address per line, "Name | url | headlines", calibre-recipe
    tuples like ('xkcd', 'https://xkcd.com/rss.xml', 'feed'), and section
    lines ("# World", "[World]", "World:").
    """
    out = []
    current = (section or "").strip()
    for raw in (textblock or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            h = HASH_SECTION.match(line)
            if h and not URL.search(line):
                current = h.group(1).strip()
            continue
        m = URL.search(line)
        if not m:
            b = BARE.search(line)
            if b and not line.startswith("#"):
                m, url = b, "https://" + b.group(1)
            else:
                for pat in SECTION:
                    s = pat.match(line)
                    if s:
                        current = s.group(1).strip(" '\"")
                        break
                continue
        else:
            url = m.group(0)
        url = url.rstrip(".,;)]'\"")
        name = line[:m.start()].strip(" \t'\"()[],|=:-\u2013\u2014")
        after = line[m.end():]
        out.append({
            "section": current or "News",
            "name": name,
            "url": url,
            "mode": "feed" if HEADLINES.search(after) else mode,
        })
    return out


def as_text(feeds):
    """Inverse of parse_paste, for the desk's edit-as-text view."""
    lines, last = [], None
    for f in feeds:
        if f["section"] != last:
            if lines:
                lines.append("")
            lines.append("# " + f["section"])
            last = f["section"]
        parts = [f["name"]] if f["name"] else []
        parts.append(f["url"])
        if f["mode"] == "feed":
            parts.append("headlines")
        lines.append(" | ".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")
