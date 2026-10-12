"""The paper's own words -- labels, dates, weather -- in English and Spanish.

Stories print in whatever language their feeds use; this covers the
paper around them, chosen by the Language setting ("es", "es-CR" -> Spanish,
anything else -> English), including the names the usual sections print
under. The desk stays in English.
"""

import datetime

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


def lang_of(code):
    return "es" if (code or "").lower().startswith("es") else "en"


def strings(code):
    return STRINGS[lang_of(code)]


def section_name(name, code="en", custom=None):
    """What a section prints as: the desk's own name for it, else the language's usual name."""
    if custom and custom.get(name):
        return custom[name]
    return SECTION_NAMES.get(lang_of(code), {}).get(name, name)


def _date(date):
    return datetime.date(*[int(x) for x in date.split("-")]) if isinstance(date, str) else date


def long_date(date, code="en"):
    """'Sunday, October 11, 2026' / 'domingo, 11 de octubre de 2026'."""
    d, lang = _date(date), lang_of(code)
    day, month = DAYS[lang][d.weekday()], MONTHS[lang][d.month - 1]
    if lang == "es":
        return "%s, %d de %s de %d" % (day, d.day, month, d.year)
    return "%s, %s %d, %d" % (day, month, d.day, d.year)


def day_month(date, code="en"):
    """'Sunday, Oct 11' / 'domingo, 11 oct' (the editions gallery)."""
    d, lang = _date(date), lang_of(code)
    day, month = DAYS[lang][d.weekday()], MONTHS[lang][d.month - 1][:3]
    return "%s, %d %s" % (day, d.day, month) if lang == "es" else "%s, %s %d" % (day, month, d.day)


def month_day(date, code="en"):
    """'October 11' / '11 de octubre'."""
    d, lang = _date(date), lang_of(code)
    month = MONTHS[lang][d.month - 1]
    return "%d de %s" % (d.day, month) if lang == "es" else "%s %d" % (month, d.day)


def weekday(date, code="en"):
    return DAYS[lang_of(code)][_date(date).weekday()]


def hm(hour, minute, code="en"):
    """'8:05 p.m.' / '8:05 p. m.'"""
    es = lang_of(code) == "es"
    suffix = ("a. m." if hour < 12 else "p. m.") if es else ("a.m." if hour < 12 else "p.m.")
    return "%d:%02d %s" % (hour % 12 or 12, minute, suffix)


def stamp(dt, code="en"):
    """'Oct 11, 8:05 p.m.' / '11 oct, 8:05 p. m.' for a datetime."""
    lang = lang_of(code)
    month = MONTHS[lang][dt.month - 1][:3]
    when = hm(dt.hour, dt.minute, code)
    return "%d %s, %s" % (dt.day, month, when) if lang == "es" else "%s %d, %s" % (month, dt.day, when)


def weather(code, english, lang_code="en"):
    if lang_of(lang_code) == "es":
        return WEATHER_ES.get(code, english)
    return english
