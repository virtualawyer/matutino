import json
import os
import re
import shutil
import time
import unittest
import xml.etree.ElementTree as ET
import zipfile

from matutino import build, extract, fetch
from matutino.build import canonical, feed_cutoff, pick, sniff

from fixtures import Fixture, temp_app, brotli


def item(link, published=None, guid=None):
    return {"link": link, "guid": guid or link, "published": published, "title": link,
            "summary": "", "content": "", "author": "", "image": None}


class Selection(unittest.TestCase):
    def test_window_seen_and_limit(self):
        now = 10000000.0
        items = [item("https://a/%d" % i, now - i * 3600) for i in range(1, 8)]
        seen = {build.story_key(items[0])}
        got = pick(items, seen, now - 5.5 * 3600, 3)
        self.assertEqual([i["link"] for i in got], ["https://a/2", "https://a/3", "https://a/4"])

    def test_todays_stories_survive_a_rebuild(self):
        now = 10000000.0
        old = item("https://a/old", now - 100 * 3600)
        got = pick([old], set(), now - 36 * 3600, 5, today={build.story_key(old)})
        self.assertEqual(got, [old])

    def test_undated_stop_at_first_printed(self):
        items = [item("https://a/new"), item("https://a/printed"), item("https://a/older")]
        got = pick(items, {build.story_key(items[1])}, 0, 5)
        self.assertEqual([i["link"] for i in got], ["https://a/new"])

    def test_cutoff(self):
        now, day = 10000000.0, 86400
        w = 36 * 3600
        self.assertEqual(feed_cutoff({"added": 1}, now, w, None), now - 7 * day)       # first issue
        self.assertEqual(feed_cutoff({"added": now - 60}, now, w, now - day), now - 7 * day)  # new feed
        self.assertEqual(feed_cutoff({"added": 1}, now, w, now - day), now - w)        # normal day
        self.assertEqual(feed_cutoff({"added": 1}, now, w, now - 3 * day), now - 3 * day - 6 * 3600)  # box was off
        self.assertEqual(feed_cutoff({"added": 1}, now, w, now - 30 * day), now - 7 * day)  # capped

    def test_strip_feed_name(self):
        self.assertEqual(build.strip_feed_name("Saturday Morning Breakfast Cereal - Blog",
                                               "Saturday Morning Breakfast Cereal"), "Blog")
        self.assertEqual(build.strip_feed_name("Blog", "Saturday Morning Breakfast Cereal"), "Blog")
        self.assertEqual(build.strip_feed_name("NPR: a story", "NPR"), "NPR: a story")  # too short to trust

    def test_canonical_and_sniff(self):
        self.assertEqual(canonical("HTTPS://Ex.com/a?utm_source=x&id=2&fbclid=9#top"), "https://ex.com/a?id=2")
        self.assertEqual(sniff(b"\xff\xd8\xff\xe0"), "jpg")
        self.assertEqual(sniff(b"RIFF1234WEBPVP8 "), "webp")
        self.assertIsNone(sniff(b"<svg xmlns="))


def check_epub(tc, path):
    z = zipfile.ZipFile(path)
    first = z.infolist()[0]
    tc.assertEqual(first.filename, "mimetype")
    tc.assertEqual(first.compress_type, zipfile.ZIP_STORED)
    tc.assertEqual(z.read("mimetype"), b"application/epub+zip")
    ET.fromstring(z.read("META-INF/container.xml"))
    ns = {"o": "http://www.idpf.org/2007/opf"}
    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    names = set(z.namelist())
    ids = {}
    for it in opf.find("o:manifest", ns):
        href = "OEBPS/" + it.get("href")
        tc.assertIn(href, names)
        ids[it.get("id")] = it
        if it.get("media-type") == "application/xhtml+xml":
            ET.fromstring(z.read(href))  # every page must be well-formed XML
    for ref in opf.find("o:spine", ns):
        tc.assertIn(ref.get("idref"), ids)
    tc.assertTrue(any("nav" in (i.get("properties") or "") for i in ids.values()))
    ET.fromstring(z.read("OEBPS/toc.ncx"))
    return z, opf


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture().__enter__()
        self.app = temp_app()
        b = self.fx.base
        self.app.add_feeds("# Local\n%s/f/news.xml\n%s/f/daily.atom\n# Comics\n%s/comic.xml headlines\n"
                           "# Broken\n%s/dead.xml\n" % (b, b, b, b), "", "full")
        # the dead feed is refused at add time; put it in directly to test a failing feed
        self.app.db.add_feed("Broken", "Dead", b + "/dead.xml", "full")

    def tearDown(self):
        self.fx.__exit__()
        shutil.rmtree(self.app._root, ignore_errors=True)

    def issue(self):
        return self.app.issue(self.app.latest_date())

    def test_build_end_to_end(self):
        r = self.app.builder.run("test")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["failed"], 1)
        dead = [f for s in r["sections"] for f in s["feeds"] if f["error"]]
        self.assertEqual(dead[0]["error"], "HTTP 404")
        iss = self.issue()
        stories = [st for sec in iss["sections"] for st in sec["stories"]]
        titles = sorted(st["title"] for st in stories)
        # Story 3 is ten days old: outside even the first issue's one-week reach.
        self.assertEqual(titles, ["Atom one", "Gone story", "Monday strip", "Story 1 & more", "Story 2 & more"])
        self.assertEqual([s["name"] for s in iss["sections"]], ["Local News", "Funnies"])  # "# Local", "# Comics"
        for st in stories:
            self.assertNotIn("<script", st["html"])
            self.assertNotIn("onclick", st["html"])
            self.assertIsNone(re.search(r'src="http', st["html"]), st["title"])  # all images local
            for rel in re.findall(r'src="(img/[^"]+)"', st["html"]) + ([st["image"]] if st["image"] else []):
                self.assertTrue(os.path.exists(os.path.join(self.app.builder.issues_dir, iss["date"], rel)))
        s1 = next(st for st in stories if st["title"].startswith("Story 1"))
        self.assertGreater(s1["words"], 300 if extract.AVAILABLE else 2)
        self.assertEqual(s1["author"], "Ana Ruiz")
        self.assertTrue(s1["image"])
        self.assertNotIn("Menu Menu", s1["html"])  # page chrome is not the story
        s2 = next(st for st in stories if st["title"].startswith("Story 2"))
        self.assertEqual(s2["image"], s1["image"])  # shared picture reaches both stories
        gone = next(st for st in stories if st["title"] == "Gone story")
        self.assertTrue(gone["excerpt_only"])
        self.assertIn("teaser", gone["html"])
        strip = next(st for st in stories if st["title"] == "Monday strip")
        self.assertEqual(strip["caption"], "The hover joke")
        self.assertTrue(strip["image"])
        self.assertEqual(strip["html"], "")  # the strip is the lead image, not repeated in the body
        self.assertIn(iss["front"]["lead"], [st["id"] for st in stories if st["mode"] == "full"])

    def test_epub_is_valid_and_filed_for_kavita(self):
        r = self.app.builder.run("test")
        path = r["kavita"]["path"]
        z, opf = check_epub(self, path)
        # Kept only in Kavita's folder: no second copy beside the issue.
        self.assertEqual([n for n in os.listdir(self.app.builder.issues_dir) if n.endswith(".epub")], [])
        self.assertFalse(os.path.exists(os.path.join(self.app.builder.issues_dir, r["date"], "issue.epub")))
        meta = ET.tostring(opf, encoding="unicode")
        self.assertIn("belongs-to-collection", meta)
        self.assertIn('content="The Morning Paper"', meta)
        self.assertIn('properties="cover-image"', meta)
        self.assertTrue(r["kavita"]["path"].endswith("The Morning Paper - %s.epub" % r["date"]))
        self.assertTrue(os.path.exists(r["kavita"]["path"]))

    def test_unmounted_kavita_folder_is_not_written(self):
        r = self.app.builder.run("test")
        folder = os.path.dirname(r["kavita"]["path"])
        shutil.rmtree(folder)  # what an unmounted drive looks like from here
        r2 = self.app.builder.run("test")
        self.assertIn("mounted", r2["kavita"]["error"])
        self.assertFalse(os.path.exists(folder))

    def test_renaming_the_paper_keeps_the_kavita_folder(self):
        r1 = self.app.builder.run("test")
        folder = os.path.dirname(r1["kavita"]["path"])
        self.assertEqual(os.path.basename(folder), "The Morning Paper")
        self.app.save_settings({"paper_name": "The Evening Post", "keep_days": 1})
        stale = os.path.join(folder, "The Morning Paper - 2020-01-01.epub")
        open(stale, "w").close()
        r2 = self.app.builder.run("test")
        self.assertEqual(r2["kavita"]["path"], os.path.join(folder, "The Evening Post - %s.epub" % r2["date"]))
        self.assertFalse(os.path.exists(stale))  # old-name issues are still pruned
        self.assertEqual(os.listdir(os.path.dirname(folder)), ["The Morning Paper"])

    def test_rebuild_same_day_reprints_and_next_day_finds_nothing_new(self):
        first = self.app.builder.run("test")
        again = self.app.builder.run("test")
        self.assertEqual(again["stories"], first["stories"])
        self.assertEqual(again["number"], first["number"])
        later = self.app.builder.run("test", now=time.time() + 86400)
        self.assertTrue(later["ok"])
        self.assertIn("No new stories", later["message"])
        self.assertEqual(len(self.app.db.issues()), 1)  # an empty day prints nothing

    def test_retention_prunes_old_issues(self):
        old = os.path.join(self.app.builder.issues_dir, "2020-01-01")
        os.makedirs(old)
        stray = os.path.join(self.app.builder.issues_dir, "2020-01-03.epub")
        open(stray, "w").close()
        stale_tmp = os.path.join(self.app.builder.issues_dir, "2020-01-02.tmp")
        os.makedirs(stale_tmp)
        self.app.builder.run("test")
        self.assertFalse(os.path.exists(old))
        self.assertFalse(os.path.exists(stale_tmp))
        self.assertFalse(os.path.exists(stray))

    def test_no_feeds_is_a_clear_failure(self):
        for f in self.app.db.feeds():
            self.app.db.delete_feed(f["id"])
        r = self.app.builder.run("test")
        self.assertFalse(r["ok"])
        self.assertIn("No feeds", r["error"])


class SpanishAndFailures(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture().__enter__()
        self.app = temp_app()

    def tearDown(self):
        self.fx.__exit__()
        shutil.rmtree(self.app._root, ignore_errors=True)

    def test_accented_article_address_is_fetched(self):
        self.app.add_feeds("# Local News\n%s/f/acentos.xml\n" % self.fx.base, "", "full")
        r = self.app.builder.run("test")
        self.assertTrue(r["ok"], r)
        st = self.app.issue(r["date"])["sections"][0]["stories"][0]
        self.assertEqual(st["title"], "Canci\u00f3n del a\u00f1o")
        self.assertEqual(st["excerpt_only"], not extract.AVAILABLE)  # fetched, not an error fallback
        self.assertGreater(st["words"], 300 if extract.AVAILABLE else 1)

    def test_one_broken_story_does_not_sink_the_issue(self):
        self.app.add_feeds("%s/f/news.xml\n" % self.fx.base, "", "full")
        real = self.app.builder._set_story

        def flaky(feed, it, key, tmp):
            if it["title"].startswith("Story 2"):
                raise UnicodeEncodeError("ascii", "a\u00f1o", 1, 2, "ordinal not in range(128)")
            return real(feed, it, key, tmp)
        self.app.builder._set_story = flaky
        r = self.app.builder.run("test")
        self.assertTrue(r["ok"], r)
        stories = {st["title"]: st for sec in self.app.issue(r["date"])["sections"] for st in sec["stories"]}
        self.assertEqual(len(stories), 3)
        self.assertTrue(stories["Story 2 & more"]["excerpt_only"])
        self.assertIn("Summary of story 2", stories["Story 2 & more"]["html"])
        self.assertEqual(stories["Story 1 & more"]["excerpt_only"], not extract.AVAILABLE)


class Library(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture().__enter__()
        self.app = temp_app(library=True)
        self.app.add_feeds("%s/f/news.xml\n" % self.fx.base, "", "full")

    def tearDown(self):
        self.fx.__exit__()
        shutil.rmtree(self.app._root, ignore_errors=True)

    def test_issues_live_in_their_own_folder(self):
        r = self.app.builder.run("test")
        self.assertTrue(r["ok"], r)
        lib = os.path.join(self.app._root, "media", "matutino")
        self.assertTrue(os.path.exists(os.path.join(lib, r["date"], "issue.json")))
        self.assertTrue(os.path.exists(os.path.join(lib, ".matutino-library")))
        self.assertFalse(os.path.exists(os.path.join(self.app.data_dir, "issues", r["date"])))

    def test_unmounted_library_refuses_to_print(self):
        self.app.builder.run("test")
        lib = self.app.builder.issues_dir
        shutil.rmtree(lib)
        os.makedirs(lib)  # the empty mount point an unplugged drive leaves behind
        r = self.app.builder.run("test")
        self.assertFalse(r["ok"])
        self.assertIn("mounted", r["error"])
        self.assertEqual(os.listdir(lib), [])

    def test_low_disk_prints_without_pictures(self):
        saved = build.LOW_DISK
        build.LOW_DISK = 1 << 62
        try:
            r = self.app.builder.run("test")
        finally:
            build.LOW_DISK = saved
        self.assertTrue(r["ok"], r)
        self.assertIn("without pictures", r["warning"])
        iss = self.app.issue(r["date"])
        self.assertTrue(all(st["image"] is None for sec in iss["sections"] for st in sec["stories"]))
        self.assertEqual(os.listdir(os.path.join(self.app.builder.issues_dir, r["date"], "img")), [])


class Fetching(unittest.TestCase):
    def test_iri_to_uri(self):
        self.assertEqual(fetch.iri_to_uri("https://dw.com/es/el-a\u00f1o?q=caf\u00e9#x"),
                         "https://dw.com/es/el-a%C3%B1o?q=caf%C3%A9#x")
        self.assertEqual(fetch.iri_to_uri("https://\u00f1and\u00fa.cr/a"), "https://xn--and-6ma2c.cr/a")
        self.assertEqual(fetch.iri_to_uri("https://ex.com/ok%20done?a=1&b=2"), "https://ex.com/ok%20done?a=1&b=2")

    def test_gzip_and_brotli_bodies(self):
        with Fixture() as fx:
            _, _, body = fetch.get(fx.base + "/gz.xml")
            self.assertTrue(body.lstrip().startswith(b"<?xml"))
            if brotli is not None:
                _, _, body = fetch.get(fx.base + "/br.xml")
                self.assertTrue(body.lstrip().startswith(b"<?xml"))

    def test_errors_are_readable(self):
        with Fixture() as fx:
            with self.assertRaises(fetch.FetchError) as cm:
                fetch.get(fx.base + "/nothing")
            self.assertEqual(str(cm.exception), "HTTP 404")
            with self.assertRaises(fetch.FetchError):
                fetch.get(fx.base + "/a/1", max_bytes=100)
        with self.assertRaises(fetch.FetchError):
            fetch.get("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
