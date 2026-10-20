"""Benchmark TODO items 3 and 4: confidence intervals, paired tests and the oncology slice, from the saved per-question replies.

  /data/vaidyx/venv/audio/bin/python -I docs/research/benchmark-paper/experiments/stats.py

Read only on ~/vaidyx/benchmark. Writes experiments/results/{ci,paired,oncology}.json (numbers only) and, outside the repo, the
doctor-check sample of the oncology filter (question text; the datasets' text is not redistributed in this repo):
/data/vaidyx/research_experiments/oncology_filter_sample.csv.

Intervals: 95 % percentile bootstrap, 4,000 resamples of questions, stratified by dataset for the pooled overall score. Paired
comparisons: the same resamples for both models (paired bootstrap of the difference) and McNemar's exact test on the discordant
questions. Baichuan-M2 direct is re-scored from the saved replies with the harness parser after removing the stray "</think>" tag
(the published table's numbers), which this script checks it reproduces.
"""
import csv
import json
import os
import re
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

B = Path.home() / "vaidyx/benchmark"
HERE = Path(__file__).resolve().parent
OUT = HERE / "results"
EXT = Path("/data/vaidyx/research_experiments")
RNG = np.random.default_rng(20261020)
NB = 4000

TEXT = ["medqa", "medmcqa", "pubmedqa", "mmlu_med", "medxpertqa"]
MODELS = ["gemma-4-31b-it", "huatuogpt-3-27b", "qwen3.5-4b", "medgemma-27b-text-it", "medgemma-27b-it", "baichuan-m2-32b", "lingshu-32b",
          "medgemma-4b-it", "med42-8b", "jsl-med-8b", "medgemma-1.5-4b-it", "openbiollm-8b", "medllama2-7b"]
VISION = ["huatuogpt-3-27b", "lingshu-32b", "gemma-4-31b-it", "qwen3.5-4b", "medgemma-4b-it", "medgemma-27b-it", "medgemma-1.5-4b-it"]
IMG = ["vqa_rad", "slake", "pathvqa", "pmc_vqa", "medxpertqa_mm", "omnimedvqa"]
ONC = re.compile(r"\b(cancer|carcinoma|tumou?r|neoplas\w*|lymphoma|leuka?emi\w*|sarcoma|metasta\w*|malignan\w*|oncolog\w*|chemotherap\w*|"
                 r"radiotherap\w*|melanoma|myeloma)", re.I)


def parse(text, valid, protocol):  # the harness parser (~/vaidyx/benchmark/run_bench.py), copied, unchanged
    t = text.strip()
    if protocol == "cot":
        m = re.findall(r"answer\s*(?:is|:)?\s*[:\-]?\s*\**\(?\[?([A-J])\b", t, flags=re.I)
        m = [x.upper() for x in m if x.upper() in valid]
        if m:
            return m[-1]
        m = [x.upper() for x in re.findall(r"\(?\boption\s+\(?([A-J])\b", t, flags=re.I) if x.upper() in valid]
        return m[-1] if m else None
    m = re.match(r"^\W*(?:answer\s*(?:is|:)?\s*)?\(?([A-J])\b", t, flags=re.I)
    if m and m.group(1).upper() in valid:
        return m.group(1).upper()
    m = re.search(r"(?:answer|option)\s*(?:is|:)?\s*\(?([A-J])\b", t, flags=re.I)
    if m and m.group(1).upper() in valid:
        return m.group(1).upper()
    return None


def jsonl(p):
    with open(p) as f:
        return [json.loads(l) for l in f]


ITEMS = {d: {x["id"]: x for x in jsonl(B / "data" / f"{d}.jsonl")} for d in TEXT}


def text_vec(model, proto, ds, key="correct"):
    rows = jsonl(B / "results" / model / proto / f"{ds}.jsonl")
    if model == "baichuan-m2-32b" and proto == "direct" and key == "correct":
        out = []
        for r in rows:
            valid = set(ITEMS[ds][r["id"]]["options"])
            p = parse(re.sub(r"</?think>", "", r["raw"]), valid, "direct")
            out.append((r["id"], p == r["gold"]))
        rows = [{"id": i, key: c} for i, c in out]
    order = sorted(rows, key=lambda r: r["id"])
    return [r["id"] for r in order], np.array([bool(r.get(key)) for r in order])


def img_vec(model, ds, key="correct", cot=False):
    rows = jsonl(B / ("results_vqa_cot" if cot else "results_vqa") / model / f"{ds}.jsonl")
    order = sorted(rows, key=lambda r: r["id"])
    return [r["id"] for r in order], np.array([bool(r.get(key)) for r in order]), [r.get("qtype") for r in order]


def boot_ci(vecs):
    """Percentile CI of the pooled accuracy of several datasets (stratified); vecs: list of bool arrays."""
    n = sum(len(v) for v in vecs)
    point = 100 * sum(v.sum() for v in vecs) / n
    stats = np.zeros(NB)
    for v in vecs:
        idx = RNG.integers(0, len(v), size=(NB, len(v)))
        stats += v[idx].sum(axis=1)
    stats = 100 * stats / n
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return round(point, 2), round(lo, 2), round(hi, 2)


def paired(a_vecs, b_vecs):
    """Paired bootstrap CI of (a - b) in points and McNemar's exact p over the pooled questions."""
    n = sum(len(v) for v in a_vecs)
    diff = np.zeros(NB)
    for a, b in zip(a_vecs, b_vecs):
        idx = RNG.integers(0, len(a), size=(NB, len(a)))
        diff += a[idx].sum(axis=1) - b[idx].sum(axis=1)
    diff = 100 * diff / n
    A, Bv = np.concatenate(a_vecs), np.concatenate(b_vecs)
    a_only, b_only = int((A & ~Bv).sum()), int((~A & Bv).sum())
    p = binomtest(a_only, a_only + b_only, 0.5).pvalue if a_only + b_only else 1.0
    point = 100 * (A.sum() - Bv.sum()) / n
    lo, hi = np.percentile(diff, [2.5, 97.5])
    return {"diff": round(point, 2), "lo": round(lo, 2), "hi": round(hi, 2), "a_only": a_only, "b_only": b_only, "p_mcnemar": float(f"{p:.3g}")}


def main():
    OUT.mkdir(exist_ok=True)
    EXT.mkdir(parents=True, exist_ok=True)
    ci = {"text": {}, "image": {}}
    vec = {}
    # text: per dataset and pooled, both protocols, and the first-token score of the direct protocol
    for m in MODELS:
        for proto in ("cot", "direct"):
            per, vs, ids = {}, [], []
            for d in TEXT:
                i, v = text_vec(m, proto, d)
                vec[(m, proto, d)] = (i, v)
                per[d] = boot_ci([v])
                vs.append(v)
            per["overall"] = boot_ci(vs)
            ci["text"][f"{m}|{proto}"] = per
        fts = [text_vec(m, "direct", d, "correct_first_token")[1] for d in TEXT]
        if m != "baichuan-m2-32b":
            ci["text"][f"{m}|first_token"] = {"overall": boot_ci(fts)}
    # check the Baichuan re-score against the published table (74.6, 67.1, 71.7, 86.9, 17.9; 58.6)
    bai = ci["text"]["baichuan-m2-32b|direct"]
    print("Baichuan direct re-scored:", [bai[d][0] for d in TEXT], "overall", bai["overall"][0])
    # images
    for m in VISION:
        per = {}
        for d in IMG:
            i, v, qt = img_vec(m, d)
            vec[(m, "img", d)] = (i, v)
            per[d] = boot_ci([v])
            if d in ("vqa_rad", "slake", "pathvqa"):
                for q in ("yesno", "open"):
                    sel = np.array([x == q for x in qt])
                    per[f"{d}_{q}"] = boot_ci([v[sel]])
        i, v, _ = img_vec(m, "omnimedvqa", "correct_first_token")
        vec[(m, "img_ft", "omnimedvqa")] = (i, v)
        per["omnimedvqa_first_token"] = boot_ci([v])
        for d in ("pmc_vqa", "medxpertqa_mm"):
            p = B / "results_vqa_cot" / m / f"{d}.jsonl"
            if p.exists():
                i, v, _ = img_vec(m, d, cot=True)
                vec[(m, "img_cot", d)] = (i, v)
                per[f"{d}_cot"] = boot_ci([v])
        ci["image"][m] = per
    json.dump(ci, open(OUT / "ci.json", "w"), indent=1)

    # the comparisons the paper's text makes
    def T(m, proto, ds=TEXT):
        return [vec[(m, proto, d)][1] for d in ds]
    def same_ids(a, b, ds, pa, pb):
        for d in ds:
            assert vec[(a, pa, d)][0] == vec[(b, pb, d)][0], (a, b, d)
    claims = [
        ("Gemma-4-31B vs HuatuoGPT-3, CoT overall", "gemma-4-31b-it", "huatuogpt-3-27b", "cot", TEXT),
        ("HuatuoGPT-3 vs Qwen3.5-4B, CoT overall", "huatuogpt-3-27b", "qwen3.5-4b", "cot", TEXT),
        ("Qwen3.5-4B vs MedGemma-27B-it, CoT overall ('matches')", "qwen3.5-4b", "medgemma-27b-it", "cot", TEXT),
        ("Qwen3.5-4B vs MedGemma-27B-it, CoT MedQA", "qwen3.5-4b", "medgemma-27b-it", "cot", ["medqa"]),
        ("Qwen3.5-4B vs MedGemma-27B-text-it, CoT overall", "qwen3.5-4b", "medgemma-27b-text-it", "cot", TEXT),
        ("MedGemma-27B-text-it vs MedGemma-27B-it, CoT overall", "medgemma-27b-text-it", "medgemma-27b-it", "cot", TEXT),
        ("MedGemma-27B-it vs Baichuan-M2, CoT overall", "medgemma-27b-it", "baichuan-m2-32b", "cot", TEXT),
        ("Baichuan-M2 vs Lingshu-32B, CoT overall", "baichuan-m2-32b", "lingshu-32b", "cot", TEXT),
        ("Med42-8B vs JSL-MedLlama, CoT overall", "med42-8b", "jsl-med-8b", "cot", TEXT),
        ("MedGemma-1.5-4B vs OpenBioLLM-8B, CoT overall", "medgemma-1.5-4b-it", "openbiollm-8b", "cot", TEXT),
        ("Qwen3.5-4B vs MedGemma-4B-it, CoT overall", "qwen3.5-4b", "medgemma-4b-it", "cot", TEXT),
        ("Gemma-4-31B vs HuatuoGPT-3, CoT MedXpertQA", "gemma-4-31b-it", "huatuogpt-3-27b", "cot", ["medxpertqa"]),
        ("HuatuoGPT-3 vs Lingshu-32B, direct overall", "huatuogpt-3-27b", "lingshu-32b", "direct", TEXT),
    ]
    out = []
    for name, a, b, proto, ds in claims:
        same_ids(a, b, ds, proto, proto)
        out.append({"comparison": name, **paired(T(a, proto, ds), T(b, proto, ds))})
    # within a model: step-by-step vs direct (paired by question)
    for m in ("gemma-4-31b-it", "huatuogpt-3-27b", "lingshu-32b", "med42-8b"):
        out.append({"comparison": f"{m}: CoT vs direct overall", **paired(T(m, "cot"), T(m, "direct"))})
    # images
    def I(m, kind, d):
        return [vec[(m, kind, d)][1]]
    img_claims = [
        ("HuatuoGPT-3 vs Lingshu-32B, OmniMedVQA first-token", "huatuogpt-3-27b", "lingshu-32b", "img_ft", "omnimedvqa"),
        ("Lingshu-32B vs Gemma-4-31B, OmniMedVQA first-token", "lingshu-32b", "gemma-4-31b-it", "img_ft", "omnimedvqa"),
        ("Lingshu-32B vs HuatuoGPT-3, SLAKE", "lingshu-32b", "huatuogpt-3-27b", "img", "slake"),
        ("Lingshu-32B vs MedGemma-4B, VQA-RAD", "lingshu-32b", "medgemma-4b-it", "img", "vqa_rad"),
        ("Gemma-4-31B vs HuatuoGPT-3, MedXpertQA-MM CoT", "gemma-4-31b-it", "huatuogpt-3-27b", "img_cot", "medxpertqa_mm"),
        ("Gemma-4-31B vs Lingshu-32B, PMC-VQA CoT", "gemma-4-31b-it", "lingshu-32b", "img_cot", "pmc_vqa"),
    ]
    for name, a, b, kind, d in img_claims:
        assert vec[(a, kind, d)][0] == vec[(b, kind, d)][0], name
        out.append({"comparison": name, **paired(I(a, kind, d), I(b, kind, d))})
    json.dump(out, open(OUT / "paired.json", "w"), indent=1)

    # TODO 4: the oncology slice of the three exam sets with clinical vignettes
    onc_sets = ["medqa", "medmcqa", "medxpertqa"]
    flag = {}
    for d in onc_sets:
        for i, it in ITEMS[d].items():
            txt = " ".join([it["question"], *it["options"].values()])
            flag[(d, i)] = bool(ONC.search(txt))
    sizes = {d: sum(flag[(d, i)] for i in ITEMS[d]) for d in onc_sets}
    onc = {"filter": ONC.pattern, "sizes": sizes, "n": sum(sizes.values()), "models": {}}
    for m in MODELS:
        row = {}
        for proto in ("cot", "direct"):
            on, off = [], []
            for d in onc_sets:
                ids, v = vec[(m, proto, d)]
                sel = np.array([flag[(d, i)] for i in ids])
                on.append(v[sel]); off.append(v[~sel])
            row[proto] = {"oncology": boot_ci(on), "rest": boot_ci(off), "all3": boot_ci([np.concatenate([a, b]) for a, b in zip(on, off)])}
        onc["models"][m] = row
    rank_all = sorted(MODELS, key=lambda m: -onc["models"][m]["cot"]["all3"][0])
    rank_onc = sorted(MODELS, key=lambda m: -onc["models"][m]["cot"]["oncology"][0])
    onc["rank_all3_cot"], onc["rank_oncology_cot"] = rank_all, rank_onc
    json.dump(onc, open(OUT / "oncology.json", "w"), indent=1)
    # the doctor-check sample: 60 flagged and 40 not flagged, fixed seed, question text kept outside the repo
    rng = np.random.default_rng(7)
    pool_on = [k for k, v in flag.items() if v]
    pool_off = [k for k, v in flag.items() if not v]
    pick = [(k, True) for k in rng.choice(len(pool_on), 60, replace=False).tolist()] + [(k, False) for k in rng.choice(len(pool_off), 40, replace=False).tolist()]
    rng.shuffle(pick)
    with open(EXT / "oncology_filter_sample.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["n", "dataset", "id", "question", "options", "filter_says_oncology", "doctor_says_oncology (yes/no)", "note"])
        for n, (k, is_on) in enumerate(pick, 1):
            d, i = (pool_on if is_on else pool_off)[k]
            it = ITEMS[d][i]
            w.writerow([n, d, i, it["question"], " | ".join(f"{a}. {b}" for a, b in it["options"].items()), "yes" if is_on else "no", "", ""])
    print("oncology slice:", sizes, "total", onc["n"])
    print("wrote", OUT, "and", EXT / "oncology_filter_sample.csv")


if __name__ == "__main__":
    main()
