#!/usr/bin/env python3
"""Compare two sets of real-mode screenshots by name (night-v3 item 9.1): the Phase 0 baseline against a later run.

  /data/vaidyx/venv/app/bin/python docs/night-v3/tools/compare_shots.py <baseline dir> <new dir> [--out report.md] [--threshold 0.02]

For every PNG name in the baseline: "missing" when the new run has no picture of that name, else the share of pixels that differ
(after the taller picture is cut to the shorter one's height; a width difference is reported as such). Names only in the new run are
listed as "new". The report lists the changed pictures with the largest share first, so a reviewer looks at those. The threshold
separates "same" from "changed" (0.02 = 2 percent of the pixels). Nothing is written except the report.
"""
import argparse, sys
from pathlib import Path

import numpy as np
from PIL import Image


def load(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)


def diff_share(a, b):
    """Share of pixels (0..1) whose colour differs by more than 16 on any channel, over the common height."""
    h = min(a.shape[0], b.shape[0])
    a, b = a[:h], b[:h]
    if a.shape[1] != b.shape[1]:
        return None
    d = np.abs(a - b).max(axis=2) > 16
    return float(d.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("new")
    ap.add_argument("--out", default="")
    ap.add_argument("--threshold", type=float, default=0.02)
    a = ap.parse_args()
    base, new = Path(a.baseline), Path(a.new)
    base_names = sorted(p.name for p in base.glob("*.png"))
    new_names = sorted(p.name for p in new.glob("*.png"))
    missing, same, changed, width = [], [], [], []
    for n in base_names:
        if n not in new_names:
            missing.append(n)
            continue
        x, y = load(base / n), load(new / n)
        s = diff_share(x, y)
        if s is None:
            width.append((n, x.shape[1], y.shape[1]))
        elif s <= a.threshold:
            same.append((n, s, x.shape[0], y.shape[0]))
        else:
            changed.append((n, s, x.shape[0], y.shape[0]))
    added = [n for n in new_names if n not in base_names]
    changed.sort(key=lambda t: -t[1])
    lines = [f"# Screenshot comparison: {base} against {new}", "",
             f"Baseline pictures {len(base_names)}, new pictures {len(new_names)}, same {len(same)}, changed {len(changed)} (more than {a.threshold:.0%} of the pixels), "
             f"width differs {len(width)}, missing in the new run {len(missing)}, new only {len(added)}.", ""]
    if missing:
        lines += ["## Missing in the new run", ""] + [f"- {n}" for n in missing] + [""]
    if width:
        lines += ["## Width differs (sideways scroll?)", ""] + [f"- {n}: {w1} to {w2}" for n, w1, w2 in width] + [""]
    if changed:
        lines += ["## Changed, largest share first", "", "| picture | share of pixels | height before | height after |", "|---|---|---|---|"]
        lines += [f"| {n} | {s:.1%} | {h1} | {h2} |" for n, s, h1, h2 in changed] + [""]
    if added:
        lines += ["## Only in the new run", ""] + [f"- {n}" for n in added] + [""]
    if same:
        lines += ["## Same (within the threshold)", ""] + [f"- {n} ({s:.2%})" for n, s, h1, h2 in same] + [""]
    text = "\n".join(lines)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(lines[2])
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
