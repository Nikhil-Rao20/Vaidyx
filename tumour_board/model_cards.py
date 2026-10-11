"""Build model and data cards (data/tumour_board/model_cards.json) from the live configuration and measured results.
Every model and data asset used by the system ships with a published card: source, version, intended use,
provenance, limitations. Run: python -m tumour_board.model_cards"""
import json
from pathlib import Path

from . import config, search

BENCH = Path("/home/bharath.tangella/vaidyx/benchmark/results")
META = {
    "Gemma-4-31B-it": dict(repo="google/gemma-4-31B-it", dir="gemma-4-31B-it", bench="gemma-4-31b-it", dev="Google DeepMind", origin="USA", lic="Apache-2.0",
                           medical=False, tags=["Google (USA)", "Non-medical", "Not medically validated"]),
    "Qwen3.5-4B": dict(repo="Qwen/Qwen3.5-4B", dir="Qwen3.5-4B", bench="qwen3.5-4b", dev="Alibaba Qwen team", origin="China", lic="Apache-2.0",
                       medical=False, tags=["Chinese (Alibaba)", "Non-medical", "Not medically validated"]),
    "MedGemma-27B-it": dict(repo="google/medgemma-27b-it", dir="medgemma-27b-it", bench="medgemma-27b-it", dev="Google", origin="USA", lic="Health AI Developer Foundations terms",
                            medical=True, tags=["Google (USA)", "Medical (domain-tuned)", "Not clinically validated"]),
    "HuatuoGPT-3-27B": dict(repo="FreedomIntelligence/HuatuoGPT-3-27B", dir="HuatuoGPT-3-27B", bench="huatuogpt-3-27b", dev="FreedomIntelligence (CUHK-Shenzhen)", origin="China",
                            lic="Apache-2.0", medical=True, tags=["Chinese", "Medical (domain-tuned)", "Not clinically validated"]),
}


def _revision(d):
    p = Path("/data/vaidyx/models") / d / ".cache" / "huggingface" / "download"
    for m in p.glob("*.metadata") if p.exists() else []:
        first = m.read_text().split("\n")[0].strip()
        if len(first) >= 7:
            return first
    return "local snapshot"


def _bench(key):
    f = BENCH / key / "cot" / "metrics.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())["datasets"]
    return ", ".join(f"{k} {v['accuracy']:.1f}" for k, v in d.items())


def build():
    ev = config.DATA_ROOT / "eval"
    load = lambda n: json.loads((ev / n).read_text()) if (ev / n).exists() else None
    cards = []
    roles = {}
    for role, m in config.models().items():
        roles.setdefault(m.get("label") or m["model"], []).append(role)
    for label, rl in roles.items():
        meta = META.get(label, {})
        f = {"Role in Vaidyx-TB": ", ".join(sorted(set(rl))), "Source": f"https://huggingface.co/{meta.get('repo', '?')}", "Revision": _revision(meta.get("dir", "")),
             "Developer / origin": f"{meta.get('dev', '?')} ({meta.get('origin', '?')})", "Licence": meta.get("lic", "?"),
             "Precision": "bf16, exact published weights (no quantization); served by vLLM on the in-house H200",
             "Decoding": "greedy (temperature 0); reasoner uses prompt-lookup speculative decoding (output identical to plain greedy decoding)",
             "Intended use": "Document transcription, classification and field extraction with verbatim quotes" if "reader" in rl or "extractor" in rl
             else "Case File Q&A, role-specific briefs, Case File summary, adjudication text, scope classification; always grounded and verified",
             "Not intended for": "Diagnosis, image interpretation, staging, treatment recommendation, prognosis, unsupervised clinical use"}
        bk = (meta.get("bench") or "").lower()
        b = load(f"bakeoff_{bk}.json")
        if b:
            r, e = b.get("reader") or {}, b["extractor"]["unguided"]
            if r:
                f["Measured: reading scans (synthetic, 5 pages)"] = f"word recall {r['mean_word_recall']:.3f}, invented numbers {r['invented_numbers_total']}, {r['seconds']} s"
            f["Measured: extraction (synthetic, 31 docs)"] = f"types {e['doc_type_ok']}/{e['docs']}, fields {e['facts_correct']}/{e['facts_expected']}, fabricated {e['fabricated']}"
        q = load(f"qa_{bk}.json")
        if q:
            f["Measured: Ask the Case File (33 probes)"] = f"pass {q['pass']}/{q['n']}, fabrication {q['fabrication']}, mean {q['mean_seconds']} s"
        se = sorted(ev.glob("summary_eval_*.json"), key=lambda x: x.stat().st_mtime)
        if se and "reasoner" in rl:
            d = json.loads(se[-1].read_text())["cases"]
            exp = sum(c["expected_fields"] for c in d.values()); cov = sum(c["in_either"] for c in d.values())
            f["Measured: Case File summary omission check (synthetic, 3 cases)"] = f"{cov}/{exp} answer-key fields present in the verified fields table or a cited summary sentence"
        if "reader" in rl:
            f["Scanned pages"] = "read twice (full resolution and 70% downscale); numbers that differ between reads are flagged and the values containing them go to expert review"
        t = load("tcga_eval.json")
        if t and ("extractor" in rl):
            f["Measured: real TCGA pathology reports (30)"] = f"{t['claims']} extracted values, {t['ungrounded_claims']} ungrounded; agreement {t['agreement']}"
        bm = _bench(bk)
        if bm:
            f["Benchmarks (full test sets, bf16, step-by-step)"] = bm
        f["Limitations"] = ("General model without medical fine-tuning; quality depends on grounding checks. " if not meta.get("medical") else "Domain-tuned, not clinically validated. ") + \
            "Can omit or mis-read information; every value is verified against the source text and unverified values are not shown as facts. Synthetic evaluation is not clinical validation."
        cards.append({"name": label, "kind": "model", "tags": meta.get("tags", []), "fields": f})
    cards.append({"name": "Snowflake arctic-embed-m-long", "kind": "model", "tags": ["Snowflake (USA)", "Non-medical"],
                  "fields": {"Role in Vaidyx-TB": "Semantic search embeddings (Case File and guideline library), CPU", "Source": f"https://huggingface.co/{search.EMBED_MODEL}",
                             "Licence": "Apache-2.0", "Precision": "fp32 ONNX (not the quantized variant)", "Limitations": "General-domain embeddings; combined with BM25 lexical search for exact values"}})
    cards.append({"name": "Protocols (Pre-Authorization rules)", "kind": "data", "tags": ["Configurable", "India-first"],
                  "fields": {"Content": "lung (NSCLC), breast, rectal, oral cavity (head and neck), cervix: required records with NCG tiers, Responsible Department, required primary fields",
                             "Provenance": "Prototype defaults informed by NCG 2019 guideline workup lists (Essential / Optimal), CAP protocols, ESMO; to be confirmed by the hospital Tumour Board",
                             "Location": "tumour_board/protocols/*.json", "Limitations": "Not a national standard: no NCG / ICMR mandatory Tumour Board dataset exists; institution-defined"}})
    cards.append({"name": "Guideline library", "kind": "data", "tags": ["India first", "Reference only"],
                  "fields": {"Content": "NCG India, ICMR, ESMO (+ Pan-Asian adaptations), CAP / ASCO-CAP, ACR, RECIST, NCI PDQ (public domain)",
                             "Provenance": "Freely downloadable documents, plus chapters of a licensed AJCC 8th edition copy; see docs/tumour-board/RESOURCES.md", "Use": "Retrieved passages shown as reference text, never as a recommendation",
                             "Staging reference": "AJCC Cancer Staging Manual 8th ed., chapters for the protocol cancers (licensed copy, internal use only)",
                             "Not included": "NCCN (licence restricts AI use), UICC TNM books, WHO Blue Books, UpToDate"}})
    cards.append({"name": "Synthetic demo Case Files", "kind": "data", "tags": ["Synthetic", "No patient data"],
                  "fields": {"Content": "8 Case Files (lung x2, breast x2, rectal x2, oral cavity, cervix), 62 documents, 16 later arrivals and 8 department intake files incl. scanned pages, phone photos, Word / Excel files, draft / preliminary / amended / cancelled versions, answer key",
                             "Provenance": "Generated by tumour_board/demo_data/make_corpus.py and india_corpus.py (Indian formats, synthetic patients)", "Limitations": "Cleaner than real hospital documents; real-report testing uses TCGA OCR text"}})
    out = config.DATA_ROOT / "model_cards.json"
    out.write_text(json.dumps(cards, indent=1))
    return cards


if __name__ == "__main__":
    for c in build():
        print(c["name"], "|", ", ".join(c["tags"]))
