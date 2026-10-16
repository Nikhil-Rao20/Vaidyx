"""HIS data into the pipeline (plan item V2-3.3). Pure functions over one document record fetched from the hospital
information system (`doc["his"]`, written by his_case.fetch); no model, no I/O.

Policy (plan 3.3, the invariant in the project rules):
  - Status and signature: the HIS report status and the Provenance signature fill `classification.status` / `signed`. The text
    rules' reading is kept beside them (`text_status`, `text_signed`) and the stricter side wins: a report the HIS calls
    preliminary or cancelled never counts as final because its PDF says FINAL, and a PDF that says "Signature pending" is not
    signed because the HIS holds a signature. `signed: yes` needs a Provenance whose verification status is verified; a final
    report without one, or whose signature failed verification, is `signed: no` with the reason in `status_notes`.
  - Document type: the HIS order code (LOINC through his_client's table) is one more opinion beside the reader model and the V1
    title keywords. Two opinions that agree settle the type; three that differ keep the dispute for a clinician (confirm_doc_type).
  - Values: HIS Observations are candidates. Each is checked against the PDF text: a value the model also read must say the same
    (discord.same); otherwise the printed text must carry it (verbatim, or the same number once Indian commas are dropped). A
    candidate found verbatim that the model missed becomes a verified fact with the located text as its quote. A candidate the
    report text does not carry is a point for review ("HIS value differs from the report text"), never a fact.
"""
import re

from . import discord, grounding, protocol

HIS_STATUS = {"final": "FINAL", "amended": "AMENDED", "corrected": "CORRECTED", "preliminary": "PRELIMINARY", "partial": "PRELIMINARY",
              "registered": "DRAFT", "cancelled": "CANCELLED", "entered-in-error": "CANCELLED"}
NEGATIVE = {"PRELIMINARY", "DRAFT", "CANCELLED"}
FINAL_OK = {"FINAL", "AMENDED", "CORRECTED"}
HIS_CANDIDATE = "his_candidate"  # facts[fid]["source"]: a structured HIS value found verbatim in the report text


def _status_from_his(h: dict) -> str:
    return HIS_STATUS.get(str(h.get("status") or "").lower(), "")


def apply_status(doc: dict) -> dict:
    """Overlay the HIS status and signature on the classification (idempotent: the text rules' reading is kept under text_*)."""
    h = doc.get("his") or {}
    c = doc.get("classification")
    if not h or not isinstance(c, dict):
        return doc
    if "text_status" not in c:
        c["text_status"], c["text_signed"] = c.get("status"), c.get("signed")
        c["text_status_quote"], c["text_signature_quote"] = c.get("status_quote") or "", c.get("signature_quote") or ""
    notes = [n for n in (c.get("status_notes") or []) if not n.startswith("HIS:")]
    his_status = _status_from_his(h)
    text_status = c.get("text_status") or "UNSTATED"
    if his_status:
        status = his_status
        if text_status in NEGATIVE and his_status in FINAL_OK:  # the PDF text contradicts the HIS: the stricter reading stands
            status = text_status
            notes.append(f"HIS: the hospital system calls this report {h.get('status')}, but its text reads {text_status.lower()}: not counted as final until the two agree")
        elif text_status in FINAL_OK and his_status in NEGATIVE:
            notes.append(f"HIS: the hospital system calls this report {h.get('status')} although its text reads {text_status.lower()}: the system's status stands")
        c["status"] = status
        c["status_quote"] = c.get("text_status_quote") if status == text_status else f"[hospital system] report status: {h.get('status')}"  # not a quote from the text: labelled
        c["status_source"] = "his"
    sig = h.get("signature")
    if sig:
        verified = str(sig.get("verification_status") or "").lower() == "verified"
        # the signed hash must be the hash of the file Vaidyx-TB downloaded (the HIS's verdict alone is not trusted)
        sha = doc.get("sha256") or h.get("document_sha256") or ""
        hash_ok = (not sig.get("document_hash")) or (not sha) or str(sig.get("document_hash")).lower() == str(sha).lower()
        text_unsigned = c.get("text_signed") == "no"  # "Signature pending", "unsigned" printed on the report: the stricter side wins
        ok = verified and hash_ok and not text_unsigned
        c["signed"] = "yes" if ok else "no"
        c["signed_source"] = "his"
        c["his_signature"] = {k: sig.get(k) for k in ("signer", "signed_at", "ca", "serial", "verification_status", "document_hash")} | {"hash_matches": hash_ok}
        block = sig.get("block") or ""
        if block and _in_pages(block, doc):
            c["signature_quote"] = block
        else:
            c["signature_quote"] = c.get("text_signature_quote") or block
            if block:
                notes.append("HIS: the signature block recorded by the hospital system was not found in the report text")
        if not verified:
            notes.append(f"HIS: the digital signature failed verification ({sig.get('verification_status') or 'unverified'}): not counted as signed")
        elif not hash_ok:
            notes.append("HIS: the signed document hash does not match the file received from the hospital system: not counted as signed")
        elif text_unsigned:
            notes.append("HIS: the hospital system holds a signature but the report text says it is not signed: not counted as signed until the two agree")
    elif his_status:  # the HIS knows the report and holds no signature for this version
        c["signed"] = "no"
        c["signed_source"] = "his"
        c.pop("his_signature", None)
        if status_counts_final(c):
            notes.append("HIS: no digital signature for this version in the hospital system: a final, signed version is required")
    c["status_notes"] = notes
    return doc


def status_counts_final(c: dict) -> bool:
    return (c.get("status") or "") in FINAL_OK


def _in_pages(text: str, doc: dict) -> bool:
    pages = [p.get("text", "") for p in doc.get("pages") or [] if isinstance(p, dict)]
    return bool(pages) and grounding.locate(text, pages) is not None


def apply_doc_type(doc: dict) -> dict:
    """The HIS order code's document type against the model's and the keyword rule's (see the module docstring)."""
    h = doc.get("his") or {}
    c = doc.get("classification")
    his_type = h.get("doc_type") or ""
    if not h or not isinstance(c, dict) or his_type not in protocol.doc_types():
        return doc
    model_type = c.get("model_doc_type_his") or c.get("doc_type") or ""
    c["model_doc_type_his"] = model_type  # the reader model's type before the HIS opinion (idempotent re-runs)
    kw = c.get("doc_type_keyword") or ""
    c["doc_type_his"] = his_type
    basis = h.get("doc_type_basis") or "the HIS order code"
    if his_type == model_type:
        c["doc_type_check"] = f"the HIS order code ({basis}) and the reader model (Qwen3.5-4B, Chinese, non-medical) agree: {his_type}"
        c.pop("doc_type_disagreement", None)
    elif kw and his_type == kw:
        c["doc_type"] = his_type
        c["doc_type_check"] = f"the HIS order code ({basis}) and the title keywords agree: {his_type}; the reader model (Qwen3.5-4B, Chinese, non-medical) said {model_type or 'nothing'}"
        c.pop("doc_type_disagreement", None)
    elif not model_type or model_type == "other":
        c["doc_type"] = his_type
        c["doc_type_check"] = f"the HIS order code ({basis}) gives {his_type}; the reader model (Qwen3.5-4B, Chinese, non-medical) gave {model_type or 'no type'}"
        c.pop("doc_type_disagreement", None)
    elif kw and kw == model_type:
        c["doc_type_check"] = (f"the reader model (Qwen3.5-4B, Chinese, non-medical) and the title keywords say {model_type}; the HIS order code ({basis}) says "
                               f"{his_type}: the two readings of the document stand")
    else:  # three opinions, or the keywords say nothing: a clinician settles it
        c["doc_type_disagreement"] = {"keyword_type": his_type, "model_type": model_type, "basis": "his",
                                      "note": f"the HIS order code ({basis}) says {his_type}; the reader model (Qwen3.5-4B, Chinese, non-medical) said {model_type}"
                                              + (f"; the title keywords say {kw}" if kw else ""),
                                      "evidence": [{"keyword": h.get("code", {}).get("code") if isinstance(h.get("code"), dict) else "", "quote": h.get("title") or "", "where": "HIS order code"}]}
        c["doc_type_check"] = c["doc_type_disagreement"]["note"]
    return doc


_COMMA_NUM = re.compile(r"(?<=\d),(?=\d{2,3}\b)")
_GENERIC = {"count", "total", "serum", "blood", "level", "value", "result", "test", "report", "the", "and", "of", "in", "status", "score", "index", "labelling"}


def _plain_numbers(s: str) -> set:
    return set(grounding.numbers(_COMMA_NUM.sub("", s or "")))


def _label_tokens(*labels) -> list:
    """The words that identify an Observation on its line, one list per label (its printed label, the fact's catalogue label),
    generic words dropped. A line is the Observation's when it carries every word of one of the lists."""
    out = []
    for lab in labels:
        toks = []
        for t in re.findall(r"[a-z0-9]+", grounding.norm(lab or "")):
            if len(t) >= 2 and t not in _GENERIC and t not in toks:
                toks.append(t)
        if toks:
            out.append(toks)
    return out


def _line_at(text: str, start: int) -> str:
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", start)
    return text[a:b if b >= 0 else len(text)]


def _labelled(line: str, token_sets: list) -> bool:
    n = grounding.norm(line)
    return any(all(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", n) for t in toks) for toks in token_sets)


def _check_value(value: str, texts: list, tokens: list) -> dict:
    """Where a structured value stands against the report text, on a line that carries the Observation's label: verbatim (with its
    location), by number (Indian commas dropped), elsewhere (printed, but not beside its label: never a fact), or absent."""
    nv = grounding.norm(value)
    for pi, text in enumerate(texts):
        for m in re.finditer(r"[^\n]+", text):
            line = m.group(0)
            if not _labelled(line, tokens):
                continue
            loc = grounding.locate(value, [line])
            if loc and loc["score"] >= 100:
                return {"result": "verbatim", "location": {"page": pi, "start": m.start() + loc["start"], "end": m.start() + loc["end"], "score": 100.0, "matched": loc["matched"]}}
            # the same value once Indian commas are dropped ("6,900 /cumm" for 6900 /cumm): the number with its unit, so a reference interval never counts
            if nv and grounding.norm(_COMMA_NUM.sub("", value)) in grounding.norm(_COMMA_NUM.sub("", line)):
                return {"result": "number", "location": None}
    loc = grounding.locate(value, texts)
    if loc and loc["score"] >= 100:
        return {"result": "elsewhere", "location": loc}
    return {"result": "absent", "location": None}


def check_observations(doc: dict) -> dict:
    """Every HIS Observation of the document against the facts the model read and the report text. Writes `doc["his_checks"]`
    (one row per observation that maps to a fact) and `doc["his_flags"]` (the ones the text does not carry), and adds a verified
    fact for a candidate found verbatim that the model missed (never for a disputed one)."""
    h = doc.get("his") or {}
    obs = [o for o in (h.get("observations") or []) if isinstance(o, dict) and o.get("fact")]
    if not obs:
        doc.pop("his_checks", None); doc.pop("his_flags", None)
        return doc
    texts = [p.get("text", "") for p in doc.get("pages") or [] if isinstance(p, dict)]
    facts = doc.setdefault("facts", {})
    cat = protocol.facts()
    checks, flags = [], []
    for o in obs:
        fid, value = o["fact"], str(o.get("value") or "").strip()
        if not value or fid not in cat:
            continue
        label = cat[fid]["label"]
        f = facts.get(fid)
        tokens = _label_tokens(o.get("label") or "", label)
        row = {"fact": fid, "label": label, "his_value": value, "obs_label": o.get("label") or "", "text_value": (f or {}).get("value")}
        if f and f.get("value") and f.get("verification") in ("verified", "confirmed", "needs_review") and f.get("source") != HIS_CANDIDATE:
            # the reader found the value in the text: the two must say the same; a different reading is flagged whatever else the page prints
            row["result"] = "agrees" if discord.same(value, f["value"], fid) else "differs"
            if row["result"] == "differs":
                row["text"] = f"HIS value differs from the report text: {label.lower()} {value} vs {f['value']}"
        else:
            chk = _check_value(value, texts, tokens)
            if chk["result"] == "verbatim":
                row["result"] = "found"
                if not f:  # a candidate the reader missed, printed verbatim beside its own label: a fact with that line as its quote
                    loc = chk["location"]
                    facts[fid] = {"value": value, "quote": loc["matched"], "model_quote": "", "verification": "verified", "reason": None, "location": loc,
                                  "state": "present", "polarity": "affirmed", "source": HIS_CANDIDATE}
                    row["added"] = True
            elif chk["result"] == "number":
                row["result"] = "found"
            elif chk["result"] == "elsewhere":
                row["result"] = "elsewhere"
                row["text"] = f"HIS value for {label.lower()} ({value}) is printed in the report but not beside its label; the reader did not read it: check the report"
            else:
                row["result"] = "differs"
                row["text"] = f"HIS value not found in the report text: {label.lower()} {value}" + (f" (the report reads {f['value']})" if f and f.get("value") else "")
        checks.append(row)
        if row.get("text"):
            flags.append({"fact": fid, "label": label, "his_value": value, "text_value": row.get("text_value"), "text": row["text"]})
    doc["his_checks"] = checks
    if flags:
        doc["his_flags"] = flags
    else:
        doc.pop("his_flags", None)
    return doc


def apply(doc: dict) -> dict:
    """Status, signature and document type after classification (before extraction)."""
    return apply_doc_type(apply_status(doc))
