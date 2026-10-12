# Changelog

## 0.5.0 (2026-10-12)

- A desktop app for macOS (Apple silicon and Intel) and Windows: the whole
  paper on your own computer, no server needed. It lives in the menu bar or the
  notification area, opens at login if you like, prints a missed issue as soon
  as the computer wakes, and files each EPUB in Documents/Matutino. The apps are
  unsigned; the README says how to open them the first time.
- On your home screen: the paper has an icon and a web-app manifest named after
  your paper, and a button in its top strip installs it or says how.
- A reading-app catalog (OPDS) at `/opds`: Librera, Readest, KOReader and other
  readers subscribe once and get each issue as an EPUB. The desk shows the
  address, and the README walks through Librera and Readest.
- The server can be told which host names to answer to; the desktop app uses
  this so a web page can't reach it through DNS tricks.
- Issues are read and written as UTF-8 explicitly (for Windows).

## 0.4.0 (2026-10-12)

- Section names print in the paper's language: on a Spanish paper the usual
  sections show as Portada, Última hora, Internacional, Tiras cómicas and so
  on, in the section menu, headings, story kickers and the EPUB.
- Printed names of your own: `World News = Mundo` on the desk's section list
  prints a section under any name while its feeds and its job stay the same.
- Spanish section names do the jobs too (Portada, Clima, Tiras cómicas...),
  pasted `# Mundo` headings find their sections, and matching ignores accents.
- Eleven more languages, the rest of those Wikipedia publishes *On this day*
  in: German, French, Portuguese, Italian, Swedish, Russian, Ukrainian,
  Bosnian, Turkish, Arabic and Chinese. Each covers dates, labels, weather and
  section names; regional codes such as `pt-BR` use their base language.
- Arabic papers are laid out right to left on the web and in the EPUB;
  stories keep their own direction.
- Language packs: drop `<code>.json` into the data folder's `languages/` to add
  a language or change a word; broken labels fall back to English.
- The desk's Language setting is now a list of the languages the paper speaks.

## 0.3.0 (2026-10-11): first public release

- Feeds in, a daily newspaper out: a broadsheet web paper (front page, sections,
  breaking band, editions gallery, night edition) and an EPUB per issue,
  optionally filed into a Kavita library as one series.
- Full-text extraction with trafilatura; feed text as the fallback.
- Pictures stored with each issue and scaled to 1400 px; reading never
  contacts the outside world.
- Sections with jobs: Front Page, Breaking News, Weather (Open-Meteo),
  Variety (On this day, Wikipedia), Funnies, Opinion.
- Paper and EPUB in English or Spanish.
- Paste feeds, site addresses or calibre-recipe tuples; `# Section` lines;
  feed packs for English and Costa Rica / Puerto Rico (Spanish).
- Safety: allowlist HTML cleaner and CSP; no local-network fetches from feed
  content (redirects included); JSON-only actions; optional password.
- Honest User-Agent by default, browser identification as an opt-in.
- Separate issue library (another drive), with an unmounted-drive guard for
  both the library and the Kavita folder; low-disk guard.
