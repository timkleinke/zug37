"""Offline tests: check(), the bot's logic with a fake Telegram, the display frame and feed."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zug37 import anzeige, bot, redaktion

T0 = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)  # a Monday
ED = {"art": "zeigen", "rubrik": "IDEENBÖRSE", "zeile": "Ein Fund", "fuss": "KI-Fremdbild", "licht": False,
      "detail": "Mehr dazu", "quellen": ["https://example.org/a"], "bezug": "KI-Fremdbild", "zeit": T0.isoformat()}


class FakeApi:
    def __init__(self): self.calls, self.docs = [], []
    def __call__(self, method, **p): self.calls.append((method, p)); return {}
    def document(self, chat, name, content, caption): self.docs.append((name, content))


class Check(unittest.TestCase):
    def test_only_ideenboerse_with_sources(self):
        ok = dict(ED); del ok["zeit"]
        self.assertEqual(redaktion.check(ok)["rubrik"], "IDEENBÖRSE")
        for bad in ({"rubrik": "FRAGE"}, {"quellen": []}, {"zeile": "x" * 91}, {"quellen": ["javascript:1"]}):
            with self.assertRaises(ValueError):
                redaktion.check({**ok, **bad})

    def test_names_blocked_case_insensitive(self):
        e = {k: v for k, v in ED.items() if k != "zeit"}
        with self.assertRaises(ValueError):
            redaktion.check({**e, "zeile": "henrik baut das auch"}, {"Henrik"})

    def test_silence(self):
        self.assertEqual(redaktion.check({"art": "stille", "begruendung": "nichts"})["art"], "stille")


class Bot(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "ausgabe.json").write_text(json.dumps(ED))

    def test_sends_once_and_records_tap(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        bot.step(api, self.d, "42", T0, [])
        sent = [c for c in api.calls if c[0] == "sendMessage"]
        self.assertEqual(len(sent), 1)
        data = sent[0][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertLessEqual(len(data.encode()), 64)
        tap = {"update_id": 7, "callback_query": {"id": "q", "data": data, "message": {"message_id": 1, "chat": {"id": 42}}}}
        bot.step(api, self.d, "42", T0, [tap])
        self.assertEqual(bot.tally(self.d)["display"]["n"], 1)
        self.assertEqual(json.loads((self.d / "bot.json").read_text())["offset"], 8)

    def test_foreign_chat_ignored(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        tap = {"update_id": 1, "callback_query": {"id": "q", "data": "n|dX", "message": {"message_id": 1, "chat": {"id": 99}}}}
        msg = {"update_id": 2, "message": {"chat": {"id": 99}, "text": "/stand"}}
        bot.step(api, self.d, "42", T0, [tap, msg])
        self.assertEqual(bot.tally(self.d)["display"]["n"], 0)
        self.assertFalse((self.d / "notizen.jsonl").exists())

    def test_sunday_comparison_and_rating(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        sunday = T0 + timedelta(days=6, hours=3)  # Sunday 10:30 Berlin
        bot.step(api, self.d, "42", sunday, [], prompt_for=lambda now: "AUFGABE")
        bot.step(api, self.d, "42", sunday, [], prompt_for=lambda now: "AUFGABE")
        self.assertEqual(len(api.docs), 1)
        answer = {"update_id": 3, "message": {"chat": {"id": 42}, "text": "Antwort aus dem Chat"}}
        bot.step(api, self.d, "42", sunday, [answer])
        data = api.calls[-1][1]["reply_markup"]["inline_keyboard"][0][2]["callback_data"]
        tap = {"update_id": 4, "callback_query": {"id": "q", "data": data, "message": {"message_id": 2, "chat": {"id": 42}}}}
        bot.step(api, self.d, "42", sunday, [tap])
        self.assertEqual(bot.tally(self.d)["chat"]["x"], 1)

    def test_day_28_summary_once(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        later = T0 + timedelta(days=28)
        bot.step(api, self.d, "42", later, [])
        bot.step(api, self.d, "42", later, [])
        self.assertEqual(sum(1 for m, p in api.calls if m == "sendMessage" and "Tag 28" in p.get("text", "")), 1)


class Anzeige(unittest.TestCase):
    def test_feed_and_frame(self):
        d = Path(tempfile.mkdtemp()); pub = d / "pub"; pub.mkdir()
        (d / "ausgabe.json").write_text(json.dumps(ED))
        env = {"Z37_STATE": str(d), "Z37_PUBLIC_DIR": str(pub), "Z37_PUBLIC_URL": "https://tm.mif.works/z37/ab/"}
        self.assertEqual(anzeige.main(env, now=T0 + timedelta(minutes=5)), 0)
        feed = json.loads((pub / "feed.json").read_text())
        self.assertEqual((pub / f"{feed['frame']['sha256']}.bin").stat().st_size, 4736)
        self.assertEqual(feed["led"], {"mode": "off", "color": "off"})


if __name__ == "__main__":
    unittest.main()
