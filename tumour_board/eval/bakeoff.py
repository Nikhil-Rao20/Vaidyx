"""Model bake-off for the Tumour Board pipeline roles, on the synthetic corpus with its answer key.

  reader:    verbatim transcription of scanned report pages (vs reference text)
  extractor: document classification + FINAL/SIGNED status + primary fields with grounded quotes (vs answer key)

Usage: python -m tumour_board.eval.bakeoff --model <key> [--port 8100]   (expects a vLLM server already running)
Writes results to data/tumour_board/eval/bakeoff_<key>.json
"""
import argparse, asyncio, json, os, re, time
from pathlib import Path

from rapidfuzz import fuzz

CORPUS = Path(os.getenv("TB_DEMO_CORPUS", "/data/vaidyx/tb_demo_corpus"))
WATERMARK = {"synthetic", "demo", "only"}


def toks(s):
    return [w for w in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", s.lower()) if len(w) > 1 and w not in WATERMARK]


def nums(s):
    return re.findall(r"\d+(?:\.\d+)?", s)


def reader_metrics(ref, hyp):
    rt, ht = toks(ref), set(toks(hyp))
    recall = sum(1 for w in rt if w in ht) / max(len(rt), 1)
    rn, hn = set(nums(ref)), set(nums(hyp))
    crit = [c for c in ["pending", "draft", "signature pending", "not reported", "awaited", "final"] if c in ref.lower()]
    return {"word_recall": round(recall, 4), "missing_numbers": sorted(rn - hn), "invented_numbers": sorted(hn - rn),
            "critical_missing": [c for c in crit if c not in hyp.lower()]}


def doc_text_ref(case, rel):
    p = CORPUS / ("cases" if (CORPUS / "cases" / case / rel).exists() else "arrivals") / case / rel
    if p.suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() for pg in PdfReader(str(p)).pages)
    if p.suffix == ".txt":
        return p.read_text()
    return (CORPUS / "truth" / "reference_text" / case / (rel + ".txt")).read_text()


def match_value(truth, got):
    from tumour_board.grounding import norm
    t, g = norm(truth), norm(got)
    return t in g or g in t or fuzz.partial_ratio(t, g) >= 85


async def run(key, port):
    from tumour_board import config, docstatus, extract, ingest, protocol
    from tumour_board.grounding import verify
    res = {"model": key, "reader": {}, "extractor": {}}
    vision = os.getenv("BAKEOFF_VISION", "1") == "1"
    # ---- reader ----
    if vision:
        rows = []
        t0 = time.time()
        scans = [(c, rel) for c in ["TB-001", "TB-002", "TB-003"] for rel, tr in json.load(open(CORPUS / "truth" / f"{c}.json"))["documents"].items() if rel.endswith(".png")]
        hyps = await asyncio.gather(*[ingest.ocr_image((CORPUS / "cases" / c / rel).read_bytes()) for c, rel in scans])
        for (c, rel), h in zip(scans, hyps):
            m = reader_metrics(doc_text_ref(c, rel), h); m["doc"] = f"{c}/{rel}"; rows.append(m)
        res["reader"] = {"seconds": round(time.time() - t0, 1), "docs": rows,
                         "mean_word_recall": round(sum(r["word_recall"] for r in rows) / len(rows), 4),
                         "invented_numbers_total": sum(len(r["invented_numbers"]) for r in rows),
                         "missing_numbers_total": sum(len(r["missing_numbers"]) for r in rows),
                         "critical_missing_total": sum(len(r["critical_missing"]) for r in rows)}
    # ---- extractor (guided and validate-and-retry) ----
    for mode in ["guided", "unguided"]:
        mf = config.DATA_ROOT / "models.json"; cfg = json.loads(mf.read_text()); cfg["extractor"]["guided_json"] = mode == "guided"; mf.write_text(json.dumps(cfg))
        stats = {"docs": 0, "doc_type_ok": 0, "status_ok": 0, "facts_expected": 0, "facts_correct": 0, "facts_missed": 0, "facts_wrong": 0,
                 "absent_expected": 0, "fabricated": 0, "model_claims": 0, "claims_unverified": 0, "errors": 0, "details": []}
        t0 = time.time()
        jobs = []
        for c in ["TB-001", "TB-002", "TB-003"]:
            truth = json.load(open(CORPUS / "truth" / f"{c}.json"))
            for rel, tr in list(truth["documents"].items()) + list(truth["arrivals"].items()):
                jobs.append((c, truth["protocol"], rel, tr))

        async def one(c, proto, rel, tr):
            text = doc_text_ref(c, rel)
            try:
                cl = await extract.classify(text)
                fids = protocol.facts_for_doc(proto, tr["doc_type"])  # evaluate fields given the true type
                raw = await extract.extract_facts(text, fids)
            except Exception as e:
                return c, rel, tr, None, None, str(e)
            return c, rel, tr, cl, (fids, raw, text), None

        for c, rel, tr, cl, fx, err in await asyncio.gather(*[one(*j) for j in jobs]):
            stats["docs"] += 1
            if not err and (not isinstance(cl, dict) or "doc_type" not in cl or not isinstance(fx[1], dict)):
                err = f"malformed output: {str(cl)[:160]}"
            if err:
                stats["errors"] += 1; stats["details"].append({"doc": rel, "error": err}); continue
            status, _, _ = docstatus.detect_status(fx[2]); signed, _ = docstatus.detect_signature(fx[2])
            stats["doc_type_ok"] += cl["doc_type"] == tr["doc_type"]
            stats["status_ok"] += status == tr["status"]
            fids, raw, text = fx
            for fid in fids:
                r = raw.get(fid) if isinstance(raw.get(fid), dict) else {}
                if r.get("found") and r.get("value"):
                    stats["model_claims"] += 1
                    if verify(r["value"], r.get("quote") or r["value"], [text])["status"] == "unverified":
                        stats["claims_unverified"] += 1
            for fid, tv in tr["fields"].items():
                if fid not in fids:
                    continue
                r = raw.get(fid) if isinstance(raw.get(fid), dict) else {}
                got = str(r.get("value") or "").strip() if r.get("found") else ""
                ok_ground = got and verify(got, r.get("quote") or got, [text])["status"] != "unverified"
                pend = bool(extract.PENDING_RE.search(got))
                if tv is None:
                    stats["absent_expected"] += 1
                    if got and ok_ground and not pend:
                        stats["fabricated"] += 1; stats["details"].append({"doc": rel, "fact": fid, "fabricated": got})
                else:
                    stats["facts_expected"] += 1
                    if got and match_value(tv, got) and ok_ground:
                        stats["facts_correct"] += 1
                    elif got:
                        stats["facts_wrong"] += 1; stats["details"].append({"doc": rel, "fact": fid, "truth": tv, "got": got, "grounded": bool(ok_ground)})
                    else:
                        stats["facts_missed"] += 1; stats["details"].append({"doc": rel, "fact": fid, "truth": tv, "missed": True})
            if cl["doc_type"] != tr["doc_type"]:
                stats["details"].append({"doc": rel, "doc_type": cl["doc_type"], "truth": tr["doc_type"]})
        stats["seconds"] = round(time.time() - t0, 1)
        stats["field_accuracy"] = round(stats["facts_correct"] / max(stats["facts_expected"], 1), 4)
        res["extractor"][mode] = stats
    out = config.DATA_ROOT / "eval" / f"bakeoff_{key}.json"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    r, e = res.get("reader", {}), res["extractor"]
    print(f"[{key}] reader recall={r.get('mean_word_recall')} invented#={r.get('invented_numbers_total')} missing#={r.get('missing_numbers_total')} critical_missing={r.get('critical_missing_total')} ({r.get('seconds')}s)")
    for mode, s in e.items():
        print(f"[{key}] extractor/{mode}: type {s['doc_type_ok']}/{s['docs']} status {s['status_ok']}/{s['docs']} fields {s['facts_correct']}/{s['facts_expected']} "
              f"wrong {s['facts_wrong']} missed {s['facts_missed']} fabricated {s['fabricated']}/{s['absent_expected']} ungrounded-claims {s['claims_unverified']}/{s['model_claims']} errors {s['errors']} ({s['seconds']}s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--model", required=True); ap.add_argument("--port", type=int, default=8100)
    a = ap.parse_args()
    from tumour_board import config
    config.DATA_ROOT.mkdir(parents=True, exist_ok=True)
    m = {"base_url": f"http://127.0.0.1:{a.port}/v1", "model": "candidate"}
    kw = json.loads(os.getenv("BAKEOFF_CHAT_KWARGS", "null"))
    if kw: m["chat_template_kwargs"] = kw
    (config.DATA_ROOT / "models.json").write_text(json.dumps({"reader": m, "reasoner": m, "extractor": dict(m)}))
    asyncio.run(run(a.model, a.port))
