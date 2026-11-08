# Auftrag: Die Werkstatt – Aufträge aus `umsetzung/` selbst umsetzen

Von Tim, 08.11.2026, vorbereitet mit Claude (Chat, Projekt MIF). Tim steuert Zug 37 vom Handy aus und will dafür nicht
mehr ins Terminal. Eine Korrektur soll als Datei in `umsetzung/` landen und beim nächsten Lauf von Zug 37 selbst
eingearbeitet werden, so wie Mina Aufträge aus ihrem Repo abholt.

## Ziel

Ein dritter Dienst neben Redaktion und Anzeige: die **Werkstatt**. Sie prüft regelmäßig, ob in `umsetzung/` ein Auftrag
ohne Bericht liegt, setzt den ältesten davon mit Claude Code um, lässt die Tests laufen, spielt den neuen Stand ein,
schreibt den Bericht und meldet sich bei Tim. Zug 37 hält sich damit selbst in Stand; Tim gibt nur noch Aufträge.

## Was die Werkstatt darf

- Als root in `/root/zug37` arbeiten: Dateien ändern, Tests laufen lassen, committen, auf `main` pushen, `install.sh`
  aufrufen (das ist der einzige Weg, wie ein Stand live geht). Nichts außerhalb von `/root/zug37`, `/opt/zug37`,
  `/etc/zug37.env`, den `zug37-*`-Units und `/var/lib/zug37` anfassen. MIF und alle anderen Dienste auf dem Server
  sind für sie nicht da.
- Claude Code mit Tims Token aus `/etc/zug37.env`, Modell wie die Redaktion. Ein Lauf je Auftrag, höchstens eine
  Nachbesserung, wenn die Tests nach dem ersten Durchgang rot sind. Danach Abbruch mit Bericht, nicht weiterflicken.
- Takt: einmal pro Stunde nachsehen, zwischen 7 und 22 Uhr Berlin. Läuft gerade die Redaktion, warten. Liegt kein
  offener Auftrag, nichts tun und nichts melden.

## Was die Werkstatt nicht darf

- Keine Änderung an `TEST.md`, an den vier Redaktionszeiten oder an der Messgröße des Tests. Das ist Tims Sache.
- Nichts, was Tims Token, den Telegram-Token oder den Deploy-Key sichtbar macht oder an eine andere Stelle kopiert.
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
