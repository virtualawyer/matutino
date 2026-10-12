"""The paper's own words -- labels, dates, weather, section names -- in many languages.

Stories print in whatever language their feeds use; this covers the paper
around them, chosen by the Language setting ("de", "pt-BR" -> Portuguese,
anything unknown -> English). English and Spanish live here; the other
languages are packs in matutino/languages/<code>.json, and a pack dropped
into the data folder's languages/ directory adds or overrides one without
touching the code. The desk stays in English.

A pack holds: name, dir ("ltr"/"rtl"), strings (every key English has),
days (Monday first), months, optional months_gen and mon (short months),
optional day1 ("1er"), and patterns for long / day_month / month_day / time /
stamp built from {weekday} {day} {month} {month_gen} {mon} {m} {year} and,
for time, {h} {H} {HH} {MM} {ampm} (with an ampm pair).
"""

import datetime
import glob
import json
import os
import re

STRINGS = {
    "en": {
        "today": "Today", "editions": "Editions", "desk": "Desk", "night": "Night edition",
        "no": "No. %d", "stories_sources": "%d stories &middot; %d sources", "n_stories": "%d stories",
        "printed": "Printed %s", "by": "By %s", "min_read": "%d min read", "continue": "Continue reading",
        "breaking": "Breaking", "more_top": "More top stories", "back_top": "Back to top",
        "printed_by": "Printed by Matutino at %s", "download_epub": "Download EPUB",
        "all_editions": "All editions", "front_page": "Front page", "previous": "Previous", "next": "Next",
        "back_front": "Back to the front", "end_paper": "End of the paper", "read_at": "Read at %s",
        "the_source": "the source",
        "excerpt": "This is the excerpt the publisher puts in its feed. The full story is at %s.",
        "on_file": "%d on file", "latest": "Latest", "no_editions": "No editions yet.",
        "go_desk": "Go to the desk", "awaiting": "Awaiting the first edition",
        "running": "The presses are running. Refresh in a minute.",
        "no_issue": "No issue has been printed yet. Add your feeds at the desk, then print the first edition.",
        "not_found": "That page is not in this paper.", "todays_paper": "Today’s paper",
        "rain": "Rain", "wind": "Wind", "uv": "UV index", "sun": "Sun", "rain_pct": "rain %s%%",
        "chance_rain": "Chance of rain", "forecast": "Forecast for %s, at press time &middot; Open-Meteo",
        "otd": "On this day &middot; %s", "otd_credit": "From Wikipedia, CC BY-SA",
        "free_software": "Free software (AGPL)", "source": "Source",
        # EPUB
        "contents": "Contents", "start": "Start reading", "original": "Original:",
        "only_excerpt": "The publisher’s feed carries only this excerpt.",
        "sun_times": "Sunrise %s, sunset %s. Open-Meteo, at press time.",
        "forecast_for": "Forecast for %s", "otd_title": "On this day, %s",
    },
    "es": {
        "today": "Hoy", "editions": "Ediciones", "desk": "Redacción", "night": "Edición nocturna",
        "no": "N.º %d", "stories_sources": "%d noticias &middot; %d fuentes", "n_stories": "%d noticias",
        "printed": "Impreso a las %s", "by": "Por %s", "min_read": "%d min de lectura",
        "continue": "Seguir leyendo", "breaking": "Última hora", "more_top": "Más noticias destacadas",
        "back_top": "Volver arriba", "printed_by": "Impreso por Matutino a las %s",
        "download_epub": "Descargar EPUB", "all_editions": "Todas las ediciones", "front_page": "Portada",
        "previous": "Anterior", "next": "Siguiente", "back_front": "Volver a la portada",
        "end_paper": "Fin del periódico", "read_at": "Leer en %s", "the_source": "la fuente",
        "excerpt": "Este es el extracto que el medio publica en su feed. La nota completa está en %s.",
        "on_file": "%d en archivo", "latest": "Última", "no_editions": "Aún no hay ediciones.",
        "go_desk": "Ir a la redacción", "awaiting": "Esperando la primera edición",
        "running": "Las prensas están funcionando. Actualice en un minuto.",
        "no_issue": ("Aún no se ha impreso ninguna edición. Agregue sus feeds en la redacción "
                     "y luego imprima la primera edición."),
        "not_found": "Esa página no está en este periódico.", "todays_paper": "El periódico de hoy",
        "rain": "Lluvia", "wind": "Viento", "uv": "Índice UV", "sun": "Sol", "rain_pct": "lluvia %s%%",
        "chance_rain": "Probabilidad de lluvia",
        "forecast": "Pronóstico para %s, al cierre de edición &middot; Open-Meteo",
        "otd": "Tal día como hoy &middot; %s", "otd_credit": "De Wikipedia, CC BY-SA",
        "free_software": "Software libre (AGPL)", "source": "Código fuente",
        "contents": "Contenido", "start": "Empezar a leer", "original": "Original:",
        "only_excerpt": "El feed del medio solo trae este extracto.",
        "sun_times": "Amanecer %s, atardecer %s. Open-Meteo, al cierre de edición.",
        "forecast_for": "Pronóstico para %s", "otd_title": "Tal día como hoy, %s",
    },
}

DAYS = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]}
MONTHS = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                 "October", "November", "December"],
          "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                 "octubre", "noviembre", "diciembre"]}

# What the usual sections print as. A section keeps its stored name (its feeds and its job
# follow that name); these only change what the paper shows. The desk can override any of
# them per section ("World News = Mundo"), which also covers names not listed here.
SECTION_NAMES = {
    "es": {
        "Front Page": "Portada", "Breaking News": "Última hora", "Local News": "Noticias locales",
        "World News": "Internacional", "International News": "Internacional",
        "Puerto Rico News": "Puerto Rico", "Business": "Economía", "Local Business": "Negocios locales",
        "Puerto Rico Business": "Negocios de Puerto Rico", "International Business": "Negocios internacionales",
        "Crypto & Markets": "Cripto y mercados", "Real Estate": "Bienes raíces", "Technology": "Tecnología",
        "Science": "Ciencia", "Science News": "Ciencia", "Health": "Salud", "Entertainment": "Entretenimiento",
        "Sports": "Deportes", "Sports News": "Deportes", "Opinion": "Opinión", "Variety": "Variedades",
        "Variety News": "Variedades", "Travel & Food": "Viajes y gastronomía", "Weather": "Clima",
        "Local Weather": "Clima", "Funnies": "Tiras cómicas", "Comics": "Tiras cómicas",
    },
}

WEATHER_ES = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado", 45: "Niebla",
    48: "Niebla helada", 51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna intensa", 56: "Llovizna helada",
    57: "Llovizna helada", 61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia intensa", 66: "Lluvia helada",
    67: "Lluvia helada", 71: "Nevada ligera", 73: "Nevada", 75: "Nevada intensa", 77: "Granos de nieve",
    80: "Chubascos", 81: "Chubascos fuertes", 82: "Chubascos violentos", 85: "Chubascos de nieve",
    86: "Chubascos de nieve", 95: "Tormentas", 96: "Tormentas con granizo", 99: "Tormentas con granizo",
}


# Packs for the two built-in languages, from the tables above.
LANGS = {
    "en": {"name": "English", "dir": "ltr", "strings": STRINGS["en"], "days": DAYS["en"], "months": MONTHS["en"],
           "long": "{weekday}, {month} {day}, {year}", "day_month": "{weekday}, {mon} {day}",
           "month_day": "{month} {day}", "time": "{h}:{MM} {ampm}", "ampm": ["a.m.", "p.m."],
           "stamp": "{mon} {day}, {time}", "weather": {}, "sections": {}},
    "es": {"name": "Español", "dir": "ltr", "strings": STRINGS["es"], "days": DAYS["es"], "months": MONTHS["es"],
           "long": "{weekday}, {day} de {month} de {year}", "day_month": "{weekday}, {day} {mon}",
           "month_day": "{day} de {month}", "time": "{h}:{MM} {ampm}", "ampm": ["a. m.", "p. m."],
           "stamp": "{day} {mon}, {time}", "weather": {str(k): v for k, v in WEATHER_ES.items()},
           "sections": SECTION_NAMES["es"]},
}
REQUIRED = ("strings", "days", "months", "long", "day_month", "month_day", "time", "stamp")


def load_dir(path):
    """Add (or override) language packs from <path>/<code>.json; returns the codes loaded."""
    loaded = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        code = os.path.splitext(os.path.basename(f))[0].lower()
        try:
            with open(f, encoding="utf-8") as fh:
                pack = json.load(fh)
            missing = [k for k in REQUIRED if k not in pack]
            if missing or len(pack["days"]) != 7 or len(pack["months"]) != 12:
                raise ValueError("needs %s, 7 days and 12 months" % ", ".join(REQUIRED))
            _check_patterns(pack)
        except (OSError, ValueError) as e:
            print("language pack %s skipped: %s" % (f, e), flush=True)
            continue
        pack.setdefault("name", code)
        pack.setdefault("dir", "ltr")
        own = {}
        for k, v in pack["strings"].items():
            if k in STRINGS["en"] and not (isinstance(v, str) and _holes(v) == _holes(STRINGS["en"][k])):
                print("language pack %s: %s ignored, it must keep %s" % (f, k, " ".join(_holes(STRINGS["en"][k])) or "no % codes"),
                      flush=True)
                continue
            own[k] = v
        pack["strings"] = dict(STRINGS["en"], **own)  # a missing or broken label falls back to English
        pack.setdefault("weather", {})
        pack.setdefault("sections", {})
        LANGS[code] = pack
        STRINGS[code] = pack["strings"]
        loaded.append(code)
    return loaded


def _holes(text):
    return sorted(re.findall(r"%[^%]|%%", text))


def _check_patterns(pack):
    """Raise ValueError if a date or time pattern names a field that doesn't exist."""
    try:
        f = _fields(datetime.date(2026, 1, 1), pack)
        for k in ("long", "day_month", "month_day"):
            pack[k].format(**f)
        pack["stamp"].format(time="", **f)
        pack["time"].format(h=1, H=1, HH="01", MM="05", ampm="")
    except (KeyError, IndexError, AttributeError, TypeError, ValueError) as e:
        raise ValueError("bad date or time pattern (%s)" % e)


def languages():
    """(code, native name) for every language the paper speaks, English and Spanish first."""
    rest = sorted((c for c in LANGS if c not in ("en", "es")), key=lambda c: LANGS[c]["name"].lower())
    return [(c, LANGS[c]["name"]) for c in ["en", "es"] + rest]


def lang_of(code):
    base = (code or "").strip().lower().replace("_", "-").split("-")[0]
    return base if base in LANGS else "en"


def pack(code):
    return LANGS[lang_of(code)]


def strings(code):
    return pack(code)["strings"]


def direction(code):
    return pack(code).get("dir", "ltr")


def section_name(name, code="en", custom=None):
    """What a section prints as: the desk's own name for it, else the language's usual name."""
    if custom and custom.get(name):
        return custom[name]
    return pack(code).get("sections", {}).get(name, name)


def _date(date):
    return datetime.date(*[int(x) for x in date.split("-")]) if isinstance(date, str) else date


def _fields(d, P):
    months = P["months"]
    return {"weekday": P["days"][d.weekday()], "day": P.get("day1") if d.day == 1 and P.get("day1") else str(d.day),
            "month": months[d.month - 1], "month_gen": (P.get("months_gen") or months)[d.month - 1],
            "mon": (P.get("mon") or [m[:3] for m in months])[d.month - 1], "m": d.month, "year": d.year}


def long_date(date, code="en"):
    """'Sunday, October 11, 2026' / 'domingo, 11 de octubre de 2026' / 'Sonntag, 11. Oktober 2026'."""
    P = pack(code)
    return P["long"].format(**_fields(_date(date), P))


def day_month(date, code="en"):
    """'Sunday, Oct 11' / 'domingo, 11 oct' (the editions gallery)."""
    P = pack(code)
    return P["day_month"].format(**_fields(_date(date), P))


def month_day(date, code="en"):
    """'October 11' / '11 de octubre' (On this day)."""
    P = pack(code)
    return P["month_day"].format(**_fields(_date(date), P))


def weekday(date, code="en"):
    return pack(code)["days"][_date(date).weekday()]


def hm(hour, minute, code="en"):
    """'8:05 p.m.' / '8:05 p. m.' / '20:05 Uhr'."""
    P = pack(code)
    ampm = P.get("ampm") or ["", ""]
    return P["time"].format(h=hour % 12 or 12, H=hour, HH="%02d" % hour, MM="%02d" % minute,
                            ampm=ampm[0 if hour < 12 else 1]).strip()


def stamp(dt, code="en"):
    """'Oct 11, 8:05 p.m.' / '11 oct, 8:05 p. m.' for a datetime."""
    P = pack(code)
    return P["stamp"].format(time=hm(dt.hour, dt.minute, code), **_fields(dt.date(), P))


def weather(code, english, lang_code="en"):
    return pack(lang_code).get("weather", {}).get(str(code)) or english


load_dir(os.path.join(os.path.dirname(__file__), "languages"))
