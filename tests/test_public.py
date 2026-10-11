"""What a public release needs: languages, safe fetching, password, honest defaults."""

import base64
import json
import os
import re
import shutil
import threading
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from matutino import db as dbmod, fetch, i18n, render, server

from fixtures import Fixture, temp_app


class Languages(unittest.TestCase):
    def test_dates_and_times(self):
        self.assertEqual(i18n.long_date("2026-10-11", "en"), "Sunday, October 11, 2026")
        self.assertEqual(i18n.long_date("2026-10-11", "es-CR"), "domingo, 11 de octubre de 2026")
        self.assertEqual(i18n.day_month("2026-10-11", "es"), "domingo, 11 oct")
        self.assertEqual(i18n.hm(20, 5, "en"), "8:05 p.m.")
        self.assertEqual(i18n.hm(0, 30, "es"), "12:30 a. m.")
        self.assertEqual(i18n.weather(95, "Thunderstorms", "es"), "Tormentas")
        self.assertEqual(i18n.weather(95, "Thunderstorms", "en"), "Thunderstorms")
        self.assertEqual(set(i18n.STRINGS["en"]), set(i18n.STRINGS["es"]))  # no label missing in either

    def test_spanish_paper_and_book(self):
        with Fixture() as fx:
            app = temp_app()
            try:
                app.save_settings({"language": "es"})
                app.add_feeds("%s/f/news.xml\n# Comics\n%s/comic.xml headlines\n" % (fx.base, fx.base), "", "full")
                r = app.builder.run("test")
                iss = app.issue(r["date"])
                page = render.front_page(iss, "UTC")
                for word in ("Seguir leyendo", "Volver arriba", "min de lectura", "Descargar EPUB", 'lang="es"'):
                    self.assertIn(word, page)
                for word in ("Continue reading", "Back to top", "min read"):
                    self.assertNotIn(word, page)
                art = render.article_page(iss, iss["sections"][0]["stories"][0], "UTC")
                self.assertIn("Portada", art)
                z = zipfile.ZipFile(r["kavita"]["path"])
                for name in z.namelist():
                    if name.endswith((".xhtml", ".opf", ".ncx")):
                        ET.fromstring(z.read(name))  # translated labels stay well-formed XML
                self.assertIn("Contenido", z.read("OEBPS/nav.xhtml").decode("utf-8"))
            finally:
                shutil.rmtree(app._root, ignore_errors=True)


class LocalNetworkGuard(unittest.TestCase):
    def setUp(self):
        fetch.ALLOW_PRIVATE = False

    def tearDown(self):
        fetch.ALLOW_PRIVATE = True

    def test_private_addresses(self):
        for url in ("http://127.0.0.1/", "http://192.168.1.1/admin", "http://10.0.0.8/", "http://[::1]/",
                    "http://169.254.169.254/latest/meta-data", "http://localhost/"):
            self.assertFalse(fetch.is_public(url), url)

    def test_feed_content_cannot_reach_the_lan(self):
        with Fixture() as fx:
            with self.assertRaises(fetch.FetchError) as cm:
                fetch.get(fx.base + "/a/1", public_only=True)
            self.assertIn("public", str(cm.exception))
            self.assertTrue(fetch.get(fx.base + "/f/news.xml")[2])  # a feed you add yourself may be local

    def test_redirects_are_checked_too(self):
        class Req(object):
            public_only = True
        with self.assertRaises(fetch.FetchError):
            fetch._Guard().redirect_request(Req(), None, 302, "Found", {}, "http://10.1.2.3/secret")


class UserAgent(unittest.TestCase):
    def tearDown(self):
        fetch.use_browser_ua(False)

    def test_honest_by_default_browser_on_request(self):
        with Fixture() as fx:
            self.assertTrue(fetch.get(fx.base + "/ua")[2].decode().startswith("Matutino/"))
            app = temp_app()
            try:
                app.save_settings({"browser_ua": True})
                self.assertIn("Chrome/", fetch.get(fx.base + "/ua")[2].decode())
                app.save_settings({"browser_ua": False})
                self.assertTrue(fetch.get(fx.base + "/ua")[2].decode().startswith("Matutino/"))
            finally:
                shutil.rmtree(app._root, ignore_errors=True)


class Defaults(unittest.TestCase):
    def test_neutral(self):
        d = dbmod.DEFAULTS
        self.assertEqual(d["weather_place"], "")
        self.assertIsNone(d["weather_lat"])
        self.assertFalse(d["browser_ua"])
        self.assertNotIn("Puerto Rico News", d["sections"])
        self.assertEqual(dbmod._system_zone(), os.environ.get("TZ") if os.environ.get("TZ") else "UTC")

    def test_no_weather_without_a_place(self):
        with Fixture() as fx:
            app = temp_app()
            try:
                app.db.save_settings({"weather_on": True})
                app.add_feeds(fx.base + "/f/news.xml", "", "full")
                r = app.builder.run("test")
                self.assertTrue(r["ok"])
                self.assertIn("no place", r["boxes"]["weather"])
                self.assertIsNone(app.issue(r["date"])["weather"])
            finally:
                shutil.rmtree(app._root, ignore_errors=True)


class Password(unittest.TestCase):
    def test_whole_site_behind_one_password(self):
        app = temp_app()
        app.password = "s3cret"
        httpd = server.make_server(app, "127.0.0.1", 0)
        base = "http://127.0.0.1:%d" % httpd.server_port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def get(path, pw=None):
            req = urllib.request.Request(base + path)
            if pw is not None:
                req.add_header("Authorization", "Basic " + base64.b64encode(("me:" + pw).encode()).decode())
            try:
                return urllib.request.urlopen(req, timeout=10).status
            except urllib.error.HTTPError as e:
                return e.code
        try:
            self.assertEqual(get("/"), 401)
            self.assertEqual(get("/desk", "wrong"), 401)
            self.assertEqual(get("/api/state", "s3cret"), 200)
            self.assertEqual(get("/healthz"), 200)  # Docker's health check needs no password
            req = urllib.request.Request(base + "/api/build", b"{}", {"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(cm.exception.code, 401)
        finally:
            httpd.shutdown()
            httpd.server_close()
            shutil.rmtree(app._root, ignore_errors=True)


class SourceLink(unittest.TestCase):
    def test_footer_offers_the_source(self):
        saved = render.PROJECT_URL
        render.PROJECT_URL = "https://example.org/matutino"
        try:
            L = i18n.strings("en")
            self.assertIn('href="https://example.org/matutino"', render._source_link(L))
            self.assertIn("AGPL", render._source_link(L))
        finally:
            render.PROJECT_URL = saved


if __name__ == "__main__":
    unittest.main()
