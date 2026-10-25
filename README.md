# Zug 37

Das Display auf meinem Schreibtisch (TickrMeter, 296 × 128, 1 Bit, eine weiße Lampe). Die Idee steht in `timkleinke/tim`, `redaktion/GRUENDUNG.md`.

## Wie es läuft

| Teil | Was | Wann |
|---|---|---|
| Redaktion | Claude Code liest das Logbuch, sucht im Netz und entscheidet: eine Sache oder Stille. Die Antwort wird Feld für Feld geprüft und nach `ausgabe.json` geschrieben. | 7:30, 12:30, 17:30 Uhr |
| Anzeige | rendert die aktuelle Ausgabe und veröffentlicht `feed.json` mit dem Frame unter `tm.mif.works/z37/<zufall>/` | alle 5 Minuten |

- Die Redaktion darf nur lesen und im Netz suchen: keine Shell, kein Schreiben. Das Logbuch kommt über einen Deploy-Key, der nur lesen darf.
- Die Anzeige hat kein Netz.
- Die Lampe leuchtet weiß bis zu drei Stunden nach einer Ausgabe mit `licht`, höchstens zweimal am Tag und nie zwischen 21 und 7 Uhr.
- Bei Stille bleibt die letzte Ausgabe stehen.
- Der Feed ist öffentlich unter einem zufälligen Pfad. Auf dem Display stehen deshalb nur Schlagzeilen. Details (`detail`, `quellen`) bleiben in `/var/lib/zug37/state/verlauf.jsonl`.

## Einrichten (MIF-Server, als root)

```
git clone git@github.com:timkleinke/zug37.git /root/zug37 && cd /root/zug37
./install.sh
```

Danach:
1. Den Deploy-Key, den das Skript ausgibt, in `timkleinke/tim` unter Settings → Deploy keys eintragen, nur lesend.
2. Den Token aus `claude setup-token` in `/etc/zug37.env` eintragen.
3. `./install.sh start`, dann einmal `systemctl start zug37-redaktion.service`.
4. Im TickrMeter-Konto eine neue App „Zug 37“ mit der Feed-URL anlegen, die das Skript ausgibt. Eine Vorschau hochladen und beim Senden `ledBrightness` setzen.

| Was | Befehl |
|---|---|
| jetzt eine Ausgabe | `systemctl start zug37-redaktion.service` |
| letzte Ausgabe lesen | `cat /var/lib/zug37/state/ausgabe.json` |
| Protokoll | `journalctl -u zug37-redaktion -u zug37-anzeige` |
| anhalten | `systemctl disable --now zug37-redaktion.timer zug37-anzeige.timer` |

## Lokal ausprobieren

```
Z37_STATE=out Z37_REPO=../tim python3 -s -B -m zug37.redaktion
Z37_STATE=out python3 -s -B -m zug37.anzeige    # out/frame.png
```
