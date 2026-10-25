# Testbetrieb

Tim, 26.10.2026: Zug 37 muss erst beweisen, dass es regelmäßig Erkenntnisse liefert, die Tim sonst nicht bekommen hätte. Ob es sich technisch weiter ausbauen lässt, zählt dafür nicht. Kein Fünf-Stufen-Programm.

## Bedingungen

1. **28 Tage**, ab der ersten Ausgabe. **Ein Lauf am Tag** (7:30 Uhr). **Nur die Ideenbörse.** Fund, Frage und Spiegel bleiben aus.
2. **Telegram ist das Messinstrument.** Jede Ausgabe kommt mit Detail, Quellen und drei Knöpfen: *Neu und relevant · Schon bekannt · Nicht relevant*. Überraschung allein ist noch kein Nutzen.
3. **Sonntags der Vergleich mit Claude im normalen Chat.** Der Bot schickt die Aufgabe als Datei. Es ist wörtlich dieselbe, die die Redaktion um 7:30 Uhr bekommen hat (`aufgabe.md`), mit demselben Logbuchauszug. Tim gibt sie Claude in einem neuen Chat mit Websuche und schickt die Antwort an den Bot zurück. Bewertet wird mit denselben drei Knöpfen. Wählt der Chat Stille, zählt das wie beim Display nicht als Ausgabe.
4. **Nach 28 Tagen** schickt der Bot das Ergebnis. Liefert das Display häufiger Neues und Relevantes als der Chat? Wenn nicht, wird nicht weiter ausgebaut.

## Messgröße

Anteil „Neu und relevant“ an allen bewerteten Ausgaben, getrennt nach Display und Chat. Stille zählt nicht als Ausgabe. Wird dasselbe zweimal angetippt, gilt das Letzte. `/stand` im Bot zeigt den Zwischenstand.

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
