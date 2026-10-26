"""Frames for Zug 37 on the TickrMeter: 296x128, 1 bit, format tickrmeter-mono-v1.

Built on the Signal Radar renderer in mif-platform (ops/tickrmeter-signal-radar): same sizes, fonts and
text handling (wrap, fit, drawable). Internally 1 = ink; export inverts to 1 = white, MSB first.
"""
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 296, 128
FRAME_BYTES = W * H // 8
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
SERIF = "/usr/share/fonts/X11/Type1/c0648bt_.pfb"     # Bitstream Charter
SERIF_I = "/usr/share/fonts/X11/Type1/c0649bt_.pfb"   # Bitstream Charter Italic
SERIF_B = "/usr/share/fonts/X11/Type1/c0632bt_.pfb"   # Bitstream Charter Bold: no hairlines, reads clean in 1 bit
SERIF_BI = "/usr/share/fonts/X11/Type1/c0633bt_.pfb"  # Bitstream Charter Bold Italic
HEAD_SIZE, HEAD_LEAD, HEAD_TOP = 21, 25, 28
ELLIPSIS = " …"


def F(path, size): return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def new():
    im = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(im); d.fontmode = "1"
    return im, d


def stone_mark(d, x, y, s=13):
    """A stone on an intersection: the mark of Zug 37."""
    c = s // 2
    d.line([(x, y + c), (x + s - 1, y + c)], fill=1)
    d.line([(x + c, y), (x + c, y + s - 1)], fill=1)
    r = c - 3
    d.ellipse([x + c - r, y + c - r, x + c + r, y + c + r], fill=1)


def spaced(d, xy, text, font, track=1, fill=1):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += round(d.textlength(ch, font=font)) + track
    return x


def spaced_w(d, text, font, track=1):
    return sum(round(d.textlength(c, font=font)) + track for c in text) - track


def dotted(d, y, x0=8, x1=W - 8):
    for x in range(x0, x1, 2): d.point((x, y), fill=1)


def fit(d, text, font, maxw, suffix):
    if d.textlength(text + suffix, font=font) <= maxw:
        return text.rstrip() + suffix
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if d.textlength(text[:mid] + suffix, font=font) <= maxw: lo = mid
        else: hi = mid - 1
    return text[:lo].rstrip() + suffix


def wrap(d, text, font, maxw, maxlines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    lines.append(cur)
    for i, line in enumerate(lines[:maxlines]):
        if d.textlength(line, font=font) > maxw:
            return lines[:i] + [fit(d, line, font, maxw, ELLIPSIS.strip())]
    if len(lines) > maxlines:
        lines = lines[:maxlines]
        while " " in lines[-1] and d.textlength(lines[-1] + ELLIPSIS, font=font) > maxw:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] = fit(d, lines[-1], font, maxw, ELLIPSIS)
    return lines


def export(im):
    out = ImageOps.invert(im.convert("L")).convert("1")
    raw = out.tobytes()
    if len(raw) != FRAME_BYTES:
        raise ValueError(f"frame has {len(raw)} bytes, expected {FRAME_BYTES}")
    return raw, out


def header(d, rubrik, hervorheben):
    stone_mark(d, 8, 5, 13)
    spaced(d, (27, 7), "ZUG 37", F(SANS_B, 9), track=1)
    if rubrik:
        f = F(SANS_B, 9); w = spaced_w(d, rubrik, f, 1); xr = W - 8
        if hervorheben:  # inversion only together with the light
            d.rectangle([xr - w - 6, 4, xr, 17], fill=1)
            spaced(d, (xr - w - 3, 6), rubrik, f, track=1, fill=0)
        else:
            spaced(d, (xr - w, 6), rubrik, f, track=1)
    dotted(d, 23)


def screen_item(rubrik, zeile, fuss, datum, kursiv=False, hervorheben=False):
    """One thing in the foreground: rubric, a headline of up to three lines, a footer."""
    im, d = new()
    header(d, rubrik, hervorheben)
    f = F(SERIF_BI if kursiv else SERIF_B, HEAD_SIZE)
    for k, line in enumerate(wrap(d, zeile, f, W - 16, 3)):
        d.text((8, HEAD_TOP + k * HEAD_LEAD), line, font=f, fill=1)
    fs = F(SANS, 10)
    wd = d.textlength(datum, font=fs) if datum else 0
    if datum: d.text((W - 8 - wd, 112), datum, font=fs, fill=1)
    if fuss:
        maxw = W - 16 - wd - 10
        if d.textlength(fuss, font=fs) > maxw: fuss = fit(d, fuss, fs, maxw, "…")
        d.text((8, 112), fuss, font=fs, fill=1)
    return export(im)


def screen_rest(note):
    """Before the first edition: a piece of the board running off the edge, one stone, the name."""
    im, d = new()
    step = 22
    for k in range(6):  # board lines run off the top and left edge
        x = 4 + k * step
        if x <= 112: d.line([(x, 0), (x, H - 1)], fill=1)
        d.line([(0, 2 + k * step), (112, 2 + k * step)], fill=1)
    cx, cy, r = 4 + 3 * step, 2 + 2 * step, 9  # off the usual points
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=1)
    d.text((134, 38), "Zug 37", font=F(SERIF, 34), fill=1)
    fs = F(SANS, 10)
    d.text((136, 90), fit(d, note, fs, W - 8 - 136, ""), font=fs, fill=1)
    return export(im)


STAND_INS = {"€": "EUR", "≥": ">=", "≤": "<=", "≠": "!=", "‐": "-", "‑": "-", "−": "-"}


def drawable(text, path=SERIF, size=18, limit=200):
    """Text the font can draw: no control characters, stand-ins for missing glyphs, base letters, else "?"."""
    f = F(path, size)
    has = lambda ch: f.getmask(ch).getbbox() is not None  # noqa: E731
    out = []
    for ch in unicodedata.normalize("NFC", " ".join(str(text)[:4 * limit].split())):
        cat = unicodedata.category(ch)
        if ch == " " or (cat not in ("Cc", "Cf") and has(ch)):
            out.append(ch)
        elif cat in ("Cc", "Cf"):
            continue
        elif ch in STAND_INS and all(has(c) for c in STAND_INS[ch]):
            out.append(STAND_INS[ch])
        elif cat in ("Mn", "Me", "So", "Sk"):
            continue
        else:
            base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            out.append(base if base and all(has(c) for c in base) else "?")
    return " ".join("".join(out).split())[:limit].rstrip()
