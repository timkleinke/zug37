#!/usr/bin/env bash
# Zug 37 on the MIF server. One command, as root, from a checkout of this repo:
#
#   ./install.sh
#
# Installs or updates everything and asks only for what it cannot know: the deploy key on GitHub,
# the Claude token and (optional) the Telegram bot token. Secrets are read hidden, never printed,
# and stored only in /etc/zug37.env (0600 root). Running it again updates code and units and skips
# every question that is already answered.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/zug37
HOMEDIR=/var/lib/zug37
ENV_FILE=/etc/zug37.env
PUBLIC_DIR=/var/www/zug37
SNIPPET=/etc/nginx/snippets/zug37.conf
HOST=tm.mif.works
LOGBOOK=git@github.com:timkleinke/tim.git
GIT_SSH="ssh -i $HOMEDIR/.ssh/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$HOMEDIR/.ssh/known_hosts"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\nAbbruch: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "bitte als root ausführen"
[ -z "$(git -C "$SRC" status --porcelain)" ] || die "ungespeicherte Änderungen in $SRC"

# Reads a pasted secret hidden. Swallows the rest of a paste that arrived on several lines, strips
# bracketed-paste markers and whitespace, never prints the value. Usage: read_secret VAR "prompt"
read_secret() {
  local first rest more
  read -rsp "$2" first; echo
  rest=""
  while IFS= read -rs -t 0.4 more; do rest="$rest$more"; done
  first="$first$rest"
  first="${first//$'\e[200~'/}"; first="${first//$'\e[201~'/}"
  first="$(printf '%s' "$first" | tr -d '[:space:]')"
  printf -v "$1" '%s' "$first"
}

# --- Voraussetzungen ---------------------------------------------------------------------------
/usr/bin/python3 -s -c 'import PIL' 2>/dev/null || die "python3 mit Pillow fehlt (apt install python3-pil)"
for f in /usr/share/fonts/X11/Type1/c0648bt_.pfb /usr/share/fonts/X11/Type1/c0649bt_.pfb \
         /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf; do
  [ -f "$f" ] || die "Schrift fehlt: $f"
done
CLAUDE_BIN="$(command -v claude || true)"
case "$CLAUDE_BIN" in
  ""|/root/*|/home/*|/opt/*)
    command -v npm >/dev/null || die "Claude Code fehlt systemweit, und npm ist nicht da"
    say "Installiere Claude Code systemweit (npm) ..."
    npm install -g --silent @anthropic-ai/claude-code >/dev/null
    CLAUDE_BIN="$(PATH=/usr/local/bin:/usr/bin command -v claude || true)"
    case "$CLAUDE_BIN" in ""|/root/*|/home/*|/opt/*) die "Claude Code liegt nicht systemweit: $CLAUDE_BIN";; esac ;;
esac

# --- Nutzer, Schlüssel, Code ---------------------------------------------------------------------
id -u zug37 >/dev/null 2>&1 || useradd --system --user-group --home-dir "$HOMEDIR" --shell /usr/sbin/nologin zug37
install -d -o zug37 -g zug37 -m 700 "$HOMEDIR" "$HOMEDIR/.ssh" "$HOMEDIR/state"
[ -f "$HOMEDIR/.ssh/id_ed25519" ] || sudo -u zug37 ssh-keygen -q -t ed25519 -N "" -C "zug37 (nur lesen)" -f "$HOMEDIR/.ssh/id_ed25519"
if [ ! -s "$HOMEDIR/.ssh/known_hosts" ]; then
  ssh-keyscan -t ed25519 github.com 2>/dev/null > "$HOMEDIR/.ssh/known_hosts.new"
  [ -s "$HOMEDIR/.ssh/known_hosts.new" ] || die "github.com nicht erreichbar (ssh-keyscan)"
  mv "$HOMEDIR/.ssh/known_hosts.new" "$HOMEDIR/.ssh/known_hosts"
  chown zug37:zug37 "$HOMEDIR/.ssh/known_hosts"; chmod 600 "$HOMEDIR/.ssh/known_hosts"
fi

REV="$(git -C "$SRC" rev-parse HEAD)"
rm -rf "$DEST.new"; install -d -m 755 "$DEST.new"
cp -r "$SRC/zug37" "$DEST.new/"; find "$DEST.new" -name __pycache__ -prune -exec rm -rf {} +
echo "$REV" > "$DEST.new/REVISION"; chmod -R u=rwX,go=rX "$DEST.new"
rm -rf "$DEST.old"; [ -d "$DEST" ] && mv "$DEST" "$DEST.old"; mv "$DEST.new" "$DEST"

# --- Env-Datei (0600 root) -----------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  ( umask 077; cat > "$ENV_FILE" <<EOT
Z37_STATE=$HOMEDIR/state
Z37_REPO=$HOMEDIR/tim
Z37_CLAUDE=$CLAUDE_BIN
Z37_PUBLIC_DIR=$PUBLIC_DIR
Z37_PUBLIC_URL=https://$HOST/z37/$(python3 -c 'import secrets; print(secrets.token_hex(20))')/
CLAUDE_CODE_OAUTH_TOKEN=
Z37_TG_TOKEN=
Z37_TG_CHAT=
EOT
  )
fi
getenv() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n 1; }
setenv() {  # value via stdin (never an argument); handed to python through the environment,
            # because python's own stdin is the heredoc with the script
  local val; val="$(cat)"
  VAL="$val" python3 - "$ENV_FILE" "$1" <<'PY'
import os, sys
path, key = sys.argv[1], sys.argv[2]
val = os.environ["VAL"].strip()
lines = [l for l in open(path).read().splitlines() if not l.startswith(key + "=")]
lines.append(f"{key}={val}")
tmp = path + ".new"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f: f.write("\n".join(lines) + "\n")
os.replace(tmp, path)
PY
}
for k in Z37_TG_TOKEN Z37_TG_CHAT; do grep -q "^$k=" "$ENV_FILE" || printf '' | setenv "$k"; done

# --- Feed: Verzeichnis und nginx -----------------------------------------------------------------
URL="$(getenv Z37_PUBLIC_URL)"; URL_PATH="/${URL#https://*/}"
install -d -o zug37 -g www-data -m 2750 "$PUBLIC_DIR"
( umask 077; sed "s|@PATH@|$URL_PATH|g" "$SRC/nginx/location.conf.template" > "$SNIPPET.new" ); mv "$SNIPPET.new" "$SNIPPET"
SITE="$(grep -l 'include snippets/tickrmeter-signal-radar.conf;' /etc/nginx/sites-enabled/* 2>/dev/null | xargs -r grep -l "server_name $HOST" | head -n 1 || true)"
[ -n "$SITE" ] || die "Server-Block für $HOST nicht gefunden"
if ! grep -q 'include snippets/zug37.conf;' "$SITE"; then
  REAL="$(readlink -f "$SITE")"; BACKUP="/var/backups/nginx-$(basename "$REAL").vor-zug37"; cp -p "$REAL" "$BACKUP"
  sed -i 's|^\(\s*\)include snippets/tickrmeter-signal-radar.conf;|&\n\1include snippets/zug37.conf;|' "$REAL"
  if nginx -t 2>/dev/null; then systemctl reload nginx
  else cp -p "$BACKUP" "$REAL"; die "nginx -t schlug fehl, Änderung zurückgenommen"; fi
fi

install -m 644 "$SRC"/systemd/zug37-*.service "$SRC"/systemd/zug37-*.timer /etc/systemd/system/
systemctl daemon-reload

# Claude Code must start for zug37 the way the service sees the system (no /root, /home, /opt).
systemd-run --quiet --wait --pipe --collect -p User=zug37 -p ProtectHome=yes -p TemporaryFileSystem=/opt:ro \
  -p BindReadOnlyPaths=/opt/zug37 -p Environment=HOME=$HOMEDIR -p Environment=DISABLE_AUTOUPDATER=1 \
  "$(getenv Z37_CLAUDE)" --version >/dev/null 2>&1 || die "Claude Code startet als zug37 nicht (Node fehlt systemweit oder ist zu alt?)"

# --- 1. Logbuch lesen dürfen ---------------------------------------------------------------------
if [ ! -d "$HOMEDIR/tim/.git" ]; then
  say "1/3  Logbuch freigeben"
  echo "Öffne https://github.com/timkleinke/tim/settings/keys/new"
  echo "Titel: zug37 · Haken bei „Allow write access“ NICHT setzen · Schlüssel:"
  echo; cat "$HOMEDIR/.ssh/id_ed25519.pub"; echo
  for i in 1 2 3; do
    read -rp "Eingetragen? Dann Enter. " _
    if sudo -u zug37 env GIT_SSH_COMMAND="$GIT_SSH" git clone -q "$LOGBOOK" "$HOMEDIR/tim" 2>/dev/null; then echo "Logbuch geholt."; break; fi
    [ "$i" = 3 ] && die "Logbuch nicht erreichbar. Schlüssel prüfen und ./install.sh erneut starten."
    echo "Noch kein Zugriff, bitte prüfen."
  done
fi

# --- 2. Claude --------------------------------------------------------------------------------
if [ -z "$(getenv CLAUDE_CODE_OAUTH_TOKEN)" ]; then
  say "2/3  Claude verbinden"
  echo "Auf deinem Mac im Terminal: claude setup-token  →  im Browser bestätigen, Token kopieren."
  for i in 1 2 3; do
    read_secret TOKEN "Token hier einfügen (unsichtbar), dann Enter: "
    [[ "$TOKEN" =~ ^[A-Za-z0-9_-]{40,400}$ ]] && break
    [ -z "$TOKEN" ] && echo "Nichts angekommen." || echo "Das sieht nicht wie ein Token aus (${#TOKEN} Zeichen angekommen, erwartet ein langer Token wie sk-ant-oat01-…)."
    [ "$i" = 3 ] && die "Kein gültiger Token. ./install.sh erneut starten."
  done
  printf '%s' "$TOKEN" | setenv CLAUDE_CODE_OAUTH_TOKEN; unset TOKEN
fi

# --- 3. Telegram -------------------------------------------------------------------------------
if [ -z "$(getenv Z37_TG_TOKEN)" ]; then
  say "3/3  Telegram (die Bewertung im Test läuft darüber)"
  echo "In Telegram: @BotFather → /newbot → Name „Zug 37“ → Token kopieren."
  read_secret TG "Bot-Token einfügen (unsichtbar), dann Enter: "
  if [ -n "$TG" ]; then
    [[ "$TG" =~ ^[0-9]{5,15}:[A-Za-z0-9_-]{30,60}$ ]] || die "Das sieht nicht wie ein Bot-Token aus (${#TG} Zeichen). ./install.sh erneut starten."
    printf '%s' "$TG" | setenv Z37_TG_TOKEN
  fi
  unset TG
fi
if [ -n "$(getenv Z37_TG_TOKEN)" ] && [ -z "$(getenv Z37_TG_CHAT)" ]; then
  # Only the private chat that sends this one-time code is accepted, then Tim confirms it.
  CODE="Z37-$(python3 -c 'import secrets; print(secrets.randbelow(900000) + 100000)')"
  echo "Schick deinem Bot in Telegram genau diese Nachricht: $CODE   (ich warte bis zu 2 Minuten)"
  CHAT=""
  for i in $(seq 1 30); do
    CHAT="$(TG="$(getenv Z37_TG_TOKEN)" CODE="$CODE" python3 - <<'PY'
import json, os, urllib.request
try:
    r = json.load(urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TG']}/getUpdates", timeout=10))
    m = [u["message"] for u in r.get("result", []) if "message" in u
         and u["message"]["chat"]["type"] == "private" and u["message"].get("text", "").strip() == os.environ["CODE"]]
    print(f'{m[-1]["chat"]["id"]} {m[-1]["chat"].get("first_name", "")} {m[-1]["chat"].get("username", "")}' if m else "")
except Exception:
    print("")
PY
)"
    [ -n "$CHAT" ] && break; sleep 4
  done
  if [ -n "$CHAT" ]; then
    read -rp "Code kam von Chat ${CHAT%% *} (${CHAT#* }). Bist du das? [j/n] " OK
    if [ "$OK" = "j" ]; then printf '%s' "${CHAT%% *}" | setenv Z37_TG_CHAT; echo "Verbunden."
    else echo "Nicht übernommen. ./install.sh erneut starten."; fi
  else echo "Code nicht gesehen. Später einfach ./install.sh erneut starten."; fi
fi

# --- Start ----------------------------------------------------------------------------------------
systemctl enable --now zug37-anzeige.timer >/dev/null 2>&1
systemctl start zug37-anzeige.service
if [ -z "$(getenv Z37_TG_CHAT)" ]; then
  # without the measuring instrument no editions: the test only counts what can be rated
  systemctl disable --now zug37-redaktion.timer zug37-bot.service >/dev/null 2>&1 || true
  say "Telegram ist noch nicht verbunden, deshalb läuft die Redaktion noch nicht. ./install.sh erneut starten."
  exit 0
fi
systemctl enable --now zug37-redaktion.timer >/dev/null 2>&1
systemctl enable zug37-bot.service >/dev/null 2>&1; systemctl restart zug37-bot.service
if [ ! -f "$HOMEDIR/state/ausgabe.json" ]; then
  say "Die Redaktion macht die erste Ausgabe (ein paar Minuten). Sie kommt gleich auch per Telegram ..."
  systemctl start zug37-redaktion.service || die "Redaktion fehlgeschlagen: journalctl -u zug37-redaktion -n 20"
  systemctl start zug37-anzeige.service
  python3 -c "import json; e=json.load(open('$HOMEDIR/state/ausgabe.json')); print('→', e.get('rubrik',''), e.get('zeile', e.get('art')))"
fi

say "Fertig ($REV)."
echo "Letzter Schritt im TickrMeter-Konto: neue App „Zug 37“, Feed-URL:"
echo "  ${URL}feed.json"
echo "Vorschau hochladen wie bei Signal Radar, beim Senden die LED-Helligkeit setzen."
echo "Updates später: cd $SRC && git pull && ./install.sh"
