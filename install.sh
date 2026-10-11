#!/bin/sh
# Build and (re)start the Matutino container. Runs ON the server, as root or
# as a user in the docker group:
#
#   sh install.sh                       # finds Kavita's library folder itself
#   sh install.sh /srv/media/Books      # or name it
#
# deploy.sh (on the Mac) copies this package over and runs it for you.
set -eu
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' matutino/__init__.py)
KAVITA=${1:-}

if [ -z "$KAVITA" ]; then
  NAME=$(docker ps --format '{{.Names}} {{.Image}}' | grep -i kavita | head -n 1 | cut -d' ' -f1 || true)
  if [ -z "$NAME" ]; then
    echo "No running Kavita container found. Name the library folder instead:"
    echo "  sh install.sh /path/to/your/kavita/library"
    exit 1
  fi
  MOUNTS=$(docker inspect -f '{{range .Mounts}}{{.Source}}|{{.Destination}}{{println}}{{end}}' "$NAME" | grep '|' || true)
  # Kavita's own config folder is not a library.
  LIBS=$(printf '%s\n' "$MOUNTS" | grep -v -i '|[^|]*config' | grep . || true)
  if [ "$(printf '%s\n' "$LIBS" | grep -c . || true)" -eq 1 ]; then
    KAVITA=$(printf '%s' "$LIBS" | cut -d'|' -f1)
    echo "Kavita ($NAME) reads $KAVITA (it sees it as $(printf '%s' "$LIBS" | cut -d'|' -f2))."
  else
    echo "Kavita ($NAME) reads these folders (server path -> Kavita path):"
    printf '%s\n' "$MOUNTS" | sed 's/|/  ->  /; s/^/  /'
    echo "Run again with the server path of the one your Book library uses:"
    echo "  ./deploy.sh <server> /that/server/path   (from the Mac)"
    exit 1
  fi
fi

if [ ! -d "$KAVITA" ]; then
  echo "No folder $KAVITA on this server -- check the path."
  exit 1
fi

if [ "${MATUTINO_DRY_RUN:-}" = 1 ]; then
  echo "DRY RUN: would start matutino:$VERSION filing EPUBs in $KAVITA"
  exit 0
fi

# Printed issues (pictures) go on the same drive as the Kavita library, next
# to it; the database stays in /opt/matutino on the root disk, since the
# media drive is exFAT and SQLite needs real file locking.
LIBRARY=${MATUTINO_LIBRARY:-$(dirname "$KAVITA")/matutino}
# The server's own time zone (the paper's default until set on the desk).
ZONE=${TZ:-$(cat /etc/timezone 2>/dev/null || echo UTC)}
mkdir -p "$LIBRARY" 2>/dev/null || true
# As root this creates the data folder; as a docker-group user Docker creates
# it on first run (bind-mount sources are made by the daemon, as root).
mkdir -p /opt/matutino 2>/dev/null || true
echo "Building matutino:$VERSION (first time takes a few minutes)..."
docker build -q -t "matutino:$VERSION" . >/dev/null
docker rm -f matutino >/dev/null 2>&1 || true
docker run -d --name matutino --restart unless-stopped -p 8771:8771 \
  -v /opt/matutino:/config -v "$LIBRARY":/issues -v "$KAVITA":/kavita \
  -e MATUTINO_ISSUES=/issues -e MATUTINO_EPUB_DIR=/kavita -e TZ="$ZONE" \
  --cpus 1.0 --memory 512m "matutino:$VERSION" >/dev/null
sleep 3
docker logs --tail 5 matutino
echo
echo "Matutino $VERSION is running. Issues: $LIBRARY  EPUBs: a folder in $KAVITA (shown on the desk)"
echo "Make sure a Kavita library covers that folder (Kavita > Settings > Libraries)."
