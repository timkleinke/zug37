"""One run of the Redaktion: update the logbook checkout, ask Claude Code, check the answer, write the edition.

Started by zug37-redaktion.timer once a day (test phase: 28 days, Ideenbörse only, see TEST.md). Environment:
  Z37_STATE    state directory (default: $STATE_DIRECTORY, else ./out)
  Z37_REPO     checkout of timkleinke/tim (read-only deploy key); pulled before each run
  Z37_CLAUDE   path of the claude binary (default: claude)
  Z37_MODEL    optional model name for claude
  CLAUDE_CODE_OAUTH_TOKEN  from `claude setup-token` (Tim's subscription)

The logbook files the Redaktion needs are put into the prompt; Claude Code itself gets web search
only (no file access, no fetch, no shell), runs in an empty directory and loads no project
settings or MCP servers from anywhere but the zug37 user. The answer must be one JSON object; it is
checked field by field (including names from menschen/ in what the public feed shows) before it is
written to ausgabe.json. Every run, shown or silent, is appended to verlauf.jsonl.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
MAX_LIGHTS_PER_DAY = 2
TOOLS = "WebSearch"
DENIED = "Bash Edit Write NotebookEdit Task Read Glob Grep WebFetch"
FILES = ["redaktion/GRUENDUNG.md", "KURS.md", "ideen/README.md"]
MAX_FILE = 20000
RUBRIKEN = ("IDEENBÖRSE",)  # test phase: only the Ideenbörse (TEST.md)
URL = re.compile(r"^https?://\S{4,400}$")


def history(state, n=30):
    try:
        lines = (state / "verlauf.jsonl").read_text().splitlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("art") == "fehler":
            continue
        out.append({k: e.get(k) for k in ("zeit", "art", "rubrik", "zeile", "bezug", "licht")})
    return out


def lights_today(state, now):
    today = now.astimezone(BERLIN).date()
    n = 0
    for e in history(state, 50):
        try:
            if e["art"] == "zeigen" and datetime.fromisoformat(e["zeit"]).astimezone(BERLIN).date() == today:
                n += 1 if e.get("licht") else 0
        except (TypeError, ValueError, KeyError):
            pass
    return n


def context(repo):
    """The logbook files for the prompt: fixed files, all project pages, the newest month of the logbook."""
    paths = [repo / f for f in FILES] + sorted((repo / "projekte").glob("*.md"))
    months = sorted((repo / "logbuch").glob("*.md"))
    paths += months[-1:]
    parts = []
    for p in paths:
        try:
            text = p.read_text()
            if len(text) > MAX_FILE:  # the logbook grows at the end: keep the newest part
                text = "[… gekürzt, nur der neueste Teil …]\n" + text[-MAX_FILE:] if "logbuch" in p.parts else text[:MAX_FILE] + "\n[… gekürzt …]"
            parts.append(f"### {p.relative_to(repo)}\n\n{text}")
        except OSError:
            continue
    return "\n\n".join(parts)


def names(repo):
    """Words that must not appear on the public display: the people in menschen/ (not Tim himself)."""
    out = set()
    for p in (repo / "menschen").glob("*.md"):
        if p.name == "tim.md":
            continue
        try:
            title = p.read_text().splitlines()[0].lstrip("# ")
        except (OSError, IndexError):
            continue
        out.update(w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", title) if w[0].isupper())
    return out


def extract(text):
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    raw = m[-1] if m else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(raw)


def check(e, banned=frozenset()):
    """Returns the cleaned edition or raises ValueError with the field name."""
    if not isinstance(e, dict) or e.get("art") not in ("zeigen", "stille"):
        raise ValueError("art")
    out = {"art": e["art"], "begruendung": str(e.get("begruendung", ""))[:800]}
    if e["art"] == "stille":
        return out
    for key, limit in (("zeile", 90), ("fuss", 60), ("detail", 1500), ("bezug", 120)):
        v = e.get(key, "")
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(key)
        out[key] = v.strip()
    if not out["zeile"]:
        raise ValueError("zeile")
    rubrik = str(e.get("rubrik", "")).strip().upper()
    if rubrik not in RUBRIKEN:
        raise ValueError("rubrik")
    out["rubrik"] = rubrik
    quellen = e.get("quellen") or []
    if not isinstance(quellen, list) or len(quellen) > 6 or not all(isinstance(q, str) and URL.match(q) for q in quellen):
        raise ValueError("quellen")
    if not quellen:
        raise ValueError("quellen")
    out["quellen"] = quellen
    shown = f"{rubrik} {out['zeile']} {out['fuss']}"
    if any(re.search(rf"\b{re.escape(n)}\b", shown, re.I) for n in banned):
        raise ValueError("privat")
    out["kursiv"] = bool(e.get("kursiv"))
    out["licht"] = bool(e.get("licht"))
    return out


def build_prompt(repo, state, now):
    """The whole task: instructions, the logbook excerpt, the time and the editions so far.
    The Sunday comparison hands exactly this text to Claude in the normal chat."""
    local = now.astimezone(BERLIN)
    h = history(state)
    return (Path(__file__).with_name("redaktion.md").read_text()
            + "\n## Das Logbuch (Auszug)\n\n" + context(repo) + "\n"
            + f"\n## Jetzt\n\n{local:%d.%m.%Y, %H:%M} Uhr (Berlin). "
            + f"Lampe heute schon {lights_today(state, now)}-mal an.\n\n## Bisherige Ausgaben\n\n"
            + (json.dumps(h, ensure_ascii=False, indent=1) if h else "noch keine") + "\n")


def ask(workdir, prompt, env):
    cmd = [env.get("Z37_CLAUDE", "claude"), "-p", "--output-format", "json",
           "--allowedTools", TOOLS, "--disallowedTools", DENIED, "--max-turns", "40",
           "--setting-sources", "user", "--strict-mcp-config"]
    if env.get("Z37_MODEL"):
        cmd += ["--model", env["Z37_MODEL"]]
    r = subprocess.run(cmd, cwd=workdir, input=prompt, capture_output=True, text=True, timeout=1500, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}")
    return json.loads(r.stdout)["result"]


def main(env=os.environ, now=None):
    state = Path(env.get("Z37_STATE") or env.get("STATE_DIRECTORY") or "out")
    repo = Path(env.get("Z37_REPO", ""))
    if not (repo / "redaktion" / "GRUENDUNG.md").is_file():
        print("Z37_REPO must be a checkout of the logbook", file=sys.stderr)
        return 2
    now = now or datetime.now(timezone.utc)
    try:
        subprocess.run(["git", "-C", str(repo), "pull", "-q", "--ff-only"], check=True, timeout=120,
                       capture_output=True)
    except (subprocess.SubprocessError, OSError):
        print("zug37-redaktion: git pull failed, using the last checkout", file=sys.stderr)
    prompt = build_prompt(repo, state, now)
    state.mkdir(parents=True, exist_ok=True)
    tmp = state / "aufgabe.md.tmp"  # word for word the task; the bot sends it for the Sunday comparison
    tmp.write_text(prompt); os.replace(tmp, state / "aufgabe.md")
    try:
        workdir = state / "leer"
        workdir.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in env.items() if not k.startswith("Z37_TG_")}  # the model never sees the bot token
        edition = check(extract(ask(workdir, prompt, clean)), names(repo))
    except Exception as e:  # noqa: BLE001 - one line, no content
        grund = f"{type(e).__name__} {e if isinstance(e, ValueError) else ''}".strip()
        print(f"zug37-redaktion: {grund}", file=sys.stderr)
        state.mkdir(parents=True, exist_ok=True)
        with open(state / "verlauf.jsonl", "a") as f:
            f.write(json.dumps({"zeit": now.isoformat(timespec="seconds"), "art": "fehler", "grund": grund[:80]}) + "\n")
        return 1
    edition["zeit"] = now.isoformat(timespec="seconds")
    if edition.get("licht") and lights_today(state, now) >= MAX_LIGHTS_PER_DAY:
        edition["licht"] = False
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "verlauf.jsonl", "a") as f:
        f.write(json.dumps(edition, ensure_ascii=False) + "\n")
    tmp = state / "ausgabe.json.tmp"
    tmp.write_text(json.dumps(edition, ensure_ascii=False, indent=1))
    os.replace(tmp, state / "ausgabe.json")
    print(f"zug37-redaktion: {edition['art']} {edition.get('rubrik', '')}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
