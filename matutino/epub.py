"""EPUB 3 writer (with an NCX for older readers). Standard library only.

Kavita groups the issues into one series from the belongs-to-collection
and calibre:series metadata; group-position is the issue number.
"""

import datetime
import os
import re
import time
import uuid
import zipfile

from . import i18n
from .sanitize import xml_attr as A, xml_text as T

MEDIA = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

CSS = """
body{font-family:Charter,"Iowan Old Style",Georgia,serif;line-height:1.5;margin:0 4%}
h1{font-size:1.7em;line-height:1.15;margin:.3em 0 .35em;font-weight:700}
h2,h3,h4{line-height:1.25;margin:1.2em 0 .4em}
.kicker{font-family:sans-serif;font-size:.72em;letter-spacing:.12em;text-transform:uppercase;margin:1.5em 0 0;opacity:.75}
.byline{font-size:.85em;font-style:italic;margin:0 0 1em;opacity:.8}
figure{margin:1em 0;text-align:center}
img{max-width:100%;height:auto}
figcaption{font-size:.8em;font-style:italic;opacity:.8}
blockquote{margin:1em 0;padding-left:1em;border-left:2px solid currentColor;font-style:italic}
html[dir="rtl"] blockquote{padding-left:0;border-left:0;padding-right:1em;border-right:2px solid currentColor}
.source{font-size:.8em;margin-top:2em;padding-top:.6em;border-top:1px solid currentColor;opacity:.75}
.mast{text-align:center;margin-top:2em}
.mast h1{font-size:2.4em;margin:0}
.dateline{text-align:center;font-size:.8em;letter-spacing:.1em;text-transform:uppercase;
  border-top:3px double currentColor;border-bottom:1px solid currentColor;padding:.35em 0;margin:.6em 0 1.2em}
.contents h2{font-family:sans-serif;font-size:.8em;letter-spacing:.14em;text-transform:uppercase;margin:1.4em 0 .3em}
.contents p{margin:.2em 0 .5em}
.contents a{text-decoration:none;color:inherit}
.section-title{font-size:2em;text-align:center;margin-top:30%;letter-spacing:.08em;text-transform:uppercase}
.box{margin:1.5em 0;padding:.6em 0;border-top:1px solid currentColor;border-bottom:1px solid currentColor}
.box .big{font-size:1.3em;font-weight:700;margin:.2em 0 .6em}
.box table{width:100%;border-collapse:collapse;font-size:.9em}
.box td{padding:.25em .3em;border-bottom:1px solid currentColor}
"""


def _deg(c):
    return "%d\u00b0" % int(round(c)) if c is not None else "\u2013"


def weather_xhtml(w, lang="en"):
    t, L = w["days"][0], i18n.strings(lang)
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s / %s</td><td>%s%%</td></tr>"
                   % (T(i18n.weekday(d["date"], lang)), T(i18n.weather(d.get("code"), d["desc"], lang)),
                      _deg(d["hi"]), _deg(d["lo"]), d["rain_pct"] if d["rain_pct"] is not None else "\u2013")
                   for d in w["days"])
    return ('<div class="box"><p class="kicker">%s</p><p class="big">%s, %s / %sC</p>'
            '<table>%s</table><p class="byline">%s</p></div>'
            % (T(L["forecast_for"] % w["place"]), T(i18n.weather(t.get("code"), t["desc"], lang)),
               _deg(t["hi"]), _deg(t["lo"]), rows, T(L["sun_times"] % (t["sunrise"], t["sunset"]))))


def otd_xhtml(o, date, lang="en"):
    L = i18n.strings(lang)
    items = "".join("<p><b>%d</b> \u2014 %s</p>" % (e["year"], T(e["text"])) for e in o["events"])
    return ('<div class="box"><p class="kicker">%s</p>%s<p class="byline">%s</p></div>'
            % (T(L["otd_title"] % i18n.month_day(date, lang)), items, T(L["otd_credit"])))


def long_date(date, lang="en"):
    return i18n.long_date(date, lang)


def _page(title, body, lang):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="%s" lang="%s"%s><head><meta charset="utf-8"/><title>%s</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>%s</body></html>'
            % (A(lang), A(lang), ' dir="rtl"' if i18n.direction(lang) == "rtl" else "", T(title), body))


def _byline(st, lang="en"):
    L = i18n.strings(lang)
    bits = []
    if st.get("author"):
        bits.append(T(L["by"] % st["author"]))
    if st.get("source"):
        bits.append(T(st["source"]))
    bits.append(T(L["min_read"] % st["minutes"]))
    return " · ".join(bits)


def story_xhtml(st, lang, section=None):
    # In a right-to-left paper a story keeps its feed's own direction.
    auto = ' dir="auto"' if i18n.direction(lang) == "rtl" else ""
    body = ['<article><p class="kicker">%s</p><h1%s>%s</h1><p class="byline">%s</p>'
            % (T(section or st["section"]), auto, T(st["title"]), _byline(st, lang))]
    if st["image"]:
        cap = "<figcaption>%s</figcaption>" % T(st["caption"]) if st.get("caption") else ""
        body.append('<figure><img src="%s" alt=""/>%s</figure>' % (A(st["image"]), cap))
    text = st["html"] or "<p>%s</p>" % T(st["summary"])
    body.append('<div%s>%s</div>' % (auto, text) if auto else text)
    if st["link"]:
        L = i18n.strings(lang)
        note = T(L["only_excerpt"]) + " " if st["excerpt_only"] else ""
        body.append('<p class="source">%s%s <a href="%s">%s</a></p>'
                    % (note, T(L["original"]), A(st["link"]), T(st["host"] or st["link"])))
    body.append("</article>")
    return _page(st["title"], "".join(body), lang)


def _images(issue):
    seen = []
    for sec in issue["sections"]:
        for st in sec["stories"]:
            for rel in ([st["image"]] if st["image"] else []) + re.findall(r'src="(img/[^"]+)"', st["html"]):
                if rel not in seen:
                    seen.append(rel)
    return seen


def write(issue, issue_dir, out_path):
    lang = issue.get("language") or "en"
    paper = issue["paper"]
    when = long_date(issue["date"], lang)
    L = i18n.strings(lang)
    names = {sec["name"]: i18n.section_name(sec["name"], lang, issue.get("section_labels")) for sec in issue["sections"]}
    title = "%s — %s" % (paper, when)
    uid = "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "matutino:%s:%s" % (paper, issue["date"]))
    images = [rel for rel in _images(issue) if os.path.exists(os.path.join(issue_dir, rel))]
    lead = issue["front"]["lead"]
    stories = {st["id"]: st for sec in issue["sections"] for st in sec["stories"]}
    cover_img = None
    for cand in ([stories[lead]["image"]] if lead and stories[lead]["image"] else []) + images:
        if cand.rsplit(".", 1)[-1] in ("jpg", "png"):
            cover_img = cand
            break

    manifest, spine = [], []
    tmp = out_path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/style.css", CSS)
        manifest.append(('css', 'style.css', 'text/css', ''))

        cover = ['<div class="mast"><h1>%s</h1></div><p class="dateline">%s · %s · %s</p>'
                 % (T(paper), T(when), T(L["no"] % issue["number"]), T(issue.get("edition", "")))]
        w = issue.get("weather")
        if w:
            t = w["days"][0]
            cover.append('<p class="dateline">%s: %s, %s / %sC</p>' % (
                T(w["place"]), T(i18n.weather(t.get("code"), t["desc"], lang)), _deg(t["hi"]), _deg(t["lo"])))
        if cover_img:
            cover.append('<figure><img src="%s" alt=""/></figure>' % A(cover_img))
        cover.append('<div class="contents">')
        for i, sec in enumerate(issue["sections"], 1):
            cover.append('<h2><a href="sec-%d.xhtml">%s</a></h2>' % (i, T(names[sec["name"]])))
            for st in sec["stories"]:
                cover.append('<p><a href="s-%s.xhtml">%s</a></p>' % (st["id"], T(st["title"])))
        cover.append("</div>")
        z.writestr("OEBPS/cover.xhtml", _page(title, "".join(cover), lang))
        manifest.append(("cover", "cover.xhtml", "application/xhtml+xml", ""))
        spine.append("cover")

        for i, sec in enumerate(issue["sections"], 1):
            items = "".join('<p><a href="s-%s.xhtml">%s</a></p>' % (st["id"], T(st["title"]))
                            for st in sec["stories"])
            if sec.get("box") == "weather" and issue.get("weather"):
                items = weather_xhtml(issue["weather"], lang) + items
            elif sec.get("box") == "onthisday" and issue.get("onthisday"):
                items = otd_xhtml(issue["onthisday"], issue["date"], lang) + items
            z.writestr("OEBPS/sec-%d.xhtml" % i, _page(names[sec["name"]], '<h1 class="section-title">%s</h1>'
                                                       '<div class="contents">%s</div>' % (T(names[sec["name"]]), items), lang))
            manifest.append(("sec-%d" % i, "sec-%d.xhtml" % i, "application/xhtml+xml", ""))
            spine.append("sec-%d" % i)
            for st in sec["stories"]:
                z.writestr("OEBPS/s-%s.xhtml" % st["id"], story_xhtml(st, lang, names.get(st["section"])))
                manifest.append(("s-" + st["id"], "s-%s.xhtml" % st["id"], "application/xhtml+xml", ""))
                spine.append("s-" + st["id"])

        for n, rel in enumerate(images):
            z.write(os.path.join(issue_dir, rel), "OEBPS/" + rel)
            ext = rel.rsplit(".", 1)[-1]
            iid = "cover-img" if rel == cover_img else "img%d" % n
            manifest.append((iid, rel, MEDIA[ext], "cover-image" if rel == cover_img else ""))

        nav, ncx, play = [], [], [1]

        def point(label, href, children=""):
            play[0] += 1
            return ('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                    '<content src="%s"/>%s</navPoint>' % (play[0], play[0], T(label), A(href), children))
        nav.append('<li><a href="cover.xhtml">%s</a></li>' % T(L["front_page"]))
        ncx.append(point(L["front_page"], "cover.xhtml"))
        for i, sec in enumerate(issue["sections"], 1):
            inner = "".join('<li><a href="s-%s.xhtml">%s</a></li>' % (st["id"], T(st["title"]))
                            for st in sec["stories"])
            nav.append('<li><a href="sec-%d.xhtml">%s</a>%s</li>' % (i, T(names[sec["name"]]), "<ol>%s</ol>" % inner if inner else ""))
            label, href = names[sec["name"]], "sec-%d.xhtml" % i
            play[0] += 1
            sec_no = play[0]
            kids = "".join(point(st["title"], "s-%s.xhtml" % st["id"]) for st in sec["stories"])
            ncx.append('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                       '<content src="%s"/>%s</navPoint>' % (sec_no, sec_no, T(label), href, kids))
        z.writestr("OEBPS/nav.xhtml", _page(L["contents"], (
            '<nav epub:type="toc" id="toc"><h1>%s</h1><ol>%s</ol></nav>'
            '<nav epub:type="landmarks" hidden=""><ol>'
            '<li><a epub:type="cover" href="cover.xhtml">%s</a></li>'
            '<li><a epub:type="bodymatter" href="sec-1.xhtml">%s</a></li>'
            '</ol></nav>') % (T(L["contents"]), "".join(nav), T(L["front_page"]), T(L["start"])), lang))
        manifest.append(("nav", "nav.xhtml", "application/xhtml+xml", "nav"))
        z.writestr("OEBPS/toc.ncx",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head>'
                   '<meta name="dtb:uid" content="%s"/><meta name="dtb:depth" content="2"/>'
                   '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/>'
                   '</head><docTitle><text>%s</text></docTitle><navMap>%s</navMap></ncx>'
                   % (A(uid), T(title), "".join(ncx)))
        manifest.append(("ncx", "toc.ncx", "application/x-dtbncx+xml", ""))

        n_stories = sum(len(s["stories"]) for s in issue["sections"])
        desc = "No. %d · %d stories · %s" % (issue["number"], n_stories,
                                                        ", ".join(names[s["name"]] for s in issue["sections"]))
        modified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issue.get("built_at") or time.time()))
        meta = [
            '<dc:identifier id="uid">%s</dc:identifier>' % T(uid),
            "<dc:title>%s</dc:title>" % T(title),
            "<dc:language>%s</dc:language>" % T(lang),
            "<dc:creator>%s</dc:creator>" % T(paper),
            "<dc:publisher>Matutino</dc:publisher>",
            "<dc:date>%s</dc:date>" % T(issue["date"]),
            "<dc:description>%s</dc:description>" % T(desc),
            '<meta property="dcterms:modified">%s</meta>' % modified,
            '<meta property="belongs-to-collection" id="series">%s</meta>' % T(paper),
            '<meta refines="#series" property="collection-type">series</meta>',
            '<meta refines="#series" property="group-position">%d</meta>' % issue["number"],
            '<meta name="calibre:series" content="%s"/>' % A(paper),
            '<meta name="calibre:series_index" content="%d"/>' % issue["number"],
        ]
        if cover_img:
            meta.append('<meta name="cover" content="cover-img"/>')
        items = "".join('<item id="%s" href="%s" media-type="%s"%s/>'
                        % (i, A(h), m, ' properties="%s"' % p if p else "") for i, h, m, p in manifest)
        refs = "".join('<itemref idref="%s"/>' % i for i in spine)
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="%s">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">%s</metadata>'
                   '<manifest>%s</manifest><spine toc="ncx"%s>%s</spine></package>'
                   % (A(lang), "".join(meta), items,
                      ' page-progression-direction="rtl"' if i18n.direction(lang) == "rtl" else "", refs))
    os.replace(tmp, out_path)
