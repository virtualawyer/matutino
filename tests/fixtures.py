"""A local web server that plays every outside site the tests need.

Feeds are generated per request with dates relative to the current time,
so the look-back window logic sees fresh and stale items as intended.
"""

import gzip
import json
import os
import shutil
import struct
import tempfile
import threading
import time
import zlib
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import brotli
except ImportError:
    brotli = None

from matutino import fetch

# The fixture server is on 127.0.0.1, which the local-network guard refuses
# for article pages and pictures. Tests that check the guard turn it back on.
fetch.ALLOW_PRIVATE = True


def png(w=48, h=48, seed=1):
    """A valid PNG of random-ish pixels (large enough to pass the size floor)."""
    rows, x = b"", seed
    for _ in range(h):
        row = bytearray([0])
        for _ in range(w * 3):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            row.append(x >> 16 & 0xFF)
        rows += bytes(row)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


IMAGES = {"/img/a.png": png(seed=1), "/img/b.png": png(seed=2), "/img/comic.png": png(64, 40, seed=3),
          "/img/pixel.gif": b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"}

WORDS = ("The council met on Tuesday to weigh a plan that would reshape the harbor district "
         "and its fishing docks over the next decade, residents said. ")


def article(n):
    # Distinct paragraphs: trafilatura treats repeated text as boilerplate.
    paras = "".join("<p>Paragraph %d of story %d. %s</p>" % (i, n, " ".join(
        "%s%d" % (w, i) if j % 7 == 0 else w for j, w in enumerate((WORDS * 4).split())))
        for i in range(6))
    return ("<!doctype html><html><head><title>Story %d</title>"
            '<meta property="og:image" content="/img/a.png"></head><body>'
            "<nav><a href='/'>Home</a> Menu Menu</nav><article><h1>Story number %d</h1>"
            '<p>Opening line of story %d with <a href="/related">a link</a>.</p>%s'
            '<figure><img src="/img/b.png" alt="Harbor"><figcaption>The harbor at dawn.</figcaption></figure>'
            '<p>More text after the picture. <img src="/img/pixel.gif" width="1" height="1"></p>'
            "<script>alert('x')</script><p onclick=\"steal()\">Closing paragraph %d.</p></article>"
            "<footer>Copyright</footer></body></html>" % (n, n, n, paras, n))


def rss(base):
    now = time.time()
    items = []
    for i, age in ((1, 3600), (2, 7200), (3, 10 * 86400)):
        items.append(
            "<item><title>Story %d &amp; more</title><link>%s/a/%d?utm_source=rss</link><guid>%s/a/%d</guid>"
            "<pubDate>%s</pubDate><dc:creator>Ana Ruiz</dc:creator>"
            "<description><![CDATA[<p>Summary of story %d.</p>]]></description>"
            '<media:content url="%s/img/a.png" medium="image"/></item>'
            % (i, base, i, base, i, formatdate(now - age), i, base))
    items.append("<item><title>Gone story</title><link>%s/missing</link><pubDate>%s</pubDate>"
                 "<description>Only this teaser survives&nbsp;here.</description></item>"
                 % (base, formatdate(now - 1800)))
    return ('<?xml version="1.0" encoding="utf-8"?><rss version="2.0" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">'
            "<channel><title>Harbor Gazette | Local News | Weather</title>%s</channel></rss>" % "".join(items))


def atom(base):
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5400))
    return ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Daily</title>'
            '<entry><title type="html">Atom &lt;em&gt;one&lt;/em&gt;</title>'
            '<link rel="alternate" href="%s/a/10"/><id>tag:x,1</id><updated>%s</updated>'
            "<author><name>Bo Li</name></author>"
            '<content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Inline <b>atom</b> body.</p></div></content>'
            "</entry></feed>" % (base, t))


def comic(base):
    return ('<?xml version="1.0"?><rss version="2.0"><channel><title>Comic Strip</title>'
            "<item><title>Monday strip</title><link>%s/comic/1</link><pubDate>%s</pubDate>"
            '<description>&lt;img src="%s/img/comic.png" title="The hover joke" alt="strip" /&gt;</description>'
            "</item></channel></rss>" % (base, formatdate(time.time() - 4 * 86400), base))


GEO = {"results": [
    {"name": "Tamarindo", "admin1": "Piura", "country": "Peru", "country_code": "PE", "latitude": -4.877, "longitude": -80.973},
    {"name": "Tamarindo", "admin1": "Guanacaste Province", "country": "Costa Rica", "country_code": "CR",
     "latitude": 10.29913, "longitude": -85.84107}]}


def forecast():
    import datetime
    t = datetime.date.today()
    days = [(t + datetime.timedelta(days=i)).isoformat() for i in range(4)]
    return {"daily": {"time": days, "weather_code": [95, 2, 61, 0], "temperature_2m_max": [30.1, 29.2, 29.1, 31.6],
                      "temperature_2m_min": [23.8, 23.3, 23.3, 24.4], "precipitation_probability_max": [98, 20, 86, 5],
                      "precipitation_sum": [11.6, 0.2, 3.3, 0], "wind_speed_10m_max": [10.4, 15.5, 9.6, 10.3],
                      "uv_index_max": [8.6, 8.35, 8.1, 8.3],
                      "sunrise": [d + "T05:31" for d in days], "sunset": [d + "T17:23" for d in days]}}


OTD = {"selected": [{"year": y, "text": "Event of %d (aftermath pictured)." % y,
                     "pages": [{"content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/%d" % y}}}]}
                    for y in (2002, 1987, 1984, 1968, 1958, 1910, 1899, 1852, 1811, 1634)]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8", enc=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        if enc == "gzip":
            body = gzip.compress(body)
        elif enc == "br":
            body = brotli.compress(body)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if enc:
            self.send_header("Content-Encoding", enc)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        base = "http://127.0.0.1:%d" % self.server.server_port
        p = self.path.split("?")[0]
        if p in IMAGES:
            if p == "/img/a.png":
                time.sleep(0.3)  # shared by several stories: widen the race window
            return self.send(200, IMAGES[p], "image/png" if p.endswith("png") else "image/gif")
        if p == "/ua":
            return self.send(200, self.headers.get("User-Agent", ""), "text/plain")
        if p == "/to-local":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/a/1" % self.server.server_port)
            self.end_headers()
            return
        if p == "/geo":
            return self.send(200, json.dumps(GEO), "application/json")
        if p == "/forecast":
            return self.send(200, json.dumps(forecast()), "application/json")
        if p.startswith("/otd/"):
            return self.send(200, json.dumps(OTD), "application/json")
        if p == "/f/news.xml":
            return self.send(200, rss(base), "application/rss+xml")
        if p == "/gz.xml":
            return self.send(200, rss(base), "application/rss+xml", enc="gzip")
        if p == "/br.xml" and brotli:
            return self.send(200, rss(base), "application/rss+xml", enc="br")
        if p == "/f/daily.atom":
            return self.send(200, atom(base), "application/atom+xml")
        if p == "/comic.xml":
            return self.send(200, comic(base), "application/rss+xml")
        if p == "/site":
            return self.send(200, '<html><head><link rel="alternate" type="application/rss+xml" '
                                  'href="/f/news.xml"></head><body>Hello</body></html>')
        if p == "/plain":
            return self.send(200, "<html><body>No feeds here</body></html>")
        if p == "/f/acentos.xml":
            return self.send(200, '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>'
                             '<title>Diario</title><item><title>Canción del año</title>'
                             '<link>%s/a/canción-del-año</link><pubDate>%s</pubDate>'
                             '<description>Resumen breve.</description></item></channel></rss>'
                             % (base, formatdate(time.time() - 600)), "application/rss+xml")
        if p == "/a/canci%C3%B3n-del-a%C3%B1o":
            return self.send(200, article(77))
        if p.startswith("/a/"):
            return self.send(200, article(int(p.rsplit("/", 1)[1])))
        if p.startswith("/comic/"):
            return self.send(200, "<html><body><p>Comic page</p></body></html>")
        return self.send(404, "nope")


class Fixture(object):
    def __enter__(self):
        from matutino import boxes
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        boxes.GEO_URL = self.base + "/geo?"
        boxes.FORECAST_URL = self.base + "/forecast?"
        boxes.OTD_URL = self.base + "/otd/%s/%02d/%02d"
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


class TempDir(object):
    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="matutino-test-")
        return self.path

    def __exit__(self, *a):
        shutil.rmtree(self.path, ignore_errors=True)


def temp_app(epub=True, library=False):
    """An App in a fresh temp folder (app._root); the caller removes it.

    library=True keeps printed issues in a folder of their own, the way the
    server keeps them on the media drive.
    """
    from matutino.server import App
    root = tempfile.mkdtemp(prefix="matutino-test-")
    kavita = os.path.join(root, "kavita")
    if epub:
        os.makedirs(kavita)
    app = App(os.path.join(root, "data"), kavita if epub else "",
              os.path.join(root, "media", "matutino") if library else "")
    app._root = root
    # The data boxes reach real services unless a Fixture has redirected
    # them; tests that want boxes turn these back on inside a Fixture.
    app.db.save_settings({"weather_on": False, "onthisday_on": False})
    return app
