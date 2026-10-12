import datetime
import json
import os
import re
import shutil
import tempfile
import unittest

from matutino import desk, epub, i18n, render

from fixtures import Fixture, temp_app
from test_build import check_epub

WIKIPEDIA = ["en", "es", "de", "fr", "pt", "it", "sv", "ru", "uk", "bs", "tr", "ar", "zh"]
EPUB_TEXT = ("contents", "start", "original", "only_excerpt", "sun_times", "forecast_for", "otd_title")


def holes(s):
    return sorted(re.findall(r"%[^%]|%%", s))


class Packs(unittest.TestCase):
    def test_every_wikipedia_language_is_complete(self):
        self.assertEqual(sorted(i18n.LANGS), sorted(WIKIPEDIA))
        en = i18n.STRINGS["en"]
        for code in WIKIPEDIA:
            P = i18n.LANGS[code]
            self.assertEqual(set(P["strings"]), set(en), code)
            for k, v in P["strings"].items():
                self.assertEqual(holes(v), holes(en[k]), "%s.%s" % (code, k))
                if k in EPUB_TEXT:
                    self.assertNotIn("&", v, "%s.%s goes into the EPUB as text" % (code, k))
            self.assertEqual(len(P["days"]), 7, code)
            self.assertEqual(len(P["months"]), 12, code)
            if code != "en":
                self.assertEqual(set(P["weather"]), set(i18n.LANGS["es"]["weather"]), code)
                self.assertTrue(set(i18n.SECTION_NAMES["es"]) <= set(P["sections"]), code)

    def test_dates_read_naturally(self):
        d, first = datetime.date(2026, 10, 11), datetime.date(2026, 10, 1)
        self.assertEqual(i18n.long_date(d, "de"), "Sonntag, 11. Oktober 2026")
        self.assertEqual(i18n.long_date(first, "fr"), "jeudi 1er octobre 2026")
        self.assertEqual(i18n.long_date(d, "fr"), "dimanche 11 octobre 2026")
        self.assertEqual(i18n.long_date(d, "ru"), "воскресенье, 11 октября 2026 г.")  # genitive month
        self.assertEqual(i18n.month_day(d, "uk"), "11 жовтня")
        self.assertEqual(i18n.long_date(d, "tr"), "11 Ekim 2026 Pazar")
        self.assertEqual(i18n.long_date(d, "zh"), "2026年10月11日 星期日")
        self.assertEqual(i18n.long_date(d, "ar"), "الأحد، 11 أكتوبر 2026")
        self.assertEqual(i18n.day_month(d, "pt-BR"), "domingo, 11 out")
        self.assertEqual(i18n.hm(20, 5, "de"), "20:05 Uhr")
        self.assertEqual(i18n.hm(20, 5, "fr"), "20 h 05")
        self.assertEqual(i18n.hm(5, 15, "sv"), "05:15")
        self.assertEqual(i18n.hm(20, 5, "ar"), "8:05 م")
        self.assertEqual(i18n.hm(20, 5, "en"), "8:05 p.m.")
        self.assertEqual(i18n.weather(61, "Light rain", "de"), "Leichter Regen")
        self.assertEqual(i18n.section_name("Funnies", "it"), "Fumetti")

    def test_language_codes(self):
        for typed, want in {"pt-BR": "pt", "zh_TW": "zh", "ES-cr": "es", "nb": "en", "": "en", None: "en"}.items():
            self.assertEqual(i18n.lang_of(typed), want, typed)
        self.assertEqual([c for c, _ in i18n.languages()][:2], ["en", "es"])
        self.assertEqual(sorted(c for c, _ in i18n.languages()), sorted(WIKIPEDIA))
        self.assertEqual(i18n.direction("ar"), "rtl")
        self.assertEqual(i18n.direction("de"), "ltr")

    def test_drop_in_pack(self):
        d = tempfile.mkdtemp()
        try:
            pack = {"name": "Nederlands", "strings": {"today": "Vandaag", "no": "Nr. %d", "by": "Door"},
                    "days": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
                    "months": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
                               "september", "oktober", "november", "december"],
                    "long": "{weekday} {day} {month} {year}", "day_month": "{weekday} {day} {mon}",
                    "month_day": "{day} {month}", "time": "{H}:{MM}", "stamp": "{day} {mon} {time}"}
            with open(os.path.join(d, "nl.json"), "w", encoding="utf-8") as f:
                json.dump(pack, f)
            with open(os.path.join(d, "xx.json"), "w", encoding="utf-8") as f:
                json.dump(dict(pack, long="{weekday} {century}"), f)  # names a field that doesn't exist
            self.assertEqual(i18n.load_dir(d), ["nl"])
            self.assertEqual(i18n.long_date("2026-10-11", "nl"), "zondag 11 oktober 2026")
            L = i18n.strings("nl")
            self.assertEqual(L["today"], "Vandaag")
            self.assertEqual(L["no"] % 3, "Nr. 3")
            self.assertEqual(L["by"], "By %s")  # lost its %s, so English stands in
            self.assertEqual(L["editions"], "Editions")  # missing: English
            self.assertEqual(i18n.lang_of("xx"), "en")
        finally:
            shutil.rmtree(d)
            for code in ("nl", "xx"):
                i18n.LANGS.pop(code, None)
                i18n.STRINGS.pop(code, None)


class Papers(unittest.TestCase):
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

    def test_german_and_arabic_papers(self):
        self.app.save_settings({"language": "de"})
        r = self.app.builder.run("test")
        iss = self.app.issue(r["date"])
        html = render.front_page(iss, "UTC")
        self.assertIn('<html lang="de">', html)
        nav = re.search(r'<nav class="sections.*?</nav>', html, re.S).group(0)
        for printed in ("Vermischtes", "Wetter", "Comics"):
            self.assertIn(printed, nav)
        self.assertIn('class="kicker label">Titelseite', html)  # the lead's kicker
        self.assertIn("An diesem Tag", html)
        self.assertIn("Vorhersage für Tamarindo", html)
        self.assertNotIn('dir="rtl"', html)

        ar = dict(iss, language="ar")
        html = render.front_page(ar, "UTC")
        self.assertIn('<html lang="ar" dir="rtl">', html)
        self.assertIn("الصفحة الأولى", html)
        st = iss["sections"][0]["stories"][0]
        self.assertIn('dir="rtl"', render.article_page(ar, st, "UTC"))
        out = os.path.join(self.app._root, "ar.epub")
        epub.write(ar, os.path.join(self.app.builder.issues_dir, r["date"]), out)
        z, opf = check_epub(self, out)
        ns = {"o": "http://www.idpf.org/2007/opf"}
        self.assertEqual(opf.find("o:spine", ns).get("page-progression-direction"), "rtl")
        story = z.read("OEBPS/s-%s.xhtml" % st["id"]).decode("utf-8")
        self.assertIn('dir="rtl"', story)
        self.assertIn('<div dir="auto">', story)  # the story keeps its feed's direction

    def test_every_language_prints_a_valid_epub(self):
        r = self.app.builder.run("test")
        iss = self.app.issue(r["date"])
        for code in WIKIPEDIA:
            out = os.path.join(self.app._root, code + ".epub")
            epub.write(dict(iss, language=code), os.path.join(self.app.builder.issues_dir, r["date"]), out)
            check_epub(self, out)
            html = render.front_page(dict(iss, language=code), "UTC")
            self.assertIn('<html lang="%s"' % code, html)

    def test_desk_offers_every_language(self):
        html = desk.page("test")
        for code, name in i18n.languages():
            self.assertIn('<option value="%s">%s (%s)</option>' % (code, name, code), html)
