"""The paper's sections: their order, their special jobs, and name matching.

A section's job comes from its name, so renaming "Funnies" to "Comics"
keeps it a comics page:

  front     feeds the front page's lead story and right-hand column
  breaking  prints as a band across the top of the front page
  weather   carries the forecast box
  variety   carries the "On this day" box
  funnies / opinion   never chosen for the front page
"""

import re

DEFAULT = [
    "Front Page", "Breaking News", "Local News", "World News", "Business", "Technology",
    "Science", "Health", "Entertainment", "Sports", "Opinion", "Variety", "Travel & Food",
    "Weather", "Funnies",
]

# Typed name -> section names to try, first one on the paper's list wins.
ALIASES = {
    "front": ["Front Page"], "top": ["Front Page"], "top stories": ["Front Page"],
    "breaking": ["Breaking News"], "news": ["Local News"], "local": ["Local News"],
    "world": ["World News"], "international": ["World News"], "international news": ["World News"],
    "international world news": ["World News"], "world international news": ["World News"],
    "business": ["Business", "Local Business"], "economy": ["Business", "Local Business"],
    "world business": ["International Business", "Business"], "tech": ["Technology"],
    "science": ["Science", "Science News"], "crypto": ["Crypto & Markets", "Business"],
    "markets": ["Crypto & Markets", "Business"], "property": ["Real Estate"],
    "comics": ["Funnies"], "comic": ["Funnies"], "cartoons": ["Funnies"],
    "sport": ["Sports", "Sports News"], "sports": ["Sports", "Sports News"],
    "weather": ["Weather", "Local Weather"], "travel": ["Travel & Food"], "food": ["Travel & Food"],
    "variety": ["Variety", "Variety News"], "editorial": ["Opinion"], "editorials": ["Opinion"],
    "columns": ["Opinion"], "pr": ["Puerto Rico News"], "pr business": ["Puerto Rico Business"],
}


def norm(s):
    s = (s or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip().replace(" and ", " ")


def role(name):
    n = norm(name)
    if "front" in n:
        return "front"
    if "breaking" in n:
        return "breaking"
    if "weather" in n:
        return "weather"
    if "variety" in n:
        return "variety"
    if "funn" in n or "comic" in n or "cartoon" in n:
        return "funnies"
    if "opinion" in n or "editorial" in n:
        return "opinion"
    return ""


def match(name, sections):
    """Map a typed or pasted section name onto the paper's list, or None."""
    n = norm(name)
    if not n:
        return None
    for s in sections:
        if norm(s) == n:
            return s
    for alias in ALIASES.get(n, []):
        if alias in sections:
            return alias
    for s in sections:
        if norm(s).startswith(n + " "):
            return s
    return None


def resolve(name, sections, default):
    """Section for a pasted feed: a list match, else the name as typed, else the default."""
    name = (name or "").strip()
    return match(name, sections) or (name[:40] if name and name.lower() != "news" else default)


def order(names, sections):
    """Sort section names by the paper's list; unknown ones keep their order at the end."""
    known = {s: i for i, s in enumerate(sections)}
    return sorted(dict.fromkeys(names), key=lambda s: (known.get(s, len(known)), ))
