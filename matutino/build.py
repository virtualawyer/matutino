"""Print one issue.

read feeds -> pick stories not printed before -> fetch + extract + clean
-> download images -> issue.json + issue.epub -> copy EPUB to Kavita
-> mark stories seen -> prune old issues.

The new issue is assembled in <date>.tmp and swapped in only when it is
complete, so a failed build never leaves a half-printed paper behind.
"""

import datetime
import hashlib
import html
import json
import os
import re
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import boxes, epub, extract, feeds, fetch, images, sanitize
from . import sections as sec_mod

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|cmpid$|ocid$|taid$)", re.I)
MAX_BODY_IMAGES = 8
SEEN_DAYS = 180
LOW_DISK = 300 * 1024 * 1024  # below this, print without pictures
CATCH_UP = 7 * 86400


class BuildError(Exception):
    pass


def tz(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return datetime.timezone.utc


def local_date(ts, zone_name, days=0):
    d = datetime.datetime.fromtimestamp(ts, tz(zone_name)).date()
    return (d + datetime.timedelta(days=days)).isoformat()


def canonical(url):
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    q = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if not TRACKING.match(k)])
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, q, ""))


def story_key(item):
    return "l:" + canonical(item["link"]) if item["link"] else "g:" + item["guid"]


def pick(items, seen, cutoff, limit, today=()):
    """New items for one feed, newest first.

    Dated items must be newer than the cutoff. Undated items are taken
    from the top of the feed until the first one already printed, since
    feeds list newest first and everything below that point is older.
    Items already in today's issue always qualify, so a rebuild reprints
    them rather than losing the ones that have since aged past the cutoff.
    """
    dated, undated, stop_undated = [], [], False
    for it in items:
        k = story_key(it)
        if it["published"]:
            if k in today or (k not in seen and it["published"] >= cutoff):
                dated.append(it)
        elif not stop_undated:
            if k in seen:
                stop_undated = True
            else:
                undated.append(it)
    dated.sort(key=lambda it: -it["published"])
    return (dated + undated)[:limit]


def feed_cutoff(feed, now, window, previous):
    """Oldest publish time worth printing for this feed.

    Normally the look-back window. If the previous issue is older than
    that (the server was off for days), reach back to it so nothing is
    skipped. A feed added since the previous issue reaches back a week, so
    a comic that posts twice a week still shows up in its first paper.
    """
    if not previous or feed.get("added", 0) > previous:
        return now - CATCH_UP
    return max(min(now - window, previous - 6 * 3600), now - CATCH_UP)


def strip_feed_name(title, feed_title):
    """'Saturday Morning Breakfast Cereal - Blog' -> 'Blog' when that is the feed's name."""
    if feed_title and len(feed_title) >= 4:
        m = re.match(r"\s*%s\s*[-\u2013\u2014:|]\s*(.+)$" % re.escape(feed_title), title, re.I)
        if m:
            return m.group(1)
    return title


def sniff(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


NOT_FRONT = ("breaking", "funnies", "weather", "variety", "opinion")


def front(sections):
    """Choose the front page: one lead story and the right-hand column.

    Feeds filed under the Front Page section supply it when they have
    stories; otherwise the top story of each news section is drawn in.
    """
    def lead_of(pool):
        return next((st for st in pool if st["image"] and st["words"] >= 120), pool[0])

    fp = next((sec for sec in sections if sec["role"] == "front" and sec["stories"]), None)
    if fp:
        lead = lead_of(fp["stories"])
        return {"lead": lead["id"], "rail": [st["id"] for st in fp["stories"] if st is not lead][:5]}
    news = [sec for sec in sections if sec["role"] not in NOT_FRONT + ("front",)]
    pool, depth = [], 0
    while depth < 4:
        for sec in news:
            if depth < len(sec["stories"]) and sec["stories"][depth]["mode"] == "full":
                pool.append(sec["stories"][depth])
        depth += 1
    if not pool:
        pool = [st for sec in news for st in sec["stories"]][:5]
    if not pool:
        return {"lead": None, "rail": []}
    lead = lead_of(pool)
    return {"lead": lead["id"], "rail": [st["id"] for st in pool if st is not lead][:4]}


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "", s).strip(" .") or "Paper"


class Builder(object):
    def __init__(self, db, data_dir, epub_dir="", issues_dir=""):
        self.db = db
        # The issue library can live on another drive than the database (the
        # media drive is exFAT: fine for pictures, unsafe for SQLite).
        self.issues_dir = issues_dir or os.path.join(data_dir, "issues")
        self.epub_dir = epub_dir
        self.lock = threading.Lock()
        self.progress = {"running": False}
        self._img_lock = threading.Lock()
        os.makedirs(self.issues_dir, exist_ok=True)

    # public ----------------------------------------------------------------
    def busy(self):
        return self.lock.locked()

    def start(self, reason="manual"):
        """Run a build on a background thread. False if one is running."""
        if self.busy():
            return False
        threading.Thread(target=self.run, args=(reason,), daemon=True).start()
        return True

    def run(self, reason="manual", now=None):
        if not self.lock.acquire(False):
            return None
        t0 = time.time()
        self.progress = {"running": True, "phase": "Starting", "done": 0, "total": 0,
                         "detail": "", "started": t0}
        try:
            report = self._run(reason, now or time.time())
        except BuildError as e:
            report = {"ok": False, "error": str(e)}
        except Exception as e:  # keep the server alive; show the failure on the desk
            traceback.print_exc()
            report = {"ok": False, "error": "%s: %s" % (e.__class__.__name__, e)}
        finally:
            self.progress = {"running": False}
            self.lock.release()
        report.update({"reason": reason, "started": t0, "finished": time.time(),
                       "seconds": round(time.time() - t0, 1)})
        self.db.put("last_report", report)
        self._log(report)
        return report

    # internals -------------------------------------------------------------
    def _phase(self, phase, total):
        self.progress.update({"phase": phase, "done": 0, "total": total, "detail": ""})

    def _tick(self, detail):
        self.progress["done"] = self.progress.get("done", 0) + 1
        self.progress["detail"] = detail

    def _check_library(self):
        """Refuse to print into an unmounted drive's empty stub.

        A marker file is left in the library the first time it is used. If
        it has been used and the marker is gone, the drive is not mounted
        (a USB media drive that dropped off), and printing now would
        quietly fill the small root disk instead.
        """
        marker = os.path.join(self.issues_dir, ".matutino-library")
        if os.path.exists(marker):
            return
        if self.db.get("library_marked"):
            raise BuildError("The issue library (%s) looks empty -- is the drive mounted? Nothing printed."
                             % self.issues_dir)
        os.makedirs(self.issues_dir, exist_ok=True)
        open(marker, "a").close()
        self.db.put("library_marked", True)

    def _run(self, reason, now):
        self._check_library()
        s = self.db.settings()
        fetch.use_browser_ua(s["browser_ua"])
        date = local_date(now, s["timezone"])
        rows = self.db.feeds()
        if not rows:
            raise BuildError("No feeds yet. Add some on the desk first.")
        seen = self.db.seen_before(date)
        today = self.db.seen_on(date)
        previous = self.db.previous_build(date)
        window = float(s["lookback_hours"]) * 3600

        self._phase("Reading feeds", len(rows))
        with ThreadPoolExecutor(6) as pool:
            wx = pool.submit(self._weather, s) if s["weather_on"] else None
            otd = pool.submit(self._on_this_day, s, date) if s["onthisday_on"] else None
            results = list(pool.map(self._read_feed, rows))
            weather, wx_err = wx.result() if wx else (None, "")
            onthisday, otd_err = otd.result() if otd else (None, "")

        picked, keys = [], set()
        for feed, parsed, err in results:
            if err:
                continue
            for it in pick(parsed["items"], seen, feed_cutoff(feed, now, window, previous),
                           int(s["per_feed"]), today):
                it["title"] = strip_feed_name(it["title"], parsed["title"])
                k = story_key(it)
                if k not in keys:
                    keys.add(k)
                    picked.append((feed, it, k))

        per_feed = {}
        for feed, _, _ in picked:
            per_feed[feed["id"]] = per_feed.get(feed["id"], 0) + 1
        sections, order = [], {}
        for feed, parsed, err in results:
            self.db.update_feed(feed["id"], last_status="failed" if err else "ok",
                                last_error=err or "", last_checked=now,
                                last_count=per_feed.get(feed["id"], 0))
            if feed["section"] not in order:
                order[feed["section"]] = len(sections)
                sections.append({"name": feed["section"], "feeds": []})
            sections[order[feed["section"]]]["feeds"].append({
                "id": feed["id"], "name": feed["name"] or (parsed or {}).get("title") or feed["url"],
                "new": per_feed.get(feed["id"], 0), "error": err or ""})
        rank = {n: i for i, n in enumerate(sec_mod.order([x["name"] for x in sections], s["sections"]))}
        sections.sort(key=lambda x: rank[x["name"]])
        report = {"ok": True, "date": date, "sections": sections,
                  "failed": sum(1 for _, _, e in results if e), "stories": len(picked),
                  "boxes": {"weather": "off" if not s["weather_on"] else wx_err or "ok",
                            "onthisday": "off" if not s["onthisday_on"] else otd_err or "ok"}}

        if not picked:
            report["message"] = "No new stories since the last issue. Nothing printed."
            return report

        tmp = os.path.join(self.issues_dir, date + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "img"))
        self._images, self._img_events = {}, {}
        self._no_pictures = shutil.disk_usage(self.issues_dir).free < LOW_DISK
        self._phase("Setting type", len(picked))
        with ThreadPoolExecutor(4) as pool:
            stories = list(pool.map(lambda p: self._story(p[0], p[1], p[2], tmp), picked))

        by_section = []
        names = sec_mod.order([sec["name"] for sec in sections], s["sections"])
        if weather:
            names += [n for n in s["sections"] if sec_mod.role(n) == "weather" and n not in names][:1]
        if onthisday:
            names += [n for n in s["sections"] if sec_mod.role(n) == "variety" and n not in names][:1]
        for name in sec_mod.order(names, s["sections"]):
            sts = [st for st in stories if st["section"] == name]
            r = sec_mod.role(name)
            box = "weather" if r == "weather" and weather else "onthisday" if r == "variety" and onthisday else ""
            if sts or box:
                by_section.append({"name": name, "role": r, "box": box, "stories": sts})
        number = self.db.next_number(date)
        issue = {
            "date": date, "number": number, "paper": s["paper_name"], "edition": s["edition"],
            "language": s["language"], "built_at": now,
            "sources": len([f for f in per_feed if per_feed[f]]),
            "sections": by_section, "front": front(by_section),
            "weather": weather, "onthisday": onthisday,
        }
        report.update({"number": number,
                       "excerpts": sum(1 for st in stories if st["excerpt_only"])})
        if self._no_pictures:
            report["warning"] = "Less than 300 MB free on the server: printed without pictures."

        with open(os.path.join(tmp, "issue.json"), "w") as f:
            json.dump(issue, f)

        final = os.path.join(self.issues_dir, date)
        old = final + ".old"
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(final):
            os.rename(final, old)
        os.rename(tmp, final)
        shutil.rmtree(old, ignore_errors=True)

        self.db.mark_seen(date, [st["key"] for st in stories])
        self.db.record_issue(date, number, len(stories), report)
        # The EPUB is only kept in Kavita's folder; the paper's download link
        # binds a fresh one on request, so the server never stores it twice.
        self._phase("Binding the EPUB", 1)
        book = os.path.join(self.issues_dir, date + ".epub")
        try:
            epub.write(issue, final, book)
            report["kavita"] = self._export(book, s, date)
        finally:
            for leftover in (book, book + ".part"):
                if os.path.exists(leftover):
                    os.remove(leftover)
        self._prune(s, now, date)
        report["message"] = "No. %d printed: %d stories from %d feeds." % (
            number, len(stories), issue["sources"])
        return report

    def _weather(self, s):
        if s["weather_lat"] is None or s["weather_lon"] is None:
            return None, "no place set (desk settings)"
        try:
            return boxes.weather(s["weather_lat"], s["weather_lon"], s["timezone"],
                                 s["weather_place"].split(",")[0].strip()), ""
        except boxes.BoxError as e:
            return None, str(e)

    def _on_this_day(self, s, date):
        try:
            y, m, d = [int(x) for x in date.split("-")]
            return boxes.on_this_day(m, d, s["language"].split("-")[0].lower()), ""
        except boxes.BoxError as e:
            return None, str(e)

    def _read_feed(self, feed):
        try:
            final, _, body = fetch.get(feed["url"], max_bytes=6000000)
            parsed = feeds.parse(body, final)
            out = (feed, parsed, None)
        except (fetch.FetchError, feeds.FeedError) as e:
            out = (feed, None, str(e) or "unreadable")
        self._tick(feed["name"] or feed["url"])
        return out

    def _image(self, url, tmp):
        """Download one image into tmp/img; return its relative path or None.

        Stories often share a picture (a site's default og:image). The first
        story to ask downloads it; any other story asking meanwhile waits
        for that result instead of being told "no image".
        """
        with self._img_lock:
            done = self._img_events.get(url)
            if done is None:
                if len(self._img_events) >= 400:
                    return None
                done = self._img_events[url] = threading.Event()
                owner = True
            else:
                owner = False
        if not owner:
            done.wait(60)
            return self._images.get(url)
        rel = None
        try:
            rel = self._download(url, tmp)
        finally:
            self._images[url] = rel
            done.set()
        return rel

    def _download(self, url, tmp):
        if self._no_pictures:
            return None
        try:
            _, _, data = fetch.get(url, max_bytes=4000000, timeout=15, public_only=True,
                                   accept="image/webp,image/png,image/jpeg,image/gif;q=0.9,*/*;q=0.5")
        except fetch.FetchError:
            return None
        ext = sniff(data)
        if not ext or len(data) < 900:
            return None
        try:
            data, ext = images.shrink(data, ext)
        except images.Rejected:
            return None
        rel = "img/%s.%s" % (hashlib.sha1(data).hexdigest()[:16], ext)
        path = os.path.join(tmp, rel)
        if not os.path.exists(path):
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
        return rel

    def _story(self, feed, it, key, tmp):
        """One story; whatever goes wrong with it stays with it.

        A single odd page or image must never sink the whole issue, so any
        failure prints the feed's own text for that story instead.
        """
        try:
            return self._set_story(feed, it, key, tmp)
        except Exception as e:
            print("STORY FALLBACK  %s: %s: %s" % (it.get("title", "")[:60], e.__class__.__name__, e), flush=True)
            self._tick(it.get("title", ""))
            text = sanitize.text(it.get("content") or it.get("summary") or "")
            link = it.get("link") or ""
            return {
                "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:10],
                "key": key, "section": feed["section"], "mode": feed["mode"],
                "source": feed["name"] or urlsplit(link).netloc, "host": urlsplit(link).netloc.replace("www.", ""),
                "title": it.get("title") or link, "link": link, "author": (it.get("author") or "")[:80],
                "published": it.get("published"), "summary": sanitize.excerpt(text, 260),
                "html": "<p>%s</p>" % sanitize.xml_text(sanitize.excerpt(text, 1200)) if text else "",
                "image": None, "caption": "", "words": len(text.split()),
                "minutes": max(1, int(round(len(text.split()) / 230.0))), "excerpt_only": True,
            }

    def _set_story(self, feed, it, key, tmp):
        link = it["link"]
        c, sm = it["content"].strip(), it["summary"].strip()
        # Image-only entries (comics) have no text at all, so "longer text"
        # alone would pick the empty field.
        feed_html = c if c and len(sanitize.text(c)) >= len(sanitize.text(sm)) else (sm or c)
        body, author, site, image = feed_html, it["author"], "", it["image"]
        excerpt_only = False
        if feed["mode"] == "full" and link:
            ex = None
            try:
                final, ctype, page = fetch.get(
                    link, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", public_only=True)
                if "html" in ctype or b"<html" in page[:2000].lower():
                    ex = extract.article(page, final)
            except fetch.FetchError:
                pass
            feed_len = len(sanitize.text(feed_html))
            if ex and len(sanitize.text(ex["html"])) >= max(400, 0.6 * feed_len):
                body = ex["html"]
                author = author or ex["author"]
                site = ex["site"]
                image = image or ex["image"]
            elif feed_len < 1200:
                excerpt_only = True

        clean, imgs = sanitize.clean(body, base=link)
        lead_src = image or (imgs[0] if imgs else None)
        lead = self._image(lead_src, tmp) if lead_src else None
        if not lead and imgs and lead_src != imgs[0]:
            lead_src, lead = imgs[0], self._image(imgs[0], tmp)

        caption = ""
        if lead_src:
            m = re.search(r'<img src="%s"[^>]*? title="([^"]*)"' % re.escape(sanitize.xml_attr(lead_src)), clean)
            caption = html.unescape(m.group(1)) if m else ""
        allowed = set(imgs[:MAX_BODY_IMAGES])
        dropped_dup = False
        for src in dict.fromkeys(imgs):
            local = self._image(src, tmp) if src in allowed else None
            attr = 'src="%s"' % sanitize.xml_attr(src)
            pat = re.compile(r"<img %s[^>]*/>" % re.escape(attr))
            if local and local == lead and not dropped_dup:
                # The lead photo is shown above the headline; drop its first
                # appearance in the body so it is not printed twice.
                clean, dropped_dup = pat.sub("", clean, count=1), True
            if local:
                clean = clean.replace(attr, 'src="%s"' % local)
            else:
                clean = pat.sub("", clean)
        clean = re.sub(r"<figure>\s*(<figcaption>.*?</figcaption>)?\s*</figure>", "", clean, flags=re.S)
        clean = re.sub(r"<(p|a)>\s*</\1>", "", clean)

        plain = sanitize.text(clean)
        words = len(plain.split())
        summary = sanitize.text(it["summary"]) or plain
        host = urlsplit(link).netloc.replace("www.", "") if link else ""
        self._tick(it["title"])
        return {
            "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:10],
            "key": key, "section": feed["section"], "mode": feed["mode"],
            "source": feed["name"] or site or host, "host": host,
            "title": it["title"], "link": link, "author": author[:80],
            "published": it["published"], "summary": sanitize.excerpt(summary, 260),
            "html": clean, "image": lead, "caption": caption if lead else "", "words": words,
            "minutes": max(1, int(round(words / 230.0))), "excerpt_only": excerpt_only,
        }

    def kavita_folder(self, s):
        """The one folder in Kavita's library that Matutino files into.

        Named after the paper the first time an issue is filed, then fixed:
        renaming the paper changes the file names and the series inside
        each EPUB, not where they go, so old issues keep being pruned.
        """
        name = self.db.get("kavita_folder")
        if not name:
            used = self.db.get("kavita_folders", [])
            name = used[-1] if used else safe_name(s["paper_name"])
            self.db.put("kavita_folder", name)
        return name

    def _export(self, src, s, date):
        """Copy the EPUB into the Kavita library folder, if one is set."""
        root = self.epub_dir
        if not root:
            return {"skipped": True}
        if not os.path.isdir(root):
            return {"error": "Kavita folder %s does not exist" % root}
        folder_name = self.kavita_folder(s)
        folder = os.path.join(root, folder_name)
        sentinel = os.path.join(folder, ".matutino")
        exported = self.db.get("kavita_folders", [])
        if folder_name in exported and not os.path.exists(sentinel):
            # We have written here before and our marker is gone: the media
            # drive is most likely not mounted and this is the empty stub
            # underneath. Writing now would hide the issue on the root disk.
            return {"error": "%s looks empty -- is the media drive mounted? EPUB not copied."
                    % folder}
        try:
            os.makedirs(folder, exist_ok=True)
            dst = os.path.join(folder, "%s - %s.epub" % (safe_name(s["paper_name"]), date))
            shutil.copyfile(src, dst + ".part")
            os.replace(dst + ".part", dst)
            open(sentinel, "a").close()
        except OSError as e:
            return {"error": "could not write to Kavita folder: %s" % e}
        if folder_name not in exported:
            self.db.put("kavita_folders", exported + [folder_name])
        return {"path": dst}

    def _prune(self, s, now, today):
        keep = max(1, int(s["keep_days"]))
        oldest = local_date(now, s["timezone"], days=-(keep - 1))
        for name in os.listdir(self.issues_dir):
            base = name.split(".")[0]
            path = os.path.join(self.issues_dir, name)
            if DATE_RE.match(base) and (base < oldest or (name != base and base != today)):
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        os.remove(path)  # a stray <date>.epub from a crashed print
                    except OSError:
                        pass
                if name == base:
                    self.db.drop_issue(base)
        if self.epub_dir and self.db.get("kavita_folder"):
            folder = os.path.join(self.epub_dir, self.db.get("kavita_folder"))
            # Any "<name> - <date>.epub": issues printed before a rename carry
            # the old name. The folder is Matutino's own (it holds .matutino).
            pat = re.compile(r"^.+ - (\d{4}-\d{2}-\d{2})\.epub$")
            if os.path.isdir(folder):
                for name in os.listdir(folder):
                    m = pat.match(name)
                    if m and m.group(1) < oldest:
                        try:
                            os.remove(os.path.join(folder, name))
                        except OSError:
                            pass
        self.db.prune_seen(local_date(now, s["timezone"], days=-SEEN_DAYS))

    def _log(self, r):
        if not r.get("ok"):
            print("BUILD FAILED: %s" % r.get("error"), flush=True)
            return
        for sec in r.get("sections", []):
            for f in sec["feeds"]:
                if f["error"]:
                    print("FEED FAILED  %s / %s: %s" % (sec["name"], f["name"], f["error"]), flush=True)
                else:
                    print("%s / %s: %d new" % (sec["name"], f["name"], f["new"]), flush=True)
        for name, state in (r.get("boxes") or {}).items():
            if state not in ("ok", "off"):
                print("BOX FAILED  %s: %s" % (name, state), flush=True)
        k = r.get("kavita") or {}
        if k.get("path"):
            print("EPUB filed: %s" % k["path"], flush=True)
        elif k.get("error"):
            print("EPUB NOT FILED: %s" % k["error"], flush=True)
        print(r.get("message", ""), "(%ss)" % r.get("seconds"), flush=True)
