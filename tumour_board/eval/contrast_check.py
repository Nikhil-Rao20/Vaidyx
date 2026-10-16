"""WCAG contrast check of the Tumour Board theme tokens in static/tb/tb.css.
Prints the contrast ratio of each text token against --bg, --panel (white) and --tint, and of each status text colour on its
own soft background. Exits 1 if any text token is below 4.5:1 on --panel or any listed pair is below 4.5:1.
Usage: python -m tumour_board.eval.contrast_check [--css static/tb/tb.css]"""
import argparse, os, re, sys

CSS = os.path.join(os.path.dirname(__file__), "..", "..", "static", "tb", "tb.css")
TEXT = ["ink", "body", "muted", "link", "indigo", "ok", "warn", "bad", "rev"]  # tokens used as text colours
BACKS = ["bg", "panel", "tint"]
PAIRS = [("on-primary", "primary"), ("ok", "ok-s"), ("warn", "warn-s"), ("bad", "bad-s"), ("rev", "rev-s"), ("link", "tint")]
MIN = 4.5


def root_tokens(css):
    """--name: #hex pairs from the first :root block (hex colours only)."""
    m = re.search(r":root\s*{([^}]*)}", css)
    if not m:
        return {}
    return {k: v.lower() for k, v in re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\b", m.group(1))}


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexcol):
    h = hexcol.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h[:3])
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg, bg):
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def check(css):
    """Returns (report lines, failures)."""
    t = root_tokens(css)
    lines, fails = [], []
    missing = [n for n in set(TEXT + BACKS + [x for p in PAIRS for x in p]) if n not in t]
    if missing:
        fails.append("missing tokens: " + ", ".join(sorted(missing)))
        return lines, fails
    lines.append(f"{'token':<12}{'colour':<10}" + "".join(f"{'on ' + b:>12}" for b in BACKS))
    for n in TEXT:
        rs = [ratio(t[n], t[b]) for b in BACKS]
        lines.append(f"{n:<12}{t[n]:<10}" + "".join(f"{r:>11.2f}{'' if r >= MIN else '*'}" for r in rs))
        if rs[1] < MIN:
            fails.append(f"--{n} {t[n]} is {rs[1]:.2f}:1 on --panel (needs {MIN}:1)")
    lines.append("pairs:")
    for fg, bg in PAIRS:
        r = ratio(t[fg], t[bg])
        lines.append(f"  --{fg} on --{bg}: {r:.2f}:1")
        if r < MIN:
            fails.append(f"--{fg} on --{bg} is {r:.2f}:1 (needs {MIN}:1)")
    return lines, fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--css", default=CSS)
    a = ap.parse_args()
    with open(a.css, encoding="utf-8") as f:
        lines, fails = check(f.read())
    print("\n".join(lines))
    print("FAIL:\n  " + "\n  ".join(fails) if fails else f"OK: every text token is at least {MIN}:1 on white")
    sys.exit(1 if fails else 0)
