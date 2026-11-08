# Auftrag: Die Werkstatt – Aufträge aus `umsetzung/` selbst umsetzen

Von Tim, 08.11.2026, vorbereitet mit Claude (Chat, Projekt MIF). Tim steuert Zug 37 vom Handy aus und will dafür nicht
mehr ins Terminal. Eine Korrektur soll als Datei in `umsetzung/` landen und beim nächsten Lauf von Zug 37 selbst
eingearbeitet werden, so wie Mina Aufträge aus ihrem Repo abholt.

## Ziel

Ein dritter Dienst neben Redaktion und Anzeige: die **Werkstatt**. Sie prüft regelmäßig, ob in `umsetzung/` ein Auftrag
ohne Bericht liegt, setzt den ältesten davon mit Claude Code um, lässt die Tests laufen, spielt den neuen Stand ein,
schreibt den Bericht und meldet sich bei Tim. Zug 37 hält sich damit selbst in Stand; Tim gibt nur noch Aufträge.

**Fassung 2 (08.11., 18:05):** ohne root. Grund: Eine Werkstatt, die stündlich als root Code aus dem Repo umsetzt und
einspielt, macht jeden Push in dieses (öffentliche!) Repo, der durchkommt, zu root auf dem MIF-Server. Claude Code hat
dieselbe Bauart in `timkleinke/zentrale` zu Recht abgelehnt.

## Was die Werkstatt darf

- Als eigener Nutzer `zug37-werkstatt` (ohne Login-Shell) in einem eigenen Arbeitsklon unter
  `/var/lib/zug37-werkstatt/` arbeiten: Dateien ändern, Tests laufen lassen, committen, auf `main` pushen (eigener
  Deploy-Key mit Schreibrecht, gehört nur diesem Nutzer).
- Geänderten Python-Code nach `/opt/zug37` kopieren (das Verzeichnis gehört dafür `zug37-werkstatt`, ist für `zug37` nur
  lesbar) und per sudo genau `systemctl restart zug37-bot` auslösen; Redaktion und Anzeige sind Timer und nehmen den
  neuen Code beim nächsten Lauf.
- Claude Code mit einem eigenen Claude-Token in `/etc/zug37-werkstatt.env` (0600, nur dieser Nutzer). Ein Lauf je
  Auftrag, höchstens eine Nachbesserung bei roten Tests, danach Abbruch mit Bericht.
- Takt: einmal pro Stunde nachsehen, zwischen 7 und 22 Uhr Berlin. Läuft gerade die Redaktion, warten. Liegt kein
  offener Auftrag, nichts tun und nichts melden.
- Ändert ein Auftrag `install.sh`, `systemd/` oder `nginx/`, pusht die Werkstatt, spielt aber nicht ein. Der Bericht sagt
  oben: „Bitte `cd /root/zug37 && git pull && ./install.sh` ausführen“, mit Grund. Das Einrichten der Werkstatt selbst
  (Nutzer, Rechte, Unit, sudoers) macht dieser erste Lauf als root, von Tim begleitet.

## Was die Werkstatt nicht darf

- Keine Änderung an `TEST.md`, an den vier Redaktionszeiten oder an der Messgröße des Tests. Das ist Tims Sache.
- Nichts als root. `/etc/zug37.env` (Tims Token für die Redaktion, Telegram) nicht lesen.
- Nichts, was Tims Token, den Telegram-Token oder den Deploy-Key sichtbar macht oder an eine andere Stelle kopiert. Vor jedem Commit prüft ein Schritt ohne Modell den Diff auf Muster von Tokens und Passwörtern und bricht ab, wenn er etwas findet.
- Keine neuen Netzzugriffe der Redaktion oder des Bots einbauen, die der Auftrag nicht ausdrücklich nennt.
- Keine Aufträge umsetzen, die sie selbst geschrieben hat. Aufträge kommen nur per Push ins Repo.

## Erwartetes Ergebnis

1. `zug37/werkstatt.py` und `systemd/zug37-werkstatt.service` plus `.timer`, von `install.sh` mit eingerichtet.
2. Je Auftrag ein Bericht `umsetzung/<name>.bericht.md` mit: was geändert wurde (Dateien, Commit), Testergebnis, ob
   eingespielt, und dem Befehl zum Zurücknehmen (`git -C /root/zug37 checkout <vorheriger Commit> && ./install.sh`).
   Der Bericht wird mit committet und gepusht.
3. Eine Telegram-Nachricht an Tim nach jedem Auftrag: eine Zeile Ergebnis, eine Zeile Rücknahme. Über den bestehenden
   Bot, ohne ihn zu verändern.
4. Ein Abschnitt „Werkstatt“ in `README.md` (Tabelle „Wie es läuft“ ergänzen, Befehle: jetzt nachsehen, Protokoll,
   anhalten).
5. Tests für die Werkstatt: findet offene Aufträge, überspringt erledigte, bricht bei roten Tests ab.

## Erster Testfall

Nach dem Einrichten liegt `2026-11-08_pruefschritt-und-zwei-bloecke.md` schon offen in `umsetzung/`. Die Werkstatt
setzt ihn beim ersten Lauf um. Daran sieht Tim, ob der Weg funktioniert.
