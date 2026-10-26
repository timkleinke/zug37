"""One run of the display: read the current edition, render, publish the feed.

Started every 5 minutes by zug37-anzeige.timer. No network, no model. Environment:
  Z37_STATE       state directory with ausgabe.json (default: $STATE_DIRECTORY, else ./out)
  Z37_PUBLIC_DIR, Z37_PUBLIC_URL  directory served by nginx and its https base URL ending in "/"
  Z37_SR_DIR      optional: the published Signal Radar feed directory, for taking turns with it

The edition (ausgabe.json) comes from the Redaktion. "stille" keeps the last shown edition.
The LED is white for LIGHT_HOURS after an edition with licht=true, never at night, else off.
If anything fails, nothing is replaced and the exit code is 1: the last good frame stays.

Taking turns with Signal Radar (the device shows one app only): from 8 to 19 o'clock, once a new
edition has stood alone for ALONE_MINUTES, the two alternate in 15-minute slots. The Signal Radar
frame is taken unchanged from its own published feed; the light is on if either feed wants it.
If that feed is missing or broken, Zug 37 simply stays.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import render

BERLIN = ZoneInfo("Europe/Berlin")
LIGHT_HOURS = 3
NIGHT_FROM, NIGHT_UNTIL = 21, 7
FRAME_FILE = re.compile(r"^[0-9a-f]{64}\.bin$")
KEEP_FRAMES = 4
PUBLIC_URL = re.compile(r"^https://[a-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9/_-]*/$")
LED_ON = {"mode": "solid", "color": "white"}
LED_OFF = {"mode": "off", "color": "off"}
ALONE_MINUTES = 90
TURNS_FROM, TURNS_UNTIL = 8, 19


def write_atomic(path, content):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(content); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def build(edition, now):
    """Returns (frame bytes, png image, led) for the edition or the rest screen."""
    if not edition or edition.get("art") != "zeigen":
        raw, png = render.screen_rest("Noch nichts, das gut genug ist.")
        return raw, png, LED_OFF
    at = datetime.fromisoformat(edition["zeit"])
    datum = f"{at.astimezone(BERLIN):%d.%m.}"
    local = now.astimezone(BERLIN)
    night = local.hour >= NIGHT_FROM or local.hour < NIGHT_UNTIL
    light = bool(edition.get("licht")) and not night and now - at < timedelta(hours=LIGHT_HOURS)
    raw, png = render.screen_item(
        render.drawable(edition["rubrik"], render.SANS_B, 9, 16).upper(),
        render.drawable(edition["zeile"], render.SERIF_BI if edition.get("kursiv") else render.SERIF_B, render.HEAD_SIZE, 160),
        render.drawable(edition.get("fuss", ""), render.SANS, 10, 60),
        datum, kursiv=bool(edition.get("kursiv")), hervorheben=light)
    return raw, png, LED_ON if light else LED_OFF


def signal_radar(sr_dir):
    """(frame bytes, led) of the current Signal Radar frame, or None. Checked like the device would."""
    if not sr_dir:
        return None
    try:
        feed = json.loads((Path(sr_dir) / "feed.json").read_text())
        sha = feed["frame"]["sha256"]
        if not FRAME_FILE.match(f"{sha}.bin"):
            return None
        raw = (Path(sr_dir) / f"{sha}.bin").read_bytes()
        if len(raw) != render.FRAME_BYTES or hashlib.sha256(raw).hexdigest() != sha:
            return None
        return raw, feed.get("led") if feed.get("led") in (LED_ON, LED_OFF) else LED_OFF
    except (OSError, ValueError, KeyError, TypeError):
        return None


def turn_for_signal_radar(edition, now):
    """True in the slots that belong to Signal Radar."""
    local = now.astimezone(BERLIN)
    if not (TURNS_FROM <= local.hour < TURNS_UNTIL):
        return False
    if edition and edition.get("zeit") and now - datetime.fromisoformat(edition["zeit"]) < timedelta(minutes=ALONE_MINUTES):
        return False
    return (local.hour * 60 + local.minute) // 15 % 2 == 1


def publish(public_dir, base_url, raw, observed, led):
    sha = hashlib.sha256(raw).hexdigest()
    frame = public_dir / f"{sha}.bin"
    if not frame.exists():
        write_atomic(frame, raw)  # frame before feed
    feed = {"v": 1, "frame": {"url": f"{base_url}{sha}.bin", "sha256": sha, "format": "tickrmeter-mono-v1"},
            "observedAt": observed, "led": led}
    body = (json.dumps(feed, separators=(",", ":")) + "\n").encode()
    if len(body) > 2048:
        raise ValueError("feed larger than 2048 bytes")
    write_atomic(public_dir / "feed.json", body)
    old = [p for p in public_dir.iterdir() if FRAME_FILE.match(p.name) and p.name != frame.name and p.is_file()]
    old.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in old[KEEP_FRAMES - 1:]:
        p.unlink()
    return sha


def main(env=os.environ, now=None):
    state = Path(env.get("Z37_STATE") or env.get("STATE_DIRECTORY") or "out")
    public_dir, public_url = env.get("Z37_PUBLIC_DIR"), env.get("Z37_PUBLIC_URL")
    if bool(public_dir) != bool(public_url) or (public_url and not PUBLIC_URL.match(public_url)):
        print("Z37_PUBLIC_DIR and Z37_PUBLIC_URL (https://host/path/) go together", file=sys.stderr)
        return 2
    now = now or datetime.now(timezone.utc)
    try:
        edition = load(state / "ausgabe.json")
        if edition and edition.get("art") == "stille":
            edition = load(state / "gezeigt.json")
        raw, png, led = build(edition, now)
        sr = signal_radar(env.get("Z37_SR_DIR"))
        if sr:
            if turn_for_signal_radar(edition, now):
                raw = sr[0]
            if sr[1] == LED_ON:
                led = LED_ON
        utc = now.astimezone(timezone.utc)
        observed = f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"
        png.save(state / "frame.png.tmp", "PNG"); os.replace(state / "frame.png.tmp", state / "frame.png")
        if public_dir:
            sha = publish(Path(public_dir), public_url, raw, observed, led)
        else:
            sha = hashlib.sha256(raw).hexdigest()
            write_atomic(state / "frame.bin", raw)
        if edition and edition.get("art") == "zeigen":
            write_atomic(state / "gezeigt.json", json.dumps(edition, ensure_ascii=False).encode())
    except Exception as e:  # noqa: BLE001 - one line, no content
        print(f"zug37-anzeige: {type(e).__name__}", file=sys.stderr)
        return 1
    print(f"zug37-anzeige: led={led['mode']} frame={sha[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
