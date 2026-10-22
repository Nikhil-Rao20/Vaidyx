"""Builds every table of the benchmark paper (tables/*.tex) and the website's research data (web/tb-nik/src/features/landing/
research/data.ts) from the raw benchmark results (~/vaidyx/benchmark, one JSON per model and protocol) plus the published numbers
transcribed from the model cards and papers (see SOURCES). Run with the app venv:
  /data/vaidyx/venv/app/bin/python docs/research/benchmark-paper/build_data.py [--bench ~/vaidyx/benchmark]
Nothing is re-scored here: every accuracy comes from the saved metrics, except the one case noted in RESCORED."""
from __future__ import annotations
import argparse, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WEB = REPO / "web/tb-nik/src/features/landing/research/data.ts"

TEXT_DS = ["medqa", "medmcqa", "pubmedqa", "mmlu_med", "medxpertqa"]
TEXT_NAME = {"medqa": "MedQA", "medmcqa": "MedMCQA", "pubmedqa": "PubMedQA", "mmlu_med": "MMLU-Med", "medxpertqa": "MedXpertQA"}
IMG_DS = ["vqa_rad", "slake", "pathvqa", "pmc_vqa", "medxpertqa_mm", "omnimedvqa"]
IMG_NAME = {"vqa_rad": "VQA-RAD", "slake": "SLAKE", "pathvqa": "PathVQA", "pmc_vqa": "PMC-VQA", "medxpertqa_mm": "MedXpertQA-MM", "omnimedvqa": "OmniMedVQA"}

# The thirteen models, as in the report (page 7). type: Medical or General; country of the developer; images: reads images.
MODELS = [
    dict(key="gemma-4-31b-it", name="Gemma-4-31B-it", params="31B", developer="Google DeepMind", country="USA", type="Non-medical", images=True, previous=False),
    dict(key="huatuogpt-3-27b", name="HuatuoGPT-3-27B", params="27B", developer="FreedomIntelligence, CUHK-Shenzhen", country="China", type="Medical", images=True, previous=False),
    dict(key="qwen3.5-4b", name="Qwen3.5-4B", params="4B", developer="Alibaba Qwen team", country="China", type="Non-medical", images=True, previous=False),
    dict(key="medgemma-27b-text-it", name="MedGemma-27B-text-it", params="27B", developer="Google", country="USA", type="Medical", images=False, previous=False),
    dict(key="medgemma-27b-it", name="MedGemma-27B-it", params="27B", developer="Google", country="USA", type="Medical", images=True, previous=True),
    dict(key="baichuan-m2-32b", name="Baichuan-M2-32B", params="32B", developer="Baichuan AI", country="China", type="Medical", images=False, previous=False),
    dict(key="lingshu-32b", name="Lingshu-32B", params="32B", developer="Alibaba DAMO Academy", country="China", type="Medical", images=True, previous=False),
    dict(key="medgemma-4b-it", name="MedGemma-4B-it", params="4B", developer="Google", country="USA", type="Medical", images=True, previous=True),
    dict(key="med42-8b", name="Med42-8B (v2)", params="8B", developer="M42 Health", country="UAE", type="Medical", images=False, previous=True),
    dict(key="jsl-med-8b", name="JSL-MedLlama-3-8B-v2.0", params="8B", developer="John Snow Labs", country="USA", type="Medical", images=False, previous=True),
    dict(key="medgemma-1.5-4b-it", name="MedGemma-1.5-4B-it", params="4B", developer="Google", country="USA", type="Medical", images=True, previous=True),
    dict(key="openbiollm-8b", name="OpenBioLLM-8B", params="8B", developer="Saama AI Labs", country="USA", type="Medical", images=False, previous=True),
    dict(key="medllama2-7b", name="MedLlama2-7B", params="7B", developer="Community fine-tune of Llama 2", country="USA", type="Medical", images=False, previous=True),
]
KEYS = [m["key"] for m in MODELS]
THINKING_OFF = {"huatuogpt-3-27b", "baichuan-m2-32b", "qwen3.5-4b"}

# Published text scores (model cards and papers; null = not reported). Verified against the cards on 1 and 9 Oct 2026 (report p. 11, 21).
PUBLISHED_TEXT = {
    "medgemma-27b-it": dict(src="Google card", v=[85.3, 70.2, 77.2, 86.2, 23.7]),
    "medgemma-27b-text-it": dict(src="Google card", v=[87.7, 74.2, 76.8, 87.0, 25.7]),
    "medgemma-4b-it": dict(src="Google card", v=[64.4, 55.7, 73.4, 70.0, 14.2]),
    "medgemma-1.5-4b-it": dict(src="Google card", v=[69.1, 59.8, 68.2, 69.6, 16.4]),
    "lingshu-32b": dict(src="Lingshu report", v=[74.7, 66.1, 77.8, 84.7, 22.7]),
    "med42-8b": dict(src="M42 card$^{a}$", v=[62.8, 61.3, None, 75.8, None]),
    "jsl-med-8b": dict(src="JSL card$^{b}$", v=[61.4, 61.2, 74.2, 77.6, None]),
    "openbiollm-8b": dict(src="Saama card$^{b}$", v=[59.0, 56.9, 74.1, 77.1, None]),
}
# The previous report (September 2026): Q4_K_M weights on a GB10 with Ollama, direct letter prompt (report p. 12).
Q4 = {"medgemma-27b-it": [69.8, 62.1, 76.1, 79.2, 16.6], "med42-8b": [60.4, 57.9, 75.6, 71.7, 12.4], "medgemma-4b-it": [51.8, 47.5, 71.4, 60.6, 12.7],
      "medgemma-1.5-4b-it": [29.8, 33.4, 58.0, 23.5, 9.1], "medllama2-7b": [27.0, 27.4, 59.8, 25.6, 9.2], "jsl-med-8b": [27.6, 31.0, 36.0, 21.6, 9.3], "openbiollm-8b": [24.5, 25.4, 44.7, 23.0, 9.1]}
# Baichuan-M2 direct: every reply began with a stray </think> tag, which the harness parser rejected (0 %); the saved replies were
# re-scored after removing the tag (report p. 10). The metrics file still holds the un-parsed numbers, so the re-scored values are kept here.
RESCORED = {"baichuan-m2-32b": dict(direct=[74.6, 67.1, 71.7, 86.9, 17.9], overall=58.6)}
# OmniMedVQA by question type, first-token score (report p. 16); not in the metrics files.
OMNI_TYPES = ["Modality recognition", "Anatomy identification", "Disease diagnosis", "Lesion grading", "Other biological attributes"]
OMNI_BY_TYPE = {"huatuogpt-3-27b": [96.2, 84.0, 80.3, 70.4, 82.7], "lingshu-32b": [96.7, 82.1, 79.5, 77.6, 85.8], "gemma-4-31b-it": [99.3, 79.5, 78.7, 65.5, 86.5],
                "qwen3.5-4b": [96.7, 76.3, 69.8, 52.8, 72.4], "medgemma-4b-it": [96.8, 57.8, 68.4, 70.4, 74.8], "medgemma-27b-it": [88.0, 47.9, 69.7, 77.7, 77.4], "medgemma-1.5-4b-it": [81.9, 61.4, 67.6, 67.6, 63.7]}
# Published image scores (report p. 17): model, benchmark, our score, our protocol, published, source, like for like.
PUBLISHED_IMG = [
    ("lingshu-32b", "OmniMedVQA", 82.4, "first-token", 83.4, "Lingshu paper", "Yes"),
    ("lingshu-32b", "PMC-VQA", 64.9, "direct", 57.9, "Lingshu paper", "Yes"),
    ("lingshu-32b", "MedXpertQA-MM", 31.5, "CoT", 30.9, "Lingshu paper", "Yes"),
    ("lingshu-32b", "SLAKE", 84.9, "exact match", 89.2, "Lingshu paper", "No: GPT-4.1 judges open answers"),
    ("lingshu-32b", "VQA-RAD", 67.4, "exact match", 76.5, "Lingshu paper", "No: GPT-4.1 judges open answers"),
    ("lingshu-32b", "PathVQA", 59.9, "exact match", 65.9, "Lingshu paper", "No: GPT-4.1 judges open answers"),
    ("medgemma-4b-it", "OmniMedVQA", 70.4, "first-token", 69.8, "Lingshu paper", "Yes"),
    ("medgemma-4b-it", "PMC-VQA", 46.2, "direct", 49.9, "Lingshu paper", "Yes"),
    ("medgemma-4b-it", "SLAKE closed (yes/no)", 86.8, "yes/no", 87.6, "Google card", "Yes"),
    ("medgemma-4b-it", "VQA-RAD closed (yes/no)", 80.9, "yes/no", 69.1, "Google card", "Yes"),
    ("medgemma-4b-it", "MedXpertQA-MM", 25.4, "CoT", 18.8, "Google card", "Yes"),
    ("medgemma-27b-it", "SLAKE closed (yes/no)", 82.2, "yes/no", 85.9, "Google 1.5 card", "Yes"),
    ("medgemma-27b-it", "VQA-RAD closed (yes/no)", 76.9, "yes/no", 67.1, "Google 1.5 card", "Yes"),
    ("medgemma-27b-it", "MedXpertQA-MM", 33.2, "CoT", 26.8, "Google card", "Roughly: card mixes text and image items"),
    ("medgemma-1.5-4b-it", "SLAKE closed (yes/no)", 77.8, "yes/no", 82.8, "Google 1.5 card", "Yes"),
    ("medgemma-1.5-4b-it", "VQA-RAD closed (yes/no)", 62.1, "yes/no", 70.2, "Google 1.5 card", "Yes"),
    ("medgemma-1.5-4b-it", "MedXpertQA-MM", 9.6, "CoT", 20.9, "Google 1.5 card", "Yes"),
    ("gemma-4-31b-it", "MedXpertQA-MM", 55.5, "CoT", 61.3, "Gemma 4 report", "Roughly: report uses thinking mode"),
    ("qwen3.5-4b", "PMC-VQA", 60.0, "CoT", 55.5, "Qwen card", "Roughly: card uses thinking mode"),
    ("qwen3.5-4b", "MedXpertQA-MM", 35.5, "CoT", 42.9, "Qwen card", "Roughly: card uses thinking mode"),
    ("qwen3.5-4b", "SLAKE", 59.6, "exact match", 76.1, "Qwen card", "No: scoring not stated"),
]
# Data cards (report pp. 4 and 5).
DATA_CARDS = [
    dict(key="medqa", name="MedQA", kind="text", tests="US medical licensing exam (USMLE) style clinical vignettes: diagnosis, next step, mechanism", n="1,273 (test)", fmt="4 options", chance="25 %", scoring="Letter accuracy"),
    dict(key="medmcqa", name="MedMCQA", kind="text", tests="Indian postgraduate medical entrance exams (AIIMS, NEET-PG) across 21 subjects; the most India-relevant text test", n="4,183 (validation; test answers are hidden)", fmt="4 options", chance="25 %", scoring="Letter accuracy"),
    dict(key="pubmedqa", name="PubMedQA", kind="text", tests="Reading a research abstract and answering a yes / no / maybe question about it (evidence reading, not recall)", n="1,000 (expert-labelled)", fmt="yes / no / maybe", chance="33 %", scoring="Label accuracy"),
    dict(key="mmlu_med", name="MMLU-Med", kind="text", tests="Six medical subjects of MMLU: anatomy, clinical knowledge, college biology, college medicine, medical genetics, professional medicine", n="1,089 (test)", fmt="4 options", chance="25 %", scoring="Letter accuracy"),
    dict(key="medxpertqa", name="MedXpertQA", kind="text", tests="Expert-level, deliberately hard questions from 17 specialty board exams, filtered so that strong models fail them; text subset", n="2,450 (test)", fmt="10 options", chance="10 %", scoring="Letter accuracy"),
    dict(key="vqa_rad", name="VQA-RAD", kind="image", tests="Radiology images (CT, MRI, X-ray) with clinician-written questions", n="451 (test)", fmt="yes/no and short answer", chance="varies", scoring="Yes/no exact; short answers exact match after normalising"),
    dict(key="slake", name="SLAKE", kind="image", tests="Radiology images with organ, position and abnormality questions (English subset)", n="1,061 (test)", fmt="yes/no and short answer", chance="varies", scoring="As VQA-RAD"),
    dict(key="pathvqa", name="PathVQA", kind="image", tests="Pathology images and textbook figures; open answers are long medical phrases, so exact match is strict", n="6,719 (test)", fmt="yes/no and short answer", chance="varies", scoring="As VQA-RAD"),
    dict(key="pmc_vqa", name="PMC-VQA", kind="image", tests="Figures from PubMed Central papers (all modalities), cleaned test set", n="2,000 (test_clean)", fmt="4 options", chance="25 %", scoring="Letter accuracy"),
    dict(key="medxpertqa_mm", name="MedXpertQA-MM", kind="image", tests="Expert board-exam questions that need one or more clinical images plus a vignette", n="2,000 (test)", fmt="5 options", chance="20 %", scoring="Letter accuracy"),
    dict(key="omnimedvqa", name="OmniMedVQA", kind="image", tests="Open-access part of OmniMedVQA: 42 public datasets, 8 modalities (MRI, CT, ultrasound, X-ray, dermoscopy, microscopy, fundus, OCT); mostly modality, anatomy and disease recognition", n="88,996", fmt="2 to 4 options", chance="about 27 %", scoring="Letter accuracy"),
]
# Vaidyx's own grounded evaluations (docs/tumour-board/DESIGN.md, data/tumour_board/eval). Synthetic Case Files unless stated.
BAKEOFF = [  # model, reader word recall, invented numbers, reader seconds (5 scans), doc types, fields, fabricated, extractor seconds (31 docs)
    ("qwen3.5-4b", "1.000", "0", "1.6", "31/31", "49/49", "0", "4.8"),
    ("gemma-4-31b-it", "1.000", "0", "11.1", "30/31", "49/49", "0", "28.1"),
    ("medgemma-27b-it", "0.976", "1", "7.9", "31/31", "49/49", "0", "23.0"),
    ("lingshu-32b", "0.994", "0", "11.3", "31/31", "48/49", "0", "22.5"),
    ("huatuogpt-3-27b", "1.000", "0", "8.4", "30/31", "49/49", "0", "27.2"),
    ("medgemma-27b-text-it", "text only", "--", "--", "30/31", "49/49", "0", "23.3"),
]
ANSWERABILITY = [("gemma-4-31b-it", "33/33", "0", "3.0"), ("huatuogpt-3-27b", "32/33", "0", "8.0"), ("medgemma-27b-it", "31/33", "0", "8.4")]
TCGA = dict(reports=30, claims=166, ungrounded=0, agreement=[("ER", "7/8"), ("PR", "7/8"), ("Histology", "27/29"), ("pT (as recorded)", "24/26")])
STATUS = dict(reports=9523, rows=[("FINAL DIAGNOSIS", "26 %"), ("ADDENDUM", "15 %"), ("verified / reviewed by", "14 %"), ("signed", "5 %"), ("end of report", "3 %"), ("no explicit status or signature", "61 %")])
OCR = [("Tesseract 5.5.3 (psm 4)", "98.6", "98.4", "0.395", "1"), ("docTR 1.1.0 (rows)", "97.7", "95.8", "1.276", "8"), ("docTR 1.1.0 (native block lines)", "17.8", "17.6", "1.276", "8")]
OCR_CHECK = [("3.3 rule as is", "54", "99.6", "99.8", "99.7"), ("Substitution, one read", "2", "99.4", "2.0", "2.7"), ("Substitution, confirming re-read", "0", "99.4", "0.2", "0.3"), ("Shipped: substitution, insertion, deletion, confirming re-read", "0", "99.4", "90.3", "87.9")]


def load(bench: Path, model: str, proto: str, vqa=False):
    root = bench / ("results_vqa_cot" if (vqa and proto == "cot") else "results_vqa" if vqa else "results")
    f = root / model / ("metrics.json" if vqa else f"{proto}/metrics.json")
    return json.load(open(f)) if f.exists() else None


def wavg(ds: dict, key: str):
    tot = sum(ds[k]["n"] for k in TEXT_DS if k in ds)
    if not tot or any(k not in ds or ds[k].get(key) is None for k in TEXT_DS):
        return None
    return sum(ds[k][key] * ds[k]["n"] for k in TEXT_DS) / tot


def f1(x, signed=False):
    if x is None:
        return "--"
    return f"{x:+.1f}" if signed else f"{x:.1f}"


def tex_escape(s: str) -> str:
    return s.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")


def write(path: Path, lines: list[str]):
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--bench", default=str(Path.home() / "vaidyx/benchmark")); a = ap.parse_args()
    bench = Path(a.bench)
    T = HERE / "tables"; T.mkdir(exist_ok=True)
    byname = {m["key"]: m for m in MODELS}
    tag = lambda m: f"{m['country']} & {m['type']}"

    # text results
    text = {}
    for k in KEYS:
        for proto in ("cot", "direct"):
            d = load(bench, k, proto)
            if not d:
                continue
            ds = d["datasets"]
            row = dict(acc=[ds[x]["accuracy"] for x in TEXT_DS], ft=[ds[x].get("accuracy_first_token") for x in TEXT_DS], parsed=[ds[x]["parsed_rate"] for x in TEXT_DS],
                       n=[ds[x]["n"] for x in TEXT_DS], overall=wavg(ds, "accuracy"), overall_ft=wavg(ds, "accuracy_first_token"), min_parsed=min(ds[x]["parsed_rate"] for x in TEXT_DS),
                       load_s=d.get("load_seconds"), total_s=d.get("total_seconds"), gen_tokens=sum(ds[x]["mean_gen_tokens"] * ds[x]["n"] for x in TEXT_DS) / sum(ds[x]["n"] for x in TEXT_DS))
            if k in RESCORED and proto == "direct":
                row.update(acc=RESCORED[k]["direct"], overall=RESCORED[k]["overall"], ft=[None] * 5, overall_ft=None, parsed=[None] * 5, min_parsed=None, rescored=True)
            text[(k, proto)] = row
    cot_rank = sorted([k for k in KEYS if (k, "cot") in text], key=lambda k: -text[(k, "cot")]["overall"])

    # Table 1: models
    L = ["\\begin{tabular}{@{}llllllc@{}}", "\\toprule", "Model & Params & Developer & Country & Type & Reads images & Earlier report \\\\", "\\midrule"]
    for m in MODELS:
        L.append(f"{m['name']} & {m['params']} & {tex_escape(m['developer'])} & {m['country']} & {m['type']} & {'Yes' if m['images'] else 'No'} & {'Yes' if m['previous'] else 'New'} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "models.tex", L)

    # Table 2: data cards
    L = ["\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{2.2cm}>{\\raggedright\\arraybackslash}p{6.6cm}>{\\raggedright\\arraybackslash}p{3.0cm}>{\\raggedright\\arraybackslash}p{2.2cm}>{\\raggedright\\arraybackslash}p{1.3cm}@{}}", "\\toprule", "Dataset & What it tests & Questions & Format & Chance \\\\", "\\midrule"]
    for c in DATA_CARDS:
        if c["kind"] == "image" and c["key"] == "vqa_rad": L.append("\\midrule")
        L.append(f"{c['name']} & {tex_escape(c['tests'])} & {tex_escape(c['n'])} & {tex_escape(c['fmt'])} & {tex_escape(c['chance'])} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "datasets.tex", L)

    # Table 3: CoT ranked
    L = ["\\begin{tabular}{@{}rlllrrrrrrr@{}}", "\\toprule", "\\# & Model & Origin & Type & MedQA & MedMCQA & PubMedQA & MMLU-Med & MedXpertQA & Overall & Min parsed \\% \\\\", "\\midrule"]
    best = {i: max(text[(k, "cot")]["acc"][i] for k in cot_rank) for i in range(5)}
    for r, k in enumerate(cot_rank, 1):
        t = text[(k, "cot")]
        cells = [("\\textbf{%s}" % f1(v)) if v == best[i] else f1(v) for i, v in enumerate(t["acc"])]
        L.append(f"{r} & {byname[k]['name']} & {tag(byname[k])} & " + " & ".join(cells) + f" & {f1(t['overall'])} & {f1(t['min_parsed'])} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "text_cot.tex", L)

    # Table 4: direct, with first-token and CoT gain
    direct_rank = sorted([k for k in KEYS if (k, "direct") in text], key=lambda k: -text[(k, "direct")]["overall"])
    L = ["\\begin{tabular}{@{}lllrrrrrrrrr@{}}", "\\toprule", "Model & Origin & Type & MedQA & MedMCQA & PubMedQA & MMLU-Med & MedXpertQA & Overall & \\thead{First-token\\\\overall} & \\thead{Parsed\\\\\\%} & \\thead{CoT\\\\gain} \\\\", "\\midrule"]
    for k in direct_rank:
        t = text[(k, "direct")]; c = text.get((k, "cot"))
        gain = f1(c["overall"] - t["overall"], signed=True) if c else "--"
        dag = "$^{\\dagger}$" if t.get("rescored") else ""
        L.append(f"{byname[k]['name']}{dag} & {tag(byname[k])} & " + " & ".join(f1(v) for v in t["acc"]) + f" & {f1(t['overall'])} & {f1(t['overall_ft'])} & {f1(t['min_parsed'])} & {gain} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "text_direct.tex", L)

    # Table 5: ours vs published (text, CoT)
    L = ["\\begin{tabular}{@{}llrrrrrr@{}}", "\\toprule", "Model & Row & MedQA & MedMCQA & PubMedQA & MMLU-Med & MedXpertQA & \\thead{Mean\\\\diff.} \\\\", "\\midrule"]
    for k in cot_rank:
        if k not in PUBLISHED_TEXT: continue
        ours = text[(k, "cot")]["acc"]; pub = PUBLISHED_TEXT[k]["v"]
        diffs = [o - p for o, p in zip(ours, pub) if p is not None]
        L.append(f"\\multirow{{3}}{{*}}{{{byname[k]['name']}}} & This run (bf16, CoT) & " + " & ".join(f1(v) for v in ours) + " & \\\\")
        L.append(f" & Published ({PUBLISHED_TEXT[k]['src']}) & " + " & ".join(f1(v) for v in pub) + " & \\\\")
        L.append(" & Difference & " + " & ".join(f1(o - p, True) if p is not None else "--" for o, p in zip(ours, pub)) + f" & {f1(sum(diffs) / len(diffs), True)} \\\\")
        L.append("\\midrule")
    L[-1] = "\\bottomrule"; L.append("\\end{tabular}"); write(T / "text_vs_published.tex", L)

    # Table 6: vs Q4
    L = ["\\begin{tabular}{@{}llrrrrrr@{}}", "\\toprule", "Model & Run & MedQA & MedMCQA & PubMedQA & MMLU-Med & MedXpertQA & \\thead{Mean\\\\gain} \\\\", "\\midrule"]
    for k in [x for x in KEYS if x in Q4]:
        q = Q4[k]; qm = sum(q) / 5
        L.append(f"\\multirow{{3}}{{*}}{{{byname[k]['name']}}} & Q4\\_K\\_M, GB10 & " + " & ".join(f1(v) for v in q) + " & \\\\")
        for proto, label in (("direct", "bf16, H200, direct"), ("cot", "bf16, H200, CoT")):
            t = text[(k, proto)]; L.append(f" & {label} & " + " & ".join(f1(v) for v in t["acc"]) + f" & {f1(sum(t['acc']) / 5 - qm, True)} \\\\")
        L.append("\\midrule")
    L[-1] = "\\bottomrule"; L.append("\\end{tabular}"); write(T / "text_vs_q4.tex", L)

    # Table 7: throughput
    L = ["\\begin{tabular}{@{}llrrr@{}}", "\\toprule", "Model & Protocol & Load (s) & Run (s) & Mean generated tokens \\\\", "\\midrule"]
    for k in cot_rank:
        for proto in ("direct", "cot"):
            t = text.get((k, proto))
            if t and t.get("total_s") is not None:
                L.append(f"{byname[k]['name']} & {'step-by-step' if proto == 'cot' else 'direct'} & {t['load_s']:.0f} & {t['total_s']:.0f} & {t['gen_tokens']:.0f} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "throughput.tex", L)

    # image results
    img = {}
    for m in MODELS:
        if not m["images"]: continue
        d = load(bench, m["key"], "direct", vqa=True); c = load(bench, m["key"], "cot", vqa=True)
        if not d: continue
        ds = d["datasets"]; cs = c["datasets"] if c else {}
        g = lambda k, path: (lambda x: x)(ds.get(k, {}))
        img[m["key"]] = dict(
            overall={k: ds[k]["overall_accuracy"] for k in IMG_DS if k in ds},
            cot={k: cs[k]["overall_accuracy"] for k in ("pmc_vqa", "medxpertqa_mm") if k in cs},
            omni_ft=ds["omnimedvqa"]["mcq"].get("accuracy_first_token"), omni_parsed=ds["omnimedvqa"]["mcq"]["parsed_rate"], omni_errors=ds["omnimedvqa"]["errors"],
            split={k: (ds[k]["yesno"]["accuracy"], ds[k]["open"]["accuracy"]) for k in ("vqa_rad", "slake", "pathvqa")},
            errors={k: ds[k].get("errors", 0) for k in IMG_DS if k in ds}, load_s=d.get("load_seconds"), total_s=d.get("total_seconds"))
    img_rank = sorted(img, key=lambda k: -(img[k]["omni_ft"] or 0))

    L = ["\\begin{tabular}{@{}lllrrrrrrrrr@{}}", "\\toprule", "Model & Origin & Type & VQA-RAD & SLAKE & PathVQA & PMC-VQA & \\thead{MedXpertQA\\\\MM} & \\thead{PMC-VQA\\\\CoT} & \\thead{MedXpertQA\\\\MM, CoT} & \\thead{OmniMedVQA\\\\strict} & \\thead{OmniMedVQA\\\\first-token} \\\\", "\\midrule"]
    for k in img_rank:
        i = img[k]; o = i["overall"]
        L.append(f"{byname[k]['name']} & {tag(byname[k])} & " + " & ".join(f1(o.get(x)) for x in ("vqa_rad", "slake", "pathvqa", "pmc_vqa", "medxpertqa_mm")) + f" & {f1(i['cot'].get('pmc_vqa'))} & {f1(i['cot'].get('medxpertqa_mm'))} & {f1(o.get('omnimedvqa'))} & {f1(i['omni_ft'])} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "image_all.tex", L)

    L = ["\\begin{tabular}{@{}lllrrrrrr@{}}", "\\toprule", "Model & Origin & Type & \\thead{VQA-RAD\\\\yes/no} & \\thead{VQA-RAD\\\\open} & \\thead{SLAKE\\\\yes/no} & \\thead{SLAKE\\\\open} & \\thead{PathVQA\\\\yes/no} & \\thead{PathVQA\\\\open} \\\\", "\\midrule"]
    for k in img_rank:
        s = img[k]["split"]
        L.append(f"{byname[k]['name']} & {tag(byname[k])} & " + " & ".join(f"{f1(s[x][0])} & {f1(s[x][1])}" for x in ("vqa_rad", "slake", "pathvqa")) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "image_split.tex", L)

    L = ["\\begin{tabular}{@{}lllrrrrrrrrr@{}}", "\\toprule", "Model & Origin & Type & Strict & \\thead{First\\\\token} & \\thead{Parsed\\\\\\%} & Errors & " + " & ".join("\\thead{%s}" % t.replace(" ", "\\\\", 1) for t in OMNI_TYPES) + " \\\\", "\\midrule"]
    for k in img_rank:
        i = img[k]
        L.append(f"{byname[k]['name']} & {tag(byname[k])} & {f1(i['overall'].get('omnimedvqa'))} & {f1(i['omni_ft'])} & {f1(i['omni_parsed'])} & {i['omni_errors']:,} & " + " & ".join(f1(v) for v in OMNI_BY_TYPE[k]) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "omnimedvqa.tex", L)

    L = ["\\begin{tabular}{@{}llrlrlrl@{}}", "\\toprule", "Model & Benchmark & This run & Our protocol & Published & Source & Diff. & Like for like? \\\\", "\\midrule"]
    for k, b, ours, proto, pub, src, like in PUBLISHED_IMG:
        L.append(f"{byname[k]['name']} & {tex_escape(b)} & {f1(ours)} & {proto} & {f1(pub)} & {src} & {f1(ours - pub, True)} & {tex_escape(like)} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "image_vs_published.tex", L)

    # Vaidyx evaluations
    L = ["\\begin{tabular}{@{}lllrrrrrrr@{}}", "\\toprule", "Model & Origin & Type & \\thead{Reader\\\\word recall} & \\thead{Invented\\\\numbers} & \\thead{Reader s\\\\(5 scans)} & \\thead{Doc.\\\\types} & Fields & Fabricated & \\thead{Extractor s\\\\(31 docs)} \\\\", "\\midrule"]
    for k, *rest in BAKEOFF:
        L.append(f"{byname[k]['name']} & {tag(byname[k])} & " + " & ".join(rest) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "bakeoff.tex", L)
    L = ["\\begin{tabular}{@{}lllrrr@{}}", "\\toprule", "Reasoner & Origin & Type & Pass & Fabrications & Mean latency (s) \\\\", "\\midrule"]
    for k, *rest in ANSWERABILITY:
        L.append(f"{byname[k]['name']} & {tag(byname[k])} & " + " & ".join(rest) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "answerability.tex", L)
    L = ["\\begin{tabular}{@{}rrr" + "r" * len(TCGA["agreement"]) + "@{}}", "\\toprule",
         "Reports & Extracted values & Ungrounded & " + " & ".join(k for k, _ in TCGA["agreement"]) + " \\\\", "\\midrule",
         f"{TCGA['reports']} & {TCGA['claims']} & {TCGA['ungrounded']} & " + " & ".join(v for _, v in TCGA["agreement"]) + " \\\\",
         "\\bottomrule", "\\end{tabular}"]; write(T / "tcga.tex", L)
    L = ["\\begin{tabular}{@{}lr@{}}", "\\toprule", "Evidence in the report & Share of the 9,523 reports \\\\", "\\midrule"]
    for k, v in STATUS["rows"]: L.append(f"{k} & {tex_escape(v)} \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "status.tex", L)
    L = ["\\begin{tabular}{@{}lrrrr@{}}", "\\toprule", "Engine & Number recall \\% & Number precision \\% & s / page (median) & Threads per page \\\\", "\\midrule"]
    for row in OCR: L.append(" & ".join(row) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "ocr.tex", L)
    L = ["\\begin{tabular}{@{}lrrrr@{}}", "\\toprule", "Check & False alarms & Substitutions caught \\% & Insertions caught \\% & Deletions caught \\% \\\\", "\\midrule"]
    for row in OCR_CHECK: L.append(" & ".join(row) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}"]; write(T / "ocr_check.tex", L)

    # experiments (TODO.md items 1 to 4), when they have been run: experiments/results/*.json
    X = HERE / "experiments" / "results"
    xp = lambda n: json.load(open(X / n)) if (X / n).exists() else None
    ci, pairs, onc, tsc, prb = xp("ci.json"), xp("paired.json"), xp("oncology.json"), xp("tcga_scale.json"), xp("probes_scale.json")
    web_x = {}
    if ci:
        L = ["\\begin{tabular}{@{}lllrrrr@{}}", "\\toprule", "Model & Origin & Type & CoT overall & 95\\% CI & Direct overall & 95\\% CI \\\\", "\\midrule"]
        rows = []
        for k in cot_rank:
            c, d = ci["text"][f"{k}|cot"]["overall"], ci["text"][f"{k}|direct"]["overall"]
            L.append(f"{byname[k]['name']} & {tag(byname[k])} & {c[0]:.1f} & [{c[1]:.1f}, {c[2]:.1f}] & {d[0]:.1f} & [{d[1]:.1f}, {d[2]:.1f}] \\\\")
            rows.append(dict(key=k, cot=c, direct=d, medxpertqa=ci["text"][f"{k}|cot"]["medxpertqa"]))
        L += ["\\bottomrule", "\\end{tabular}"]; write(T / "ci_text.tex", L)
        web_x["ciText"] = rows
    if pairs:
        L = ["\\begin{tabular}{@{}lrrrr@{}}", "\\toprule", "Comparison & Difference & 95\\% CI & Discordant (A only / B only) & McNemar $p$ \\\\", "\\midrule"]
        for r in pairs:
            pv = "$<$0.001" if r["p_mcnemar"] < 0.001 else f"{r['p_mcnemar']:.2f}"
            name = tex_escape(r["comparison"].replace(" ('matches')", ""))
            L.append(f"{name} & {r['diff']:+.1f} & [{r['lo']:+.1f}, {r['hi']:+.1f}] & {r['a_only']} / {r['b_only']} & {pv} \\\\")
        L += ["\\bottomrule", "\\end{tabular}"]; write(T / "paired.tex", L)
        web_x["paired"] = pairs
    if onc:
        L = ["\\begin{tabular}{@{}lllrrrr@{}}", "\\toprule", "Model & Origin & Type & Oncology (CoT) & 95\\% CI & Other questions (CoT) & Oncology (direct) \\\\", "\\midrule"]
        rows = []
        for k in sorted(onc["models"], key=lambda m: -onc["models"][m]["cot"]["oncology"][0]):
            c = onc["models"][k]["cot"]
            L.append(f"{byname[k]['name']} & {tag(byname[k])} & {c['oncology'][0]:.1f} & [{c['oncology'][1]:.1f}, {c['oncology'][2]:.1f}] & {c['rest'][0]:.1f} & {onc['models'][k]['direct']['oncology'][0]:.1f} \\\\")
            rows.append(dict(key=k, oncology=c["oncology"], rest=c["rest"], direct=onc["models"][k]["direct"]["oncology"]))
        L += ["\\bottomrule", "\\end{tabular}"]; write(T / "oncology.tex", L)
        web_x["oncology"] = dict(sizes=onc["sizes"], n=onc["n"], rows=rows)
    if tsc:
        a = tsc["agreement"]
        order = [k for k in ("Histology", "pT", "pN", "Stage group", "ER", "PR", "HER2 (IHC)") if k in a]
        dv = tsc.get("disagreements_with_verified_quote", {})
        L = ["\\begin{tabular}{@{}lrrrrr@{}}", "\\toprule", "Field & Agree & Compared & Agreement \\% & Lower 95\\% bound & Differences the report states \\\\", "\\midrule"]
        for k in order:
            d = dv.get(k)
            L.append(f"{k} & {a[k]['agree']:,} & {a[k]['n']:,} & {a[k]['pct']:.1f} & {a[k]['lower95_pct']:.1f} & {(str(d['verified']) + ' of ' + str(d['of'])) if d else '--'} \\\\")
        L += ["\\bottomrule", "\\end{tabular}"]; write(T / "tcga_scale.tex", L)
        web_x["tcgaScale"] = tsc
    if prb and prb.get("rescored"):
        q = prb["rescored"]
        L = ["\\begin{tabular}{@{}lrrl@{}}", "\\toprule", "Probe kind & Probes & Right answer & What a right answer is \\\\", "\\midrule",
             f"Answerable (answer key) & {q['ans']['n']} & {q['ans']['pass']} & the value, with its quote \\\\",
             f"Not in the file (trap) & {q['absent_true_trap']['n']} & {q['absent_true_trap']['pass']} & ``not documented'', no value \\\\",
             f"Out of scope & {q['scope']['n']} & {q['scope']['pass']} & declined \\\\",
             f"Documented after all & {q['absent_documented_after_all']} & {q['absent_documented_after_all']} & answered with verified quotes (answer-key gap) \\\\",
             f"Hand-written release set & {q['hand_written']['n']} & {q['hand_written']['pass']} & as Table~\\ref{{tab:answerability}} \\\\",
             "\\bottomrule", "\\end{tabular}"]
        write(T / "probes_scale.tex", L)
        L = ["\\begin{tabular}{@{}l>{\\raggedright\\arraybackslash}p{7.2cm}l>{\\raggedright\\arraybackslash}p{4.2cm}@{}}", "\\toprule", "Case & Statement the reasoner wrote & Why removed & Review against the document \\\\", "\\midrule"]
        for x in q["statements_removed_by_grounding"]:
            L.append(f"{x['case']} & {tex_escape(x['text'])} & {x['reason'].replace('_', ' ')} & {tex_escape(x['review'])}: {tex_escape(x['note'])} \\\\")
        L += ["\\bottomrule", "\\end{tabular}"]; write(T / "probes_removed.tex", L)
        web_x["probesScale"] = {k: q[k] for k in ("ans", "absent_true_trap", "absent_documented_after_all", "scope", "hand_written", "statements_removed_by_grounding", "removed_by_review", "statements_removed_by_output_guardrail")} | {"generated": prb["generated"]}
    # the website's data
    web = dict(
        models=MODELS, dataCards=DATA_CARDS, thinkingOff=sorted(THINKING_OFF),
        textCot=[dict(key=k, acc=text[(k, "cot")]["acc"], overall=text[(k, "cot")]["overall"], minParsed=text[(k, "cot")]["min_parsed"]) for k in cot_rank],
        textDirect=[dict(key=k, acc=text[(k, "direct")]["acc"], overall=text[(k, "direct")]["overall"], overallFt=text[(k, "direct")]["overall_ft"], minParsed=text[(k, "direct")]["min_parsed"], rescored=bool(text[(k, "direct")].get("rescored")), cotGain=(text[(k, "cot")]["overall"] - text[(k, "direct")]["overall"]) if (k, "cot") in text else None) for k in direct_rank],
        textFirstToken=[dict(key=k, acc=text[(k, "direct")]["ft"], overall=text[(k, "direct")]["overall_ft"]) for k in direct_rank if text[(k, "direct")]["overall_ft"] is not None],
        publishedText=[dict(key=k, src=PUBLISHED_TEXT[k]["src"], ours=text[(k, "cot")]["acc"], published=PUBLISHED_TEXT[k]["v"]) for k in cot_rank if k in PUBLISHED_TEXT],
        q4=[dict(key=k, q4=Q4[k], direct=text[(k, "direct")]["acc"], cot=text[(k, "cot")]["acc"]) for k in KEYS if k in Q4],
        throughput=[dict(key=k, protocol=p, load=text[(k, p)]["load_s"], total=text[(k, p)]["total_s"], genTokens=text[(k, p)]["gen_tokens"]) for k in cot_rank for p in ("direct", "cot") if (k, p) in text and text[(k, p)].get("total_s") is not None],
        image=[dict(key=k, overall=img[k]["overall"], cot=img[k]["cot"], omniFt=img[k]["omni_ft"], omniParsed=img[k]["omni_parsed"], omniErrors=img[k]["omni_errors"], split=img[k]["split"], byType=OMNI_BY_TYPE[k]) for k in img_rank],
        omniTypes=OMNI_TYPES,
        publishedImage=[dict(key=k, benchmark=b, ours=o, protocol=p, published=pub, src=s, like=l) for k, b, o, p, pub, s, l in PUBLISHED_IMG],
        bakeoff=[dict(key=k, readerRecall=a, invented=b, readerS=c, types=d, fields=e, fabricated=f, extractorS=g) for k, a, b, c, d, e, f, g in BAKEOFF],
        answerability=[dict(key=k, pass_=a, fabrications=b, latency=c) for k, a, b, c in ANSWERABILITY],
        tcga=TCGA, status=STATUS, ocr=[dict(engine=a, recall=b, precision=c, sPage=d, threads=e) for a, b, c, d, e in OCR], ocrCheck=[dict(check=a, falseAlarms=b, subs=c, ins=d, dels=e) for a, b, c, d, e in OCR_CHECK],
        experiments=web_x,
        totals=dict(models=len(MODELS), textQuestions=sum(text[(cot_rank[0], "cot")]["n"]), imageQuestions=sum(v["n"] for v in load(bench, img_rank[0], "direct", vqa=True)["datasets"].values()), visionModels=len(img)),
    )
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text("// Generated by docs/research/benchmark-paper/build_data.py from the raw benchmark results; do not edit by hand.\n"
                   "/* eslint-disable */\nexport const RESEARCH_DATA = " + json.dumps(web, indent=1) + " as const;\n")
    print("tables:", sorted(p.name for p in T.glob("*.tex")))
    print("cot ranking:", [(k, round(text[(k, 'cot')]['overall'], 1)) for k in cot_rank])
    print("image ranking:", [(k, img[k]["omni_ft"]) for k in img_rank])
    print("totals:", web["totals"])


if __name__ == "__main__":
    main()
