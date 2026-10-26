# Zug 37

Das Display auf meinem Schreibtisch (TickrMeter, 296 × 128, 1 Bit, eine weiße Lampe). Die Idee steht in `timkleinke/tim`, `redaktion/GRUENDUNG.md`.

## Wie es läuft

Zurzeit im **Testbetrieb** bis Tag 28, Bedingungen in [TEST.md](TEST.md).

| Teil | Was | Wann |
|---|---|---|
| Redaktion | Claude Code bekommt einen Auszug aus dem Logbuch, sucht im Netz Belege zu einer Idee oder Neues zu einem Projekt und entscheidet: eine Ausgabe oder Stille. Die Antwort wird Feld für Feld geprüft und nach `ausgabe.json` geschrieben. | 7:30, 11:00, 14:30, 18:00 Uhr |
| Anzeige | rendert die aktuelle Ausgabe und veröffentlicht `feed.json` mit dem Frame unter `tm.mif.works/z37/<zufall>/` | alle 5 Minuten |
| Bot | schickt jede Ausgabe nach Telegram und nimmt die Bewertung entgegen. Sonntags der Vergleich mit dem Chat, an Tag 28 das Ergebnis. | ständig |

- Die Redaktion hat nur die Websuche: kein Dateizugriff, kein Abruf von Seiten, keine Shell. Sie läuft in einem leeren Verzeichnis ohne Projekt-Settings. Das Logbuch kommt über einen Deploy-Key, der nur lesen darf.
- Die Anzeige hat kein Netz. Der Bot spricht nur mit Telegram und ruft kein Modell auf.
- Die Lampe leuchtet weiß bis zu drei Stunden nach einer Ausgabe mit `licht`, höchstens zweimal am Tag und nie zwischen 21 und 7 Uhr.
- Bei Stille bleibt die letzte Ausgabe stehen.
- Abwechslung mit Signal Radar: Eine neue Ausgabe steht 90 Minuten allein. Danach wechseln sich Zug 37 und Signal Radar zwischen 8 und 19 Uhr alle 15 Minuten ab. Das Bild von Signal Radar kommt unverändert aus dessen Feed. Die Lampe leuchtet, wenn einer der beiden sie will.
- Der Feed ist öffentlich unter einem zufälligen Pfad. Auf dem Display stehen deshalb nur Schlagzeilen, Namen aus `menschen/` werden abgewiesen. Details und Quellen gehen nur an Tims Telegram.

## Einrichten (MIF-Server, als root)

```
git clone git@github.com:timkleinke/zug37.git /root/zug37 && /root/zug37/install.sh
```

Das Skript fragt nacheinander nach dem Deploy-Key (Logbuch nur lesen), dem Claude-Token (`claude setup-token` in einem zweiten Terminal) und optional dem Telegram-Bot. Danach macht es die erste Ausgabe und nennt die Feed-URL für die App „Zug 37“ im TickrMeter-Konto. Ein erneuter Aufruf aktualisiert alles und überspringt, was schon beantwortet ist.

| Was | Befehl |
|---|---|
| jetzt eine Ausgabe | `systemctl start zug37-redaktion.service` |
| Vorschau-Links fürs TickrMeter-Konto | `/root/zug37/vorschau.sh` |
| letzte Ausgabe lesen | `cat /var/lib/zug37/state/ausgabe.json` |
| Protokoll | `journalctl -u zug37-redaktion -u zug37-anzeige` |
| anhalten | `systemctl disable --now zug37-redaktion.timer zug37-anzeige.timer zug37-bot.service` |

## Lokal ausprobieren

```
Z37_STATE=out Z37_REPO=../tim python3 -s -B -m zug37.redaktion
Z37_STATE=out python3 -s -B -m zug37.anzeige    # out/frame.png
python3 -s -B -m unittest discover -s tests -t .
```
