# Matutino -- RSS feeds in, a daily broadsheet (web + EPUB for Kavita) out.

FROM python:3.12-slim-bookworm

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY matutino/ /app/matutino/

# /config holds the SQLite database and the printed issues. Map it to a
# normal Linux filesystem (ext4), never the exFAT media drive: exFAT has no
# file locking and SQLite corrupts on it.
VOLUME ["/config"]

# EPUBs for Kavita are off unless MATUTINO_EPUB_DIR names a mounted folder
# (the compose file and install.sh use /kavita). /kavita is deliberately not a
# VOLUME: an anonymous volume would swallow EPUBs nobody reads.
ENV MATUTINO_DATA=/config \
    MATUTINO_PORT=8771 \
    PYTHONUNBUFFERED=1

EXPOSE 8771

HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8771/healthz', timeout=8)" || exit 1

CMD ["python3", "-m", "matutino"]
