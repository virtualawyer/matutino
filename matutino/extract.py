"""Full-text extraction from an article page, via trafilatura.

trafilatura is the one third-party dependency. Without it Matutino still
works and prints whatever the feed itself carries.
"""

try:
    import trafilatura
except ImportError:  # pragma: no cover - exercised only on stdlib installs
    trafilatura = None

AVAILABLE = trafilatura is not None


def article(page_bytes, url):
    """Return {"html", "image", "author", "site"} or None."""
    if trafilatura is None or not page_bytes:
        return None
    try:
        body = trafilatura.extract(
            page_bytes, url=url, output_format="html", include_images=True,
            include_links=True, include_comments=False, include_tables=True,
            favor_precision=True)
        meta = trafilatura.extract_metadata(page_bytes, default_url=url)
    except Exception:
        return None
    if not body:
        return None
    return {
        "html": body,
        "image": getattr(meta, "image", None) if meta else None,
        "author": (getattr(meta, "author", None) or "") if meta else "",
        "site": (getattr(meta, "sitename", None) or "") if meta else "",
    }
