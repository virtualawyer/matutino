import json
import shutil
import threading
import time
import unittest
import urllib.error
import urllib.request

from matutino import server
from matutino.server import due, next_print, slot_for

from fixtures import Fixture, temp_app

S = {"schedule_on": True, "build_time": "05:15", "timezone": "America/Costa_Rica"}
# 2026-10-11 05:15 in Costa Rica (UTC-6) is 11:15 UTC.
SLOT = 1791717300.0


class Schedule(unittest.TestCase):
    def test_slot(self):
        self.assertEqual(slot_for(S, SLOT + 3600), SLOT)

    def test_due(self):
        self.assertFalse(due(S, SLOT - 60, None, {}))                   # too early
        self.assertTrue(due(S, SLOT + 60, SLOT - 86400, {}))             # time, not yet printed
        self.assertFalse(due(S, SLOT + 60, SLOT + 30, {}))               # already printed today
        self.assertFalse(due(dict(S, schedule_on=False), SLOT + 60, None, {}))
        tries = {"slot": SLOT, "count": 1, "last": SLOT + 60}
        self.assertFalse(due(S, SLOT + 600, None, tries))                # retry waits 30 min
        self.assertTrue(due(S, SLOT + 60 + 1800, None, tries))
        self.assertFalse(due(S, SLOT + 9000, None, dict(tries, count=4)))  # gives up for the day

    def test_next_print(self):
        self.assertEqual(next_print(S, SLOT - 3600, None), "today at 5:15 a.m.")
        self.assertEqual(next_print(S, SLOT + 3600, SLOT + 60), "tomorrow at 5:15 a.m.")
        self.assertEqual(next_print(S, SLOT + 3600, SLOT - 86400), "shortly")
        self.assertIsNone(next_print(dict(S, schedule_on=False), SLOT, None))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = Fixture().__enter__()
        cls.app = temp_app()
        cls.httpd = server.make_server(cls.app, "127.0.0.1", 0)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.fx.__exit__()
        shutil.rmtree(cls.app._root, ignore_errors=True)

    def get(self, path):
        try:
            r = urllib.request.urlopen(self.base + path, timeout=30)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(self, path, body=None, ctype="application/json"):
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": ctype}, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=60)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def wait_idle(self):
        for _ in range(300):
            if not self.app.builder.busy():
                return
            time.sleep(0.1)
        self.fail("build did not finish")

    def test_1_empty_paper_and_desk(self):
        code, h, body = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Go to the desk", body)
        self.assertIn("default-src 'none'", h["Content-Security-Policy"])
        self.assertEqual(self.get("/desk")[0], 200)
        state = json.loads(self.get("/api/state")[2])
        for k in ("settings", "feeds", "feeds_text", "building", "issues", "next_build", "epub_ok"):
            self.assertIn(k, state)
        self.assertTrue(state["epub_ok"])

    def test_2_post_needs_json(self):
        code, j = self.post("/api/build", ctype="application/x-www-form-urlencoded")
        self.assertEqual(code, 415)
        self.assertFalse(self.app.builder.busy())

    def test_3_add_feeds(self):
        b = self.fx.base
        code, j = self.post("/api/feeds", {"text": "%s/site\n%s/plain\n" % (b, b), "section": "Local", "mode": "full"})
        self.assertEqual(code, 200)
        self.assertEqual(j["added"], ["Harbor Gazette"])  # discovered from the page, title shortened
        self.assertEqual(j["failed"][0]["error"], "no feed found at that address")
        code, j = self.post("/api/feeds", {"text": b + "/f/news.xml", "mode": "full"})
        self.assertEqual(j["existing"], [b + "/f/news.xml"])
        self.assertEqual(self.post("/api/feeds", {"text": "x", "mode": "loud"})[0], 400)

    def test_4_edit_feeds(self):
        b = self.fx.base
        fid = self.app.db.feed_by_url(b + "/f/news.xml")["id"]
        self.assertEqual(self.post("/api/feeds/%d" % fid, {"mode": "feed"})[0], 200)
        self.assertEqual(self.app.db.feed_by_url(b + "/f/news.xml")["mode"], "feed")
        self.assertEqual(self.post("/api/feeds/%d" % fid, {"mode": "nope"})[0], 400)
        text = "# Comics\nStrip | %s/comic.xml | headlines\n# Local\nGazette | %s/f/news.xml\n" % (b, b)
        code, j = self.post("/api/feeds/text", {"text": text})
        self.assertEqual((j["total"], j["added"], j["removed"]), (2, 1, 0))
        feeds = self.app.db.feeds()
        self.assertEqual([(f["section"], f["name"], f["mode"]) for f in feeds],
                         [("Funnies", "Strip", "feed"), ("Local News", "Gazette", "full")])
        code, j = self.post("/api/feeds/text", {"text": "# Local\n%s/f/news.xml\n%s/f/daily.atom\n" % (b, b)})
        self.assertEqual((j["total"], j["added"], j["removed"]), (2, 1, 1))
        self.assertEqual(self.app.db.feed_by_url(b + "/f/news.xml")["name"], "Gazette")  # blank keeps the name

    def test_5_settings(self):
        self.assertEqual(self.post("/api/settings", {"build_time": "5:15pm"})[0], 400)
        self.assertEqual(self.post("/api/settings", {"timezone": "Mars/Olympus"})[0], 400)
        self.assertEqual(self.post("/api/settings", {"paper_name": ""})[0], 400)
        code, _ = self.post("/api/settings", {"per_feed": 999, "keep_days": 0, "edition": "Guanacaste Edition",
                                              "schedule_on": False})
        self.assertEqual(code, 200)
        s = self.app.db.settings()
        self.assertEqual((s["per_feed"], s["keep_days"], s["edition"], s["schedule_on"]),
                         (30, 1, "Guanacaste Edition", False))
        self.post("/api/settings", {"per_feed": 5, "keep_days": 14})

    def test_6_print_and_read(self):
        code, j = self.post("/api/build")
        self.assertTrue(j["started"])
        self.wait_idle()
        report = self.app.db.get("last_report")
        self.assertTrue(report["ok"], report)
        date = report["date"]
        code, h, body = self.get("/")
        self.assertIn(b"Guanacaste Edition", body)
        self.assertEqual(self.get("/issue/%s" % date)[0], 200)  # redirected to the slash form
        iss = self.app.issue(date)
        st = iss["sections"][0]["stories"][0]
        code, h, body = self.get("/issue/%s/%s" % (date, st["id"]))
        self.assertEqual(code, 200)
        self.assertIn(b'rel="next"', body)
        img = next(s["image"] for sec in iss["sections"] for s in sec["stories"] if s["image"])
        code, h, body = self.get("/issue/%s/%s" % (date, img))
        self.assertEqual((code, h["Content-Type"]), (200, "image/png"))
        self.assertIn("immutable", h["Cache-Control"])
        code, h, body = self.get("/issue/%s/epub" % date)
        self.assertEqual(code, 200)
        self.assertIn("attachment", h["Content-Disposition"])
        self.assertEqual(body[:2], b"PK")
        self.assertEqual(self.get("/archive")[0], 200)

    def test_7_nothing_escapes_the_issue_folder(self):
        for path in ("/issue/2026-10-11/img/../../matutino.db", "/issue/2026-10-11/img/%2e%2e%2fmatutino.db",
                     "/issue/../data/matutino.db", "/issue/2026-10-11/0123456789/../epub", "/nope"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_8_scheduler_tick(self):
        self.post("/api/settings", {"schedule_on": True})
        s = self.app.db.settings()
        slot = slot_for(s, time.time() + 86400)
        self.assertTrue(self.app.tick(now=slot + 60))
        self.assertEqual(self.app.db.get("auto_tries")["count"], 1)
        self.assertFalse(self.app.tick(now=slot + 120))  # same morning: waits 30 minutes to retry


if __name__ == "__main__":
    unittest.main()


class PageScripts(unittest.TestCase):
    """The desk is one inline script: a stray escape breaks the whole page."""

    def test_inline_scripts_parse(self):
        import os, re, shutil as sh, subprocess, tempfile
        from matutino import desk, render
        node = sh.which("node")
        if not node:
            self.skipTest("node not installed")
        pages = {"desk": desk.page("test"), "paper": render.doc("t", "")}
        for name, html in pages.items():
            for i, js in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                    f.write(js)
                try:
                    r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, "%s script %d: %s" % (name, i, r.stderr))
                finally:
                    os.remove(f.name)
