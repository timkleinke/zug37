"""One run of the Redaktion: update the logbook checkout, ask Claude Code, check the answer, write the edition.

Started by zug37-redaktion.timer a few times a day. Environment:
  Z37_STATE    state directory (default: $STATE_DIRECTORY, else ./out)
  Z37_REPO     checkout of timkleinke/tim (read-only deploy key); pulled before each run
  Z37_CLAUDE   path of the claude binary (default: claude)
  Z37_MODEL    optional model name for claude
  CLAUDE_CODE_OAUTH_TOKEN  from `claude setup-token` (Tim's subscription)

Claude Code may only read the checkout and use web search and fetch: no shell, no writing.
The answer must be one JSON object; it is checked field by field before it is written to
ausgabe.json. Every run, shown or silent, is appended to verlauf.jsonl.
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
TOOLS = "Read Glob Grep WebSearch WebFetch"
DENIED = "Bash Edit Write NotebookEdit Task"
RUBRIK = re.compile(r"^[A-ZÄÖÜ ]{2,14}$")
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


def extract(text):
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    raw = m[-1] if m else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(raw)


def check(e):
    """Returns the cleaned edition or raises ValueError with the field name."""
    if not isinstance(e, dict) or e.get("art") not in ("zeigen", "stille"):
        raise ValueError("art")
    out = {"art": e["art"], "begruendung": str(e.get("begruendung", ""))[:800]}
    if e["art"] == "stille":
        return out
    for key, limit in (("zeile", 140), ("fuss", 60), ("detail", 1500), ("bezug", 120)):
        v = e.get(key, "")
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(key)
        out[key] = v.strip()
    if not out["zeile"]:
        raise ValueError("zeile")
    rubrik = str(e.get("rubrik", "")).strip().upper()
    if not RUBRIK.match(rubrik):
        raise ValueError("rubrik")
    out["rubrik"] = rubrik
    quellen = e.get("quellen") or []
    if not isinstance(quellen, list) or len(quellen) > 6 or not all(isinstance(q, str) and URL.match(q) for q in quellen):
        raise ValueError("quellen")
    if rubrik in ("IDEENBÖRSE", "FUND") and not quellen:
        raise ValueError("quellen")
    out["quellen"] = quellen
    out["kursiv"] = bool(e.get("kursiv"))
    out["licht"] = bool(e.get("licht"))
    return out


def ask(repo, prompt, env):
    cmd = [env.get("Z37_CLAUDE", "claude"), "-p", prompt, "--output-format", "json",
           "--allowedTools", TOOLS, "--disallowedTools", DENIED, "--max-turns", "40"]
    if env.get("Z37_MODEL"):
        cmd += ["--model", env["Z37_MODEL"]]
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=1500, env=env)
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
    local = now.astimezone(BERLIN)
    prompt = (Path(__file__).with_name("redaktion.md").read_text()
              + f"\n## Jetzt\n\n{local:%A, %d.%m.%Y, %H:%M} Uhr (Berlin). "
              + f"Lampe heute schon {lights_today(state, now)}-mal an.\n\n## Bisherige Ausgaben\n\n"
              + (json.dumps(history(state), ensure_ascii=False, indent=1) if history(state) else "noch keine") + "\n")
    try:
        edition = check(extract(ask(repo, prompt, dict(env))))
    except Exception as e:  # noqa: BLE001 - one line, no content
        print(f"zug37-redaktion: {type(e).__name__} {e if isinstance(e, ValueError) else ''}".rstrip(), file=sys.stderr)
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
