#!/bin/sh
# Ship Matutino to the Debian box and (re)start its container. Run on the Mac:
#
#   ./deploy.sh you@192.168.1.10                # finds Kavita's library folder itself
#   ./deploy.sh you@192.168.1.10 /srv/media/books   # or name it
#
# Use user@address if your server login differs from this Mac's. You type your
# server password for the copy and the login. Docker needs root unless your
# account is in the docker group: it then uses sudo if you have it, otherwise
# it asks for the server's ROOT password (su).
set -eu

HOST=${1:?usage: deploy.sh [user@]server-address [kavita-library-folder]}
KAVITA=${2:-}
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' matutino/__init__.py)
PKG="matutino-$VERSION.tar.gz"

mkdir -p dist
COPYFILE_DISABLE=1 tar czf "dist/$PKG" --no-xattrs --no-mac-metadata --exclude __pycache__ --exclude '*.pyc' \
    Dockerfile docker-compose.yml requirements.txt README.md install.sh matutino
echo "Built dist/$PKG"

scp "dist/$PKG" "$HOST:/tmp/$PKG"
# Quote the folder for the remote shell (it may contain spaces).
QK="'$(printf '%s' "$KAVITA" | sed "s/'/'\\\\''/g")'"
# The source unpacks into the login's home, so no root is needed for that.
# -t so sudo or su can ask for a password.
ssh -t "$HOST" "set -e
rm -rf \"\$HOME/matutino-src\"; mkdir -p \"\$HOME/matutino-src\"
tar xzf /tmp/$PKG -C \"\$HOME/matutino-src\"; rm -f /tmp/$PKG
INSTALL=\"\$HOME/matutino-src/install.sh\"
if docker info >/dev/null 2>&1; then
  sh \"\$INSTALL\" $QK
elif sudo -n true 2>/dev/null || id -nG | tr ' ' '\n' | grep -qx sudo; then
  sudo sh \"\$INSTALL\" $QK
else
  echo 'Docker needs root on this server. Enter the ROOT password:'
  su -c \"sh '\$INSTALL' $QK\" root
fi"
echo "Open http://${HOST#*@}:8771/desk"
