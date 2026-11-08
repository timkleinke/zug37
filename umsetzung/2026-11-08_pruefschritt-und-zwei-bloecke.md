# Auftrag: Fund und Bezug trennen, Quellen lesen, Aussagen prüfen

Von Tim, 08.11.2026, vorbereitet mit Claude (Chat, Projekt MIF). Grundlage: drei gegengeprüfte Ausgaben
(`mif-intern/besprechungen/2026-11-08_zug37-fehlermuster.md`).

## Befund

Die Funde von Zug 37 sind relevant, die Kernzahlen aus der Erstquelle stimmen fast immer. Falsch wird es an drei
Stellen: Zahlen aus Zweitquellen (Blogs, die eine Studie zitieren), Verbindungen, die die Redaktion selbst herstellt und
als Tatsache schreibt („Defacta ist ein Produkt in diesem Markt“, „Kantar verkauft das als Brand Authenticity
Framework“), und behauptete Marktlücken („eine automatisierte Variante gibt es nicht“, obwohl es zwei gibt). Dazu
abgeschnittene Zahlen in der Schlagzeile („4 %“ statt 94 %).

Die wahrscheinlichste Ursache steht in `redaktion.py`: Die Redaktion hat nur `WebSearch`. Sie liest Suchergebnis-
Ausschnitte, nie die Seite. Aus Ausschnitten lassen sich Zahlen nicht prüfen, Zweit- und Erstquelle nicht
unterscheiden und Abwesenheiten nicht belegen.

## Ziel

Zug 37 soll weiter finden, was es findet. Aber was auf dem Display und in Telegram steht, soll in zwei Teile zerfallen:
was die Quelle sagt, und was Zug 37 daraus für Tim folgert. Und jede Aussage im ersten Teil soll gegen den Text der
genannten Quelle geprüft sein, bevor sie erscheint.

## Was zu bauen ist

1. **Quellen lesen.** Die Redaktion bekommt zusätzlich `WebFetch`, damit sie die Seiten liest, die sie als Quelle
   nennt. Alles andere bleibt gesperrt (kein Dateizugriff, keine Shell). Im Prompt steht, dass Zahlen nur aus der
   gelesenen Erstquelle übernommen werden; eine Zahl, die nur in einer Zweitquelle steht, wird als solche genannt oder
   weggelassen.
2. **Zwei Blöcke im `detail`.** Erster Block „Fund“: was die Quelle sagt, mit Datum und Herausgeber. Zweiter Block
   „Bezug“: was das für Tims Idee oder Projekt heißt, warum jetzt. `zeile` und `fuss` auf dem Display kommen nur aus
   dem Fund. Drei Regeln für den Bezug, im Prompt: Verweise auf das Logbuch nur mit Dateipfad, sonst weglassen.
   Abwesenheiten nur als „in einer Suche nach X nichts gefunden“, nie als „gibt es nicht“. Verbindungen zwischen Quellen
   als „ich verbinde“, nicht als Tatsache.
3. **Prüfschritt.** Nach der Redaktion ein zweiter, kurzer Claude-Aufruf (eigener Prompt `pruefung.md`, Modell über
   `Z37_PRUEF_MODEL`, Vorgabe Sonnet). Er bekommt die fertige Ausgabe und die Texte der genannten Quellen (die Redaktion
   legt sie beim Lesen in den Zustand) und markiert jede Aussage des Fund-Blocks: in der Quelle, nicht in der Quelle, nur
   in Zweitquelle. Was nicht in der Quelle steht, wird aus dem Fund gestrichen oder in den Bezug verschoben. Fällt dabei
   die `zeile`, wird aus der Ausgabe Stille, mit Begründung im Verlauf. Der Prüfschritt ändert keine Wörter, er
   streicht oder verschiebt nur.
4. **Zählen.** In `verlauf.jsonl` je Ausgabe: Zahl der geprüften Aussagen, Zahl der gestrichenen, Zahl der verschobenen.
   `/stand` im Bot zeigt die Summen seit diesem Auftrag. Nach zehn Ausgaben sieht Tim, ob die drei Fehlerarten
   verschwunden sind.

## Was gleich bleibt

- Die vier Zeiten, Ideenbörse und Fund, die Messgröße und der Sonntagsvergleich (`TEST.md`). Der Chat bekommt am Sonntag
  weiterhin wörtlich die Aufgabe der Redaktion, also auch den neuen Prompt. Der Prüfschritt gilt nur für das Display.
- Grenzen des öffentlichen Feeds (keine Namen aus `menschen/`, keine Details auf dem Display).
- Die Redaktion läuft weiter als `zug37` ohne Dateizugriff; `WebFetch` ist die einzige neue Fähigkeit.

## Erwartetes Ergebnis

Geänderte `redaktion.md`, `redaktion.py`, neue `pruefung.md`, angepasster Bot (`/stand`), Tests für den Prüfschritt
(streicht, verschiebt, macht Stille) und für die zwei Blöcke. Ein Lauf der Redaktion nach dem Einspielen als Probe, dessen
Ausgabe im Bericht steht.
