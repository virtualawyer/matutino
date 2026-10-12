"""Matutino as a desktop app for macOS and Windows.

    python -m matutino.desktop [--background] [--check]

Runs the same paper as the server, for this computer only: it listens on
127.0.0.1, keeps its data in the user's application-data folder, files each
EPUB in Documents/Matutino and lives in the menu bar (macOS) or the
notification area (Windows). The paper opens in the default browser. A print
missed while the computer slept happens as soon as it wakes.

--background starts without opening the browser (used at login); --check
starts a throwaway paper, checks that everything the app needs is inside the
bundle, and exits 0 or 1 (used by the build).
"""

import argparse
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import webbrowser

from . import VERSION, i18n

NAME = "Matutino"
AGENT = "io.github.virtualawyer.matutino"
PORTS = list(range(8771, 8791))
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(__file__))


# places ----------------------------------------------------------------------
def data_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, NAME)


def documents_dir():
    if os.name == "nt":  # Documents may be redirected (OneDrive); the registry knows where
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                path = os.path.expandvars(winreg.QueryValueEx(k, "Personal")[0])
            if os.path.isdir(path):
                return path
        except OSError:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def books_dir():
    return os.path.join(documents_dir(), NAME)


# the computer's own zone and language, for a new paper -------------------------
def system_zone():
    name = ""
    try:
        import tzlocal
        name = tzlocal.get_localzone_name() or ""
    except Exception:
        try:
            name = os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1]
        except (IndexError, OSError):
            pass
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return name
    except Exception:
        return "UTC"


def system_language():
    code = ""
    if sys.platform == "darwin":  # apps opened from Finder have no LANG
        try:
            code = subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    elif os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                code = buf.value
        except Exception:
            pass
    if not code:
        code = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    return i18n.lang_of(code.split(".")[0])


# open at login -------------------------------------------------------------------
def _launch_command():
    """How to start this app again, in the background."""
    if FROZEN and sys.platform == "darwin":
        bundle = sys.executable.split(".app/")[0] + ".app"
        return ["/usr/bin/open", "-g", "-a", bundle, "--args", "--background"]
    if FROZEN:
        return [sys.executable, "--background"]
    return [sys.executable, "-m", "matutino.desktop", "--background"]


def _agent_path():
    return os.path.expanduser("~/Library/LaunchAgents/%s.plist" % AGENT)


def login_enabled():
    if sys.platform == "darwin":
        return os.path.exists(_agent_path())
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, NAME)
            return True
        except OSError:
            return False
    return False


def set_login(on):
    cmd = _launch_command()
    if sys.platform == "darwin":
        import plistlib
        path = _agent_path()
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                plistlib.dump({"Label": AGENT, "ProgramArguments": cmd, "RunAtLoad": True}, f)
        elif os.path.exists(path):
            os.remove(path)
    elif os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass


# one copy at a time ----------------------------------------------------------------
def _state_path(d):
    return os.path.join(d, "desktop.json")


def last_port(d):
    try:
        with open(_state_path(d), encoding="utf-8") as f:
            return int(json.load(f)["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def running_port(d):
    """The port of a Matutino already running on this data folder, or None."""
    port = last_port(d)
    if not port:
        return None
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=2) as r:
            if r.headers.get("Server", "").startswith("Matutino/") and r.read() == b"ok":
                return port
    except (OSError, ValueError):
        pass
    return None


def free_port(prefer=None):
    """The port used last time if it's free (bookmarks keep working), else the first free one."""
    for port in ([prefer] if prefer else []) + PORTS + [0]:
        s = socket.socket()
        try:
            if os.name != "nt":  # a port our last run just let go of is free (Windows means another thing by this)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    raise OSError("no free port")


def open_path(path):
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


# the app -----------------------------------------------------------------------------
def start(d, books, port):
    """Start the paper on 127.0.0.1:port. Returns (app, httpd)."""
    from .server import App, make_server
    os.makedirs(books, exist_ok=True)
    app = App(d, books)
    if not app.db.get("desktop_setup"):
        # A new paper follows the computer's clock and language.
        app.db.save_settings({"timezone": system_zone(), "language": system_language()})
        app.db.put("desktop_setup", True)
    app.allowed_hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port}
    httpd = make_server(app, "127.0.0.1", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return app, httpd


def tray(app, httpd, url, books, d):
    import pystray
    from PIL import Image

    icon_dir = os.path.join(HERE, "static")
    if sys.platform == "darwin":
        import AppKit
        import Foundation

        class Icon(pystray.Icon):
            # A template image: macOS tints it for light and dark menu bars,
            # and the 44 px art drawn at 18 pt stays sharp on Retina screens.
            def _assert_image(self):
                if self._icon_image:
                    return
                b = io.BytesIO()
                self._icon.save(b, "png")
                img = AppKit.NSImage.alloc().initWithData_(Foundation.NSData(b.getvalue()))
                side = self._status_bar.thickness() * .82
                img.setSize_((side, side))
                img.setTemplate_(True)
                self._icon_image = img
                self._status_item.button().setImage_(img)
        image = Image.open(os.path.join(icon_dir, "tray-template.png"))
    else:
        Icon = pystray.Icon
        image = Image.open(os.path.join(icon_dir, "tray.png"))

    def quit_app(icon, _item):
        icon.stop()
        httpd.shutdown()

    item = pystray.MenuItem
    menu = pystray.Menu(
        item("Open the paper", lambda *_: webbrowser.open(url + "/"), default=True),
        item("Open the desk", lambda *_: webbrowser.open(url + "/desk")),
        item("Print now", lambda *_: app.builder.start("manual"), enabled=lambda _: not app.builder.busy()),
        item("Show the EPUB folder", lambda *_: open_path(books)),
        pystray.Menu.SEPARATOR,
        item("Open at login", lambda *_: set_login(not login_enabled()), checked=lambda _: login_enabled()),
        item("Matutino %s" % VERSION, None, enabled=False),
        item("Quit Matutino", quit_app),
    )
    Icon(NAME, image, NAME, menu).run()


def check():
    """Start a throwaway paper and make sure the bundle has all it needs."""
    import ssl
    from zoneinfo import ZoneInfo
    from . import extract, images
    problems = []
    d = tempfile.mkdtemp(prefix="matutino-check-")
    port = free_port()
    app, httpd = start(os.path.join(d, "data"), os.path.join(d, "books"), port)
    base = "http://127.0.0.1:%d" % port
    for path in ("/healthz", "/", "/desk", "/opds", "/manifest.webmanifest", "/static/icon-192.png"):
        try:
            with urllib.request.urlopen(base + path, timeout=10) as r:
                if r.status != 200:
                    problems.append("%s answered %s" % (path, r.status))
        except Exception as e:
            problems.append("%s: %s" % (path, e))
    req = urllib.request.Request(base + "/healthz", headers={"Host": "evil.example"})
    try:
        urllib.request.urlopen(req, timeout=5)
        problems.append("a foreign Host header was let in")
    except urllib.error.HTTPError as e:
        if e.code != 421:
            problems.append("foreign Host header answered %s" % e.code)
    httpd.shutdown()
    if not extract.AVAILABLE:
        problems.append("full-text extraction (trafilatura) is missing")
    else:
        page = ("<html><body><article><h1>A headline</h1>%s</article></body></html>"
                % ("<p>%s</p>" % ("Words here. " * 40) * 4)).encode("utf-8")
        if "Words here" not in (extract.article(page, "https://example.com/a") or {}).get("html", ""):
            problems.append("trafilatura is present but extracts nothing (data files missing?)")
    if not images.AVAILABLE:
        problems.append("picture shrinking (Pillow) is missing")
    if len(i18n.LANGS) < 13:
        problems.append("only %d languages loaded" % len(i18n.LANGS))
    try:
        ZoneInfo("America/Costa_Rica")
    except Exception as e:
        problems.append("time zones: %s" % e)
    if not ssl.create_default_context().cert_store_stats().get("x509_ca"):
        problems.append("no certificate authorities: https feeds would fail")
    for name in ("tray.png", "tray-template.png"):
        if not os.path.exists(os.path.join(HERE, "static", name)):
            problems.append("icon %s is missing" % name)
    result = "Matutino %s check: %s" % (VERSION, "; ".join(problems) or "ok")
    print(result, flush=True)
    if os.environ.get("MATUTINO_CHECK_LOG"):  # a windowed build has no console to print to
        with open(os.environ["MATUTINO_CHECK_LOG"], "a", encoding="utf-8") as f:
            f.write(result + "\n")
    return 1 if problems else 0


def _setup_frozen():
    """In a bundle: keep a log, and give https the bundled certificates."""
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    log = os.path.join(d, "matutino.log")
    if os.path.exists(log) and os.path.getsize(log) > 2 * 1024 * 1024:
        os.replace(log, log + ".1")
    if sys.stdout is None or not sys.stdout.isatty():
        sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass


def main(argv=None):
    p = argparse.ArgumentParser(prog="matutino-desktop", description="Matutino in the menu bar / notification area.")
    p.add_argument("--background", action="store_true", help="don't open the browser (used at login)")
    p.add_argument("--check", action="store_true", help="check the bundle and exit")
    args, _ = p.parse_known_args(argv)  # macOS may add its own arguments
    if FROZEN and not args.check:
        _setup_frozen()
    elif FROZEN:
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except ImportError:
            pass
    if args.check:
        return check()
    d = data_dir()
    os.makedirs(d, exist_ok=True)
    port = running_port(d)
    if port:  # already running: just show the paper
        if not args.background:
            webbrowser.open("http://127.0.0.1:%d/" % port)
        return 0
    port = free_port(last_port(d))
    books = books_dir()
    app, httpd = start(d, books, port)
    app.run_scheduler()
    url = "http://127.0.0.1:%d" % port
    with open(_state_path(d), "w", encoding="utf-8") as f:
        json.dump({"port": port, "pid": os.getpid()}, f)
    print("Matutino %s on %s (data: %s, EPUBs: %s)" % (VERSION, url, d, books), flush=True)
    if not args.background:
        webbrowser.open(url + ("/" if app.db.feeds() else "/desk"))
    try:
        tray(app, httpd, url, books, d)
    except ImportError:  # no tray library (e.g. Linux from source): run until stopped
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    finally:
        httpd.server_close()  # desktop.json stays: the next start reuses the port
    return 0


if __name__ == "__main__":
    sys.exit(main())
