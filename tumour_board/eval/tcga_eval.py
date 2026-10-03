"""Extraction on REAL de-identified pathology reports (TCGA OCR text, tatonetti-lab, MIT) vs TCGA clinical ground truth.
Measures: grounding of every claim, agreement with ground truth where the report states the field, speed."""
import asyncio, csv, json, re, sys, time
from pathlib import Path

from tumour_board import config, extract
from tumour_board.grounding import verify, norm

SRC = Path("/data/vaidyx/tb_resources/real_data/tcga_eval_subset_30.csv")
FIELDS = ["histologic_type", "grade", "lvi", "margins", "er", "pr", "her2", "recorded_stage", "mmr"]


def polarity(s):
    s = norm(s)
    if re.search(r"\bnegative\b|not (amplified|detected)|\b0\b|1\+", s): return "negative"
    if re.search(r"\bpositive\b|amplified|3\+", s): return "positive"
    if "2+" in s or "equivocal" in s: return "equivocal"
    return None


async def main():
    rows = list(csv.DictReader(open(SRC)))
    t0 = time.time()
    res = await asyncio.gather(*[extract.extract_facts(r["report_text_ocr"], FIELDS) for r in rows])
    claims = ungrounded = 0; agree = {}; details = []
    for r, x in zip(rows, res):
        text = r["report_text_ocr"]
        for f in FIELDS:
            e = x.get(f) or {}
            if not (e.get("found") and e.get("value")): continue
            claims += 1
            v = verify(e["value"], e.get("quote") or e["value"], [text])
            if v["status"] == "unverified":
                ungrounded += 1; details.append({"id": r["patient_id"], "field": f, "value": e["value"], "quote": e.get("quote"), "why": v["reason"]})
        def cmp(name, gt, got, fn):
            if not gt or not got: return
            a = agree.setdefault(name, [0, 0]); a[1] += 1
            ok = fn(gt, got); a[0] += ok
            if not ok: details.append({"id": r["patient_id"], "field": name, "gt": gt, "got": got})
        g = lambda f: (x.get(f) or {}).get("value") if (x.get(f) or {}).get("found") else None
        cmp("ER", r["gt_er_status_by_ihc"], g("er"), lambda a, b: polarity(b) == a.lower())
        cmp("PR", r["gt_pr_status_by_ihc"], g("pr"), lambda a, b: polarity(b) == a.lower())
        cmp("pT (as recorded)", r["gt_ajcc_tumor_pathologic_pt"], g("recorded_stage"), lambda a, b: re.sub(r"[^a-z0-9]", "", a.lower())[:2] in re.sub(r"[^a-z0-9]", "", b.lower()))
        cmp("Histology", r["gt_histological_diagnosis"], g("histologic_type"),
            lambda a, b: any(w in norm(b) for w in [w for w in norm(a).split() if len(w) > 5][:2]) or ("adenocarcinoma" in norm(a) and "adenocarcinoma" in norm(b)))
    out = {"reports": len(rows), "seconds": round(time.time() - t0, 1), "claims": claims, "ungrounded_claims": ungrounded,
           "agreement": {k: f"{a}/{n}" for k, (a, n) in agree.items()}, "details": details}
    (config.DATA_ROOT / "eval" / "tcga_eval.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "details"}, indent=1))
    for d in details[:14]: print("  ", d)


asyncio.run(main())
