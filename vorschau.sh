#!/usr/bin/env bash
# Prints the two download links the TickrMeter account needs as a preview: feed.json and the frame it
# points to. Both are the live, public files, so they always match. Run as root on the server:
#   /root/zug37/vorschau.sh
set -euo pipefail
URL="$(sed -n 's/^Z37_PUBLIC_URL=//p' /etc/zug37.env | head -n 1)"
FEED=/var/www/zug37/feed.json
[ -n "$URL" ] && [ -f "$FEED" ] || { echo "Noch kein Feed. Erst ./install.sh ausführen." >&2; exit 1; }
SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["frame"]["sha256"])' "$FEED")"
echo
echo "Vorschau für die App „Zug 37“ (beide Dateien laden, dann im TickrMeter-Konto hochladen):"
echo "  1. ${URL}feed.json"
echo "  2. ${URL}${SHA}.bin"
echo
echo "Tipp: Im Mac-Terminal mit gedrückter Cmd-Taste auf einen Link klicken öffnet ihn im Browser."
echo "Im Browser mit Rechtsklick auf die Seite → „Seite sichern unter …“ bzw. die .bin lädt direkt."
