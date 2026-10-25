"""Telegram as the measuring instrument of the test (TEST.md). Runs as zug37-bot.service.

- Every new edition from the Redaktion comes to Tim with detail, sources and three buttons:
  Neu und relevant · Schon bekannt · Nicht relevant. The tap is written to bewertungen.jsonl.
- Sundays from 9:00 the bot sends the exact Redaktion task as a file. Tim gives it to Claude in the
  normal chat and sends the answer back here; it gets the same three buttons (quelle "chat").
- A text message otherwise is kept as a note on the current edition. /stand shows the count so far.
- On day 28 after the first edition the bot sends the result and the decision rule.

Only messages from Z37_TG_CHAT count. The bot token comes from the environment and is never logged.
No model is called here.
"""
import html
import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
URTEILE = {"n": "Neu und relevant", "b": "Schon bekannt", "x": "Nicht relevant"}
TESTTAGE = 28


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


def buttons(key):
    return {"inline_keyboard": [[{"text": v, "callback_data": f"{k}|{key}"[:64]} for k, v in URTEILE.items()]]}


def edition_text(e):
    q = "\n".join(f'<a href="{html.escape(u, quote=True)}">{html.escape(u.split("/")[2])}</a>' for u in e.get("quellen", []))
    return (f"<b>{html.escape(e['zeile'])}</b>\n<i>{html.escape(e.get('fuss', ''))}</i>\n\n"
            f"{html.escape(e.get('detail', ''))}\n\n{q}")[:4000]


def tally(state, since=None):
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
        return f"{name}: {c['n']} neu und relevant von {total} bewertet ({share}), {c['b']} bekannt, {c['x']} nicht relevant"
    return line("Display", t["display"]) + "\n" + line("Chat", t["chat"])


def step(api, state, chat, now, updates, prompt_for=None):
    """One round: send what is new, handle updates. Returns the next offset. Pure logic, testable."""
    st = load(state / "bot.json", {})
    e = load(state / "ausgabe.json", None)
    if e and e.get("art") == "zeigen" and e.get("zeit") != st.get("gesendet"):
        api("sendMessage", chat_id=chat, text=edition_text(e), parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=buttons(f"d{e['zeit']}"))
        st["gesendet"] = e["zeit"]
        st.setdefault("start", e["zeit"])
    local = now.astimezone(BERLIN)
    week = f"{local:%G-W%V}"
    if prompt_for and local.weekday() == 6 and local.hour >= 9 and st.get("vergleich") != week and st.get("start"):
        api.document(chat, f"zug37-vergleich-{week}.md", prompt_for(now),
                     "Vergleich: Gib diese Datei Claude in einem neuen Chat (mit Websuche) und schick mir die Antwort hier zurück.")
        st["vergleich"] = week
        st["warte_auf_chat"] = week
    if st.get("start") and not st.get("ende"):
        start = datetime.fromisoformat(st["start"])
        if now - start >= timedelta(days=TESTTAGE):
            t = tally(state)
            api("sendMessage", chat_id=chat, text="Tag 28. Ergebnis des Tests:\n\n" + tally_text(t)
                + "\n\nRegel: Liefert das Display häufiger Neues und Relevantes als der Chat? Wenn nicht, wird nicht weiter ausgebaut.")
            st["ende"] = now.isoformat(timespec="seconds")
    offset = st.get("offset", 0)
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if cq and str(cq.get("message", {}).get("chat", {}).get("id")) == str(chat):
            code, _, key = cq.get("data", "").partition("|")
            if code in URTEILE and key:
                quelle = "chat" if key.startswith("c") else "display"
                append(state / "bewertungen.jsonl", {"zeit": now.isoformat(timespec="seconds"), "quelle": quelle,
                                                     "id": key[1:], "urteil": code})
                api("answerCallbackQuery", callback_query_id=cq["id"], text=URTEILE[code])
                api("editMessageReplyMarkup", chat_id=chat, message_id=cq["message"]["message_id"],
                    reply_markup={"inline_keyboard": [[{"text": f"Bewertet: {URTEILE[code]}", "callback_data": cq["data"]}]]})
            continue
        m = u.get("message")
        if not m or str(m.get("chat", {}).get("id")) != str(chat) or not m.get("text"):
            continue
        text = m["text"].strip()
        if text in ("/stand", "/start"):
            api("sendMessage", chat_id=chat, text=tally_text(tally(state)))
        elif st.get("warte_auf_chat"):
            key = f"c{st['warte_auf_chat']}"
            append(state / "vergleich.jsonl", {"zeit": now.isoformat(timespec="seconds"), "woche": st["warte_auf_chat"],
                                               "antwort": text[:4000]})
            api("sendMessage", chat_id=chat, text="Antwort aus dem Chat erhalten. Wie war sie?", reply_markup=buttons(key))
            st["warte_auf_chat"] = None
        else:
            append(state / "notizen.jsonl", {"zeit": now.isoformat(timespec="seconds"), "zu": st.get("gesendet"),
                                             "text": text[:2000]})
            api("sendMessage", chat_id=chat, text="Notiert.")
    st["offset"] = offset
    save(state / "bot.json", st)
    return offset


def main(env=os.environ):
    token, chat = env.get("Z37_TG_TOKEN"), env.get("Z37_TG_CHAT")
    state = Path(env.get("Z37_STATE") or env.get("STATE_DIRECTORY") or "out")
    repo = Path(env.get("Z37_REPO", ""))
    if not token or not chat:
        print("Z37_TG_TOKEN and Z37_TG_CHAT are required", file=sys.stderr)
        return 2
    api = Telegram(token)

    def prompt_for(now):
        from . import redaktion
        return redaktion.build_prompt(repo, state, now)

    print("zug37-bot: läuft")
    while True:
        try:
            offset = load(state / "bot.json", {}).get("offset", 0)
            updates = api("getUpdates", timeout=40, offset=offset, allowed_updates=["message", "callback_query"])
            step(api, state, chat, datetime.now(timezone.utc), updates, prompt_for)
        except Exception as e:  # noqa: BLE001 - keep running, log only the type
            print(f"zug37-bot: {type(e).__name__}", file=sys.stderr)
            time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
