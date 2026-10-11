import os
import re
import shutil
import unittest
import zipfile

from matutino import boxes, render
from matutino import sections as S
from matutino.server import ApiError

from fixtures import Fixture, temp_app
from test_build import check_epub


class Sections(unittest.TestCase):
    OWN = ["Front Page", "Breaking News", "Local News", "World News", "Puerto Rico News", "Opinion",
           "Local Business", "Puerto Rico Business", "International Business", "Crypto & Markets",
           "Real Estate", "Entertainment", "Science News", "Technology", "Health", "Variety News",
           "Travel & Food", "Local Weather", "Funnies", "Sports News"]

    def test_match_and_resolve(self):
        cases = {"World": "World News", "international / world news": "World News", "Comics": "Funnies",
                 "Front": "Front Page", "Sports": "Sports", "business": "Business", "science": "Science",
                 "weather": "Weather", "TRAVEL & FOOD": "Travel & Food"}
        for typed, want in cases.items():
            self.assertEqual(S.match(typed, S.DEFAULT), want, typed)
        # A paper's own list: aliases try each candidate, prefixes still work.
        own = {"PR Business": "Puerto Rico Business", "puerto rico": "Puerto Rico News", "crypto": "Crypto & Markets",
               "Sports": "Sports News", "business": "Local Business", "weather": "Local Weather",
               "science": "Science News"}
        for typed, want in own.items():
            self.assertEqual(S.match(typed, self.OWN), want, typed)
        self.assertIsNone(S.match("Surfing", S.DEFAULT))
        self.assertEqual(S.resolve("Surfing", S.DEFAULT, "Local News"), "Surfing")
        self.assertEqual(S.resolve("", S.DEFAULT, "Local News"), "Local News")

    def test_roles_follow_names(self):
        self.assertEqual(S.role("Front Page"), "front")
        self.assertEqual(S.role("Comics"), "funnies")
        self.assertEqual(S.role("Weather & Tides"), "weather")
        self.assertEqual(S.role("World News"), "")

    def test_order(self):
        self.assertEqual(S.order(["Funnies", "Zines", "Local News", "Alpha"], S.DEFAULT),
                         ["Local News", "Funnies", "Zines", "Alpha"])


class Boxes(unittest.TestCase):
    def test_geocode_uses_the_qualifier(self):
        with Fixture():
            self.assertEqual(boxes.geocode("Tamarindo, Costa Rica")["lat"], 10.2991)
            self.assertEqual(boxes.geocode("Tamarindo")["name"], "Tamarindo, Piura, Peru")
            with self.assertRaises(boxes.BoxError):
                boxes.geocode("Tamarindo, Narnia")

    def test_weather(self):
        with Fixture():
            w = boxes.weather(10.3, -85.8, "America/Costa_Rica", "Tamarindo")
        self.assertEqual(len(w["days"]), 4)
        self.assertEqual((w["days"][0]["desc"], w["days"][0]["icon"]), ("Thunderstorms", "storm"))
        self.assertEqual(w["days"][0]["rain_pct"], 98)
        self.assertEqual(round(boxes.c_to_f(30)), 86)
        html = render.weather_panel(w)
        self.assertIn("30&deg;", html)
        self.assertIn("5:31 a.m.", html)

    def test_on_this_day_spreads_across_years(self):
        with Fixture():
            o = boxes.on_this_day(10, 11)
        years = [e["year"] for e in o["events"]]
        self.assertEqual(len(years), 6)
        self.assertEqual((years[0], years[-1]), (2002, 1634))
        self.assertEqual(years, sorted(years, reverse=True))
        self.assertEqual(o["events"][0]["text"], "Event of 2002.")  # Wikipedia's "(pictured)" dropped
        self.assertEqual(boxes.PHOTO_NOTE.sub("", "Nace Tita Merello (en la imagen), actriz"), "Nace Tita Merello, actriz")

    def test_unreachable_service_is_a_box_error(self):
        boxes_url = boxes.FORECAST_URL
        boxes.FORECAST_URL = "http://127.0.0.1:9/forecast?"
        try:
            with self.assertRaises(boxes.BoxError):
                boxes.weather(1, 1, "UTC", "x")
        finally:
            boxes.FORECAST_URL = boxes_url


class FrontPageAndBoxes(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture().__enter__()
        self.app = temp_app()
        b = self.fx.base
        self.app.add_feeds("# Front Page\n%s/f/news.xml\n# Breaking\n%s/f/daily.atom\n# Comics\n%s/comic.xml headlines\n"
                           % (b, b, b), "", "full")
        self.app.db.save_settings({"weather_on": True, "onthisday_on": True, "weather_place": "Tamarindo",
                                   "weather_lat": 10.2991, "weather_lon": -85.8411})

    def tearDown(self):
        self.fx.__exit__()
        shutil.rmtree(self.app._root, ignore_errors=True)

    def test_issue_layout(self):
        r = self.app.builder.run("test")
        self.assertEqual(r["boxes"], {"weather": "ok", "onthisday": "ok"})
        iss = self.app.issue(r["date"])
        names = [(s["name"], s["box"], len(s["stories"])) for s in iss["sections"]]
        self.assertEqual(names, [("Front Page", "", 3), ("Breaking News", "", 1), ("Variety", "onthisday", 0),
                                 ("Weather", "weather", 0), ("Funnies", "", 1)])
        front_ids = [st["id"] for st in iss["sections"][0]["stories"]]
        self.assertIn(iss["front"]["lead"], front_ids)
        self.assertEqual(sorted(iss["front"]["rail"] + [iss["front"]["lead"]]), sorted(front_ids))

        html = render.front_page(iss, "America/Costa_Rica")
        self.assertIn('class="breaking', html)
        self.assertIn("Atom one", re.search(r'class="breaking.*?</div>', html, re.S).group(0))
        self.assertIn('class="wx-panel"', html)
        self.assertIn('class="ear r wx"', html)
        self.assertIn("On this day", html)
        self.assertNotIn("More top stories", html)  # every Front Page story is on the front
        self.assertIn('id="top"', html)
        self.assertEqual(html.count('class="totop label" href="#top"'), html.count('class="sec rise'))

        z, opf = check_epub(self, r["kavita"]["path"])
        pages = " ".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xhtml"))
        self.assertIn("Forecast for Tamarindo", pages)
        self.assertIn("Event of 2002", pages)

    def test_editions_page_draws_a_cover_per_issue(self):
        r = self.app.builder.run("test")
        iss = self.app.issue(r["date"])
        row = self.app.db.issue(r["date"])
        html = render.archive_page([(row, iss), (dict(row, number=0), iss)], "The Morning Paper")
        self.assertEqual(html.count('class="sheet"'), 2)
        self.assertEqual(html.count("ed-tag"), 2)  # one tag element + its CSS rule
        self.assertIn('class="c-band"', html)
        self.assertIn('/issue/%s/epub' % r["date"], html)


class Settings(unittest.TestCase):
    def setUp(self):
        self.app = temp_app()

    def tearDown(self):
        shutil.rmtree(self.app._root, ignore_errors=True)

    def test_sections_are_cleaned(self):
        self.app.save_settings({"sections": "Front Page\n\n  Local News \nLocal News\nSurf Report\n"})
        self.assertEqual(self.app.db.settings()["sections"], ["Front Page", "Local News", "Surf Report"])
        with self.assertRaises(ApiError):
            self.app.save_settings({"sections": "\n \n"})

    def test_weather_place_is_geocoded(self):
        with Fixture():
            out = self.app.save_settings({"weather_place": "Tamarindo, Costa Rica"})
            self.assertEqual(out["settings"]["weather_place"], "Tamarindo, Guanacaste Province, Costa Rica")
            self.assertEqual(out["settings"]["weather_lon"], -85.8411)
            with self.assertRaises(ApiError):
                self.app.save_settings({"weather_place": "Tamarindo, Narnia"})

    def test_pasted_sections_land_on_the_list(self):
        with Fixture() as fx:
            self.app.add_feeds("# World\n%s/f/news.xml\n# Surfing\n%s/f/daily.atom\n" % (fx.base, fx.base), "", "full")
            self.app.add_feeds("%s/comic.xml" % fx.base, "", "feed")
        got = {f["url"].rsplit("/", 1)[1]: f["section"] for f in self.app.db.feeds()}
        self.assertEqual(got, {"news.xml": "World News", "daily.atom": "Surfing", "comic.xml": "Local News"})


if __name__ == "__main__":
    unittest.main()
