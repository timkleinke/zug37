# Umsetzung: Aufträge an die Werkstatt

Hier legt Tim (oder Claude in Tims Namen) Aufträge an Zug 37 ab, als eine Markdown-Datei je Auftrag, Name
`JJJJ-MM-TT_<kurzname>.md`. Die Werkstatt (`zug37-werkstatt.timer`) schaut regelmäßig nach neuen Dateien, setzt den
ältesten offenen Auftrag mit Claude Code um, prüft, spielt ein und schreibt den Bericht daneben als
`JJJJ-MM-TT_<kurzname>.bericht.md`. Ein Auftrag gilt als erledigt, sobald sein Bericht existiert. Tim bekommt eine
Telegram-Nachricht mit dem Ergebnis und dem Befehl zum Zurücknehmen.

Ein Auftrag beschreibt Ziel, was die Werkstatt dafür darf und was am Ende da sein soll. Keine Dateidiffs, keine
Regelkataloge. Was nicht im Auftrag steht, bleibt wie es ist.

Der erste Auftrag (`2026-11-08_werkstatt.md`) baut die Werkstatt selbst und muss deshalb einmal von Hand gestartet werden:

```
cd /root/zug37 && git pull && claude "Lies umsetzung/2026-11-08_werkstatt.md und setze den Auftrag um."
```

Danach reicht ein Push in diesen Ordner.
