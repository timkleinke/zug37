# Auftrag: Funde an der Sache prüfen, nicht an der Überschrift

Stand 06.11.2026 · für Claude Code im Repo `timkleinke/zug37` · Ergebnis als Pull Request gegen `main`, kein Merge und kein Deploy ohne Tim

## Anlass

Zug 37 hat zweimal ein Angebot falsch eingeordnet, weil es nach Namen und Werbetext geurteilt hat statt nach dem, was das Angebot tatsächlich tut.

- **04.11.2026, brandaudit.online:** Tim hat das Tool selbst ausprobiert. Ergebnis laut Tim „unterirdisch“: zufällige Zahlen, falsche Aussagen. Die Ausgabe hatte es als relevanten Fund gemeldet.
- **06.11.2026, Branditify (branditify.com/tools/brand-audit):** Die Ausgabe schrieb, das Tool liefere „genau das, was Tim unter Brand-Quickcheck beschrieben hat“, der einfachste Kern der Idee sei „damit besetzt“. Die Seite selbst sagt etwas anderes. Geprüft werden feste HTML-Merkmale einer einzelnen Seite: Vorhandensein und Länge von H1, Title und Meta-Description, Favicon, Webfonts, OG-Bild, Schema-Auszeichnung, ein Call-to-Action, ein Analytics-Tag. Ausdrücklich nicht bewertet werden laut Seite Positionierung, Logo, Farbwelt, Kundenwahrnehmung oder Geschmack. „KI“ meint dort nur die automatische Ausführung der Prüfungen. Die Dimension „Positioning“ ist also eine Längenprüfung der H1. Mit Tims Brand-Quickcheck hat das inhaltlich wenig zu tun.

Beide Fälle haben dasselbe Muster: Die Redaktion übernimmt die Selbstbeschreibung eines Angebots und zieht daraus eine Folgerung für Tims Ideen, ohne zu prüfen, was hinter den Begriffen steckt.

## Vermutete Ursache (zu prüfen, nicht gesetzt)

- Die Redaktion darf nur suchen, nicht lesen. In `zug37/redaktion.py` steht `WebFetch` unter `DENIED`. Sie sieht also nur Suchtreffer mit kurzen Ausschnitten und kann die Methodik eines Tools gar nicht nachlesen.
- Der Sonntagsvergleich ist dadurch schief. Claude im normalen Chat kann Seiten öffnen, die Redaktion nicht. Gemessen wird damit auch dieser Unterschied, nicht nur die Qualität der Redaktion.
- `zug37/redaktion.md` verlangt „nur echte Funde mit Quelle“. Es unterscheidet aber nicht zwischen dem, was eine Quelle über sich behauptet, und dem, was belegt ist. Eine Folgerung wie „Idee besetzt“ braucht mehr als einen Produktnamen.
- Unklar ist, welches Modell läuft (`Z37_MODEL` ist optional) und wie viele Suchschritte ein Lauf tatsächlich macht.

Prüfe diese Punkte, ergänze andere, wenn du sie findest, und sag, welche du für ausschlaggebend hältst.

## Ziel

Eine Ausgabe behauptet nur, was die Quelle belegt. Bei Tools und Angeboten heißt das: Die Redaktion weiß, was das Angebot tatsächlich tut (Eingabe, Prüfung, Ausgabe), bevor sie es mit einer Idee von Tim vergleicht. Folgerungen wie „besetzt“, „gelöst“ oder „Konkurrenz“ stehen nur da, wenn sie aus diesem Vergleich folgen. Kann die Redaktion das nicht prüfen, steht das im `detail` oder sie wählt Stille.

## Spielraum

- Du darfst der Redaktion das Lesen von Seiten erlauben. Wäge dabei ab: Mehr gelesener Webinhalt heißt mehr Fläche für eingeschleuste Anweisungen. Dagegen steht, dass die Redaktion sonst kein Werkzeug hat, ihre Antwort nur ein JSON-Objekt ist und Feld für Feld geprüft wird. Schreib die Abwägung in den PR. Ob es so live geht, entscheidet Tim.
- Du darfst `redaktion.md` umschreiben. Halte es kurz und als Ziel formuliert, nicht als lange Regelliste.
- Wenn ein zusätzliches Feld in der Ausgabe hilft (etwa die Unterscheidung „laut Anbieter“ und „geprüft“), darfst du es einführen, samt Prüfung in `check()` und Anzeige im Telegram-Detail. Das Display selbst bleibt bei Schlagzeilen.
- Keine neuen Dienste, keine neue Infrastruktur.

## Testbetrieb beachten

Zug 37 ist im Testbetrieb (`TEST.md`, 28 Tage). Eine Änderung an der Redaktion während des Tests verschiebt die Messung. Trage sie deshalb in `TEST.md` unter „Bedingungen“ mit Datum und Grund ein, so wie die Änderung vom 26.10. Da der Sonntagsvergleich wörtlich dieselbe Aufgabe bekommt (`aufgabe.md`), gilt eine Änderung an `redaktion.md` automatisch für beide Seiten. Eine Änderung an den erlaubten Werkzeugen gilt nur für die Redaktion. Schreib dazu, wie sich das auf den Vergleich auswirkt.

## Erwartetes Ergebnis

1. Ein Pull Request gegen `main` mit:
   - der Diagnose: welche Ursache du für ausschlaggebend hältst und warum;
   - den Änderungen an `redaktion.py` und `redaktion.md`;
   - Tests in `tests/test_zug37.py` für alles, was `check()` oder die Werkzeugliste ändert; alle Tests grün;
   - dem Eintrag in `TEST.md`.
2. Im PR-Text eine Probe: Wie würde die geänderte Redaktion den Branditify-Fall behandeln? Das ist kein Modelllauf im Test, sondern eine nachvollziehbare Begründung anhand des neuen Prompts. Wenn du einen echten Lauf lokal machen kannst (`README.md`, „Lokal ausprobieren“), umso besser; dann die Ausgabe beilegen.
3. Was du nicht klären konntest, steht offen im PR.
