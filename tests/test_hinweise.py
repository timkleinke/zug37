"""Offline tests for the Hinweise for Mina: checks, feedback, and one whole run against local git repos."""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from zug37 import hinweise

T0 = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
HINT = {"art": "hinweis", "titel": "Apify Store zeigt zahlende Nutzer je Actor", "kurztitel": "Apify zahlende Nutzer",
        "thema": "Apify Store: sichtbare Nachfrage", "quellen": ["https://apify.com/store"],
        "bezug": "DECISIONS 17.11. Kurskorrektur Punkt 3",
        "befund": "Im Apify Store steht bei jedem Actor die Zahl der monatlichen Nutzer, darunter 1.200 bei einem Beispiel.",
        "zahlen": [{"angabe": "1.200 monatliche Nutzer", "quelle": "https://apify.com/store", "status": "Primärquelle"}],
        "bedeutung": "Mina könnte prüfen, ob eine Nische mit wenigen Anbietern und vielen Nutzern zu ihr passt.",
        "begruendung": "passt zur Kandidatenrunde"}


class Check(unittest.TestCase):
    def test_good_hint_and_slug(self):
        h = hinweise.check(HINT)
        self.assertEqual(h["kurztitel"], "apify-zahlende-nutzer")
        self.assertEqual(hinweise.check({"art": "stille", "begruendung": "nichts"})["art"], "stille")

    def test_rejects(self):
        cases = {
            "quellen": {"quellen": []},
            "zahlen": {"zahlen": []},  # numbers in the finding without source and status
            "thema": {"thema": "Solana-Wallets für Trader"},
            "zitat": {"befund": "Die Seite sagt: „" + "wort " * 15 + "“ und mehr Text, damit es lang genug ist."},
        }
        for field, bad in cases.items():
            with self.assertRaises(ValueError, msg=field):
                hinweise.check({**HINT, **bad})
        with self.assertRaises(ValueError):
            hinweise.check({**HINT, "zahlen": [{"angabe": "6 Besucher", "quelle": "laut Gerücht", "status": "Primärquelle"}]})
        with self.assertRaises(ValueError):
            hinweise.check({**HINT, "titel": "Ladepunktdaten auf Apify"})
        ok = hinweise.check({**HINT, "zahlen": HINT["zahlen"] + [{"angabe": "48 bestätigte Besucher",
                                                                  "quelle": "Mina: STATUS.md", "status": "Primärquelle"}]})
        self.assertEqual(len(ok["zahlen"]), 2)

    def test_feedback_lines(self):
        text = ("x\n- Zug37-Hinweis 2026-11-18-apify-zahlende-nutzer.md: übernommen, kommt in die Kandidatenliste\n"
                "Zug37-Hinweis `2026-11-19-chrome.md`: **verworfen** – Konto nötig\n"
                "Zug37-Hinweis 2026-11-18-apify-zahlende-nutzer.md: verworfen, doch nicht\n")
        f = hinweise.feedback(text)
        self.assertEqual(f["2026-11-19-chrome.md"]["urteil"], "verworfen")
        self.assertEqual(f["2026-11-18-apify-zahlende-nutzer.md"], {"urteil": "verworfen", "grund": "doch nicht"})

    def test_status_head_and_decisions_tail(self):
        self.assertEqual(hinweise.status_head("# S\nKopf\n## Lauf 1\nalt\n"), "# S\nKopf\n")
        d = "".join(f"## E{i}\ntext {i}\n" for i in range(8))
        tail = hinweise.decisions_tail(d, 3)
        self.assertTrue(tail.startswith("## E5") and "E4" not in tail)


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class Run(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.d = d
        for name in ("mina", "ablage"):
            sh("git", "init", "-q", "--bare", "-b", "main", str(d / f"{name}.git"))
            sh("git", "clone", "-q", str(d / f"{name}.git"), str(d / f"{name}-src"))
        src = d / "mina-src"
        (src / "STATUS.md").write_text("# STATUS\n48/400 bestätigt, Prepaid aus.\n## Lauf\nalt\n")
        (src / "EXPERIMENTS.md").write_text("# EXPERIMENTS\n## Test B\n149 €\n")
        (src / "DECISIONS.md").write_text("# DECISIONS\n## 17.11. Kurskorrektur\nKanal zuerst.\n")
        (d / "ablage-src" / "README.md").write_text("Ablage\n")
        for name in ("mina", "ablage"):
            s = d / f"{name}-src"
            sh("git", "add", "-A", cwd=s)
            sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init", cwd=s)
            sh("git", "push", "-q", "origin", "HEAD:main", cwd=s)
            sh("git", "clone", "-q", str(d / f"{name}.git"), str(d / name))
        self.env = {"Z37_STATE": str(d / "state"), "Z37_MINA": str(d / "mina"), "Z37_HINWEISE": str(d / "ablage"),
                    "Z37_MINA_KEY": "", "Z37_HINWEISE_KEY": "", "PATH": "/usr/bin:/bin", "HOME": str(d)}
        self.prompts = []

    def asker(self, answers):
        def ask(workdir, prompt, env, web, schema=None):
            self.prompts.append((web, prompt))
            return "```json\n" + json.dumps(answers.pop(0), ensure_ascii=False) + "\n```"
        return ask

    def test_filed_after_check_and_pushed(self):
        fixed = {**HINT, "bedeutung": "Mina könnte prüfen, ob das zu ihrer Runde passt (48 bestätigte Besucher bisher)."}
        rc = hinweise.main(self.env, T0, self.asker([HINT, {"urteil": "korrigiert", "grund": "Besucherzahl war alt",
                                                            "pruefungen": [], "hinweis": fixed}]))
        self.assertEqual(rc, 0)
        self.assertTrue(self.prompts[0][0] and not self.prompts[1][0])  # research with web, comparison without
        self.assertIn("48/400", self.prompts[1][1])
        log = [json.loads(x) for x in (self.d / "state" / "hinweise.jsonl").read_text().splitlines()]
        self.assertEqual(log[-1]["art"], "abgelegt")
        name = log[-1]["datei"]
        self.assertEqual(name, "2026-11-18-apify-zahlende-nutzer.md")
        sh("git", "clone", "-q", str(self.d / "ablage.git"), str(self.d / "check"))
        text = (self.d / "check" / "hinweise" / name).read_text()
        self.assertIn("## Mögliche Bedeutung für Mina", text)
        self.assertIn("korrigiert (Besucherzahl war alt)", text)
        self.assertIn("1.200 monatliche Nutzer. Quelle: https://apify.com/store. Primärquelle", text)
        self.assertNotIn("Ablage", [p.name for p in (self.d / "mina").iterdir()])

    def test_rejected_and_daily_limit(self):
        hinweise.main(self.env, T0, self.asker([HINT, {"urteil": "verworfen", "grund": "kennt Mina schon"}]))
        log = (self.d / "state" / "hinweise.jsonl").read_text()
        self.assertIn('"verworfen"', log)
        self.assertFalse((self.d / "ablage" / "hinweise").exists())
        for i in range(3):
            hinweise.main(self.env, T0, self.asker([{**HINT, "kurztitel": f"h{i}xx"}, {"urteil": "ok"}]))
        self.prompts.clear()
        hinweise.main(self.env, T0, self.asker([]))
        self.assertEqual(self.prompts, [])  # fourth of the day: no model call at all
        self.assertEqual(hinweise.filed_today(self.d / "state", T0), 3)

    def push_mina(self, name, text):
        src = self.d / "mina-src"
        (src / name).write_text(text)
        sh("git", "add", "-A", cwd=src)
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", name, cwd=src)
        sh("git", "push", "-q", "origin", "HEAD:main", cwd=src)

    def test_question_first_then_own_search(self):
        self.push_mina("ZUG37.md", "# Fragen an Zug 37\n\n## F1 · offen · Wie viele Nutzer haben Ladedaten-Actors?\n"
                                   "Gibt es bei Apify Actors zu Ladepunkten mit zahlenden Nutzern?\n\n"
                                   "## F0 · beantwortet · alte Frage\nx\n")
        answer = {**HINT, "titel": "Ladepunkt-Actors auf Apify haben kaum Nutzer", "kurztitel": "ladepunkt-actors"}
        self.assertEqual(hinweise.main(self.env, T0, self.asker([answer, {"urteil": "ok"}])), 0)
        self.assertIn("## Offene Frage von Mina (hat Vorrang)", self.prompts[0][1])
        self.assertIn("ZUG37.md F1", self.prompts[1][1])
        self.assertNotIn("alte Frage", self.prompts[0][1])
        log = [json.loads(x) for x in (self.d / "state" / "hinweise.jsonl").read_text().splitlines()]
        self.assertEqual((log[-1]["art"], log[-1]["frage"]), ("abgelegt", "F1"))
        text = (self.d / "ablage" / "hinweise" / log[-1]["datei"]).read_text()
        self.assertIn("- Frage: ZUG37.md F1", text)
        self.assertIn("Bezug bei Mina: ZUG37.md F1", text)
        self.prompts.clear()
        hinweise.main(self.env, T0, self.asker([{"art": "stille", "begruendung": "nichts"}]))
        self.assertNotIn("## Offene Frage von Mina", self.prompts[0][1])  # answered once is enough

    def test_question_given_up_after_three_tries(self):
        self.push_mina("ZUG37.md", "## Was zahlen Shopify-Händler für Feeds?\ntext\n")
        for _ in range(3):
            hinweise.main(self.env, T0, self.asker([{"art": "stille", "begruendung": "keine Quelle"}]))
        self.assertTrue(all("## Offene Frage von Mina" in p for _, p in self.prompts))
        self.prompts.clear()
        hinweise.main(self.env, T0, self.asker([{"art": "stille", "begruendung": "x"}]))
        self.assertNotIn("## Offene Frage von Mina", self.prompts[0][1])

    def test_numbers_status_variants_and_source_at_number(self):
        h = hinweise.check({**HINT, "zahlen": [
            {"angabe": "1.200 Nutzer", "quelle": "https://apify.com/x", "status": "Selbstauskunft"},
            {"angabe": "3 Anbieter", "quelle": "Mina: RESEARCH.md §24", "status": "Primärquelle (gezählt)"},
            {"angabe": "26 Mio. Nutzer", "quelle": "https://dev.to/x", "status": "Drittauswertung"}]})
        self.assertEqual([z["status"] for z in h["zahlen"]], ["Selbstauskunft/unbelegt", "Primärquelle", "Drittauswertung"])
        with self.assertRaisesRegex(ValueError, "zahlen 1: status"):  # the old two-level label is no longer enough
            hinweise.check({**HINT, "zahlen": [{"angabe": "1", "quelle": "https://a.org/x", "status": "belegt"}]})
        self.assertIn("https://apify.com/x", h["quellen"])
        with self.assertRaisesRegex(ValueError, "zahlen 1: status"):
            hinweise.check({**HINT, "zahlen": [{"angabe": "1", "quelle": "https://a.org/x", "status": "geschätzt"}]})

    def test_learn_notes_mina_feedback(self):
        hinweise.main(self.env, T0, self.asker([HINT, {"urteil": "ok"}]))
        src = self.d / "mina-src"
        with open(src / "DECISIONS.md", "a") as f:
            f.write("Zug37-Hinweis 2026-11-18-apify-zahlende-nutzer.md: übernommen, geht in Kandidat 2\n")
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "fb", cwd=src)
        sh("git", "push", "-q", "origin", "HEAD:main", cwd=src)
        sh("git", "pull", "-q", cwd=self.d / "mina")
        note = hinweise.learn(self.d / "state", self.d / "mina", T0, force=True)
        self.assertIn("übernommen: geht in Kandidat 2", note)


if __name__ == "__main__":
    unittest.main()
