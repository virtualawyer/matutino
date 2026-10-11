"""One HTTP GET with a size cap, gzip, and a browser User-Agent.

Many news sites refuse urllib's default agent, so every request presents
as a desktop browser. Responses are capped before decompression and after,
so a hostile or broken server cannot fill memory.
"""

import http.client
import ipaddress
import os
import socket
import ssl
import urllib.error
import urllib.request
import zlib
from urllib.parse import quote, urlsplit, urlunsplit

from . import PROJECT_URL, VERSION


class FetchError(Exception):
    pass


# Matutino says what it is by default. Some news sites refuse anything that
# does not look like a browser; the "identify as a web browser" setting
# switches to BROWSER_UA for those who accept that trade-off.
UA = "Matutino/%s (%s)" % (VERSION, "+" + PROJECT_URL if PROJECT_URL else "self-hosted news reader")
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
_browser = False

# Article pages and pictures come from addresses written by feed authors, so
# by default they may not point into the local network (a hostile feed must
# not be able to make the server poke at a router). Feeds you add yourself
# may be local. MATUTINO_ALLOW_PRIVATE=1 lifts the rule (and the tests use it).
ALLOW_PRIVATE = os.environ.get("MATUTINO_ALLOW_PRIVATE") == "1"


def use_browser_ua(on):
    global _browser
    _browser = bool(on)


def is_public(url):
    """True if every address the host resolves to is on the public internet."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or \
                ip.is_multicast or ip.is_unspecified:
            return False
    return True


class _Guard(urllib.request.HTTPRedirectHandler):
    """Re-check the public-address rule on every redirect hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if getattr(req, "public_only", False) and not ALLOW_PRIVATE and not is_public(newurl):
            raise FetchError("redirects into the local network")
        new = urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
        if new is not None:
            new.public_only = getattr(req, "public_only", False)
        return new

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # stdlib-only install: trust the system store
    _CTX = ssl.create_default_context()




try:
    import brotli  # optional: some CDNs send Brotli whatever we ask for
except ImportError:
    brotli = None


class _Undecodable(Exception):
    pass


def iri_to_uri(url):
    """Percent-encode an address with accents in it ('/año/', 'ñandú.cr').

    Spanish feeds link to such addresses all the time, and http.client only
    sends ASCII, so the raw form fails before a byte goes out.
    """
    if url.isascii():
        return url
    p = urlsplit(url)
    netloc = p.netloc
    if not netloc.isascii():
        netloc = p.hostname.encode("idna").decode("ascii") + (":%d" % p.port if p.port else "")
    safe = "/:@!$&'()*+,;=%~"
    return urlunsplit((p.scheme, netloc, quote(p.path, safe=safe), quote(p.query, safe=safe + "?"),
                       quote(p.fragment, safe=safe)))


def get(url, max_bytes=8000000, timeout=20, accept="*/*", ua=None, public_only=False):
    """Return (final_url, content_type, body_bytes) or raise FetchError.

    public_only: refuse local-network addresses (see ALLOW_PRIVATE).
    """
    if not url.lower().startswith(("http://", "https://")):
        raise FetchError("not an http(s) address")
    try:
        url = iri_to_uri(url)
    except (UnicodeError, ValueError):
        raise FetchError("unusable address")
    if public_only and not ALLOW_PRIVATE and not is_public(url):
        raise FetchError("not a public internet address")
    ua = ua or (BROWSER_UA if _browser else UA)
    try:
        return _get(url, max_bytes, timeout, accept, "gzip, deflate", ua, public_only)
    except _Undecodable:
        # Some CDNs answer with Brotli no matter what we ask for; the
        # standard library cannot decode it, so ask for plain bytes.
        return _get(url, max_bytes, timeout, accept, "identity", ua, public_only)


_OPENER = urllib.request.build_opener(_Guard, urllib.request.HTTPSHandler(context=_CTX))


def _get(url, max_bytes, timeout, accept, encoding, ua, public_only=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Encoding": encoding + (", br" if brotli is not None and encoding != "identity" else ""),
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    })
    try:
        req.public_only = public_only
        with _OPENER.open(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise FetchError("larger than %d MB" % (max_bytes // 1000000))
            enc = (r.headers.get("Content-Encoding") or "").lower().strip()
            if enc == "br" and brotli is not None:
                try:
                    data = brotli.decompress(data)
                except brotli.error:
                    raise FetchError("broken Brotli response")
                if len(data) > max_bytes:
                    raise FetchError("larger than %d MB" % (max_bytes // 1000000))
                enc = "identity"
            if enc not in ("", "identity", "gzip", "x-gzip", "deflate"):
                if encoding == "identity":
                    raise FetchError("server insists on %s compression" % enc)
                raise _Undecodable()
            if enc in ("gzip", "x-gzip", "deflate"):
                d = zlib.decompressobj(47)  # 32+15: auto-detect gzip/zlib
                data = d.decompress(data, max_bytes + 1)
                if len(data) > max_bytes:
                    raise FetchError("larger than %d MB" % (max_bytes // 1000000))
            return r.geturl(), r.headers.get_content_type(), data
    except urllib.error.HTTPError as e:
        raise FetchError("HTTP %d" % e.code)
    except urllib.error.URLError as e:
        raise FetchError(_reason(e.reason))
    except (socket.timeout, TimeoutError):
        raise FetchError("timed out")
    except (http.client.HTTPException, ConnectionError, ssl.SSLError, UnicodeError,
            zlib.error, ValueError, OSError) as e:
        raise FetchError(_reason(e))


def _reason(r):
    s = str(r) or r.__class__.__name__
    if "timed out" in s:
        return "timed out"
    if "Name or service not known" in s or "nodename nor servname" in s:
        return "host not found"
    return s[:120]
