"""Home-screen install, the reading-app catalog (OPDS) and the desktop app."""

import base64
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from matutino import desktop, i18n, opds, render, server

from fixtures import Fixture, temp_app

ATOM = "{http://www.w3.org/2005/Atom}"


def fetch(base, path, host=None, pw=None):
    req = urllib.request.Request(base + path)
    if host:
        req.add_header("Host", host)
    if pw is not None:
        req.add_header("Authorization", "Basic " + base64.b64encode(("me:" + pw).encode()).decode())
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class Served(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture().__enter__()
        cls.app = temp_app()
        b = cls.fx.base
        cls.app.add_feeds("# Front Page\n%s/f/news.xml\n# Breaking\n%s/f/daily.atom\n" % (b, b), "", "full")
        cls.app.db.save_settings({"paper_name": "La Mañana", "language": "es"})
        cls.report = cls.app.builder.run("test")
        cls.httpd = server.make_server(cls.app, "127.0.0.1", 0)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.fx.__exit__()
        shutil.rmtree(cls.app._root, ignore_errors=True)

    def test_home_screen_icon_and_manifest(self):
        code, headers, body = fetch(self.base, "/")
        page = body.decode("utf-8")
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">', page)
        self.assertIn('<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">', page)
        self.assertIn('<meta name="apple-mobile-web-app-title" content="La Mañana">', page)
        self.assertIn('class="install" type="button" hidden', page)
        self.assertIn('data-ios="%s"' % i18n.strings("es")["install_ios"], page)  # in the paper's language
        self.assertIn("manifest-src 'self'", headers["Content-Security-Policy"])
        code, headers, body = fetch(self.base, "/manifest.webmanifest")
        m = json.loads(body)
        self.assertEqual((m["name"], m["display"], m["start_url"], m["lang"]), ("La Mañana", "standalone", "/", "es"))
        self.assertEqual({i["sizes"] for i in m["icons"]}, {"192x192", "512x512"})
        self.assertTrue(any(i.get("purpose") == "maskable" for i in m["icons"]))
        for icon in m["icons"]:
            code, headers, body = fetch(self.base, icon["src"])
            self.assertEqual((code, headers["Content-Type"]), (200, "image/png"))
            self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(fetch(self.base, "/static/favicon.svg")[1]["Content-Type"], "image/svg+xml")
        self.assertEqual(fetch(self.base, "/static/../server.py")[0], 404)
        self.assertEqual(fetch(self.base, "/static/nope.png")[0], 404)

    def test_reading_app_catalog(self):
        code, headers, body = fetch(self.base, "/opds")
        self.assertEqual(code, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/atom+xml;profile=opds-catalog"))
        feed = ET.fromstring(body)
        self.assertEqual(feed.find(ATOM + "title").text, "La Mañana")
        entries = feed.findall(ATOM + "entry")
        self.assertEqual(len(entries), 1)
        date = self.report["date"]
        e = entries[0]
        self.assertEqual(e.find(ATOM + "title").text, "La Mañana — " + i18n.long_date(date, "es"))
        links = {l.get("rel"): l for l in e.findall(ATOM + "link")}
        acq = links["http://opds-spec.org/acquisition"]
        self.assertEqual((acq.get("href"), acq.get("type")), ("/issue/%s/epub" % date, "application/epub+zip"))
        code, headers, body = fetch(self.base, acq.get("href"))
        self.assertEqual((code, body[:2]), (200, b"PK"))  # the EPUB itself
        iss = self.app.issue(date)
        lead = next(st for sec in iss["sections"] for st in sec["stories"] if st["id"] == iss["front"]["lead"])
        if lead["image"]:  # the lead's picture is the cover (no picture without the full-text library)
            self.assertIn("http://opds-spec.org/image/thumbnail", links)
            code, headers, body = fetch(self.base, links["http://opds-spec.org/image"].get("href"))
            self.assertEqual(code, 200)
        else:
            self.assertNotIn("http://opds-spec.org/image", links)

    def test_catalog_in_every_language_is_valid_xml(self):
        iss = self.app.issue(self.report["date"])
        row = self.app.db.issue(self.report["date"])
        for code in i18n.LANGS:
            ET.fromstring(opds.catalog('Paper "<&>"', [(row, dict(iss, language=code))]))
        ET.fromstring(opds.catalog("Empty", []))


class Password(unittest.TestCase):
    def test_icons_are_public_the_rest_is_not(self):
        app = temp_app()
        app.password = "s3cret"
        httpd = server.make_server(app, "127.0.0.1", 0)
        base = "http://127.0.0.1:%d" % httpd.server_port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            self.assertEqual(fetch(base, "/static/apple-touch-icon.png")[0], 200)
            self.assertEqual(fetch(base, "/manifest.webmanifest")[0], 401)
            self.assertEqual(fetch(base, "/opds")[0], 401)
            self.assertEqual(fetch(base, "/opds", pw="s3cret")[0], 200)  # reading apps send Basic auth
        finally:
            httpd.shutdown()
            httpd.server_close()
            shutil.rmtree(app._root, ignore_errors=True)


class Desktop(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="matutino-desktop-")
        self.zone, self.lang = desktop.system_zone, desktop.system_language
        desktop.system_zone = lambda: "Europe/Berlin"
        desktop.system_language = lambda: "de"

    def tearDown(self):
        desktop.system_zone, desktop.system_language = self.zone, self.lang
        shutil.rmtree(self.root, ignore_errors=True)

    def test_paper_for_this_computer_only(self):
        d, books = os.path.join(self.root, "data"), os.path.join(self.root, "Documents", "Matutino")
        port = desktop.free_port()
        app, httpd = desktop.start(d, books, port)
        base = "http://127.0.0.1:%d" % port
        try:
            self.assertTrue(os.path.isdir(books))
            s = app.db.settings()
            self.assertEqual((s["timezone"], s["language"]), ("Europe/Berlin", "de"))  # a new paper follows the computer
            self.assertEqual(fetch(base, "/healthz")[0], 200)
            self.assertEqual(fetch(base, "/", host="localhost:%d" % port)[0], 200)
            # A page elsewhere that points its own name at 127.0.0.1 (DNS rebinding) gets nothing.
            self.assertEqual(fetch(base, "/api/state", host="evil.example:%d" % port)[0], 421)
            self.assertEqual(fetch(base, "/desk", host="evil.example")[0], 421)
            # The one-copy check finds this server through desktop.json.
            with open(os.path.join(d, "desktop.json"), "w") as f:
                json.dump({"port": port}, f)
            self.assertEqual(desktop.running_port(d), port)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertIsNone(desktop.running_port(d))  # stopped: start a new one...
        self.assertEqual(desktop.free_port(desktop.last_port(d)), port)  # ...on the same port, so bookmarks work
        app.db.save_settings({"language": "fr"})
        app2, httpd2 = desktop.start(d, books, desktop.free_port())  # a later start keeps the owner's choices
        httpd2.shutdown()
        httpd2.server_close()
        self.assertEqual(app2.db.settings()["language"], "fr")

    def test_login_command_and_places(self):
        self.assertEqual(desktop._launch_command()[-3:], ["-m", "matutino.desktop", "--background"])
        self.assertTrue(desktop.data_dir().endswith("Matutino"))
        self.assertTrue(desktop.books_dir().endswith(os.path.join("", "Matutino")))
        self.assertIn(desktop.free_port(), desktop.PORTS + list(range(1024, 65536)))

    def test_server_answers_any_host_unless_told(self):
        app = temp_app()
        httpd = server.make_server(app, "127.0.0.1", 0)
        base = "http://127.0.0.1:%d" % httpd.server_port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            self.assertEqual(fetch(base, "/healthz", host="paper.lan:8771")[0], 200)  # the Docker server stays open
        finally:
            httpd.shutdown()
            httpd.server_close()
            shutil.rmtree(app._root, ignore_errors=True)
