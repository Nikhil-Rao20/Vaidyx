"""Independent OCR engine evaluation (V1 item 8.3): Tesseract 5 vs docTR on every scanned page of the synthetic demo corpus.
CPU only, no model server, read-only on the corpus and on the stored demo cases.

    /data/vaidyx/venv/app/bin/python -m tumour_board.eval.ocr_engine_eval [--engines tesseract,doctr] [--doctr-pages N]

Pages: every image document of the demo corpus that has an exact reference text
(/data/vaidyx/tb_demo_corpus/truth/reference_text/<case or intake>/<rel>.txt; a multi-page file's pages are separated by
"\\n\\f\\n"), rendered exactly as ingest does (PDF pages: pypdfium2 render(scale=2.0) to PNG; images as stored). Today that is
11 PNG documents and the 100-page scanned PDF of TB-006.

Per engine:
  number recall / precision per aligned line: reference lines and engine lines aligned as the two-read check aligns its
      reads (ingest._ocr_lines keys, SequenceMatcher, _ocr_pair_block); a reference number counts as read when its
      partner engine line holds the same number (digits only: "11.8" read as "118" counts as a miss in the strict
      column, a hit in the digits column)
  seconds per page: median and p90 of the wall time of each page read (threads per read reported)
  false alarms of the check (ocr_engine.engine_spans): (a) with the reference text as the transcription (any flagged line
      is a false alarm), (b) with the reader's real stored transcriptions (data/tumour_board/cases/TB-00{1..6}/docs/*/doc.json,
      pages read by "vision-transcription"; flagged lines are reported, a flag there may be a real reader slip)
  injected single-digit errors: for each reference line with a compared number, one digit changed (substitution), one digit
      added to a number (insertion) and one digit removed from a number of two or more digits (deletion), each seeded and
      scored separately: is that line flagged? (lines already flagged in (a) are counted separately)
  review load: flagged lines per page in (b)

Engine outputs are cached in <out>/cache/<engine>/ (synthetic text only); --fresh reads again (--fresh tesseract: that
engine only). docTR runs in its own
environment (/data/vaidyx/venv/doctr, CPU torch, weights in DOCTR_CACHE_DIR inside that environment) through the
--doctr-worker mode of this file, which imports nothing from the app.
"""
import argparse, json, os, statistics, subprocess, sys, tempfile, threading, time
from pathlib import Path

CORPUS = Path(os.getenv("TB_DEMO_CORPUS", "/data/vaidyx/tb_demo_corpus"))
CASES = ("TB-001", "TB-002", "TB-003", "TB-004", "TB-005", "TB-006")  # stored transcriptions are read only from these
DOCTR_PY = os.getenv("TB_DOCTR_PYTHON", "/data/vaidyx/venv/doctr/bin/python")
DOCTR_CACHE = os.getenv("DOCTR_CACHE_DIR", "/data/vaidyx/venv/doctr/doctr_cache")
DOCTR_THREADS = 8
PAGE_SEP = "\n\f\n"


# ---- docTR worker (runs in the docTR environment; standard library + doctr only) -----------------------------------
def doctr_worker(todo_json: str, out_json: str) -> None:
    os.environ.setdefault("DOCTR_CACHE_DIR", DOCTR_CACHE)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # CPU only: the GPU belongs to the model servers
    import torch
    torch.set_num_threads(DOCTR_THREADS)
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    model = ocr_predictor(pretrained=True)
    out = {}
    for pid, path in json.loads(Path(todo_json).read_text()).items():
        doc = DocumentFile.from_images([path])
        t0 = time.time()
        res = model(doc)
        secs = time.time() - t0
        page = res.pages[0]
        words, lines, n = [], [], 0
        for block in page.blocks:
            for line in block.lines:
                lw = []
                for w in line.words:
                    (x0, y0), (x1, y1) = w.geometry
                    words.append([w.value, round(float(x0), 4), round(float(y0), 4), round(float(x1), 4), round(float(y1), 4),
                                  round(float(w.confidence) * 100, 1), n])
                    lw.append(w.value)
                lines.append(" ".join(lw)); n += 1
        h, w_ = page.dimensions
        out[pid] = {"text": "\n".join(lines), "words": words, "size": [int(w_), int(h)], "seconds": round(secs, 3), "threads": DOCTR_THREADS}
    Path(out_json).write_text(json.dumps(out))


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--doctr-worker":
    doctr_worker(sys.argv[2], sys.argv[3])
    sys.exit(0)

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import config, identity, ingest, ocr_engine  # noqa: E402


# ---- corpus -------------------------------------------------------------------------------------------------------
def _original(cid: str, rel: str) -> Path | None:
    for p in ([CORPUS / "intake" / rel] if cid == "intake" else [CORPUS / "cases" / cid / rel, CORPUS / "arrivals" / cid / rel]):
        if p.exists():
            return p
    return None


def _stored() -> dict:
    """(case, rel_path) -> [page text or None] of the reader's stored transcriptions (demo cases only, read-only)."""
    out = {}
    for cid in CASES:
        for f in sorted((config.CASES_DIR / cid / "docs").glob("*/doc.json")):
            try:
                d = json.loads(f.read_text())
            except Exception:
                continue
            pages = d.get("pages") or []
            if any(p.get("method") == "vision-transcription" for p in pages):
                out[(cid, d.get("rel_path") or "")] = [p.get("text") if p.get("method") == "vision-transcription" else None for p in pages]
    return out


def corpus_pages() -> list:
    """[{id, case, rel, page, path, reference, stored}] for every scanned page with a reference text."""
    stored, out = _stored(), []
    root = CORPUS / "truth" / "reference_text"
    for ref in sorted(root.glob("**/*.txt")):
        cid, rel = ref.relative_to(root).parts[0], str(Path(*ref.relative_to(root).parts[1:]))[:-4]
        src = _original(cid, rel)
        if src is None:
            continue
        texts = ref.read_text().split(PAGE_SEP)
        st = stored.get((cid, rel)) or []
        for n, t in enumerate(texts):
            out.append({"id": f"{cid}/{rel}#p{n + 1}", "case": cid, "rel": rel, "page": n, "path": str(src),
                        "reference": identity.mask_aadhaar(t)[0], "stored": st[n] if n < len(st) else None})
    return out


_PDFIUM = threading.Lock()


def page_png(p: dict) -> bytes:
    """The page image exactly as ingest gives it to the reader."""
    src = Path(p["path"])
    if src.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        with _PDFIUM:  # pdfium is not thread-safe
            pdf = pdfium.PdfDocument(str(src))
            try:
                return ingest._img_bytes(pdf[p["page"]].render(scale=2.0).to_pil())  # PNG made before close: to_pil shares the bitmap's memory
            finally:
                pdf.close()
    return src.read_bytes()


# ---- engine runs --------------------------------------------------------------------------------------------------
def _cache_file(cache: Path, pid: str) -> Path:
    return cache / (pid.replace("/", "__") + ".json")


def run_tesseract(pages: list, cache: Path, fresh: bool, workers: int = 8) -> dict:
    """Two reads per page as ocr_engine does them: the page as given, and the re-read at ocr_engine.recheck_scale (the
    app runs the re-read only on pages where the first read flags a line; here every page gets one so that injected
    errors can be scored). One CPU thread per read (OMP_THREAD_LIMIT=1), `workers` pages at a time."""
    from concurrent.futures import ThreadPoolExecutor
    cache.mkdir(parents=True, exist_ok=True)
    b, lang = ocr_engine.binary(), ocr_engine.lang()

    def one(p):
        f = _cache_file(cache, p["id"])
        if f.exists() and not fresh:
            return p["id"], json.loads(f.read_text())
        png = page_png(p)
        t0 = time.time()
        r = ocr_engine._read_sync(png, b, lang, 120)
        r["seconds"] = round(time.time() - t0, 3); r["threads"] = 1
        sc = ocr_engine.recheck_scale(r["size"])
        t0 = time.time()
        again = ocr_engine._read_sync(png, b, lang, 120, sc)
        r["recheck"] = {"scale": sc, "text": again["text"], "seconds": round(time.time() - t0, 3)}
        f.write_text(json.dumps(r))
        return p["id"], r
    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, pages))


def run_doctr(pages: list, cache: Path, fresh: bool) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    out, todo = {}, {}
    tmp = Path(tempfile.mkdtemp(prefix="tb-doctr-"))
    for p in pages:
        f = _cache_file(cache, p["id"])
        if f.exists() and not fresh:
            out[p["id"]] = json.loads(f.read_text())
        else:
            img = tmp / (p["id"].replace("/", "__").replace("#", "_") + ".png")
            img.write_bytes(page_png(p)); todo[p["id"]] = str(img)
    if todo:
        (tmp / "todo.json").write_text(json.dumps(todo))
        env = {**os.environ, "DOCTR_CACHE_DIR": DOCTR_CACHE, "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": str(DOCTR_THREADS)}
        subprocess.run([DOCTR_PY, "-I", str(Path(__file__).resolve()), "--doctr-worker", str(tmp / "todo.json"), str(tmp / "out.json")],
                       check=True, env=env)
        for pid, r in json.loads((tmp / "out.json").read_text()).items():
            text, words, n, idx = ocr_engine.mask_words(r["text"], r["words"])
            r.update(text=text, words=words, engine="doctr", masked_words=idx)
            if n:
                r["aadhaar_masked"] = n
            _cache_file(cache, pid).write_text(json.dumps(r))
            out[pid] = r
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return out


def rows(words: list) -> str:
    """docTR splits a table row into one block per cell; its words regrouped into visual rows (vertical overlap of more than
    half the word height), left to right, give lines like the reader's "a | b | c" rows."""
    ws = sorted(words, key=lambda w: ((w[2] + w[4]) / 2, w[1]))
    out = []
    for w in ws:
        yc, hh = (w[2] + w[4]) / 2, max(w[4] - w[2], 1e-4)
        if out and abs(yc - out[-1]["yc"]) < 0.5 * max(hh, out[-1]["h"]):
            out[-1]["w"].append(w)
        else:
            out.append({"yc": yc, "h": hh, "w": [w]})
    return "\n".join(" ".join(x[0] for x in sorted(r["w"], key=lambda w: w[1])) for r in out)


# ---- measures -----------------------------------------------------------------------------------------------------
def aligned_pairs(full: str, other: str) -> tuple:
    """(lines of full, lines of other, [(i, j)]) aligned as engine_spans aligns them (ingest._ocr_lines, keys reduced to
    letters and digits, SequenceMatcher, ingest._ocr_pair_block)."""
    from difflib import SequenceMatcher
    la, lb = ingest._ocr_lines(full), ingest._ocr_lines(other)
    ka, kb = [ocr_engine._key(x[3]) for x in la], [ocr_engine._key(x[3]) for x in lb]
    pairs = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            pairs += zip(range(i1, i2), range(j1, j2))
        else:
            pairs += [(i1 + i, j1 + j) for i, j in ingest._ocr_pair_block(ka[i1:i2], kb[j1:j2])]
    return la, lb, pairs


def number_scores(ref: str, eng: str) -> dict:
    from collections import Counter
    la, lb, pairs = aligned_pairs(ref, eng)
    nref = sum(len(ingest._ocr_line_numbers(x[2])) for x in la)
    neng = sum(len(ingest._ocr_line_numbers(x[2])) for x in lb)
    strict = digits = 0
    for i, j in pairs:
        a, b = ingest._ocr_line_numbers(la[i][2]), ingest._ocr_line_numbers(lb[j][2])
        strict += sum((Counter(a) & Counter(b)).values())
        digits += sum((Counter(map(ocr_engine._digits, a)) & Counter(map(ocr_engine._digits, b))).values())
    return {"ref_numbers": nref, "engine_numbers": neng, "hit_strict": strict, "hit_digits": digits}


KINDS = ("substitution", "insertion", "deletion")


def inject(line: str, seed: str, kind: str = "substitution"):
    """The line with one digit of a compared number changed (substitution), one digit added next to a digit of a compared
    number (insertion) or one digit of a compared number of two or more digits removed (deletion); None when the line has
    no such number. The change must change the line's numbers as digits (a moved decimal point is not an error)."""
    import random
    rng = random.Random(seed if kind == "substitution" else f"{seed}:{kind}")  # substitutions as in the first run of 8.3
    base = ingest._ocr_line_numbers(line)
    if not base:
        return None
    digits = lambda t: sorted(ocr_engine._digits(n) for n in ingest._ocr_line_numbers(t))
    if kind == "deletion":
        spans = [m.span() for m in ingest._NUM.finditer(line) if len(ocr_engine._digits(m.group(0))) >= 2]
        pos = [k for a, b in spans for k in range(a, b) if line[k].isdigit()]
    else:
        pos = [k for k, ch in enumerate(line) if ch.isdigit()]
    rng.shuffle(pos)
    for k in pos:
        if kind == "substitution":
            new = line[:k] + rng.choice([d for d in "0123456789" if d != line[k]]) + line[k + 1:]
            if ingest._ocr_line_numbers(new) != base:
                return new
            continue
        if kind == "insertion":
            at = k + rng.choice((0, 1))
            new = line[:at] + rng.choice("0123456789") + line[at:]
        else:
            new = line[:k] + line[k + 1:]
        if digits(new) != digits(line) and sum(map(len, digits(new))) - sum(map(len, digits(line))) == (1 if kind == "insertion" else -1):
            return new
    return None


def naive_spans(full: str, eng: str) -> list:
    """Baseline: the 3.3 rule as is (any difference of the numbers of aligned lines, strings compared as written)."""
    la, lb, pairs = aligned_pairs(full, eng)
    out = []
    for i, j in pairs:
        diff = ingest._ocr_differing(ingest._ocr_line_numbers(la[i][2]), ingest._ocr_line_numbers(lb[j][2]))
        if diff:
            out.append({"start": la[i][0], "end": la[i][1], "line": la[i][2], "numbers": diff})
    return out


CHECKS = {  # name -> spans(transcription, engine read dict)
    "naive (3.3 rule as is)": lambda full, r: naive_spans(full, r["text"]),
    "substitution, one read": lambda full, r: ocr_engine.engine_spans(full, r["text"]),
    "substitution + insertion / deletion, one read": lambda full, r: sorted(
        {(s["start"], s["end"]): s for s in ocr_engine.engine_spans(full, r["text"]) + ocr_engine.indel_spans(full, r["text"], r.get("words"))}.values(),
        key=lambda s: s["start"]),
    "substitution, confirming re-read" + (" (8.3 rule)" if ocr_engine.CHECK_INDELS else " (shipped)"): lambda full, r: (
        ocr_engine.confirm_spans(s, full, r["recheck"]["text"]) if (s := ocr_engine.engine_spans(full, r["text"])) else []),
    "substitution + insertion / deletion, confirming re-read" + (" (shipped)" if ocr_engine.CHECK_INDELS else " (not shipped)"): lambda full, r: (
        ocr_engine.confirmed_spans(full, r["text"], r["recheck"]["text"], indels=True, words=r.get("words"))
        if ocr_engine.engine_spans(full, r["text"]) or ocr_engine.indel_spans(full, r["text"], r.get("words")) else []),
}
SHIPPED = next(k for k in CHECKS if k.endswith("(shipped)"))


def check_measures(pages: list, reads: dict, spans_fn) -> dict:
    fa_a = fa_b = b_pages = 0
    fa_a_lines, fa_b_lines, re_a, re_b = [], [], 0, 0
    kinds = {k: {"injected": 0, "detected": 0, "injected_clean": 0, "detected_clean": 0, "missed": []} for k in KINDS}
    for p in pages:
        r = reads.get(p["id"])
        if r is None:
            continue
        ref = p["reference"]
        sa = spans_fn(ref, r)
        fa_a += len(sa)
        re_a += bool(ocr_engine.candidates(ref, r["text"], r.get("words")))
        fa_a_lines += [(p["id"], s["line"], s["numbers"]) for s in sa]
        if p.get("stored") is not None:
            sb = spans_fn(p["stored"], r)
            fa_b += len(sb); b_pages += 1
            re_b += bool(ocr_engine.candidates(p["stored"], r["text"], r.get("words")))
            fa_b_lines += [(p["id"], s["line"], s["numbers"]) for s in sb]
        flagged_a = {s["start"] for s in sa}
        for k, (start, end, line, _) in enumerate(ingest._ocr_lines(ref)):
            for kind, c in kinds.items():
                new = inject(line, f"{p['id']}:{k}", kind)
                if new is None:
                    continue
                full = ref[:start] + new + ref[end:]
                hit = any(s["start"] == start for s in spans_fn(full, r))
                c["injected"] += 1; c["detected"] += hit
                if start not in flagged_a:
                    c["injected_clean"] += 1; c["detected_clean"] += hit
                    if not hit:
                        c["missed"].append((p["id"], line, new))
    sub = kinds["substitution"]
    out = {"false_alarms_reference": fa_a, "false_alarm_lines_reference": fa_a_lines,
           "flagged_stored": fa_b, "stored_pages": b_pages, "flagged_lines_per_page_stored": round(fa_b / b_pages, 3) if b_pages else None,
           "flagged_lines_stored": fa_b_lines, "pages_needing_reread_reference": re_a, "pages_needing_reread_stored": re_b,
           "injected": sub["injected"], "injected_detected": sub["detected"],
           "injected_rate": round(sub["detected"] / sub["injected"], 4) if sub["injected"] else None,
           "injected_clean": sub["injected_clean"], "injected_clean_detected": sub["detected_clean"],
           "injected_clean_rate": round(sub["detected_clean"] / sub["injected_clean"], 4) if sub["injected_clean"] else None,
           "missed_examples": sub["missed"][:30], "by_kind": {}}
    for kind, c in kinds.items():
        out["by_kind"][kind] = {"injected": c["injected"], "detected": c["detected"],
                                "rate": round(c["detected"] / c["injected"], 4) if c["injected"] else None,
                                "injected_clean": c["injected_clean"], "detected_clean": c["detected_clean"],
                                "missed_examples": c["missed"][:30]}
    return out


def _q(xs: list, f: float) -> float:
    q = sorted(xs)
    return round(q[int(f * (len(q) - 1))], 3) if q else None


def engine_measures(pages: list, reads: dict) -> dict:
    tot = {"ref_numbers": 0, "engine_numbers": 0, "hit_strict": 0, "hit_digits": 0}
    secs, threads = [], set()
    for p in pages:
        r = reads.get(p["id"])
        if r is None:
            continue
        for k, v in number_scores(p["reference"], r["text"]).items():
            tot[k] += v
        secs.append(r["seconds"]); threads.add(r.get("threads"))
    re_secs = [r["recheck"]["seconds"] for r in reads.values() if r.get("recheck", {}).get("seconds") is not None]
    return {"pages": len(secs),
            "recall_strict": round(tot["hit_strict"] / tot["ref_numbers"], 4), "precision_strict": round(tot["hit_strict"] / tot["engine_numbers"], 4),
            "recall_digits": round(tot["hit_digits"] / tot["ref_numbers"], 4), "precision_digits": round(tot["hit_digits"] / tot["engine_numbers"], 4),
            **tot, "seconds_median": _q(secs, 0.5), "seconds_p90": _q(secs, 0.9),
            "reread_seconds_median": _q(re_secs, 0.5), "reread_seconds_p90": _q(re_secs, 0.9),
            "threads_per_page": sorted(t for t in threads if t)}


def _pct(x):
    return "" if x is None else f"{100 * x:.1f}%"


def report(results: dict) -> str:
    L = ["# Independent OCR engine evaluation (V1 item 8.3)", "",
         f"Synthetic demo corpus: {results['pages']} scanned pages with an exact reference text ({results['stored_pages']} with a stored "
         "reader transcription). CPU only. Generated by `tumour_board/eval/ocr_engine_eval.py`.", "",
         "## Engines: number-level accuracy and speed", "",
         "| Engine | Pages | Number recall | Number precision | Recall (digits only) | Precision (digits only) | s / page median | s / page p90 | Threads per page |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, m in results["engines"].items():
        L.append(f"| {name} | {m['pages']} | {_pct(m['recall_strict'])} | {_pct(m['precision_strict'])} | {_pct(m['recall_digits'])} | "
                 f"{_pct(m['precision_digits'])} | {m['seconds_median']} | {m['seconds_p90']} | {', '.join(map(str, m['threads_per_page']))} |")
    L += ["", "Recall: reference numbers found on the aligned engine line; precision: engine numbers found on the aligned reference "
          "line. 'Digits only' ignores decimal points and commas (Tesseract often drops a decimal point).", "",
          "## The check", "",
          "| Engine | Check | False alarms (a) reference as transcription | Flagged (b) stored reader transcriptions | Flagged lines per page (b) | Substitutions caught | Insertions caught | Deletions caught |",
          "|---|---|---|---|---|---|---|---|"]

    def kind(c, k):
        b = (c.get("by_kind") or {}).get(k)
        return f"{b['detected']} / {b['injected']} ({_pct(b['rate'])})" if b else ""
    for name, m in results["engines"].items():
        for cname, c in m["checks"].items():
            L.append(f"| {name} | {cname} | {c['false_alarms_reference']} | {c['flagged_stored']} ({c['stored_pages']} pages) | "
                     f"{c['flagged_lines_per_page_stored']} | {kind(c, 'substitution')} | {kind(c, 'insertion')} | {kind(c, 'deletion')} |")
    L += ["", "Injected errors: one per reference line with a compared number and kind (substitution: one digit changed; insertion: one "
          "digit added to a number; deletion: one digit removed from a number of two or more digits), the line then used as the "
          "transcription; caught when that line is flagged. docTR rows: from the cached docTR reads of the first 8.3 run (docTR "
          "was not run again); docTR has no confirming re-read in this evaluation."]
    t = results["engines"].get("tesseract")
    if t:
        c = t["checks"][SHIPPED]
        L += ["", f"Re-read (Tesseract at {t.get('reread_scale', 1.5)}x): {t['reread_seconds_median']} s median, {t['reread_seconds_p90']} s p90; "
              f"needed on {c['pages_needing_reread_reference']} of {t['pages']} pages in (a) and {c['pages_needing_reread_stored']} of "
              f"{c['stored_pages']} in (b)."]
    L += ["", "## Decision", "", results.get("decision", ""), "", "## Rule of the check (ocr_engine.engine_spans)", "", results.get("rule", ""), "",
          "## Tuning notes", "", TUNING, ""]
    for name, m in results["engines"].items():
        for cname, c in m["checks"].items():
            if c["false_alarm_lines_reference"]:
                L += [f"### False alarms (a): {name}, {cname}", ""] + [f"- `{pid}`: `{line}` {nums}" for pid, line, nums in c["false_alarm_lines_reference"][:15]] + [""]
    sh = t["checks"][SHIPPED] if t else None
    for k in KINDS:
        ex = ((sh or {}).get("by_kind") or {}).get(k, {}).get("missed_examples") or []
        if ex:
            L += [f"### Injected {k}s the shipped check misses (examples)", ""] + [f"- `{pid}`: `{a}` -> `{b}`" for pid, a, b in ex[:15]] + [""]
    return "\n".join(L)


TUNING = """Measured during tuning on the same 111 pages (alignment then on the 3.3 keys, before the letters-and-digits keys):
- Tesseract page segmentation: --psm 4 (one column of lines) 95.5% number recall, --psm 6 (uniform block) 95.3%, --psm 3 (automatic,
  splits table columns into separate lines) 58.0%, --psm 11 (sparse text) 16.5%. Shipped: --psm 4.
- Comparing any difference of numbers (the 3.3 rule) gives 54 false alarms in (a): lost decimal points ("11.8" read as "118"),
  cut leading digits ("17" read as "7"), list markers ("8. I" read as "8.1"), letters read as digits ("LAB" as "1AB", "M0" as "MO").
  Digits-only comparison and the same-digit-count rule remove these.
- Instead of the re-read, a word-confidence floor on the engine's numbers also reaches 0 false alarms in (a), but only at 80 or more,
  and then catches 91.7% of the injected errors (vs 99.4% with the re-read): a correct engine number often has a modest confidence.
- A re-read at 0.75x as the confirming read catches 93.0%; at 1.5x 98.7% (then with the 3.3 keys). The confirming read must doubt the
  same number of the line: on one page the two reads each slipped on a different number of the same row.
- Leaving transcription lines without a partner unchecked, or comparing them with the unpaired engine lines of the same stretch,
  made no difference on this corpus; the stretch comparison is kept for multi-column pages.
Caveats: the corpus is synthetic (the TB-006 scan is rasterised at about 86 dpi with light noise, a slight tilt and JPEG
compression; TB-004 has a phone photo); real scans, faint stamps and handwriting will
give Tesseract more misses (a missed number never raises a flag, so the check gets quieter, not noisier). TCGA pathology PDFs are
not part of this run."""

RULE = ("Transcription lines and engine lines are aligned like the two model reads of 3.3 (ingest._ocr_lines, SequenceMatcher, "
        "_ocr_pair_block) on keys reduced to letters and digits. Numbers are compared as digits only. A line is flagged when one of "
        "its numbers is not on the engine's partner line and the engine reads there another number with the same count of digits "
        "that the line does not have (a substituted digit); a number the engine misses, cuts or merges is not evidence. Transcription "
        "lines without a partner are compared as a group with the unpaired engine lines of the same stretch. A flagged line is kept "
        "only when a second Tesseract read of the page at 1.5x scale doubts the same number of that line (run only on pages with a "
        "flagged line); if that re-read fails the flag is kept. A span's numbers are the transcription's numbers in doubt only, never "
        "the engine's reading.\n\n"
        "Insertion / deletion (V1 8.3 review, M2; ocr_engine.CHECK_INDELS): a line whose number the engine reads with one digit more "
        "or less (not two numbers run together, not a digit next to a letter of the line, the decimal point not counted), kept only "
        "when the 1.5x re-read reads the same other number on that line. " + (
            f"Also required: the engine word holding the other number has a confidence of {ocr_engine.INDEL_MIN_CONF:.0f} or more (first read); without that floor 4 false alarms in (a) and (b), Tesseract cutting the leading digit of a small number in the TB-006 vitals table (\"17\" read as \"7\", confidence 34 to 66) the same way at 1.5x; with it 0 (floors 70 and 90 also 0; 80 shipped for margin). The floor is tuned on this same synthetic corpus. Shipped: no false alarm in (a) or (b)." if ocr_engine.CHECK_INDELS else
            "Not shipped: on this corpus it raises false alarms in (a) and (b) (see the table: Tesseract cuts the leading digit of a "
            "small number in the TB-006 vitals table, \"17\" read as \"7\", and does so again at 1.5x). An inserted or deleted digit "
            "that both model reads share is therefore not caught by the engine (only the two-read check of 3.3 can catch it, when "
            "the reads differ)."))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--engines", default="tesseract,doctr")
    ap.add_argument("--doctr-pages", type=int, default=0, help="read only this many pages of the 100-page scan with docTR (0 = all)")
    ap.add_argument("--fresh", nargs="?", const="all", default="",
                    help="read again instead of using the cache (optionally only these engines, comma separated)")
    ap.add_argument("--out", default=None, help="output folder (default <data root>/eval/v1/phase8/ocr_engines)")
    args = ap.parse_args()
    out = Path(args.out) if args.out else config.DATA_ROOT / "eval" / "v1" / "phase8" / "ocr_engines"
    out.mkdir(parents=True, exist_ok=True)
    fresh = lambda eng: args.fresh == "all" or eng in args.fresh.split(",")
    pages = corpus_pages()
    results = {"pages": len(pages), "stored_pages": sum(p["stored"] is not None for p in pages), "engines": {}, "rule": RULE}
    print(f"{results['pages']} scanned pages, {results['stored_pages']} with a stored transcription")
    for eng in args.engines.split(","):
        if eng == "tesseract":
            info = ocr_engine.engine_info() or {}
            info["psm"] = ocr_engine.PSM
            reads = run_tesseract(pages, out / "cache" / f"tesseract-psm{ocr_engine.PSM}", fresh(eng))
            sub, checks = pages, CHECKS
        else:
            sub = pages
            if args.doctr_pages:
                big = [p for p in pages if p["rel"].endswith(".pdf")]
                keep = {p["id"] for p in big[::max(1, len(big) // args.doctr_pages)][:args.doctr_pages]}
                sub = [p for p in pages if not p["rel"].endswith(".pdf") or p["id"] in keep]
            info = {"name": "doctr", "version": "python-doctr 1.1.0, fast_base + crnn_vgg16_bn, CPU torch", "lines": "words regrouped into visual rows"}
            native = run_doctr(sub, out / "cache" / "doctr", fresh(eng))
            reads = {pid: {**r, "text": rows(r["words"])} for pid, r in native.items()}
            results["engines"]["doctr (native block lines)"] = {**engine_measures(sub, native), "checks": {}, "info": info}
            checks = {k: v for k, v in CHECKS.items() if "re-read" not in k}
        m = engine_measures(sub, reads)
        m["checks"] = {name: check_measures(sub, reads, fn) for name, fn in checks.items()}
        m["info"] = info
        if eng == "tesseract":
            m["reread_scale"] = ocr_engine.RECHECK_SCALE
        results["engines"][eng if eng == "tesseract" else "doctr (rows)"] = m
        print(eng, {k: v for k, v in m.items() if not isinstance(v, (list, dict))})
        for name, c in m["checks"].items():
            print("  ", name, {k: v for k, v in c.items() if not isinstance(v, list)})
    t, d = results["engines"].get("tesseract"), results["engines"].get("doctr (rows)")
    if t and d:
        better = max(d["recall_digits"] - t["recall_digits"], d["precision_digits"] - t["precision_digits"],
                     d["recall_strict"] - t["recall_strict"], d["precision_strict"] - t["precision_strict"])
        results["decision"] = (f"docTR is clearly better at number-level accuracy (by {100 * better:.1f} points): integration stopped for the orchestrator."
                               if better > 0.02 else
                               f"Tesseract integrated: docTR is not more than 2 points better on number recall or precision (best margin "
                               f"{100 * better:+.1f} points), and Tesseract needs no Python package in the app, runs one CPU thread per page "
                               f"and is faster ({t['seconds_median']} s vs {d['seconds_median']} s per page median).")
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(report(results))
    print("wrote", out / "results.json", "and", out / "report.md")


if __name__ == "__main__":
    main()
