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

    def tap(self, api, uid, idx=0, mid=1):
        data = [c for c in api.calls if c[0] == "sendMessage" and "reply_markup" in c[1]][-1][1]["reply_markup"]["inline_keyboard"][0][idx]["callback_data"]
        return {"update_id": uid, "callback_query": {"id": "q", "data": data, "message": {"message_id": mid, "chat": {"id": 42}}}}

    def test_sends_once_and_records_tap(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        bot.step(api, self.d, "42", T0, [])
        sent = [c for c in api.calls if c[0] == "sendMessage"]
        self.assertEqual(len(sent), 1)
        self.assertLessEqual(len(sent[0][1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].encode()), 64)
        bot.step(api, self.d, "42", T0, [self.tap(api, 7)])
        self.assertEqual(bot.tally(self.d)["display"]["n"], 1)
        self.assertEqual(json.loads((self.d / "bot.json").read_text())["offset"], 8)

    def test_retap_changes_verdict_and_errors_do_not_repeat(self):
        class Flaky(FakeApi):
            def __call__(self, method, **p):
                super().__call__(method, **p)
                if method in ("answerCallbackQuery", "editMessageReplyMarkup"):
                    raise RuntimeError("400")
        api = Flaky()
        bot.step(api, self.d, "42", T0, [])
        bot.step(api, self.d, "42", T0, [self.tap(api, 1, 0)])
        bot.step(api, self.d, "42", T0, [self.tap(api, 2, 2)])
        bot.step(api, self.d, "42", T0, [])
        self.assertEqual(sum(1 for c in api.calls if c[0] == "sendMessage"), 1)
        t = bot.tally(self.d)["display"]
        self.assertEqual((t["n"], t["x"]), (0, 1))
        self.assertEqual(json.loads((self.d / "bot.json").read_text())["offset"], 3)

    def test_foreign_chat_ignored(self):
        api = FakeApi()
        bot.step(api, self.d, "42", T0, [])
        tap = {"update_id": 1, "callback_query": {"id": "q", "data": "n|dX", "message": {"message_id": 1, "chat": {"id": 99}}}}
        msg = {"update_id": 2, "message": {"chat": {"id": 99, "type": "private"}, "text": "/stand"}}
        bot.step(api, self.d, "42", T0, [tap, msg])
        self.assertEqual(bot.tally(self.d)["display"]["n"], 0)
        self.assertFalse((self.d / "notizen.jsonl").exists())

    def sunday(self, api, text_parts, silence=False):
        bot.step(api, self.d, "42", T0, [])
        (self.d / "aufgabe.md").write_text("AUFGABE WÖRTLICH")
        sunday = T0 + timedelta(days=6, hours=3)  # Sunday 10:30 Berlin
        import os
        os.utime(self.d / "aufgabe.md", (sunday.timestamp(), sunday.timestamp()))
        bot.step(api, self.d, "42", sunday, [])
        bot.step(api, self.d, "42", sunday, [])
        msgs = [{"update_id": 10 + i, "message": {"chat": {"id": 42, "type": "private"}, "text": p}} for i, p in enumerate(text_parts)]
        bot.step(api, self.d, "42", sunday, msgs)
        bot.step(api, self.d, "42", sunday + timedelta(minutes=2), [])
        return sunday

    def test_sunday_same_task_and_joined_answer(self):
        api = FakeApi()
        self.sunday(api, ["Teil eins", "Teil zwei"])
        self.assertEqual(api.docs, [("zug37-vergleich-2026-W44.md", "AUFGABE WÖRTLICH")])
        v = [json.loads(l) for l in (self.d / "vergleich.jsonl").read_text().splitlines()]
        self.assertEqual(v[0]["antwort"], "Teil eins\nTeil zwei")
        api_tap = self.tap(api, 20, 1, mid=2)
        bot.step(api, self.d, "42", T0 + timedelta(days=6, hours=4), [api_tap])
        self.assertEqual(bot.tally(self.d)["chat"]["b"], 1)
        self.assertFalse((self.d / "notizen.jsonl").exists())

    def test_sunday_silence_does_not_count(self):
        api = FakeApi()
        self.sunday(api, ['```json\n{"art": "stille", "begruendung": "nichts"}\n```'])
        self.assertIn("zählt nicht", api.calls[-1][1]["text"])
        self.assertNotIn("reply_markup", api.calls[-1][1])

    def test_long_detail_never_cuts_html(self):
        e = {**ED, "detail": '"' * 1500, "quellen": ["https://example.org/" + "a&" * 150] * 6}
        text = bot.edition_text(e)
        self.assertLessEqual(len(text), bot.MAX_TEXT)
        self.assertEqual(text.count("<a "), text.count("</a>"))

    def test_unsafe_links_dropped(self):
        e = {**ED, "quellen": ["https://github.com@evil.tld/x", "http://example.org", "https://exämple.org/", "https://ok.org/a"]}
        self.assertEqual(bot.edition_text(e).count("<a "), 1)

    def test_day_28_summary_once_after_edition(self):
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


class Abwechslung(unittest.TestCase):
    def setUp(self):
        import hashlib
        self.d = Path(tempfile.mkdtemp()); self.pub = self.d / "pub"; self.pub.mkdir(); self.sr = self.d / "sr"; self.sr.mkdir()
        (self.d / "ausgabe.json").write_text(json.dumps(ED))  # edition at 07:30 Berlin
        self.srraw = bytes([0x55]) * 4736
        sha = hashlib.sha256(self.srraw).hexdigest()
        (self.sr / f"{sha}.bin").write_bytes(self.srraw)
        (self.sr / "feed.json").write_text(json.dumps({"v": 1, "frame": {"sha256": sha}, "led": {"mode": "solid", "color": "white"}}))
        self.env = {"Z37_STATE": str(self.d), "Z37_PUBLIC_DIR": str(self.pub), "Z37_PUBLIC_URL": "https://h.example/z/", "Z37_SR_DIR": str(self.sr)}

    def shown(self, minutes_after_edition):
        anzeige.main(self.env, now=T0 + timedelta(minutes=minutes_after_edition))
        feed = json.loads((self.pub / "feed.json").read_text())
        return (self.pub / f"{feed['frame']['sha256']}.bin").read_bytes() == self.srraw, feed["led"]

    def test_alone_first_then_turns_and_shared_light(self):
        self.assertFalse(self.shown(30)[0])           # 08:00, edition still alone
        a, b = self.shown(120)[0], self.shown(135)[0]  # 09:30 and 09:45: one each
        self.assertNotEqual(a, b)
        self.assertEqual(self.shown(120)[1], {"mode": "solid", "color": "white"})

    def test_evening_and_broken_feed_keep_zug37(self):
        self.assertFalse(self.shown(12 * 60 + 15)[0])  # 19:45 Berlin
        (self.sr / "feed.json").write_text("kaputt")
        self.assertFalse(self.shown(135)[0])
        self.assertFalse(self.shown(120)[0])


if __name__ == "__main__":
    unittest.main()
