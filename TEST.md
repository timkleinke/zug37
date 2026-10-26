# Testbetrieb

Tim, 26.10.2026: Zug 37 muss erst beweisen, dass es regelmäßig Erkenntnisse liefert, die Tim sonst nicht bekommen hätte. Ob es sich technisch weiter ausbauen lässt, zählt dafür nicht. Kein Fünf-Stufen-Programm.

## Bedingungen

1. **28 Tage**, ab der ersten Ausgabe. **Vier Läufe am Tag** (7:30, 11:00, 14:30, 18:00 Uhr), jeder darf schweigen. **Ideenbörse und Fund.** Frage und Spiegel bleiben aus. *(Tim, 26.10., 11:30: zuerst ein Lauf, nur Ideenbörse; geändert, weil mehr Ausgaben mehr Bewertungen bringen und die Frage des Tests dieselbe bleibt.)*
2. **Telegram ist das Messinstrument.** Jede Ausgabe kommt mit Detail, Quellen und drei Knöpfen: *Neu und relevant · Schon bekannt · Nicht relevant*. Überraschung allein ist noch kein Nutzen.
3. **Sonntags der Vergleich mit Claude im normalen Chat.** Der Bot schickt die Aufgabe als Datei. Es ist wörtlich dieselbe, die die Redaktion am Sonntag um 7:30 Uhr bekommen hat (`aufgabe.md`), mit demselben Logbuchauszug. Tim gibt sie Claude in einem neuen Chat mit Websuche und schickt die Antwort an den Bot zurück. Bewertet wird mit denselben drei Knöpfen. Wählt der Chat Stille, zählt das wie beim Display nicht als Ausgabe.
4. **Nach 28 Tagen** schickt der Bot das Ergebnis. Liefert das Display häufiger Neues und Relevantes als der Chat? Wenn nicht, wird nicht weiter ausgebaut.

## Messgröße

Anteil „Neu und relevant“ an allen bewerteten Ausgaben, getrennt nach Display und Chat. Verglichen werden Anteile, nicht Mengen: Das Display liefert bis zu vier Ausgaben am Tag, der Chat eine pro Woche. Stille zählt nicht als Ausgabe. Wird dasselbe zweimal angetippt, gilt das Letzte. `/stand` im Bot zeigt den Zwischenstand.

Die Daten liegen auf dem Server in `/var/lib/zug37/state/`:

| Datei | Inhalt |
|---|---|
| `verlauf.jsonl` | jeder Lauf der Redaktion: Ausgabe, Stille oder Fehler |
| `bewertungen.jsonl` | jeder Tipp auf einen Knopf |
| `vergleich.jsonl` | die Antworten aus dem Chat |
| `notizen.jsonl` | freie Nachrichten an den Bot, jeweils zur aktuellen Ausgabe |

## Gut zu wissen

- Telegram-Chats mit Bots sind nicht Ende-zu-Ende verschlüsselt. Die Sonntagsdatei enthält einen Auszug aus dem Logbuch (Kurs, Ideen, Projekte, aktueller Monat). Bei Verdacht den Bot-Token bei @BotFather erneuern und `./install.sh` neu starten.
- Der Bot hört nur auf den Chat, der beim Einrichten den Einmal-Code geschickt hat und von Tim bestätigt wurde.
- Auf ein bewertetes Item kann Tim nochmals tippen. Es gilt das Letzte.

## Offen (aus den Prüfungen, bewusst nicht in diesem Stand)

- Bot und Redaktion laufen unter demselben Nutzer. Ein kompromittierter Bot könnte den Claude-Token eines laufenden Redaktionslaufs lesen oder `ausgabe.json` schreiben. Abhilfe wäre ein eigener Nutzer für den Bot. Voraussetzung für den Angriff ist eine Lücke im Bot selbst, der nur mit Telegram spricht.
- Am Sonntag nach 9 Uhr wird die erste freie Nachricht als Antwort aus dem Chat gewertet, und Dateien an den Bot werden ignoriert.
- Nach Tag 28 laufen Redaktion und Sonntagsversand weiter, bis Tim entscheidet.
