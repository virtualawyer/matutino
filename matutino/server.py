"""HTTP server, JSON API, and the daily print scheduler."""

import base64
import datetime
import hmac
import json
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import VERSION, boxes, build, desk, epub, extract, feeds, fetch, i18n, images, opds, render
from . import sections as sec_mod
from .build import Builder, tz, local_date
from .db import DB, DEFAULTS
from .epub import long_date

MAX_BODY = 512 * 1024
CSP = ("default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
       "script-src 'unsafe-inline'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")
DATE = r"(\d{4}-\d{2}-\d{2})"
ISSUE_RE = re.compile(r"^/issue/%s/?$" % DATE)
STORY_RE = re.compile(r"^/issue/%s/([0-9a-f]{10})$" % DATE)
IMG_RE = re.compile(r"^/issue/%s/img/([0-9a-f]{16}\.(?:jpg|png|gif|webp))$" % DATE)
EPUB_RE = re.compile(r"^/issue/%s/epub$" % DATE)
FEED_RE = re.compile(r"^/api/feeds/(\d+)$")
FEED_DEL_RE = re.compile(r"^/api/feeds/(\d+)/delete$")
IMG_TYPES = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
# Icons for browsers and home screens: public, so a password never hides them.
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC = {"/static/" + n: {"svg": "image/svg+xml", "png": "image/png"}[n.rsplit(".", 1)[1]]
          for n in (os.listdir(STATIC_DIR) if os.path.isdir(STATIC_DIR) else []) if n.rsplit(".", 1)[-1] in ("svg", "png")}
RETRY_GAP = 1800
MAX_TRIES = 4


class ApiError(Exception):
    def __init__(self, msg, code=400):
        Exception.__init__(self, msg)
        self.code = code


# scheduling ----------------------------------------------------------------
def slot_for(s, now):
    """Today's print time (epoch) in the paper's time zone."""
    local = datetime.datetime.fromtimestamp(now, tz(s["timezone"]))
    hh, mm = [int(x) for x in s["build_time"].split(":")]
    return local.replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp()


def due(s, now, latest_built, tries):
    """Should the scheduler print now?

    Once today's print time has passed, print unless an issue has already
    been printed since then. A failed or empty run is retried every 30
    minutes, at most four tries per day, so a dead network cannot spin.
    """
    if not s["schedule_on"]:
        return False
    slot = slot_for(s, now)
    if now < slot or (latest_built or 0) >= slot:
        return False
    if tries.get("slot") != slot:
        return True
    return tries.get("count", 0) < MAX_TRIES and now - tries.get("last", 0) >= RETRY_GAP


def next_print(s, now, latest_built):
    if not s["schedule_on"]:
        return None
    slot = slot_for(s, now)
    when = "today"
    if now >= slot and (latest_built or 0) >= slot:
        slot, when = slot + 86400, "tomorrow"
    elif now >= slot:
        return "shortly"
    return "%s at %s" % (when, render.hour(slot, s["timezone"]))


# app -----------------------------------------------------------------------
class App(object):
    def __init__(self, data_dir, epub_dir="", issues_dir="", password=None):
        os.makedirs(data_dir, exist_ok=True)
        # Optional HTTP Basic password for the whole site (any user name).
        self.password = os.environ.get("MATUTINO_PASSWORD", "") if password is None else password
        self.data_dir = data_dir
        self.epub_dir = epub_dir
        # Drop-in language packs (<code>.json) in the data folder join the built-in ones.
        i18n.load_dir(os.path.join(data_dir, "languages"))
        self.db = DB(os.path.join(data_dir, "matutino.db"))
        self.builder = Builder(self.db, data_dir, epub_dir, issues_dir)
        fetch.use_browser_ua(self.db.settings()["browser_ua"])
        self._cache = {}
        # Host names the server answers to; None = any. The desktop app sets
        # its own loopback names so a web page can't reach it by DNS tricks.
        self.allowed_hosts = None

    # issues
    def issue(self, date):
        path = os.path.join(self.builder.issues_dir, date, "issue.json")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        hit = self._cache.get(date)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._cache[date] = (mtime, data)
        return data

    def latest_date(self):
        rows = self.db.issues()
        for r in rows:
            if os.path.exists(os.path.join(self.builder.issues_dir, r["date"], "issue.json")):
                return r["date"]
        return None

    def latest_built(self):
        r = self.db.q("SELECT MAX(built_at) AS t FROM issues")
        return r[0]["t"] if r else None

    def state(self):
        s = self.db.settings()
        now = time.time()
        fs = self.db.feeds()
        issues = self.db.issues()
        for i in issues:
            i["long"] = long_date(i["date"])
        return {
            "version": VERSION, "now": now, "settings": s, "feeds": fs,
            "feeds_text": feeds.as_text(fs), "building": self.builder.busy(),
            "roles": {n: sec_mod.role(n) for n in s["sections"]},
            "progress": self.builder.progress, "last_report": self.db.get("last_report"),
            "issues": issues, "next_build": next_print(s, now, self.latest_built()),
            "today_long": long_date(local_date(now, s["timezone"])),
            "epub_dir": self.epub_dir,
            "epub_ok": bool(self.epub_dir) and os.path.isdir(self.epub_dir) and os.access(self.epub_dir, os.W_OK),
            "extractor": extract.AVAILABLE, "shrinker": images.AVAILABLE,
            "disk_free_mb": shutil.disk_usage(self.builder.issues_dir).free // 1048576,
            "library": self.builder.issues_dir,
            # Display only: the folder is fixed at the first filing, not here.
            "kavita_folder": self.db.get("kavita_folder") or (self.db.get("kavita_folders") or [""])[-1]
            or build.safe_name(s["paper_name"]),
            "kavita_free_mb": (shutil.disk_usage(self.epub_dir).free // 1048576
                               if self.epub_dir and os.path.isdir(self.epub_dir) else None),
        }

    # feeds
    def _discover_all(self, entries):
        def one(e):
            try:
                url, title = feeds.discover(e["url"])
                return e, url, title, None
            except feeds.FeedError as ex:
                return e, None, None, str(ex)
        with ThreadPoolExecutor(6) as pool:
            return list(pool.map(one, entries))

    def _default_section(self, s, wanted=""):
        return sec_mod.match(wanted, s["sections"], s["section_labels"]) or (wanted.strip()[:40] if wanted.strip() else "") or \
            ("Local News" if "Local News" in s["sections"] else s["sections"][0] if s["sections"] else "News")

    def _resolve(self, entries, default):
        s = self.db.settings()
        names, labels = s["sections"], s["section_labels"]
        for e in entries:
            e["section"] = sec_mod.resolve(e["section"], names, default, labels)
        return entries

    def add_feeds(self, text, section, mode):
        if mode not in ("full", "feed"):
            raise ApiError("mode must be full or feed")
        default = self._default_section(self.db.settings(), section)
        entries = self._resolve(feeds.parse_paste(text, default, mode)[:100], default)
        added, existing, failed, fresh = [], [], [], []
        for e in entries:
            (existing if self.db.feed_by_url(e["url"]) else fresh).append(e)
        existing = [e["url"] for e in existing]
        for e, url, title, err in self._discover_all(fresh):
            if err:
                failed.append({"url": e["url"], "error": err})
            elif self.db.feed_by_url(url):
                existing.append(url)
            else:
                name = (e["name"] or title or "").strip()[:80]
                self.db.add_feed(e["section"][:40], name, url, e["mode"])
                added.append(name or url)
        return {"added": added, "existing": existing, "failed": failed}

    def replace_feeds(self, text):
        default = self._default_section(self.db.settings())
        entries = self._resolve(feeds.parse_paste(text, default)[:300], default)
        current = {f["url"]: f for f in self.db.feeds()}
        keep, fresh = [], []
        for e in entries:
            (keep if e["url"] in current else fresh).append(e)
        found = self._discover_all(fresh)
        failed, added = [], 0
        with self.db.lock:
            wanted = set()
            pos = 0
            resolved = {}
            for e, url, title, err in found:
                resolved[e["url"]] = (url, title, err)
            for e in entries:
                pos += 1
                if e["url"] in current:
                    f = current[e["url"]]
                    wanted.add(f["id"])
                    self.db.update_feed(f["id"], section=e["section"][:40], name=(e["name"] or f["name"])[:80],
                                        mode=e["mode"], position=pos)
                    continue
                url, title, err = resolved[e["url"]]
                if err:
                    failed.append({"url": e["url"], "error": err})
                    continue
                f = self.db.feed_by_url(url)
                if f:
                    wanted.add(f["id"])
                    self.db.update_feed(f["id"], section=e["section"][:40], mode=e["mode"], position=pos)
                    continue
                fid = self.db.add_feed(e["section"][:40], (e["name"] or title or "")[:80], url, e["mode"])
                self.db.update_feed(fid, position=pos)
                wanted.add(fid)
                added += 1
            removed = 0
            for f in current.values():
                if f["id"] not in wanted:
                    self.db.delete_feed(f["id"])
                    removed += 1
        return {"total": len(self.db.feeds()), "added": added, "removed": removed, "failed": failed}

    def update_feed(self, fid, body):
        fields = {}
        if "mode" in body:
            if body["mode"] not in ("full", "feed"):
                raise ApiError("mode must be full or feed")
            fields["mode"] = body["mode"]
        for k in ("name", "section"):
            if k in body:
                v = str(body[k]).strip()[:80]
                if k == "section" and not v:
                    raise ApiError("section cannot be empty")
                fields[k] = v
        self.db.update_feed(fid, **fields)
        return {"ok": True}

    def save_settings(self, body):
        cur = self.db.settings()
        s = {}
        ranges = {"per_feed": (1, 30), "lookback_hours": (6, 336), "keep_days": (1, 365)}
        for k in body:
            if k not in DEFAULTS or k in ("weather_lat", "weather_lon", "section_labels"):
                continue  # coordinates come from the place; labels come with the section list
            v = body[k]
            if k in ("schedule_on", "weather_on", "onthisday_on", "browser_ua"):
                s[k] = bool(v)
            elif k in ranges:
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ApiError("%s must be a number" % k.replace("_", " "))
                s[k] = max(ranges[k][0], min(ranges[k][1], v))
            elif k == "sections":
                lines = v.splitlines() if isinstance(v, str) else v if isinstance(v, list) else None
                if lines is None:
                    raise ApiError("sections must be a list")
                # "World News = Mundo" keeps the section (its feeds and job) and prints it as Mundo
                names, labels = [], {}
                for line in lines:
                    name, _, label = str(line).partition("=")
                    name, label = name.strip()[:40], label.strip()[:40]
                    if name and name not in names:
                        names.append(name)
                        if label and label != name:
                            labels[name] = label
                if not names:
                    raise ApiError("The paper needs at least one section.")
                s[k] = names[:40]
                s["section_labels"] = {n: labels[n] for n in s[k] if n in labels}
            else:
                v = str(v).strip()
                if k == "paper_name" and not (1 <= len(v) <= 60):
                    raise ApiError("The paper needs a name (up to 60 characters).")
                if k == "build_time" and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
                    raise ApiError("Print time must look like 05:15.")
                if k == "timezone":
                    try:
                        from zoneinfo import ZoneInfo
                        ZoneInfo(v)
                    except Exception:
                        raise ApiError("Unknown time zone: %s" % v)
                if k == "language" and not re.match(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$", v):
                    raise ApiError("Language must be a code like en or es.")
                if k == "weather_place":
                    if v == cur["weather_place"]:
                        continue
                    if not v:
                        s.update(weather_place="", weather_lat=None, weather_lon=None)
                        continue
                    try:
                        found = boxes.geocode(v)
                    except boxes.BoxError as e:
                        raise ApiError(str(e))
                    s.update(weather_place=found["name"], weather_lat=found["lat"], weather_lon=found["lon"])
                    continue
                s[k] = v[:60]
        self.db.save_settings(s)
        fetch.use_browser_ua(self.db.settings()["browser_ua"])
        return {"ok": True, "settings": self.db.settings()}

    # scheduler
    def tick(self, now=None):
        now = now or time.time()
        s = self.db.settings()
        tries = self.db.get("auto_tries", {})
        if self.builder.busy() or not self.db.feeds() or not due(s, now, self.latest_built(), tries):
            return False
        slot = slot_for(s, now)
        count = tries.get("count", 0) + 1 if tries.get("slot") == slot else 1
        self.db.put("auto_tries", {"slot": slot, "count": count, "last": now})
        print("Scheduled print (try %d)" % count, flush=True)
        self.builder.run("scheduled")
        return True

    def run_scheduler(self):
        def loop():
            while True:
                try:
                    self.tick()
                except Exception as e:  # never let the scheduler thread die
                    print("scheduler: %s" % e, flush=True)
                time.sleep(20)
        threading.Thread(target=loop, daemon=True).start()


# http ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "Matutino/" + VERSION

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-cache")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json", {"Cache-Control": "no-store"})

    def _404(self):
        self._send(404, render.not_found_page(self.app.db.settings()["language"]))

    def _host_ok(self):
        hosts = self.app.allowed_hosts
        return hosts is None or (self.headers.get("Host") or "").lower() in hosts

    def _authorized(self):
        if not self.app.password:
            return True
        head = self.headers.get("Authorization") or ""
        if not head.startswith("Basic "):
            return False
        try:
            given = base64.b64decode(head[6:]).decode("utf-8").split(":", 1)[1]
        except (ValueError, IndexError, UnicodeError):
            return False
        return hmac.compare_digest(given.encode("utf-8"), self.app.password.encode("utf-8"))

    def _challenge(self):
        body = b"Matutino needs a password."
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Matutino", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        app = self.app
        path = urlsplit(self.path).path
        if not self._host_ok():
            return self._send(421, "wrong host", "text/plain; charset=utf-8")
        if path == "/healthz":  # for Docker's health check; never behind the password
            return self._send(200, "ok", "text/plain; charset=utf-8")
        if path in STATIC:
            with open(os.path.join(STATIC_DIR, path[8:]), "rb") as f:
                return self._send(200, f.read(), STATIC[path], {"Cache-Control": "public, max-age=86400"})
        if not self._authorized():
            return self._challenge()
        s = app.db.settings()
        zone, lang = s["timezone"], s["language"]
        # Section names print as the desk names them today, also in older issues.
        named = lambda iss: iss and dict(iss, section_labels=s["section_labels"])
        if path == "/":
            date = app.latest_date()
            if not date:
                return self._send(200, render.empty_page(s["paper_name"], app.builder.busy(), lang))
            return self._send(200, render.front_page(named(app.issue(date)), zone))
        if path == "/desk":
            return self._send(200, desk.page(VERSION))
        if path in ("/archive", "/editions"):
            return self._send(200, render.archive_page(
                [(r, named(app.issue(r["date"]))) for r in app.db.issues() if app.issue(r["date"])], s["paper_name"], lang))
        if path == "/api/state":
            return self._json(200, app.state())
        if path == "/manifest.webmanifest":
            return self._send(200, opds.manifest(s["paper_name"], lang), "application/manifest+json")
        if path == "/opds":
            eds = [(r, app.issue(r["date"])) for r in app.db.issues()]
            return self._send(200, opds.catalog(s["paper_name"], [(r, i) for r, i in eds if i]),
                              opds.ACQ + ";charset=utf-8", {"Cache-Control": "no-cache"})
        m = ISSUE_RE.match(path)
        if m:
            if not path.endswith("/"):
                return self._send(301, "", headers={"Location": path + "/"})
            issue = named(app.issue(m.group(1)))
            return self._send(200, render.front_page(issue, zone)) if issue else self._404()
        m = STORY_RE.match(path)
        if m:
            issue = named(app.issue(m.group(1)))
            st = issue and next((x for sec in issue["sections"] for x in sec["stories"]
                                 if x["id"] == m.group(2)), None)
            return self._send(200, render.article_page(issue, st, zone)) if st else self._404()
        m = IMG_RE.match(path)
        if m:
            fp = os.path.join(app.builder.issues_dir, m.group(1), "img", m.group(2))
            if not os.path.isfile(fp):
                return self._404()
            with open(fp, "rb") as f:
                return self._send(200, f.read(), IMG_TYPES[m.group(2).rsplit(".", 1)[1]],
                                  {"Cache-Control": "public, max-age=31536000, immutable"})
        m = EPUB_RE.match(path)
        if m:
            issue = app.issue(m.group(1))
            if not issue:
                return self._404()
            # Bound on request from the stored issue: keeping a copy per day
            # would double what the issues take on the server's disk.
            fd, tmp = tempfile.mkstemp(suffix=".epub", prefix="dl-", dir=app.builder.issues_dir)
            os.close(fd)
            try:
                epub.write(issue, os.path.join(app.builder.issues_dir, m.group(1)), tmp)
                with open(tmp, "rb") as f:
                    data = f.read()
            finally:
                for leftover in (tmp, tmp + ".part"):
                    if os.path.exists(leftover):
                        os.remove(leftover)
            name = re.sub(r"[^A-Za-z0-9 ._-]+", "", "%s - %s.epub" % (issue["paper"], issue["date"]))
            return self._send(200, data, "application/epub+zip",
                              {"Content-Disposition": 'attachment; filename="%s"' % name})
        return self._404()

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self._host_ok():
            return self._json(421, {"error": "wrong host"})
        if not self._authorized():
            return self._challenge()
        # JSON only: a plain cross-site <form> cannot send this content type,
        # which is all the CSRF protection a LAN-only, password-less app gets.
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._json(415, {"error": "send application/json"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            return self._json(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})
        app = self.app
        try:
            if path == "/api/feeds":
                return self._json(200, app.add_feeds(str(body.get("text", "")),
                                                     str(body.get("section", "")), body.get("mode", "full")))
            if path == "/api/feeds/text":
                return self._json(200, app.replace_feeds(str(body.get("text", ""))))
            if path == "/api/build":
                return self._json(200, {"started": app.builder.start("manual")})
            if path == "/api/settings":
                return self._json(200, app.save_settings(body))
            m = FEED_RE.match(path)
            if m:
                return self._json(200, app.update_feed(int(m.group(1)), body))
            m = FEED_DEL_RE.match(path)
            if m:
                app.db.delete_feed(int(m.group(1)))
                return self._json(200, {"ok": True})
        except ApiError as e:
            return self._json(e.code, {"error": str(e)})
        return self._json(404, {"error": "unknown endpoint"})


def make_server(app, host, port):
    handler = type("BoundHandler", (Handler,), {"app": app})
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), handler)


def serve(data_dir, epub_dir, host, port, scheduler=True, issues_dir=""):
    app = App(data_dir, epub_dir, issues_dir)
    if scheduler:
        app.run_scheduler()
    httpd = make_server(app, host, port)
    print("Matutino %s on http://%s:%d  (data: %s, library: %s, kavita: %s, full text: %s, pictures: %s)"
          % (VERSION, host, port, data_dir, app.builder.issues_dir, epub_dir or "off",
             "on" if extract.AVAILABLE else "OFF", "shrunk" if images.AVAILABLE else "FULL SIZE"), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
