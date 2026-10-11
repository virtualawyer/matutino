"""Data boxes printed without feeds: the weather and "On this day".

Both come from free, keyless public APIs (Open-Meteo, Wikipedia) and are
fetched once at print time. A failure leaves the box out of that issue;
it never stops the paper.
"""

import json
import re
from urllib.parse import urlencode

from . import fetch

UA = fetch.UA  # always honest towards these free services
# Module-level so the tests can point them at a local server.
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search?"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast?"
OTD_URL = "https://%s.wikipedia.org/api/rest_v1/feed/onthisday/selected/%02d/%02d"

# WMO weather interpretation codes -> (short description, icon name)
WMO = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "sun"), 2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"), 45: ("Fog", "fog"), 48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Heavy drizzle", "drizzle"),
    56: ("Freezing drizzle", "drizzle"), 57: ("Freezing drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Heavy showers", "rain"), 82: ("Violent showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorms", "storm"), 96: ("Storms, hail", "storm"), 99: ("Storms, hail", "storm"),
}
OTD_LANGS = {"en", "de", "fr", "sv", "pt", "ru", "es", "ar", "bs", "uk", "it", "tr", "zh"}


PHOTO_NOTE = re.compile(r"\s*\((?:[^()]*\s)?(?:pictured|en la imagen|en la foto(?:graf\u00eda)?|"
                        r"en la ilustraci\u00f3n|na imagem|im Bild|en photo)\)", re.I)


class BoxError(Exception):
    pass


def _json(url, ua=UA):
    try:
        _, _, body = fetch.get(url, max_bytes=2000000, timeout=15, accept="application/json", ua=ua)
        return json.loads(body.decode("utf-8"))
    except (fetch.FetchError, ValueError) as e:
        raise BoxError(str(e) or "unreadable reply")


def geocode(place):
    """'Springfield, Illinois' -> {"name", "lat", "lon"}; qualifiers pick between towns."""
    parts = [p.strip() for p in (place or "").split(",") if p.strip()]
    if not parts:
        raise BoxError("No place given.")
    data = _json(GEO_URL +
                 urlencode({"name": parts[0], "count": 10, "language": "en"}))
    results = data.get("results") or []
    quals = [q.lower() for q in parts[1:]]
    for r in results:
        hay = " ".join(str(r.get(k) or "") for k in ("admin1", "admin2", "country", "country_code")).lower()
        if all(q in hay for q in quals):
            label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
            return {"name": label, "lat": round(r["latitude"], 4), "lon": round(r["longitude"], 4)}
    raise BoxError("Couldn't find %s. Try adding the country, e.g. \"Springfield, Illinois\"." % place)


def weather(lat, lon, tz_name, place):
    q = urlencode({
        "latitude": lat, "longitude": lon, "timezone": tz_name, "forecast_days": 4,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "precipitation_sum,wind_speed_10m_max,uv_index_max,sunrise,sunset",
    })
    d = _json(FORECAST_URL + q).get("daily") or {}
    days = []
    for i, date in enumerate(d.get("time") or []):
        def v(k, cast=float):
            seq = d.get(k) or []
            return cast(seq[i]) if i < len(seq) and seq[i] is not None else None
        code = v("weather_code", int)
        desc, icon = WMO.get(code, ("", "cloud"))
        days.append({
            "date": date, "code": code, "desc": desc, "icon": icon,
            "hi": v("temperature_2m_max"), "lo": v("temperature_2m_min"),
            "rain_pct": v("precipitation_probability_max", int), "rain_mm": v("precipitation_sum"),
            "wind": v("wind_speed_10m_max"), "uv": v("uv_index_max"),
            "sunrise": (v("sunrise", str) or "")[11:16], "sunset": (v("sunset", str) or "")[11:16],
        })
    if not days or days[0]["hi"] is None:
        raise BoxError("no forecast in the reply")
    return {"place": place, "days": days}


def on_this_day(month, day, lang="en", limit=6):
    lang = lang if lang in OTD_LANGS else "en"
    data = _json(OTD_URL % (lang, month, day))
    events = []
    for e in data.get("selected") or []:
        if not e.get("text") or e.get("year") is None:
            continue
        pages = e.get("pages") or []
        link = ""
        if pages:
            link = ((pages[0].get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        # "(aftermath pictured)" / "(en la imagen)" point at Wikipedia's photo,
        # which we don't print.
        text = PHOTO_NOTE.sub("", e["text"]).strip()
        events.append({"year": int(e["year"]), "text": text, "link": link})
    if not events:
        raise BoxError("no events in the reply")
    events.sort(key=lambda e: -e["year"])
    if len(events) > limit:  # spread across the centuries rather than the latest few
        step = (len(events) - 1) / float(limit - 1)
        events = [events[int(round(i * step))] for i in range(limit)]
    return {"lang": lang, "events": events}


def c_to_f(c):
    return None if c is None else c * 9.0 / 5.0 + 32


# Engraving-style glyphs: one stroke weight, currentColor, 24x24.
ICONS = {
    "sun": '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.6M12 18.9v2.6M2.5 12h2.6M18.9 12h2.6'
           'M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
    "partly": '<path d="M8.5 3.2v1.9M3.2 8.5h1.9M4.7 4.7l1.3 1.3M12.3 4.7 11 6"/><path d="M5.6 11.2a3.4 3.4 0 1 1 6-3"/>'
              '<path d="M8 19.5h10a3.3 3.3 0 0 0 .4-6.6 5 5 0 0 0-9.6 1.3A2.7 2.7 0 0 0 8 19.5z"/>',
    "cloud": '<path d="M6.5 18.5h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6A3.2 3.2 0 0 0 6.5 18.5z"/>',
    "fog": '<path d="M6.5 13.5h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6"/><path d="M3.5 16.5h17M5.5 19.5h13M7.5 22h9"/>',
    "drizzle": '<path d="M6.5 15h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6A3.2 3.2 0 0 0 6.5 15z"/>'
               '<path d="M8 18v1M12 18v1M16 18v1M10 21v1M14 21v1"/>',
    "rain": '<path d="M6.5 14.5h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6A3.2 3.2 0 0 0 6.5 14.5z"/>'
            '<path d="M8.5 17l-1.2 3M12.5 17l-1.2 3M16.5 17l-1.2 3"/>',
    "storm": '<path d="M6.5 14.5h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6A3.2 3.2 0 0 0 6.5 14.5z"/>'
             '<path d="M12.8 15.5l-2.3 3.6h3l-2.2 3.4"/>',
    "snow": '<path d="M6.5 14.5h11a4 4 0 0 0 .5-8 6 6 0 0 0-11.6 1.6A3.2 3.2 0 0 0 6.5 14.5z"/>'
            '<path d="M8.5 18.5h.01M12 18.5h.01M15.5 18.5h.01M10.2 21.3h.01M13.8 21.3h.01"/>',
}


def icon(name, size=24, cls="wx"):
    return ('<svg class="%s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
            % (cls, size, size, ICONS.get(name, ICONS["cloud"])))
