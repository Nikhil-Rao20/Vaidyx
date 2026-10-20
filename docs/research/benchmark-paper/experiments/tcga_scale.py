"""Benchmark TODO item 2: the shipped extractor on every TCGA pathology report that has clinical ground truth (breast, lung
adenocarcinoma, colorectal: 2,102 reports), against the cBioPortal clinical tables.

  cd ~/vaidyx/Vaidyx && /data/vaidyx/venv/app/bin/python docs/research/benchmark-paper/experiments/tcga_scale.py [--limit N]

Same fields, prompt, model and grounding check as tumour_board/eval/tcga_eval.py (the 30-report run), on the OCR text of the
public de-identified reports (TCGA-Reports, Kefeli and Tatonetti 2024). Writes experiments/results/tcga_scale.json (numbers only) and
the per-report details with quotes to /data/vaidyx/research_experiments/tcga_scale_details.jsonl.

Agreement is counted only where both sides state the field: ER, PR (IHC status), HER2 (IHC: 0 / 1+ negative, 2+ equivocal, 3+
positive), histology (key words), and pT, pN and the stage group only when the extracted value states that category (a report that
gives a stage group is not counted as a wrong pT). A ground truth of "Indeterminate", "[Not Available]" and the like is skipped.
"""
import argparse
import asyncio
import csv
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tumour_board import extract  # noqa: E402
from tumour_board.grounding import norm, verify  # noqa: E402

R = Path("/data/vaidyx/tb_resources/real_data")
HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "tcga_scale.json"
EXT = Path("/data/vaidyx/research_experiments/tcga_scale_details.jsonl")
RAWX = Path("/data/vaidyx/research_experiments/tcga_scale_extractions.jsonl")  # every reading, so scoring can be redone offline
FIELDS = ["histologic_type", "grade", "lvi", "margins", "er", "pr", "her2", "recorded_stage", "mmr"]
csv.field_size_limit(10 ** 9)


PENDING = re.compile(r"pending|to follow|will be (performed|reported|issued|sent)|to be (performed|reported)|see (addendum|separate|prior|previous)|sent for|"
                     r"not (performed|done|available)|in progress|requested|\bordered\b|previously reported|refer to|deferred", re.I)
FISH = re.compile(r"fish|amplif|ratio|copy|cep17|sish|cish", re.I)


def polarity(s):
    """tcga_eval.py's rule, plus the phrasings the 30-report run met by hand: "no ... receptors found" is negative, a share of
    stained cells of 1 % or more is positive (ASCO/CAP), "weak / moderate / strong staining" is positive."""
    s = norm(s)
    if re.search(r"\bnegative\b|not (amplified|detected)|\b0\b|1\+|\bno\b.*\b(found|seen|identified|staining|expression)|absent|lack", s):
        return "negative"
    if "2+" in s or "equivocal" in s or "borderline" in s:
        return "equivocal"
    if re.search(r"\bpositive\b|amplified|3\+|(weak|moderate|strong|intense)\w*\s+(nuclear\s+)?(staining|expression|reactivity)", s):
        return "positive"
    if re.search(r"low positive|weakly positive", s):
        return "positive"
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*%", s)
    if m and float(m.group(1)) >= 1:  # a share of stained tumour cells, 1 % or more (ASCO/CAP)
        return "positive"
    return None


def gt_ok(v):
    v = (v or "").strip()
    return v and not re.search(r"not available|not evaluated|indeterminate|unknown|^\[|^nx$|^tx$|^mx$|stage x|other, specify|please specify", v, re.I)


def t_cat(s):
    m = re.search(r"\bp?y?(T(?:is|[0-4]))", s or "", re.I)
    return m.group(1).upper() if m else None


def n_cat(s):
    m = re.search(r"(?<![A-Za-z])p?(N[0-3])", s or "", re.I)
    return m.group(1).upper() if m else None


ROMAN = {"0": 0, "I": 1, "II": 2, "III": 3, "IV": 4}


def stage_group(s):
    m = re.search(r"stage\s*(IV|III|II|I|0)\s*([ABC])?", s or "", re.I)
    return (m.group(1).upper(), (m.group(2) or "").upper()) if m else None


def histo_ok(gt, got):
    """Key words compared by their first six letters (infiltrating / infiltrative, ductal / duct are one word here)."""
    a, b = norm(gt), norm(got)
    stems = lambda t: {w[:4] for w in re.findall(r"[a-z]+", t) if len(w) > 3} - {"carc", "inva", "infi", "tumo", "mali", "prim", "mixe", "othe", "poor", "well", "mode", "diff", "grad", "type", "lung", "colo", "rect", "brea", "situ", "with", "spec", "plea", "hist"}
    sa, sb = stems(a), stems(b)
    if "adenoc" in sa:
        return "adenoc" in sb
    return bool(sa & sb) if sa else False


def load():
    kind = {r["patient_id"]: r["cancer_type"] for r in csv.DictReader(open(R / "tcga_path_reports_text/tcga_patient_to_cancer_type.csv"))}
    gt = {}
    for f in ("brca", "luad", "coadread"):
        for r in csv.DictReader(open(R / f"tcga_ground_truth_clinical/cbioportal_{f}_tcga_patient_clinical.csv")):
            gt[r["patientId"]] = r
    rows = []
    for r in csv.DictReader(open(R / "tcga_path_reports_text/TCGA_Reports.csv")):
        pid = r["patient_filename"].split(".")[0]
        if pid in gt:
            rows.append({"id": pid, "project": kind.get(pid, "?"), "text": r["text"], "gt": gt[pid]})
    return rows


def wilson_upper(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    return round(100 * (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n), 3)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rescore", action="store_true", help="score the saved readings again, no model calls")
    a = ap.parse_args()
    rows = load()
    if a.limit:
        rows = rows[: a.limit]
    print(f"{len(rows)} reports", {p: sum(r['project'] == p for r in rows) for p in ('BRCA', 'LUAD', 'COAD', 'READ')}, flush=True)
    t0 = time.time()
    done = 0

    async def one(r):
        nonlocal done
        try:
            x = await extract.extract_facts(r["text"], FIELDS)
        except Exception as e:  # noqa: BLE001
            x = {"_error": str(e)[:200]}
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{len(rows)} in {time.time() - t0:.0f} s", flush=True)
        return x

    if a.rescore:
        saved = {j["id"]: j["x"] for j in map(json.loads, open(RAWX))}
        res = [saved.get(r["id"], {"_error": "not in the saved readings"}) for r in rows]
        secs = json.loads(OUT.read_text()).get("seconds", 0) if OUT.exists() else 0
    else:
        res = await asyncio.gather(*[one(r) for r in rows])
        secs = time.time() - t0
        RAWX.parent.mkdir(parents=True, exist_ok=True)
        with open(RAWX, "w") as f:
            for r, x in zip(rows, res):
                f.write(json.dumps({"id": r["id"], "x": x}) + "\n")
    EXT.parent.mkdir(parents=True, exist_ok=True)
    claims = ungrounded = errors = 0
    per_field_claims = {f: 0 for f in FIELDS}
    agree = {}
    stated = {"pT": 0, "pN": 0, "stage group": 0}
    pend, fish, dis_grounded = {}, [0], {}
    with open(EXT, "w") as det:
        for r, x in zip(rows, res):
            if "_error" in x:
                errors += 1
                det.write(json.dumps({"id": r["id"], "error": x["_error"]}) + "\n")
                continue
            text, g = r["text"], r["gt"]
            val = lambda f: (x.get(f) or {}).get("value") if (x.get(f) or {}).get("found") and (x.get(f) or {}).get("value") else None
            grounded = {}
            for f in FIELDS:
                e = x.get(f) or {}
                if not (e.get("found") and e.get("value")):
                    continue
                claims += 1
                per_field_claims[f] += 1
                v = verify(e["value"], e.get("quote") or e["value"], [text])
                grounded[f] = v["status"] != "unverified"
                if v["status"] == "unverified":
                    ungrounded += 1
                    det.write(json.dumps({"id": r["id"], "kind": "ungrounded", "field": f, "value": e["value"], "quote": e.get("quote"), "why": v.get("reason")}) + "\n")

            def cmp(name, gtv, got, ok_fn, fld):
                if not gt_ok(gtv) or not got:
                    return
                if PENDING.search(got) and name in ("ER", "PR", "HER2 (IHC)"):
                    pend[name] = pend.get(name, 0) + 1  # the report says the result is still to come: not a reading to score
                    return
                if name == "HER2 (IHC)" and FISH.search(got) and not re.search(r"[0-3]\s*\+|ihc|score|immuno", got, re.I):
                    fish[0] += 1  # the report gives the in situ hybridisation result, the record the IHC score: different tests
                    return
                c = agree.setdefault(name, [0, 0])
                c[1] += 1
                ok = bool(ok_fn(gtv, got))
                c[0] += ok
                if not ok:
                    g_ = grounded.get(fld, False)
                    dg = dis_grounded.setdefault(name, [0, 0]); dg[1] += 1; dg[0] += g_
                    det.write(json.dumps({"id": r["id"], "kind": "disagree", "field": name, "gt": gtv, "got": got, "quote_verified": g_}) + "\n")
            if r["project"] == "BRCA":
                cmp("ER", g.get("ER_STATUS_BY_IHC"), val("er"), lambda a, b: polarity(b) == a.strip().lower(), "er")
                cmp("PR", g.get("PR_STATUS_BY_IHC"), val("pr"), lambda a, b: polarity(b) == a.strip().lower(), "pr")
                cmp("HER2 (IHC)", g.get("IHC_HER2"), val("her2"), lambda a, b: polarity(b) == a.strip().lower(), "her2")
            cmp("Histology", g.get("HISTOLOGICAL_DIAGNOSIS"), val("histologic_type"), histo_ok, "histologic_type")
            st = val("recorded_stage")
            if t_cat(st):
                stated["pT"] += 1
                cmp("pT", g.get("AJCC_TUMOR_PATHOLOGIC_PT"), st, lambda a, b: t_cat(b) == t_cat(a), "recorded_stage")
            if n_cat(st):
                stated["pN"] += 1
                cmp("pN", g.get("AJCC_NODES_PATHOLOGIC_PN"), st, lambda a, b: n_cat(b) == n_cat(a), "recorded_stage")
            if stage_group(st):
                stated["stage group"] += 1
                cmp("Stage group", g.get("AJCC_PATHOLOGIC_TUMOR_STAGE"), st, lambda a, b: stage_group(b) and stage_group(a) and stage_group(b)[0] == stage_group(a)[0], "recorded_stage")
    out = {
        "reports": len(rows), "by_project": {p: sum(r["project"] == p for r in rows) for p in ("BRCA", "LUAD", "COAD", "READ")},
        "errors": errors, "seconds": round(secs, 1), "claims": claims, "ungrounded": ungrounded,
        "ungrounded_rate_pct": round(100 * ungrounded / max(claims, 1), 3), "ungrounded_upper95_pct": wilson_upper(ungrounded, claims),
        "claims_per_field": per_field_claims, "stated_in_extracted_stage": stated, "report_says_pending": pend, "her2_fish_only": fish[0], "disagreements_with_verified_quote": {k: {"verified": a_, "of": n} for k, (a_, n) in dis_grounded.items()},
        "agreement": {k: {"agree": a_, "n": n, "pct": round(100 * a_ / n, 1), "lower95_pct": round(100 - wilson_upper(n - a_, n), 1)} for k, (a_, n) in agree.items()},
        "model": "extractor role (Qwen3.5-4B, Chinese, non-medical), as shipped", "details_file": str(EXT),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


asyncio.run(main())
