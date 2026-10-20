"""Figures of the benchmark paper and the Research page, drawn as hand-built SVG from the generated data (research/data.ts).

  /data/vaidyx/venv/app/bin/python docs/research/benchmark-paper/experiments/figures.py
  node docs/research/benchmark-paper/experiments/figures_pdf.cjs        # SVG -> vector PDF for the paper (Chromium, fonts embedded)

One SVG per figure serves both places: its colours are CSS variables with light fallbacks, so inline on the website it follows the
light and dark themes (--l-* tokens of landing.css), and rendered on its own it is the light version for the paper.
Writes web/tb-nik/src/features/landing/research/figures/<name>.svg and docs/research/benchmark-paper/figures/<name>.svg.
"""
import html
import json
import math
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "web/tb-nik/src/features/landing/research/data.ts"
WEB = REPO / "web/tb-nik/src/features/landing/research/figures"
PAPER = REPO / "docs/research/benchmark-paper/figures"

src = DATA.read_text()
D = json.loads(src[src.index("{"): src.rindex("} as const") + 1])
MODELS = {m["key"]: m for m in D["models"]}
X = D.get("experiments", {})

W = 960
FONT = "'Inter Variable', Inter, system-ui, sans-serif"
STYLE = """
.fg{fill:var(--l-fg,#0f172a)} .fg2{fill:var(--l-fg-2,#475569)} .fg3{fill:var(--l-fg-3,#94a3b8)}
.ln{stroke:var(--l-line,#e2e8f0)} .ln2{stroke:var(--l-line-2,#cbd5e1)} .ax{stroke:var(--l-fg-3,#94a3b8)}
.bg{fill:var(--l-surface,#ffffff)} .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}
.neu{fill:var(--l-line-2,#cbd5e1)} .med{fill:#0e9aa7} .gen{fill:#7c5cf0} .medS{stroke:#0e9aa7} .genS{stroke:#7c5cf0}
.warm{fill:#e8973a} .warmS{stroke:#e8973a} .bad{fill:#e35d6a}
text{font-family:FONT} .t-num,.t-ax{font-variant-numeric:tabular-nums}
.t-title{font-size:19px;font-weight:650;letter-spacing:-.01em} .t-sub{font-size:13.5px}
.t-lab{font-size:13.5px;font-weight:550} .t-tag{font-size:11.5px} .t-num{font-size:12.5px;font-weight:600} .t-ax{font-size:12px}
""".replace("FONT", FONT)


# inline on the website the <style> applies to the whole page: every rule is scoped to the figure's root class
SCOPED = re.sub(r"([^{}]+)\{", lambda m: ",".join(".vfig " + x.strip() for x in m.group(1).split(",")) + "{", STYLE.replace("\n", " "))


def esc(s):
    return html.escape(str(s), quote=True)


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.parts, self.head = w, h, label, [], set()

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, cls="fg t-lab", anchor="start", extra=""):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')

    def line(self, x1, y1, x2, y2, cls="ln", w=1, extra=""):
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}" stroke-width="{w}" {extra}/>')

    def rect(self, x, y, w, h, cls, r=0, extra=""):
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(0, w):.1f}" height="{max(0, h):.1f}" rx="{r}" class="{cls}" {extra}/>')

    def circle(self, x, y, r, cls, extra=""):
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" class="{cls}" {extra}/>')

    def save(self, name):
        """The web version keeps its title and subtitle; the paper version leaves them to the LaTeX caption."""
        def doc(parts, h, shift):
            body = "\n".join(parts)
            g = f'<g transform="translate(0,{-shift})">\n{body}\n</g>' if shift else body
            return (f'<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 {self.w} {h}" width="{self.w}" height="{h}" role="img" '
                    f'aria-label="{esc(self.label)}"><style>{SCOPED}</style>\n{g}\n</svg>\n')
        WEB.mkdir(parents=True, exist_ok=True); PAPER.mkdir(parents=True, exist_ok=True)
        (WEB / f"{name}.svg").write_text(doc(self.parts, self.h, 0))
        rest = [p for i, p in enumerate(self.parts) if i not in self.head]
        (PAPER / f"{name}.svg").write_text(doc(rest, self.h - 50, 50))
        print("figure", name, f"{self.w}x{self.h}")


def kind(k):
    return "med" if MODELS[k]["type"] == "Medical" else "gen"


def tagline(k):
    m = MODELS[k]
    return f"{m['country']} · {m['type']}"


def legend(s, x, y, items):
    for cls, lab in items:
        s.circle(x + 6, y - 4.5, 6, cls)
        s.text(x + 18, y, lab, "fg2 t-tag")
        x += 30 + 7.2 * len(lab)


def header(s, title, sub):
    s.head.update({len(s.parts), len(s.parts) + 1})
    s.text(0, 22, title, "fg t-title")
    s.text(0, 44, sub, "fg2 t-sub")


def xaxis(s, x0, x1, y0, y1, lo, hi, step, fmt="{:.0f}", label=None):
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    v = lo
    while v <= hi + 1e-9:
        s.line(sx(v), y0, sx(v), y1, "ln", 1)
        s.text(sx(v), y1 + 18, fmt.format(v), "fg3 t-ax", "middle")
        v += step
    if label:
        s.text((x0 + x1) / 2, y1 + 38, label, "fg2 t-ax", "middle")
    return sx


# --------------------------------------------------------------------------------------------------------------- F1 ranking + CI
def fig_ranking():
    rows = X.get("ciText") or [{"key": r["key"], "cot": [r["overall"], r["overall"], r["overall"]]} for r in D["textCot"]]
    n = len(rows)
    top, rh, lx, x0, x1 = 92, 36, 0, 290, W - 150
    s = Svg(W, top + n * rh + 70, "Step-by-step accuracy of the 13 models with 95 per cent confidence intervals")
    header(s, "Text accuracy, step by step, with 95 % confidence intervals", "All 9,995 questions of the five text sets; bars are bootstrap intervals. Shaded: models that cannot be told apart.")
    legend(s, 0, 70, [("med", "Medical fine-tune"), ("gen", "General model, not medically validated")])
    sx = xaxis(s, x0, x1, top - 6, top + n * rh, 30, 80, 10, label="Accuracy, %")
    # the tie group: ranks 3 to 6
    tie = [i for i, r in enumerate(rows) if 2 <= i <= 5]
    if tie:
        s.rect(0, top + tie[0] * rh - 2, W - 40, len(tie) * rh + 2, "band", 10)
        s.text(W - 46, top + tie[0] * rh + 15, "within one point: tied", "fg2 t-tag", "end")
    for i, r in enumerate(rows):
        y = top + i * rh + rh / 2
        k = r["key"]
        p, lo, hi = r["cot"]
        s.text(lx, y + 1, MODELS[k]["name"], "fg t-lab")
        s.text(lx, y + 15, tagline(k), "fg3 t-tag")
        s.line(sx(lo), y, sx(hi), y, f"{kind(k)}S", 13, 'stroke-linecap="round" opacity=".22"')
        s.line(sx(lo), y - 6, sx(lo), y + 6, f"{kind(k)}S", 1.6, 'opacity=".7"')
        s.line(sx(hi), y - 6, sx(hi), y + 6, f"{kind(k)}S", 1.6, 'opacity=".7"')
        s.circle(sx(p), y, 5.5, kind(k), 'stroke="var(--l-surface,#fff)" stroke-width="2"')
        s.text(sx(hi) + 12, y + 4.5, f"{p:.1f}", "fg t-num")
        s.text(sx(hi) + 48, y + 4.5, f"{lo:.1f} to {hi:.1f}", "fg3 t-tag")
    s.save("ranking")


# --------------------------------------------------------------------------------------------------------------- F2 reasoning gain
def fig_reasoning():
    rows = sorted(D["textDirect"], key=lambda r: -(r["overall"] + (r["cotGain"] or 0)))
    n = len(rows)
    top, rh, x0, x1 = 92, 32, 300, W - 70
    s = Svg(W, top + n * rh + 70, "Direct answer against step-by-step accuracy for each model")
    header(s, "What reasoning adds", "Overall text accuracy with a one-letter answer (open dot) and when the model may reason first (filled dot).")
    s.circle(6, 65.5, 6, "bg", 'stroke="var(--l-fg-2,#475569)" stroke-width="2"'); s.text(18, 70, "Direct answer", "fg2 t-tag")
    s.circle(126, 65.5, 6, "fg2"); s.text(138, 70, "Step by step", "fg2 t-tag")
    sx = xaxis(s, x0, x1, top - 6, top + n * rh, 20, 80, 10, label="Accuracy, %")
    for i, r in enumerate(rows):
        y = top + i * rh + rh / 2
        k = r["key"]
        a, b = r["overall"], r["overall"] + (r["cotGain"] or 0)
        s.text(0, y + 1, MODELS[k]["name"] + (" †" if r.get("rescored") else ""), "fg t-lab")
        s.text(0, y + 15, tagline(k), "fg3 t-tag")
        s.line(sx(a), y, sx(b), y, f"{kind(k)}S", 3.5, 'stroke-linecap="round" opacity=".55"')
        s.circle(sx(a), y, 6, "bg", f'stroke="{"#0e9aa7" if kind(k) == "med" else "#7c5cf0"}" stroke-width="2.5"')
        s.circle(sx(b), y, 7, kind(k), 'stroke="var(--l-surface,#fff)" stroke-width="2"')
        g = r["cotGain"] or 0
        s.text(sx(max(a, b)) + 12, y + 4.5, f"{g:+.1f}", "fg t-num" if g >= 0 else "fg2 t-num")
    s.save("reasoning")


# --------------------------------------------------------------------------------------------------------------- F3 vs published
def fig_published():
    pts = []
    sets = ["MedQA", "MedMCQA", "PubMedQA", "MMLU-Med", "MedXpertQA"]
    for r in D["publishedText"]:
        for i, (o, p) in enumerate(zip(r["ours"], r["published"])):
            if p is not None:
                pts.append((r["key"], sets[i], o, p))
    size = 520
    pad_l, pad_t = 60, 96
    s = Svg(W, pad_t + size + 70, "This run against the published scores")
    header(s, "The harness reproduces the model cards", "Each dot is one model on one text set: published score across, this run up. On the line = identical; band = within 3 points.")
    lo, hi = 0, 100
    sx = lambda v: pad_l + (v - lo) / (hi - lo) * size
    sy = lambda v: pad_t + size - (v - lo) / (hi - lo) * size
    for v in range(0, 101, 20):
        s.line(sx(v), sy(0), sx(v), sy(100), "ln"); s.line(sx(0), sy(v), sx(100), sy(v), "ln")
        s.text(sx(v), sy(0) + 18, v, "fg3 t-ax", "middle"); s.text(sx(0) - 8, sy(v) + 4, v, "fg3 t-ax", "end")
    s.add(f'<polygon points="{sx(0)},{sy(3)} {sx(97)},{sy(100)} {sx(100)},{sy(100)} {sx(100)},{sy(97)} {sx(3)},{sy(0)} {sx(0)},{sy(0)}" class="band"/>')
    s.line(sx(0), sy(0), sx(100), sy(100), "ax", 1.4, 'stroke-dasharray="5 5"')
    s.text(sx(50), sy(0) + 40, "Published score, %", "fg2 t-ax", "middle")
    s.text(sx(0) - 44, sy(50), "This run, %", "fg2 t-ax", "middle", f'transform="rotate(-90 {sx(0) - 44} {sy(50)})"')
    lik = {"med42-8b", "jsl-med-8b", "openbiollm-8b"}
    for k, ds, o, p in pts:
        cls = "warm" if k in lik else "med"
        s.circle(sx(p), sy(o), 6.5, cls, 'opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"')
    # side notes
    nx = pad_l + size + 40
    s.circle(nx + 6, pad_t + 20, 7, "med"); s.text(nx + 20, pad_t + 25, "Generated answers on the card", "fg t-lab")
    s.text(nx + 20, pad_t + 43, "MedGemma 27B, 27B-text, 4B, 1.5-4B; Lingshu-32B", "fg2 t-tag")
    s.circle(nx + 6, pad_t + 74, 7, "warm"); s.text(nx + 20, pad_t + 79, "Answer likelihood on the card", "fg t-lab")
    s.text(nx + 20, pad_t + 97, "Med42-8B, JSL-MedLlama-8B, OpenBioLLM-8B", "fg2 t-tag")
    diffs = {}
    for k, ds, o, p in pts:
        diffs.setdefault(k, []).append(o - p)
    yy = pad_t + 150
    s.text(nx, yy, "Mean difference, this run minus card", "fg2 t-tag"); yy += 24
    for k in [r["key"] for r in D["publishedText"]]:
        d = sum(diffs[k]) / len(diffs[k])
        s.text(nx, yy, MODELS[k]["name"], "fg t-tag"); s.text(W - 30, yy, f"{d:+.1f}", "fg t-num", "end"); yy += 22
    s.save("published")


# --------------------------------------------------------------------------------------------------------------- F4 4-bit vs bf16
def fig_q4():
    rows = D["q4"]
    n = len(rows)
    top, rh, x0, x1 = 92, 40, 300, W - 70
    s = Svg(W, top + n * rh + 70, "The same weights at 4 bits and at full precision")
    header(s, "Full precision against the earlier 4-bit run", "Mean of the five text sets, the same models: 4-bit weights (Sept. 2026), then bf16 direct, then bf16 step by step.")
    for x, cls, lab in ((0, "fg3", "4-bit (Q4_K_M)"), (150, "fg2", "bf16, direct"), (270, "med", "bf16, step by step")):
        s.circle(x + 6, 65.5, 6, cls); s.text(x + 18, 70, lab, "fg2 t-tag")
    sx = xaxis(s, x0, x1, top - 6, top + n * rh, 10, 80, 10, label="Mean accuracy over the five sets, %")
    for i, r in enumerate(sorted(rows, key=lambda r: -sum(r["cot"]))):
        y = top + i * rh + rh / 2
        q, d, c = sum(r["q4"]) / 5, sum(r["direct"]) / 5, sum(r["cot"]) / 5
        k = r["key"]
        s.text(0, y + 1, MODELS[k]["name"], "fg t-lab"); s.text(0, y + 15, tagline(k), "fg3 t-tag")
        s.line(sx(min(q, d, c)), y, sx(max(q, d, c)), y, "ln2", 3, 'stroke-linecap="round"')
        s.add(f'<path d="M{sx(q):.1f},{y:.1f} L{sx(c):.1f},{y:.1f}" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>')
        s.circle(sx(q), y, 6.5, "fg3"); s.circle(sx(d), y, 6.5, "fg2"); s.circle(sx(c), y, 7.5, "med", 'stroke="var(--l-surface,#fff)" stroke-width="2"')
        s.text(sx(max(q, d, c)) + 12, y + 4.5, f"{c - q:+.1f}", "fg t-num")
    s.save("q4")


# --------------------------------------------------------------------------------------------------------------- F5 image heatmap
def fig_images():
    cols = [("VQA-RAD", lambda r: r["overall"].get("vqa_rad")), ("SLAKE", lambda r: r["overall"].get("slake")), ("PathVQA", lambda r: r["overall"].get("pathvqa")),
            ("PMC-VQA", lambda r: r["overall"].get("pmc_vqa")), ("PMC-VQA, CoT", lambda r: r["cot"].get("pmc_vqa")),
            ("MedXpertQA-MM, CoT", lambda r: r["cot"].get("medxpertqa_mm")), ("OmniMedVQA", lambda r: r["omniFt"])]
    rows = D["image"]
    top, rh, x0 = 128, 44, 250
    cw = (W - x0) / len(cols)
    s = Svg(W, top + len(rows) * rh + 40, "Image question accuracy of the seven vision models")
    header(s, "Image questions: who leads where", "Accuracy, %; darker = higher, ringed = best in the column. Direct protocol unless marked CoT; OmniMedVQA uses the first-token score.")
    for j, (name, _) in enumerate(cols):
        a, _, b = name.partition(", ")
        s.text(x0 + j * cw + cw / 2, top - (28 if b else 14), a, "fg2 t-tag", "middle")
        if b:
            s.text(x0 + j * cw + cw / 2, top - 13, b, "fg3 t-tag", "middle")
    best = [max((f(r) or 0) for r in rows) for _, f in cols]
    for i, r in enumerate(rows):
        y = top + i * rh
        k = r["key"]
        s.text(0, y + rh / 2 + 1, MODELS[k]["name"], "fg t-lab"); s.text(0, y + rh / 2 + 15, tagline(k), "fg3 t-tag")
        for j, (_, f) in enumerate(cols):
            v = f(r)
            if v is None:
                continue
            a = 0.08 + 0.85 * max(0, (v - 0)) / 100
            col = "#0e9aa7" if MODELS[k]["type"] == "Medical" else "#7c5cf0"
            s.rect(x0 + j * cw + 3, y + 3, cw - 6, rh - 6, "", 8, f'fill="{col}" fill-opacity="{a:.2f}"')
            strong = abs(v - best[j]) < 1e-6
            if strong:  # the column's best: a ring
                s.rect(x0 + j * cw + 1, y + 1, cw - 2, rh - 2, "", 10, 'fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"')
            s.text(x0 + j * cw + cw / 2, y + rh / 2 + 5, f"{v:.1f}", "t-num", "middle",
                   f'fill="{"#ffffff" if a > 0.55 else "var(--l-fg,#0f172a)"}" font-weight="{800 if strong else 600}"')
    s.save("images")


# --------------------------------------------------------------------------------------------------------------- F6 oncology
def fig_oncology():
    o = X.get("oncology")
    if not o:
        return
    rows = o["rows"]
    n = len(rows)
    top, rh, x0, x1 = 92, 32, 300, W - 70
    s = Svg(W, top + n * rh + 70, "Accuracy on questions about cancer against the other questions")
    header(s, f"Cancer questions against the rest ({o['n']} of the MedQA, MedMCQA and MedXpertQA questions)", "Step by step. Open dot: the other questions of the same sets; filled dot: questions that mention cancer, with its 95 % interval.")
    sx = xaxis(s, x0, x1, top - 6, top + n * rh, 20, 80, 10, label="Accuracy, %")
    for i, r in enumerate(rows):
        y = top + i * rh + rh / 2
        k = r["key"]
        a, (p, lo, hi) = r["rest"][0], r["oncology"]
        s.text(0, y + 1, MODELS[k]["name"], "fg t-lab"); s.text(0, y + 15, tagline(k), "fg3 t-tag")
        s.line(sx(lo), y, sx(hi), y, f"{kind(k)}S", 3, 'stroke-linecap="round" opacity=".35"')
        s.circle(sx(a), y, 5.5, "bg", 'stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"')
        s.circle(sx(p), y, 6.5, kind(k), 'stroke="var(--l-surface,#fff)" stroke-width="2"')
        s.text(sx(max(hi, a)) + 10, y + 4.5, f"{p - a:+.1f}", "fg t-num" if p - a >= -0.05 else "fg2 t-num")
    s.save("oncology")


# --------------------------------------------------------------------------------------------------------------- F7 size vs accuracy
def fig_size():
    rows = D["textCot"]
    pad_l, pad_t, w, h = 60, 92, W - 90, 420
    s = Svg(W, pad_t + h + 70, "Model size against step-by-step accuracy")
    header(s, "Newer models beat bigger ones", "Parameters (log scale) against overall step-by-step accuracy. Ring: the model was also in the earlier 4-bit report.")
    legend(s, 0, 70, [("med", "Medical fine-tune"), ("gen", "General model, not medically validated")])
    lo_b, hi_b = 3, 52
    lx = lambda v: pad_l + (math.log10(v) - math.log10(lo_b)) / (math.log10(hi_b) - math.log10(lo_b)) * w
    sy = lambda v: pad_t + h - (v - 30) / (80 - 30) * h
    for v in (4, 8, 16, 32):
        s.line(lx(v), sy(30), lx(v), sy(80), "ln"); s.text(lx(v), sy(30) + 18, f"{v}B", "fg3 t-ax", "middle")
    for v in range(30, 81, 10):
        s.line(lx(lo_b), sy(v), lx(hi_b), sy(v), "ln"); s.text(lx(lo_b) - 10, sy(v) + 4, v, "fg3 t-ax", "end")
    s.text(lx(12), sy(30) + 40, "Parameters", "fg2 t-ax", "middle")
    # label side and nudge per model, so no label sits next to another model's dot
    place = {"gemma-4-31b-it": ("l", 0), "huatuogpt-3-27b": ("l", 0), "medgemma-27b-text-it": ("l", -8), "medgemma-27b-it": ("l", 10),
             "baichuan-m2-32b": ("r", -4), "lingshu-32b": ("r", 2), "med42-8b": ("r", -7), "jsl-med-8b": ("r", 9)}
    for r in rows:
        k = r["key"]
        b = float(MODELS[k]["params"].rstrip("B"))
        x, y = lx(b), sy(r["overall"])
        if MODELS[k]["previous"]:
            s.circle(x, y, 12.5, "", f'fill="none" stroke="{"#0e9aa7" if kind(k) == "med" else "#7c5cf0"}" stroke-width="1.6" opacity=".5"')
        s.circle(x, y, 7.5, kind(k), 'opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"')
        side, dy = place.get(k, ("r", 0))
        s.text(x + (18 if side == "r" else -18), y + 4.5 + dy, MODELS[k]["name"], "fg t-tag", "start" if side == "r" else "end")
    s.save("size")


# --------------------------------------------------------------------------------------------------------------- F8 grounding ablation
def fig_grounding():
    p = X.get("probesScale")
    if not p or "absent_true_trap" not in p:
        return
    rows = [("Answerable", p["ans"]["n"], p["ans"]["pass"], "the value, with its quote"),
            ("Not in the file (trap)", p["absent_true_trap"]["n"], p["absent_true_trap"]["pass"], "said “not documented”, no value"),
            ("Out of scope", p["scope"]["n"], p["scope"]["pass"], "declined"),
            ("Documented after all", p["absent_documented_after_all"], p["absent_documented_after_all"], "answered with verified quotes"),
            ("Hand-written release set", p["hand_written"]["n"], p["hand_written"]["pass"], "the 57 gate probes")]
    removed = p["statements_removed_by_grounding"]
    top, rh, x0, x1 = 96, 46, 250, W - 150
    total = sum(r[1] for r in rows)
    s = Svg(W, top + len(rows) * rh + 140, "Ask-the-Case-File probes and what the grounding layer removed")
    header(s, f"{total} questions to the Case File: right answers, and what grounding removed", "Shipped pipeline (Gemma-4-31B-it, non-medical, with the verbatim-quote check). Bar length: probes; teal: right answer.")
    for x, cls, lab in ((0, "med", "Right answer"), (130, "neu", "Missed"), (230, "bad", "Fabricated value shown")):
        s.rect(x, 61, 12, 12, cls, 3); s.text(x + 18, 71, lab, "fg2 t-tag")
    mx = max(r[1] for r in rows)
    sx = lambda v: x0 + v / mx * (x1 - x0)
    for i, (lab, n, ok, what) in enumerate(rows):
        y = top + i * rh
        s.text(0, y + 18, lab, "fg t-lab"); s.text(0, y + 33, what, "fg3 t-tag")
        s.rect(x0, y + 8, sx(n) - x0, 20, "neu", 6)
        s.rect(x0, y + 8, sx(ok) - x0, 20, "med", 6)
        s.text(sx(n) + 10, y + 23, f"{ok} of {n}", "fg t-num")
    y = top + len(rows) * rh + 34
    s.text(0, y, f"The grounding layer removed {len(removed)} statements in all, reviewed by hand against the documents:", "fg t-lab")
    cols = {"wrong number caught": "bad", "wrong date caught": "bad", "true, quote did not match": "neu", "statement of absence": "neu"}
    xx, yy = 0, y + 20
    for r in removed:
        lab = r["review"]
        w = 12 + 7.0 * len(lab)
        if xx + w > W:
            xx, yy = 0, yy + 40
        s.rect(xx, yy, w, 28, cols.get(lab, "neu"), 14, 'opacity=".9"' if cols.get(lab) == "bad" else 'opacity=".7"')
        s.text(xx + w / 2, yy + 18.5, lab, "t-tag", "middle", f'fill="{"#ffffff" if cols.get(lab) == "bad" else "var(--l-fg,#0f172a)"}" font-weight="600"')
        xx += w + 10
    s.text(0, yy + 52, "Without the layer, two answers would have carried a wrong detail (8 to 13 cm for 8 to 12 cm; a date off by ten days); two true statements were lost.", "fg2 t-tag")
    s.save("grounding")


# --------------------------------------------------------------------------------------------------------------- F9 TCGA agreement
def fig_tcga():
    t = X.get("tcgaScale")
    if not t or t.get("reports", 0) < 1000:
        return
    a = t["agreement"]
    dv = t.get("disagreements_with_verified_quote", {})
    order = [k for k in ("Histology", "pT", "pN", "Stage group", "ER", "PR", "HER2 (IHC)") if k in a]
    top, rh, x0, x1 = 112, 42, 190, W - 300
    s = Svg(W, top + len(order) * rh + 76, "Agreement with the TCGA clinical record on real pathology reports")
    header(s, f"{t['reports']:,} real pathology reports against the clinical record",
           f"Shipped extractor (Qwen3.5-4B, Chinese, non-medical). {t['claims']:,} values read; {t['ungrounded']} had no verifiable quote and are flagged. Tick: lower 95 % bound.")
    s.text(W - 250, top - 14, "Differences the report itself states", "fg2 t-tag")
    sx = xaxis(s, x0, x1, top - 6, top + len(order) * rh, 0, 100, 20, "{:.0f}", "Agreement with the record, %")
    for i, k in enumerate(order):
        y = top + i * rh + rh / 2
        r = a[k]
        s.text(0, y + 1, k, "fg t-lab"); s.text(0, y + 15, f"{r['agree']:,} of {r['n']:,}", "fg3 t-tag")
        s.rect(sx(0), y - 9, sx(r["pct"]) - sx(0), 18, "med", 6, 'opacity=".9"')
        s.line(sx(r["lower95_pct"]), y - 13, sx(r["lower95_pct"]), y + 13, "ax", 2)
        s.text(sx(r["pct"]) + 10, y + 4.5, f"{r['pct']:.1f}", "fg t-num")
        d = dv.get(k)
        if d:
            frac = d["verified"] / max(1, d["of"])
            s.rect(W - 250, y - 6, 120, 12, "neu", 6)
            s.rect(W - 250, y - 6, 120 * frac, 12, "warm", 6)
            s.text(W - 120, y + 4.5, f"{d['verified']} of {d['of']}", "fg t-num")
    s.save("tcga")


if __name__ == "__main__":
    for f in (fig_ranking, fig_reasoning, fig_published, fig_q4, fig_images, fig_oncology, fig_size, fig_grounding, fig_tcga):
        f()
