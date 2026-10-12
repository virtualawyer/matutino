"""A reading-app catalog (OPDS 1.2) of the issues on file, and the web-app manifest.

Apps such as Librera, Readest and KOReader subscribe to /opds once; every
issue then shows up in them as an EPUB to download, newest first.
"""

import json
import time
from xml.sax.saxutils import escape

from . import i18n

ACQ = "application/atom+xml;profile=opds-catalog;kind=acquisition"
IMG = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}


def _t(s):
    return escape(s or "", {'"': "&quot;"})


def _when(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts or 0))


def catalog(paper, editions):
    """editions: [(row, issue)] newest first; row has date, number, built_at."""
    entries = []
    for row, issue in editions:
        lang = issue.get("language") or "en"
        L = i18n.strings(lang)
        date = row["date"]
        total = sum(len(s["stories"]) for s in issue["sections"])
        stories = {st["id"]: st for sec in issue["sections"] for st in sec["stories"]}
        lead = stories.get(issue["front"]["lead"]) if issue["front"].get("lead") else None
        links = ['<link rel="http://opds-spec.org/acquisition" href="/issue/%s/epub" type="application/epub+zip"/>' % date,
                 '<link rel="alternate" href="/issue/%s/" type="text/html"/>' % date]
        if lead and lead.get("image"):
            ext = lead["image"].rsplit(".", 1)[-1]
            if ext in IMG:
                href = "/issue/%s/%s" % (date, lead["image"])
                links += ['<link rel="http://opds-spec.org/image" href="%s" type="%s"/>' % (_t(href), IMG[ext]),
                          '<link rel="http://opds-spec.org/image/thumbnail" href="%s" type="%s"/>' % (_t(href), IMG[ext])]
        entries.append(
            "<entry><title>%s</title><id>urn:matutino:%s:%s</id><updated>%s</updated>"
            "<author><name>%s</name></author><dc:language>%s</dc:language><dc:issued>%s</dc:issued>"
            "<summary>%s</summary>%s</entry>"
            % (_t("%s — %s" % (issue["paper"], i18n.long_date(date, lang))), _t(issue["paper"]), date,
               _when(row["built_at"]), _t(issue["paper"]), _t(lang), date,
               _t("%s, %s" % (L["no"] % row["number"], L["n_stories"] % total)), "".join(links)))
    updated = _when(editions[0][0]["built_at"] if editions else time.time())
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/" '
            'xmlns:opds="http://opds-spec.org/2010/catalog">'
            "<id>urn:matutino:%s</id><title>%s</title><updated>%s</updated><author><name>Matutino</name></author>"
            '<link rel="self" href="/opds" type="%s"/><link rel="start" href="/opds" type="%s"/>%s</feed>'
            % (_t(paper), _t(paper), updated, ACQ, ACQ, "".join(entries)))


def manifest(paper, lang="en"):
    return json.dumps({
        "name": paper, "short_name": paper, "start_url": "/", "scope": "/", "id": "/",
        "display": "standalone", "background_color": "#f5f1e8", "theme_color": "#f5f1e8",
        "lang": i18n.lang_of(lang), "dir": i18n.direction(lang),
        "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
                   "purpose": "maskable"}],
    }, ensure_ascii=False)
