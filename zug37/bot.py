"""Telegram as the measuring instrument of the test (TEST.md). Runs as zug37-bot.service.

- Every new edition from the Redaktion comes to Tim with detail, sources and three buttons:
  Neu und relevant · Schon bekannt · Nicht relevant. A tap is written to bewertungen.jsonl; tapping
  again changes the verdict (the last one counts).
- Sundays from 9:00 the bot sends the Redaktion's task of that morning (state/aufgabe.md, written by
  the 7:30 run before it asked Claude), so the chat gets word for word the same task. Tim gives it to
  Claude in the normal chat and sends the answer back; messages within ANSWER_WINDOW are joined. The
  answer gets the same three buttons (quelle "chat"); an answer that is silence does not count.
- Any other text is kept as a note on the current edition. /stand shows the count so far.
- On day 28 after the first edition the bot sends the result and the decision rule.

Only Z37_TG_CHAT counts. State is saved after every step that changes it, every Telegram call that is
only cosmetic is best effort, and one failing update never blocks the others. No model is called here.
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
URTEILE = {"n": "Neu und relevant", "b": "Schon bekannt", "x": "Nicht relevant"}
TESTTAGE = 28
ANSWER_WINDOW = timedelta(seconds=90)
MAX_TEXT = 3900


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}/"

    def __call__(self, method, **params):
        data = json.dumps(params).encode()
        req = urllib.request.Request(self.base + method, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=params.get("timeout", 0) + 20) as r:
            body = json.load(r)
        if not body.get("ok"):
            raise RuntimeError(f"telegram {method}: {body.get('error_code')}")
        return body["result"]

    def document(self, chat, name, content, caption):
        """sendDocument as multipart/form-data, stdlib only."""
        b = uuid.uuid4().hex
        parts = [f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n',
                 f'--{b}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n',
                 f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\n'
                 'Content-Type: text/markdown\r\n\r\n']
        data = "".join(parts).encode() + content.encode() + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(self.base + "sendDocument", data=data,
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if not json.load(r).get("ok"):
                raise RuntimeError("telegram sendDocument")


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def append(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def quietly(api, method, **params):
    """For calls that only change how something looks: a failure must not stop anything."""
    try:
        api(method, **params)
    except Exception:  # noqa: BLE001
        pass


def buttons(key, chosen=None):
    return {"inline_keyboard": [[{"text": ("● " if k == chosen else "") + v, "callback_data": f"{k}|{key}"}
                                 for k, v in URTEILE.items()]]}


def safe_url(u):
    """Only plain https links to an ASCII host, no user@host tricks."""
    try:
        p = urlsplit(u)
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.hostname) and "@" not in p.netloc and p.netloc.isascii()


def edition_text(e):
    """HTML for Telegram. Fields are cut before escaping, so no tag or entity is ever cut in half."""
    links = [u for u in e.get("quellen", []) if safe_url(u)]
    q = "\n".join(f'<a href="{html.escape(u, quote=True)}">{html.escape(u[:120])}</a>' for u in links)
    detail = e.get("detail", "")
    head = f"<b>{html.escape(e['zeile'][:200])}</b>\n<i>{html.escape(e.get('fuss', '')[:100])}</i>"
    while True:
        text = f"{head}\n\n{html.escape(detail)}\n\n{q}"
        if len(text) <= MAX_TEXT:
            return text
        if not detail:
            return head  # links alone too long: headline only, never a cut tag
        detail = detail[: max(0, len(detail) - 200)].rstrip()
        detail = detail + " …" if detail else ""


def tally(state):
    rows = []
    try:
        rows = [json.loads(line) for line in (state / "bewertungen.jsonl").read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        pass
    latest = {}  # a later tap on the same item replaces the earlier one
    for r in rows:
        latest[(r["quelle"], r["id"])] = r["urteil"]
    out = {"display": {k: 0 for k in URTEILE}, "chat": {k: 0 for k in URTEILE}}
    for (quelle, _), urteil in latest.items():
        if quelle in out and urteil in out[quelle]:
            out[quelle][urteil] += 1
    return out


def tally_text(t):
    def line(name, c):
        total = sum(c.values())
        share = f"{100 * c['n'] // total} %" if total else "–"
        return f"{name}: {c['n']} neu und relevant von {total} bewertet ({share}), {c['b']} schon bekannt, {c['x']} nicht relevant"
    return line("Display", t["display"]) + "\n" + line("Chat", t["chat"])


def is_silence(text):
    m = re.findall(r"\{[^{}]*\"art\"\s*:\s*\"stille\"[^{}]*\}", text, re.S)
    return bool(m) and not re.search(r"\"art\"\s*:\s*\"zeigen\"", text)


def finish_answer(api, state, chat, st, now):
    """The chat's answer is complete: store it, then buttons (or 'does not count' for silence)."""
    p = st.pop("puffer")
    append(state / "vergleich.jsonl", {"zeit": now.isoformat(timespec="seconds"), "woche": p["woche"], "antwort": p["text"]})
    if is_silence(p["text"]):
        api("sendMessage", chat_id=chat, text="Der Chat hat Stille gewählt. Das zählt nicht als Ausgabe, wie beim Display.")
    else:
        api("sendMessage", chat_id=chat, text="Antwort aus dem Chat erhalten. Wie war sie?", reply_markup=buttons(f"c{p['woche']}"))


def handle(api, state, chat, st, now, u):
    cq = u.get("callback_query")
    if cq:
        if str(cq.get("message", {}).get("chat", {}).get("id")) != str(chat):
            return
        code, _, key = cq.get("data", "").partition("|")
        if code in URTEILE and key[:1] in ("d", "c") and len(key) > 1:
            append(state / "bewertungen.jsonl", {"zeit": now.isoformat(timespec="seconds"),
                                                 "quelle": "chat" if key[0] == "c" else "display",
                                                 "id": key[1:], "urteil": code})
            quietly(api, "answerCallbackQuery", callback_query_id=cq["id"], text=URTEILE[code])
            quietly(api, "editMessageReplyMarkup", chat_id=chat, message_id=cq["message"]["message_id"],
                    reply_markup=buttons(key, chosen=code))
        return
    m = u.get("message")
    if not m or str(m.get("chat", {}).get("id")) != str(chat) or m.get("chat", {}).get("type") != "private":
        return
    text = (m.get("text") or "").strip()
    if not text:
        return
    if text in ("/stand", "/start"):
        api("sendMessage", chat_id=chat, text=tally_text(tally(state)))
    elif st.get("puffer"):
        st["puffer"]["text"] = (st["puffer"]["text"] + "\n" + text)[:20000]
        st["puffer"]["bis"] = (now + ANSWER_WINDOW).isoformat()
    elif st.get("warte_auf_chat"):
        st["puffer"] = {"woche": st.pop("warte_auf_chat"), "text": text, "bis": (now + ANSWER_WINDOW).isoformat()}
        api("sendMessage", chat_id=chat, text="Empfangen. Kommt noch mehr, schick es gleich hinterher.")
    else:
        append(state / "notizen.jsonl", {"zeit": now.isoformat(timespec="seconds"), "zu": st.get("gesendet"),
                                         "text": text[:2000]})
        quietly(api, "sendMessage", chat_id=chat, text="Notiert.")


def step(api, state, chat, now, updates):
    """One round. Saves the state after each change, so a failure never repeats a sent message."""
    path = state / "bot.json"
    st = load(path, {})
    e = load(state / "ausgabe.json", None)
    if e and e.get("art") == "zeigen" and e.get("zeit") != st.get("gesendet"):
        api("sendMessage", chat_id=chat, text=edition_text(e), parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=buttons(f"d{e['zeit']}"))
        st["gesendet"] = e["zeit"]
        st.setdefault("start", e["zeit"])
        save(path, st)
    local = now.astimezone(BERLIN)
    week = f"{local:%G-W%V}"
    task = state / "aufgabe.md"
    if (local.weekday() == 6 and local.hour >= 9 and st.get("start") and st.get("vergleich") != week
            and task.exists() and datetime.fromtimestamp(task.stat().st_mtime, BERLIN).date() == local.date()):
        api.document(chat, f"zug37-vergleich-{week}.md", task.read_text(),
                     "Vergleich: Gib diese Datei Claude in einem neuen Chat (mit Websuche) und schick mir die Antwort hier zurück.")
        st["vergleich"], st["warte_auf_chat"] = week, week
        save(path, st)
    if st.get("puffer") and now >= datetime.fromisoformat(st["puffer"]["bis"]):
        finish_answer(api, state, chat, st, now)
        save(path, st)
    if st.get("start") and not st.get("ende") and now - datetime.fromisoformat(st["start"]) >= timedelta(days=TESTTAGE):
        api("sendMessage", chat_id=chat, text="Tag 28. Ergebnis des Tests:\n\n" + tally_text(tally(state))
            + "\n\nRegel: Liefert das Display häufiger Neues und Relevantes als der Chat? Wenn nicht, wird nicht weiter ausgebaut.")
        st["ende"] = now.isoformat(timespec="seconds")
        save(path, st)
    for u in updates:
        st["offset"] = max(st.get("offset", 0), u["update_id"] + 1)
        try:
            handle(api, state, chat, st, now, u)
        except Exception as ex:  # noqa: BLE001 - one bad update must not block the rest
            print(f"zug37-bot: update {type(ex).__name__}", file=sys.stderr)
        save(path, st)
    return st.get("offset", 0)


def main(env=os.environ):
    token, chat = env.get("Z37_TG_TOKEN"), env.get("Z37_TG_CHAT")
    state = Path(env.get("Z37_STATE") or env.get("STATE_DIRECTORY") or "out")
    if not token or not chat:
        print("Z37_TG_TOKEN and Z37_TG_CHAT are required", file=sys.stderr)
        return 2
    api = Telegram(token)
    print("zug37-bot: läuft")
    while True:
        try:
            offset = load(state / "bot.json", {}).get("offset", 0)
            updates = api("getUpdates", timeout=30, offset=offset, allowed_updates=["message", "callback_query"])
            step(api, state, chat, datetime.now(timezone.utc), updates)
        except Exception as ex:  # noqa: BLE001 - keep running, log only the type
            print(f"zug37-bot: {type(ex).__name__}", file=sys.stderr)
            time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
