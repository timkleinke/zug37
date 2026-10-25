#!/usr/bin/env bash
# Zug 37 on the MIF server. Run as root from a clean checkout of this repo.
#
#   ./install.sh          install or update: user, code, units, deploy key, env file, feed path, nginx
#   ./install.sh start    after the token is in /etc/zug37.env and the deploy key is on GitHub:
#                         clone the logbook, render once, enable the timers
#
# Never prints the token. The random feed path is printed once for the TickrMeter app and stays in
# /etc/zug37.env and the nginx snippet (both 0600), not in the repo.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/zug37
HOMEDIR=/var/lib/zug37
ENV_FILE=/etc/zug37.env
PUBLIC_DIR=/var/www/zug37
SNIPPET=/etc/nginx/snippets/zug37.conf
HOST=tm.mif.works
LOGBOOK=git@github.com:timkleinke/tim.git

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

if [ "${1:-}" = "start" ]; then
  grep -q '^CLAUDE_CODE_OAUTH_TOKEN=.\+' "$ENV_FILE" || { echo "put the token into $ENV_FILE first (CLAUDE_CODE_OAUTH_TOKEN=...)" >&2; exit 1; }
  if [ ! -d "$HOMEDIR/tim/.git" ]; then
    sudo -u zug37 env GIT_SSH_COMMAND="ssh -i $HOMEDIR/.ssh/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$HOMEDIR/.ssh/known_hosts" \
      git clone -q "$LOGBOOK" "$HOMEDIR/tim" || { echo "clone failed: is the deploy key added to timkleinke/tim?" >&2; exit 1; }
  fi
  systemctl start zug37-anzeige.service
  systemctl enable --now zug37-anzeige.timer zug37-redaktion.timer
  echo "started. First edition now: systemctl start zug37-redaktion.service (takes a few minutes)"
  exit 0
fi

if [ -n "$(git -C "$SRC" status --porcelain)" ]; then
  echo "uncommitted changes in $SRC; install only a committed state" >&2; exit 1
fi
command -v python3 >/dev/null && python3 -c 'import PIL' 2>/dev/null || { echo "needs python3 with Pillow (apt install python3-pil)" >&2; exit 1; }
for f in /usr/share/fonts/X11/Type1/c0648bt_.pfb /usr/share/fonts/X11/Type1/c0649bt_.pfb /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf; do
  [ -f "$f" ] || { echo "missing font $f (apt install fonts-liberation xfonts-scalable or t1-xfree86-nonfree)" >&2; exit 1; }
done

# Claude Code must be runnable by the zug37 user, so not from root's or another user's home.
CLAUDE_BIN="$(command -v claude || true)"
case "$CLAUDE_BIN" in
  ""|/root/*|/home/*|/opt/*) echo "claude not installed system-wide; run: npm install -g @anthropic-ai/claude-code" >&2; exit 1 ;;
esac

id -u zug37 >/dev/null 2>&1 || useradd --system --user-group --home-dir "$HOMEDIR" --shell /usr/sbin/nologin zug37
install -d -o zug37 -g zug37 -m 700 "$HOMEDIR" "$HOMEDIR/.ssh" "$HOMEDIR/state"
[ -f "$HOMEDIR/.ssh/id_ed25519" ] || sudo -u zug37 ssh-keygen -q -t ed25519 -N "" -C "zug37-redaktion (read-only)" -f "$HOMEDIR/.ssh/id_ed25519"
if [ ! -s "$HOMEDIR/.ssh/known_hosts" ]; then
  ssh-keyscan -t ed25519 github.com 2>/dev/null > "$HOMEDIR/.ssh/known_hosts.new"
  [ -s "$HOMEDIR/.ssh/known_hosts.new" ] || { echo "ssh-keyscan github.com failed" >&2; exit 1; }
  mv "$HOMEDIR/.ssh/known_hosts.new" "$HOMEDIR/.ssh/known_hosts"
  chown zug37:zug37 "$HOMEDIR/.ssh/known_hosts"; chmod 600 "$HOMEDIR/.ssh/known_hosts"
fi

REV="$(git -C "$SRC" rev-parse HEAD)"
rm -rf "$DEST.new"; install -d -m 755 "$DEST.new"
cp -r "$SRC/zug37" "$DEST.new/"; find "$DEST.new" -name __pycache__ -prune -exec rm -rf {} +
echo "$REV" > "$DEST.new/REVISION"; chmod -R u=rwX,go=rX "$DEST.new"
rm -rf "$DEST.old"; [ -d "$DEST" ] && mv "$DEST" "$DEST.old"; mv "$DEST.new" "$DEST"

if [ ! -f "$ENV_FILE" ]; then
  RANDOM_PART="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
  ( umask 077; cat > "$ENV_FILE" <<EOT
Z37_STATE=$HOMEDIR/state
Z37_REPO=$HOMEDIR/tim
Z37_CLAUDE=$CLAUDE_BIN
Z37_PUBLIC_DIR=$PUBLIC_DIR
Z37_PUBLIC_URL=https://$HOST/z37/$RANDOM_PART/
CLAUDE_CODE_OAUTH_TOKEN=
EOT
  )
fi
URL="$(sed -n 's/^Z37_PUBLIC_URL=//p' "$ENV_FILE")"
URL_PATH="/${URL#https://*/}"

install -d -o zug37 -g www-data -m 2750 "$PUBLIC_DIR"
( umask 077; sed "s|@PATH@|$URL_PATH|g" "$SRC/nginx/location.conf.template" > "$SNIPPET.new" ); mv "$SNIPPET.new" "$SNIPPET"

# Include the snippet in the tm.mif.works server block, next to the Signal Radar feed. Test before reload.
SITE="$(grep -l 'include snippets/tickrmeter-signal-radar.conf;' /etc/nginx/sites-enabled/* 2>/dev/null | xargs -r grep -l "server_name $HOST" | head -n 1 || true)"
if [ -z "$SITE" ]; then
  echo "could not find the $HOST server block; add 'include snippets/zug37.conf;' there by hand" >&2
elif ! grep -q 'include snippets/zug37.conf;' "$SITE"; then
  REAL="$(readlink -f "$SITE")"; BACKUP="/var/backups/nginx-$(basename "$REAL").vor-zug37"; cp -p "$REAL" "$BACKUP"
  sed -i 's|^\(\s*\)include snippets/tickrmeter-signal-radar.conf;|&\n\1include snippets/zug37.conf;|' "$REAL"
  if nginx -t 2>/dev/null; then systemctl reload nginx; echo "nginx: zug37 feed added to $REAL"
  else cp -p "$BACKUP" "$REAL"; echo "nginx -t failed, change reverted" >&2; exit 1; fi
fi

install -m 644 "$SRC"/systemd/zug37-*.service "$SRC"/systemd/zug37-*.timer /etc/systemd/system/
systemctl daemon-reload

echo
echo "installed $REV to $DEST"
echo "1) Deploy key for timkleinke/tim (Settings > Deploy keys, read-only):"
cat "$HOMEDIR/.ssh/id_ed25519.pub"
echo "2) Token: nano $ENV_FILE  ->  CLAUDE_CODE_OAUTH_TOKEN=<from claude setup-token>"
echo "3) ./install.sh start"
echo "Feed for the TickrMeter app: ${URL}feed.json"
