"""Hinweise für Mina: ein Fund von außen, mit Minas Stand abgeglichen, als Datei in timkleinke/zug37-hinweise.

Started by zug37-hinweise.timer once a day (13:00, Tim 18.11.; review after a week), apart from the Redaktion. The Redaktion, its prompt and the
Telegram messages stay untouched. One run:

  1. git pull of Mina's repo (read-only deploy key) and of the Ablage (write deploy key).
  2. Once a week: read Mina's feedback lines in DECISIONS.md ("Zug37-Hinweis <datei>: übernommen/verworfen,
     Grund") into state/hinweise-lernen.md, which goes into every later prompt.
  3. Claude with web search only gets hinweise.md, Mina's state, the new Zug 37 editions and the earlier
     hints, and answers with one hint or silence.
  4. The answer is checked field by field (sources, every number with source and status, topics that are
     not for Mina, no long quotes).
  5. git pull of Mina's repo again, then a second Claude call without any tools compares the hint with
     Mina's state: ok, korrigiert (the corrected hint is checked again) or verworfen.
  6. The hint becomes hinweise/JJJJ-MM-TT-kurztitel.md in the Ablage, is committed and pushed.

At most MAX_PER_DAY hints per Berlin day. Every run, filed or not, is appended to state/hinweise.jsonl.
Mina's repo is only ever pulled, never written. Environment (defaults below):
  Z37_STATE, Z37_MINA, Z37_HINWEISE, Z37_MINA_KEY, Z37_HINWEISE_KEY, Z37_KNOWN_HOSTS, Z37_CLAUDE, Z37_MODEL
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zug37.redaktion import BERLIN, DENIED, INLINE_URL, URL, extract

HOME = Path("/var/lib/zug37")
MAX_PER_DAY = 3
STATUS_MAX, EXPERIMENTS_MAX, DECISIONS_MAX, DECISIONS_ENTRIES = 14000, 40000, 16000, 5
STATI = ("belegt", "Selbstauskunft/unbelegt")
FEEDBACK = re.compile(r"Zug37-Hinweis\s+`?([0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+\.md)`?\s*:?\s*\**\s*"
                      r"(übernommen|verworfen)\**\s*[,:;–-]?\s*(.*)", re.I)
NOT_FOR_MINA = re.compile(r"\b(meme\w*|krypto\w*|crypto\w*|solana|bitcoin|trading|rösterei|roesterei|karl|dachmarke)\b", re.I)
OLD_FIELD = re.compile(r"(ladepunkt|ladesäul|ladeinfrastruktur|ladestation|energiedaten)", re.I)
CLOSED = re.compile(r"\b(erledigt|beantwortet|geschlossen|zurückgezogen)\b", re.I)
MAX_TRIES = 3  # a question that gets no filed answer after three runs is left alone
QUOTE = re.compile(r"[„“”\"»«]([^„“”\"»«]{1,600})[„“”\"»«]")


# --- git -------------------------------------------------------------------------------------------
def git(repo, *args, key=None, env=os.environ, timeout=120):
    e = {k: v for k, v in env.items() if not k.startswith("Z37_TG_") and k != "CLAUDE_CODE_OAUTH_TOKEN"}
    if key:
        known = env.get("Z37_KNOWN_HOSTS", str(HOME / ".ssh/known_hosts"))
        e["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes -o UserKnownHostsFile={known}"
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout, env=e)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {r.stderr.strip()[-200:]}")
    return r.stdout.strip()


# --- Minas Stand -----------------------------------------------------------------------------------
def status_head(text):
    """The head block of STATUS.md: everything before the first '## ' heading."""
    m = re.search(r"^## ", text, re.M)
    head = text[: m.start()] if m else text
    return head if len(head) <= STATUS_MAX else head[:STATUS_MAX] + "\n[… gekürzt …]"


def decisions_tail(text, n=DECISIONS_ENTRIES):
    """The last n '## ' entries of DECISIONS.md (the newest are at the end)."""
    starts = [m.start() for m in re.finditer(r"^## ", text, re.M)]
    tail = text[starts[-n]:] if len(starts) >= n else text
    return tail if len(tail) <= DECISIONS_MAX else "[… gekürzt, nur der neueste Teil …]\n" + tail[-DECISIONS_MAX:]


def read(path):
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def mina_stand(repo):
    """Mina's state as one block of text plus the commit it comes from."""
    repo = Path(repo)
    exp = read(repo / "EXPERIMENTS.md")
    if len(exp) > EXPERIMENTS_MAX:
        exp = "[… gekürzt, nur der neueste Teil …]\n" + exp[-EXPERIMENTS_MAX:]
    text = (f"### STATUS.md (Kopfblock)\n\n{status_head(read(repo / 'STATUS.md'))}\n\n"
            f"### EXPERIMENTS.md\n\n{exp}\n\n"
            f"### DECISIONS.md (die letzten {DECISIONS_ENTRIES} Einträge)\n\n{decisions_tail(read(repo / 'DECISIONS.md'))}\n")
    return text


def mina_rev(repo, env=os.environ):
    try:
        return git(repo, "log", "-1", "--format=%h %cd", "--date=format:%d.%m.%Y %H:%M", env=env)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return "unbekannt"


# --- Protokoll und Rückkanal -----------------------------------------------------------------------
def log_entries(state):
    out = []
    for line in read(state / "hinweise.jsonl").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def keep(state, name, text):
    state.mkdir(parents=True, exist_ok=True)
    tmp = state / (name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, state / name)


def append_log(state, entry):
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "hinweise.jsonl", "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def filed_today(state, now):
    today = now.astimezone(BERLIN).date()
    n = 0
    for e in log_entries(state):
        try:
            if e.get("art") == "abgelegt" and datetime.fromisoformat(e["zeit"]).astimezone(BERLIN).date() == today:
                n += 1
        except (KeyError, ValueError, TypeError):
            pass
    return n


def feedback(decisions):
    """Mina's verdicts per file; a later line for the same file replaces an earlier one."""
    out = {}
    for m in FEEDBACK.finditer(decisions):
        out[m.group(1)] = {"urteil": m.group(2).lower(), "grund": m.group(3).strip().rstrip("*").strip()[:300]}
    return out


def learn(state, mina_repo, now, force=False):
    """Once a week: Mina's feedback lines into hinweise-lernen.md. Returns the current note (may be empty)."""
    note = state / "hinweise-lernen.md"
    try:
        fresh = now - datetime.fromtimestamp(note.stat().st_mtime, timezone.utc) < timedelta(days=7)
    except OSError:
        fresh = False
    if fresh and not force:
        return read(note)
    verdicts = feedback(read(Path(mina_repo) / "DECISIONS.md"))
    filed = {e["datei"]: e for e in log_entries(state) if e.get("art") == "abgelegt" and e.get("datei")}
    lines = [f"# Was bei Mina ankommt (Stand {now.astimezone(BERLIN):%d.%m.%Y})", ""]
    if not filed:
        lines.append("Noch keine Hinweise abgelegt.")
    else:
        took = sum(1 for v in verdicts.values() if v["urteil"] == "übernommen")
        lines.append(f"{len(filed)} Hinweise abgelegt, {len(verdicts)} von Mina beantwortet: "
                     f"{took} übernommen, {len(verdicts) - took} verworfen, {len(filed) - len(verdicts)} ohne Antwort.")
        lines.append("")
        for datei, e in sorted(filed.items()):
            v = verdicts.get(datei)
            urteil = f"{v['urteil']}: {v['grund'] or 'ohne Grund'}" if v else "noch keine Antwort"
            lines.append(f"- {datei} ({e.get('thema', '')}): {urteil}")
    text = "\n".join(lines) + "\n"
    state.mkdir(parents=True, exist_ok=True)
    tmp = note.with_name(note.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, note)
    return text


def questions(text):
    """Mina's questions in ZUG37.md: one '## ' section each. A heading with erledigt/beantwortet/geschlossen/
    zurückgezogen is closed. The id is 'F<n>' from the heading, else a short hash of the heading."""
    out = []
    parts = re.split(r"^## +", text, flags=re.M)[1:]
    for part in parts:
        head, _, body = part.partition("\n")
        head = head.strip()
        if not head or CLOSED.search(head):
            continue
        m = re.search(r"\bF\d+\b", head)
        qid = m.group(0) if m else "F-" + hashlib.sha1(head.encode()).hexdigest()[:8]
        out.append({"id": qid, "titel": head[:200], "text": body.strip()[:2000]})
    return out


def open_question(mina, state):
    """The first question in ZUG37.md that Zug 37 has neither answered nor tried MAX_TRIES times."""
    log = log_entries(state)
    answered = {e.get("frage") for e in log if e.get("art") == "abgelegt"}
    tries = Counter(e.get("frage") for e in log if e.get("frage") and e.get("art") != "abgelegt")
    for q in questions(read(Path(mina) / "ZUG37.md")):
        if q["id"] not in answered and tries[q["id"]] < MAX_TRIES:
            return q
    return None


def editions_since(state, since):
    """The Zug 37 editions for Tim since the last hint run: candidates, never copied as they are."""
    out = []
    for line in read(state / "verlauf.jsonl").splitlines():
        try:
            e = json.loads(line)
            if e.get("art") == "zeigen" and datetime.fromisoformat(e["zeit"]) > since:
                out.append({k: e.get(k) for k in ("zeit", "rubrik", "zeile", "bezug", "detail", "quellen")})
        except (ValueError, KeyError, TypeError):
            continue
    return out


# --- Prüfung ----------------------------------------------------------------------------------------
def slug(text):
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:50].rstrip("-")


def status_of(s):
    """'belegt' or 'Selbstauskunft/unbelegt', also from close variants; None if neither."""
    s = s.strip().lower()
    if "selbst" in s or "unbelegt" in s or "unklar" in s:
        return STATI[1]
    return STATI[0] if s.startswith("belegt") else None


def check(h, frage=False):
    """Returns the cleaned hint or raises ValueError with the field name."""
    if not isinstance(h, dict) or h.get("art") not in ("hinweis", "stille"):
        raise ValueError("art")
    out = {"art": h["art"], "begruendung": str(h.get("begruendung", ""))[:800]}
    if h["art"] == "stille":
        return out
    for key, lo, hi in (("titel", 1, 120), ("thema", 1, 160), ("bezug", 1, 300), ("befund", 40, 1800),
                        ("bedeutung", 20, 1000)):
        v = h.get(key, "")
        if not isinstance(v, str) or not lo <= len(v.strip()) <= hi:
            raise ValueError(key)
        out[key] = v.strip()
    for key in ("befund", "bedeutung"):
        out[key] = INLINE_URL.sub("[Link in den Quellen]", out[key])
    out["kurztitel"] = slug(str(h.get("kurztitel") or out["titel"]))
    if len(out["kurztitel"]) < 3:
        raise ValueError("kurztitel")
    quellen = h.get("quellen")
    if not isinstance(quellen, list) or not 1 <= len(quellen) <= 6 or not all(isinstance(q, str) and URL.match(q) for q in quellen):
        raise ValueError("quellen")
    quellen = list(quellen)
    out["quellen"] = quellen
    zahlen = h.get("zahlen") or []
    if not isinstance(zahlen, list) or len(zahlen) > 20:
        raise ValueError("zahlen: keine Liste")
    clean = []
    for i, z in enumerate(zahlen, 1):
        if not isinstance(z, dict):
            raise ValueError(f"zahlen {i}: kein Objekt")
        angabe, quelle, status = (str(z.get(k, "")).strip() for k in ("angabe", "quelle", "status"))
        status = status_of(status)
        if not angabe or len(angabe) > 300:
            raise ValueError(f"zahlen {i}: angabe")
        if not status:
            raise ValueError(f"zahlen {i}: status")
        if URL.match(quelle) and quelle not in quellen and len(quellen) < 6:
            quellen.append(quelle)  # a source named only at the number still counts as a source
        if quelle not in quellen and not (quelle.startswith("Mina:") and 6 < len(quelle) <= 100):
            raise ValueError(f"zahlen {i}: quelle")
        clean.append({"angabe": angabe, "quelle": quelle, "status": status})
    if re.search(r"\d", out["befund"]) and not clean:
        raise ValueError("zahlen: Zahlen im Befund ohne Quelle")
    out["zahlen"] = clean
    if NOT_FOR_MINA.search(" ".join(out[k] for k in ("titel", "thema", "befund", "bedeutung"))):
        raise ValueError("thema")
    if not frage and OLD_FIELD.search(out["titel"] + " " + out["thema"]):
        raise ValueError("thema")  # the new round is outside charging and energy data (unless Mina asked)
    for key in ("befund", "bedeutung"):
        if any(len(q.split()) > 10 for q in QUOTE.findall(out[key])) or re.search(r"^\s*>", out[key], re.M):
            raise ValueError("zitat")
    return out


def check_verdict(v):
    if not isinstance(v, dict) or v.get("urteil") not in ("ok", "korrigiert", "verworfen"):
        raise ValueError("urteil")
    pr = v.get("pruefungen") if isinstance(v.get("pruefungen"), list) else []
    return {"urteil": v["urteil"], "grund": str(v.get("grund", ""))[:500],
            "pruefungen": [p for p in pr if isinstance(p, dict)][:20], "hinweis": v.get("hinweis")}


# --- Datei ------------------------------------------------------------------------------------------
def render(h, day, rev, verdict, frage=None):
    quellen = "\n".join(f"  - {q}" for q in h["quellen"])
    if frage:
        quellen += f"\n- Frage: ZUG37.md {frage['id']}: {frage['titel']}"
    abgleich = f"Minas Stand {rev}: {verdict['urteil']}"
    if verdict["urteil"] == "korrigiert" and verdict["grund"]:
        abgleich += f" ({verdict['grund']})"
    zahlen = "\n".join(f"- {z['angabe']}. Quelle: {z['quelle']}. {z['status']}" for z in h["zahlen"]) or "- keine"
    return (f"# {h['titel']}\n\n"
            f"- Datum: {day:%Y-%m-%d}\n- Thema: {h['thema']}\n- Quellen:\n{quellen}\n"
            f"- Bezug bei Mina: {h['bezug']}\n- Abgleich: {abgleich}\n\n"
            f"## Befund\n\n{h['befund']}\n\n## Zahlen\n\n{zahlen}\n\n"
            f"## Mögliche Bedeutung für Mina\n\n{h['bedeutung']}\n\n"
            f"*Vorschlag von Zug 37, keine Anweisung. Rückmeldung bitte als Zeile in DECISIONS.md: "
            f"„Zug37-Hinweis <Dateiname>: übernommen / verworfen, Grund“.*\n")


def filename(folder, day, kurz):
    name = f"{day:%Y-%m-%d}-{kurz}.md"
    i = 2
    while (folder / name).exists():
        name = f"{day:%Y-%m-%d}-{kurz}-{i}.md"
        i += 1
    return name


def file_hint(repo, text, name, key, env):
    git(repo, "pull", "-q", "--ff-only", key=key, env=env)
    folder = Path(repo) / "hinweise"
    folder.mkdir(exist_ok=True)
    if (folder / name).exists():
        name = filename(folder, datetime.strptime(name[:10], "%Y-%m-%d"), name[11:-3])
    (folder / name).write_text(text)
    git(repo, "add", f"hinweise/{name}", env=env)
    git(repo, "-c", "user.name=Zug 37", "-c", "user.email=zug37@users.noreply.github.com",
        "commit", "-q", "-m", f"Hinweis {name}", env=env)
    try:
        git(repo, "push", "-q", "origin", "HEAD", key=key, env=env)
    except RuntimeError:
        git(repo, "pull", "-q", "--rebase", key=key, env=env)
        git(repo, "push", "-q", "origin", "HEAD", key=key, env=env)
    return name


# --- Claude -----------------------------------------------------------------------------------------
S = {"type": "string"}
HINT_SCHEMA = {"type": "object", "required": ["art", "begruendung"], "properties": {
    "art": {"type": "string", "enum": ["hinweis", "stille"]}, "titel": S, "kurztitel": S, "thema": S,
    "quellen": {"type": "array", "items": S}, "bezug": S, "befund": S, "bedeutung": S, "begruendung": S,
    "zahlen": {"type": "array", "items": {"type": "object", "required": ["angabe", "quelle", "status"], "properties": {
        "angabe": S, "quelle": S, "status": {"type": "string", "enum": list(STATI)}}}}}}
VERDICT_SCHEMA = {"type": "object", "required": ["urteil", "grund"], "properties": {
    "urteil": {"type": "string", "enum": ["ok", "korrigiert", "verworfen"]}, "grund": S,
    "pruefungen": {"type": "array", "items": {"type": "object", "properties": {
        "behauptung": S, "minas_stand": S, "ergebnis": S}}},
    "hinweis": {"anyOf": [{"type": "null"}, HINT_SCHEMA]}}}


def ask(workdir, prompt, env, web, schema=None):
    """Claude Code in print mode. With a schema the answer is structured output (no hand-written JSON that can
    break on a quotation mark); it is returned as a ```json block, like a free answer."""
    cmd = [env.get("Z37_CLAUDE", "claude"), "-p", "--output-format", "json", "--max-turns", "40" if web else "5",
           "--setting-sources", "user", "--strict-mcp-config"]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    cmd += ["--allowedTools", "WebSearch", "--disallowedTools", DENIED] if web else ["--tools", ""]
    if env.get("Z37_MODEL"):
        cmd += ["--model", env["Z37_MODEL"]]
    clean = {k: v for k, v in env.items() if not k.startswith("Z37_TG_")}
    r = subprocess.run(cmd, cwd=workdir, input=prompt, capture_output=True, text=True, timeout=1500, env=clean)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}")
    out = json.loads(r.stdout)
    if schema and isinstance(out.get("structured_output"), dict):
        return "```json\n" + json.dumps(out["structured_output"], ensure_ascii=False, indent=1) + "\n```"
    return out["result"]


def question_block(frage):
    return (f"\n## Offene Frage von Mina (hat Vorrang)\n\nZUG37.md {frage['id']}: {frage['titel']}\n\n"
            f"{frage['text'] or '(ohne weiteren Text)'}\n")


def build_prompt(stand, editions, earlier, note, now, frage=None):
    local = now.astimezone(BERLIN)
    return (Path(__file__).with_name("hinweise.md").read_text()
            + (question_block(frage) if frage else "")
            + "\n## Minas Stand\n\n" + stand
            + "\n## Neue Ausgaben von Zug 37 für Tims Display\n\n"
            + (json.dumps(editions, ensure_ascii=False, indent=1) if editions else "keine") + "\n"
            + "\n## Bisherige Hinweise an Mina\n\n"
            + (json.dumps(earlier, ensure_ascii=False, indent=1) if earlier else "noch keine") + "\n"
            + "\n## Rückmeldungen von Mina\n\n" + (note or "noch keine") + "\n"
            + f"\n## Jetzt\n\n{local:%d.%m.%Y, %H:%M} Uhr (Berlin).\n")


def build_check_prompt(stand, hint, frage=None):
    return (Path(__file__).with_name("abgleich.md").read_text()
            + (question_block(frage) + "\nDer Hinweis beantwortet diese Frage. Damit passt er zur Phase.\n" if frage else "")
            + "\n## Der Hinweis\n\n```json\n" + json.dumps(hint, ensure_ascii=False, indent=1) + "\n```\n"
            + "\n## Minas Stand\n\n" + stand)


# --- Lauf -------------------------------------------------------------------------------------------
def main(env=os.environ, now=None, asker=ask):
    state = Path(env.get("Z37_STATE") or env.get("STATE_DIRECTORY") or "out")
    mina = Path(env.get("Z37_MINA", HOME / "mina"))
    ablage = Path(env.get("Z37_HINWEISE", HOME / "hinweise"))
    mina_key = env.get("Z37_MINA_KEY", str(HOME / ".ssh/mina_ro"))
    ablage_key = env.get("Z37_HINWEISE_KEY", str(HOME / ".ssh/hinweise_rw"))
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")

    frage = None

    def done(art, code=0, **kw):
        if frage:
            kw = {"frage": frage["id"], **kw}
        append_log(state, {"zeit": stamp, "art": art, **kw})
        print(f"zug37-hinweise: {art} {kw.get('datei') or kw.get('grund', '')}".strip()[:200])
        return code

    if not (mina / "STATUS.md").is_file() or not (ablage / ".git").is_dir():
        return done("fehler", 2, grund="Minas Checkout oder die Ablage fehlt")
    try:
        git(mina, "pull", "-q", "--ff-only", key=mina_key, env=env)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        return done("fehler", 1, grund=f"Minas Stand nicht aktuell: {e}"[:200])  # never compare against an old state
    note = learn(state, mina, now)
    if filed_today(state, now) >= MAX_PER_DAY:
        return done("stille", grund=f"schon {MAX_PER_DAY} Hinweise heute")

    previous = [e for e in log_entries(state) if e.get("art") != "fehler"]
    since = datetime.fromisoformat(previous[-1]["zeit"]) if previous else now - timedelta(days=1)
    earlier = [{k: e.get(k) for k in ("zeit", "datei", "titel", "thema")} for e in log_entries(state)
               if e.get("art") == "abgelegt"][-30:]
    frage = open_question(mina, state)  # Mina's open question comes before the own search
    workdir = state / "leer"
    workdir.mkdir(parents=True, exist_ok=True)

    def asked(prompt, web, what):
        answer = asker(workdir, prompt, env, web, schema=HINT_SCHEMA if what == "recherche" else VERDICT_SCHEMA)
        keep(state, f"hinweise-letzte-{what}.txt", answer)  # the raw answer of the last run, for checking errors
        return extract(answer)

    try:
        hint = check(asked(build_prompt(mina_stand(mina), editions_since(state, since), earlier, note, now, frage),
                           True, "recherche"), bool(frage))
    except Exception as e:  # noqa: BLE001 - one line, no content
        return done("fehler", 1, grund=f"Recherche: {type(e).__name__} {e if isinstance(e, ValueError) else ''}".strip())
    if hint["art"] == "stille":
        return done("stille", grund=hint["begruendung"])
    if frage and frage["id"] not in hint["bezug"]:
        hint["bezug"] = f"ZUG37.md {frage['id']}; {hint['bezug']}"[:300]

    # Abgleich: the newest state, pulled right before the comparison
    try:
        git(mina, "pull", "-q", "--ff-only", key=mina_key, env=env)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        return done("fehler", 1, grund=f"Minas Stand vor dem Abgleich nicht aktuell: {e}"[:200], titel=hint["titel"])
    rev = mina_rev(mina, env)
    try:
        verdict = check_verdict(asked(build_check_prompt(mina_stand(mina), hint, frage), False, "abgleich"))
        if verdict["urteil"] == "korrigiert":
            fixed = check({**(verdict["hinweis"] or {}), "art": "hinweis"}, bool(frage))
            fixed["begruendung"] = hint["begruendung"]
            if frage and frage["id"] not in fixed["bezug"]:
                fixed["bezug"] = f"ZUG37.md {frage['id']}; {fixed['bezug']}"[:300]
            hint = fixed
    except Exception as e:  # noqa: BLE001
        return done("fehler", 1, grund=f"Abgleich: {type(e).__name__} {e if isinstance(e, ValueError) else ''}".strip(),
                    titel=hint["titel"])
    record = {"titel": hint["titel"], "thema": hint["thema"], "mina": rev, "urteil": verdict["urteil"],
              "grund": verdict["grund"], "pruefungen": verdict["pruefungen"]}
    if verdict["urteil"] == "verworfen":
        return done("verworfen", **record)

    day = now.astimezone(BERLIN)
    name = filename(ablage / "hinweise", day, hint["kurztitel"])
    try:
        name = file_hint(ablage, render(hint, day, rev, verdict, frage), name, ablage_key, env)
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        return done("fehler", 1, grund=f"Ablage: {e}"[:200], **record)
    return done("abgelegt", datei=name, **record)


if __name__ == "__main__":
    sys.exit(main())
