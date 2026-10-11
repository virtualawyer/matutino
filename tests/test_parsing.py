import unittest
import xml.etree.ElementTree as ET

from matutino import feeds, sanitize


class FeedParsing(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"
      xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/"><channel>
      <title>Test &amp; Co</title><item><title>A &amp; B</title><link>/a</link><guid>g1</guid>
      <pubDate>Sun, 11 Oct 2026 08:00:00 -0600</pubDate><dc:creator>Jane</dc:creator>
      <description><![CDATA[<p>Short</p>]]></description>
      <content:encoded><![CDATA[<p>Full &lt;b&gt; text</p>]]></content:encoded>
      <enclosure url="/pic.jpg" type="image/jpeg"/></item></channel></rss>"""

    def test_rss2_fields(self):
        f = feeds.parse(self.RSS, "https://ex.com/feed")
        self.assertEqual(f["title"], "Test & Co")
        it = f["items"][0]
        self.assertEqual(it["title"], "A & B")
        self.assertEqual(it["link"], "https://ex.com/a")
        self.assertEqual(it["guid"], "g1")
        self.assertEqual(it["author"], "Jane")
        self.assertEqual(it["published"], 1791727200.0)
        self.assertEqual(it["image"], "https://ex.com/pic.jpg")
        self.assertIn("&lt;b&gt;", it["content"])  # literal text stays escaped, not a tag

    def test_atom_xhtml_and_html_title(self):
        f = feeds.parse(b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>At</title><entry>
          <title type="html">X &lt;i&gt;y&lt;/i&gt;</title><link rel="self" href="https://ex.com/self"/>
          <link rel="alternate" href="https://ex.com/1"/><id>u1</id><updated>2026-10-11T10:00:00Z</updated>
          <author><name>Bo</name></author><content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
          <p>One <em>two</em></p></div></content></entry></feed>""")
        it = f["items"][0]
        self.assertEqual(it["title"], "X y")
        self.assertEqual(it["link"], "https://ex.com/1")
        self.assertEqual(it["author"], "Bo")
        self.assertEqual(it["published"], 1791712800.0)
        self.assertIn("<p>One <em>two</em></p>", it["content"])

    def test_rdf(self):
        f = feeds.parse(b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
          xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>R</title></channel>
          <item><title>Old school</title><link>https://ex.com/r</link><dc:date>2026-10-10T08:00:00+02:00</dc:date></item></rdf:RDF>""")
        self.assertEqual(f["items"][0]["title"], "Old school")
        self.assertEqual(f["items"][0]["published"], 1791612000.0)

    def test_repairs_html_entities_and_bare_ampersands(self):
        f = feeds.parse(b"<rss><channel><title>Caf&eacute; &nbsp;News</title><item><title>Fish & chips&hellip;</title>"
                        b"<link>https://ex.com/x?a=1&b=2</link></item></channel></rss>")
        self.assertEqual(f["title"], "Café News")
        self.assertEqual(f["items"][0]["title"], "Fish & chips…")
        self.assertEqual(f["items"][0]["link"], "https://ex.com/x?a=1&b=2")

    def test_repairs_broken_tags_seen_in_the_wild(self):
        f = feeds.parse(b'<rss version="2.0" xmlns:a="https://x/a/"xmlns:content="http://purl.org/rss/1.0/modules/content/">'
                        b'<channel><title>T</title><item><title>One</title><link>https://x/1</link>'
                        b'<content:encoded<![CDATA[<p>Body "quoted"text=1</p>]]></content:encoded></item></channel></rss>')
        self.assertEqual(f["items"][0]["title"], "One")
        self.assertIn('"quoted"text=1', f["items"][0]["content"])  # article text is left alone

    def test_refuses_entity_declarations(self):
        with self.assertRaises(feeds.FeedError):
            feeds.parse(b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><title>&a;</title></channel></rss>')

    def test_html_is_not_a_feed(self):
        with self.assertRaises(feeds.FeedError):
            feeds.parse(b"<html><body>hi</body></html>")

    def test_dates(self):
        self.assertEqual(feeds.parse_date("2026-10-11T10:00:00Z"), 1791712800.0)
        self.assertEqual(feeds.parse_date("2026-10-11T12:00:00+02:00"), 1791712800.0)
        self.assertEqual(feeds.parse_date("2026-10-11"), 1791676800.0)
        self.assertIsNone(feeds.parse_date("yesterday-ish"))
        self.assertIsNone(feeds.parse_date(""))

    def test_short_title(self):
        self.assertEqual(feeds.short_title("The Tico Times | Costa Rica News | Travel"), "The Tico Times")
        self.assertEqual(feeds.short_title("BBC News - World"), "BBC News")
        self.assertEqual(feeds.short_title("A - B"), "A - B")


class Paste(unittest.TestCase):
    def test_everything_people_paste(self):
        got = feeds.parse_paste("""SECTIONS = [
('World', [
  ('BBC', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
  ('xkcd', 'https://xkcd.com/rss.xml', 'feed'),
]),
# Tech
Hacker News | https://hnrss.org/frontpage | headlines
arstechnica.com
[Costa Rica]
https://ticotimes.net/feed
Comics:
just some words, ignored
""")
        self.assertEqual([(e["section"], e["name"], e["url"], e["mode"]) for e in got], [
            ("World", "BBC", "https://feeds.bbci.co.uk/news/world/rss.xml", "full"),
            ("World", "xkcd", "https://xkcd.com/rss.xml", "feed"),
            ("Tech", "Hacker News", "https://hnrss.org/frontpage", "feed"),
            ("Tech", "", "https://arstechnica.com", "full"),
            ("Costa Rica", "", "https://ticotimes.net/feed", "full"),
        ])

    def test_comments(self):
        got = feeds.parse_paste("""# Matutino feed pack: English, international.
# 26 feeds, each one fetched.
# Weather
# Atlantic hurricane outlooks; swap for your region's alerts.
NHC | https://www.nhc.noaa.gov/index-at.xml | headlines
# old | https://dead.example/feed
""")
        self.assertEqual([(e["section"], e["url"]) for e in got], [("Weather", "https://www.nhc.noaa.gov/index-at.xml")])

    def test_defaults(self):
        self.assertEqual(feeds.parse_paste("https://a.com/feed")[0]["section"], "News")
        e = feeds.parse_paste("https://a.com/feed", "Local", "feed")[0]
        self.assertEqual((e["section"], e["mode"]), ("Local", "feed"))

    def test_name_with_feed_word_is_not_headlines(self):
        self.assertEqual(feeds.parse_paste("Daily feed digest https://a.com/rss")[0]["mode"], "full")

    def test_text_round_trip(self):
        rows = [{"section": "World", "name": "BBC", "url": "https://b.com/rss", "mode": "full"},
                {"section": "Comics", "name": "", "url": "https://x.com/rss", "mode": "feed"}]
        back = feeds.parse_paste(feeds.as_text(rows))
        self.assertEqual([(r["section"], r["name"], r["url"], r["mode"]) for r in back],
                         [(r["section"], r["name"], r["url"], r["mode"]) for r in rows])


class Sanitize(unittest.TestCase):
    def well_formed(self, markup):
        ET.fromstring("<div>%s</div>" % markup)

    def test_strips_active_content(self):
        out, _ = sanitize.clean('<p onclick="x()">Hi<script>alert(1)</script><style>p{}</style>'
                                '<iframe src="https://e.vil"></iframe> <a href="javascript:alert(1)">x</a>'
                                '<img src="data:image/png;base64,AAA" onerror="x()"></p>', "https://ex.com/")
        for bad in ("script", "alert", "style", "iframe", "onclick", "onerror", "javascript", "data:"):
            self.assertNotIn(bad, out)
        self.assertIn("Hi", out)
        self.well_formed(out)

    def test_resolves_relative_urls_and_collects_images(self):
        out, imgs = sanitize.clean('<p><a href="/b">b</a><img src="pic.jpg" alt="A&B"></p>', "https://ex.com/dir/page")
        self.assertIn('href="https://ex.com/b"', out)
        self.assertEqual(imgs, ["https://ex.com/dir/pic.jpg"])
        self.assertIn('alt="A&amp;B"', out)

    def test_lazy_and_srcset_images(self):
        _, imgs = sanitize.clean('<img data-src="/lazy.jpg"><img srcset="/s1.jpg 1x, /s2.jpg 2x">', "https://ex.com/")
        self.assertEqual(imgs, ["https://ex.com/lazy.jpg", "https://ex.com/s1.jpg"])

    def test_drops_tracking_pixels(self):
        _, imgs = sanitize.clean('<img src="https://ex.com/t.gif" width="1" height="1">'
                                 '<img src="https://feeds.feedburner.com/~r/x.gif">', "")
        self.assertEqual(imgs, [])

    def test_void_tags_do_not_swallow_the_rest(self):
        out, _ = sanitize.clean("<p>Before</p><input type=text><embed src=x><p>After</p>", "")
        self.assertIn("After", out)

    def test_messy_markup_is_well_formed(self):
        for markup in ["<p>a<p>b<ul><li>c<li>d</ul>", "<b><i>x</b></i></div></p>",
                       "<h1>T</h1><table><tr><td colspan=2 onmouseover=x>1<td>2</table>",
                       "<p>ctrl\x01chars\x0b</p><br><hr>", "<a href='/x'><a href='/y'>nested</a></a>",
                       "<blockquote><p>q</blockquote>tail &amp; &lt;tag&gt;"]:
            out, _ = sanitize.clean(markup, "https://ex.com/")
            self.well_formed(out)

    def test_renames(self):
        out, _ = sanitize.clean("<h1>T</h1><b>b</b><i>i</i>", "")
        self.assertEqual(out, "<h2>T</h2><strong>b</strong><em>i</em>")

    def test_keeps_image_title(self):
        out, _ = sanitize.clean('<img src="https://x.com/c.png" title="Joke &quot;here&quot;">', "")
        self.assertIn('title="Joke &quot;here&quot;"', out)

    def test_text_and_excerpt(self):
        self.assertEqual(sanitize.text("<p>A&amp;B</p>\n<p>c</p>"), "A&B c")
        self.assertEqual(sanitize.excerpt("one two three four", 12), "one two…")


if __name__ == "__main__":
    unittest.main()
