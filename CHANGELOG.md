# Changelog

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
