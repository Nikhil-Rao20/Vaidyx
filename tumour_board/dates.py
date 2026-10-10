"""Document dates (V1 item 3.1).

One place that answers "what date does this document carry?" for the gate, search, agents, Q&A, the timeline and the
UI. Two dates per document, both read from the text with their labels (the finder lives below `doc_dates`):

  report date   when the report was signed out (reported on, authorised, verified, signed, date of report, the date on the
                signature line): which version of a report is the newest
  event date    when the clinical event happened (study / scan date, sample collected, procedure, visit, discharge,
                date of completion): the clinical order, "after treatment" checks, the timeline

If only one of the two was found, it stands in for the other and is marked assumed. A document with neither is marked
unconfirmed: the gate asks a clinician to confirm the date (confirm_dates) wherever the date matters, and never guesses
from the DOB, a next-review date or the filename (the filename date is only a suggestion for the dialog).
"""

import json
import re
from datetime import date as _date
from functools import lru_cache

from . import config, docstatus, grounding


def doc_dates(doc) -> dict:
    """The dates of a document as every consumer should see them (the clinician's confirmation, overlaid by
    rules.case_docs(), is already in the classification when it exists).

    report / event: ISO date or "" · report_assumed / event_assumed: the other date stands in · unconfirmed: no date was
    found in the text (nothing stands in) · flags: sanity flags from the finder · sort: key for ordering by (event, report)."""
    c = doc.get("classification") or {}
    report = c.get("report_date_iso") or ""
    event = c.get("event_date_iso") or ""
    return {"report": report or event, "event": event or report,
            "report_assumed": bool(c.get("report_date_assumed")) or (not report and bool(event)),
            "event_assumed": bool(c.get("event_date_assumed")) or (not event and bool(report)),
            # the finder (or a clinician saying "not stated") answers the question explicitly; otherwise no date = unconfirmed
            "unconfirmed": bool(c["date_unconfirmed"]) if c.get("date_unconfirmed") is not None else not (report or event),
            "flags": list(c.get("date_flags") or []),
            "sort": (event or report, report or event)}


# ---- the finder (plan 3.1 b, c, d): dates read from the text with their labels -----------------------------------
_GAP = 20          # at most this many characters between the end of a label and the date it labels
_JOINERS = re.compile(r"^\s*(/|to|till|until|upto|up\s+to|-|–|&|and|,)?\s*$", re.I)
_SEP_ONLY = re.compile(r"^\s*(/|&|and|,)\s*$", re.I)
_CLAUSE = re.compile(r"(?<=\w{4}[.!?])\s+(?=[A-Z])|(?<=;)\s+")  # sentence breaks, not abbreviations ("Reg. date", "Dr. Rao")
_PROSE = re.compile(r"\w{4}[.!?]\s+[A-Z]|\w{3}[.!?]$")  # a line with a sentence end is prose, not a table header
_EDGE = " \t:;,.-–=#*|()[]"


@lru_cache(maxsize=1)
def lexicon():
    """protocols/dates.json with every label regex compiled (loaded once)."""
    d = json.loads((config.PROTOCOL_DIR / "dates.json").read_text())
    return {**d, "labels": [dict(x, _rx=re.compile(x["rx"], re.I)) for x in d["labels"]]}


def _clean(s):
    return " ".join((s or "").split()).strip(_EDGE)


def _label(text, gap=_GAP):
    """The label nearest to the end of text (the words just before a date): (entry, label text) or (None, '')."""
    near = _clean(text)
    if not near:
        return None, ""
    lex = lexicon()["labels"]
    for x in lex:
        if x.get("full") and x["_rx"].fullmatch(near):
            if x["kind"] == "unspecified" and near[:1].islower():  # "... on CT\ndated 10-Nov-2025": prose about another record
                return next(y for y in lex if y["group"] == "another record (dated)"), near
            return x, near
    clause = _clean(_CLAUSE.split(near)[-1])
    best = None
    for x in lex:
        if x.get("full"):
            continue
        for m in x["_rx"].finditer(clause):
            if len(clause) - m.end() <= gap and (best is None or (m.end(), m.end() - m.start()) > (best[1].end(), best[1].end() - best[1].start())):
                best = (x, m)
    if best is None:
        return None, ""
    for x in lex:  # an ignore word anywhere in the clause ("compared with", "next review", "printed on") wins
        if x.get("anywhere") and x is not best[0]:
            m = x["_rx"].search(clause)
            if m and best[0]["kind"] != "ignore":
                return x, _clean(clause[m.start():])
    return best[0], _clean(clause[best[1].start():best[1].end()])


def _header_labels(line):
    """Date-column labels of a header line, in order: [(entry, label text, start)], non-overlapping."""
    found = []
    for x in lexicon()["labels"]:
        if x.get("full") or x.get("header") is False:
            continue
        for m in x["_rx"].finditer(line):
            found.append((m.start(), -(m.end() - m.start()), m.end(), x, _clean(m.group(0))))
    out, end = [], -1
    for s, _, e, x, t in sorted(found, key=lambda f: (f[0], f[1])):
        if s >= end and t:
            out.append((x, t, s)); end = e
    if not out and _clean(line).lower() in ("date", "dated"):
        out = [(next(y for y in lexicon()["labels"] if y["kind"] == "unspecified"), _clean(line), 0)]
    return out


def _numeric_flags(m):
    if not m.group("d4"):
        return False, False
    d, mo = int(m.group("d4")), int(m.group("m4"))
    return (mo > 12 and d <= 12), (d <= 12 and mo <= 12 and d != mo)


def _scan_page(text, page):
    """Every date on one page with its label: list of candidate dicts (internal fields start with '_')."""
    lines = text.split("\n")
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos); pos += len(ln) + 1
    dated_lines = [list(docstatus._DATE_RX.finditer(ln)) for ln in lines]
    signer = [bool(docstatus._SIGNER_LINE.search(ln)) for ln in lines]
    out = []
    for li, line in enumerate(lines):
        ms = dated_lines[li]
        if not ms:
            continue
        prev = li - 1
        while prev >= 0 and not lines[prev].strip() and li - prev <= 2:
            prev -= 1
        header = lines[prev] if prev >= 0 and lines[prev].strip() and not dated_lines[prev] else None
        items, prev_end = [], 0
        for m in ms:
            iso = docstatus.match_iso(m, (1900, 2100))
            seg = line[prev_end:m.start()]
            prev_end = m.end()
            near = next((c for c in reversed(seg.split("|")) if _clean(c)), "")
            entry, text_label = _label(near)
            mf, amb = _numeric_flags(m)
            items.append({"m": m, "iso": iso, "seg": seg, "entry": entry, "label": text_label, "quote": line.strip(),
                          "month_first": mf, "ambiguous": amb, "near": near})
        # dates with no label of their own: the table header above (same column, or same order), or a label ending the line above
        if header is not None and any(it["entry"] is None for it in items):
            if "|" in header and "|" in line:
                hcells = header.split("|")
                for it in items:
                    col = line[:it["m"].start()].count("|")
                    if it["entry"] is None and col < len(hcells):
                        e, t = _label(hcells[col], gap=2)
                        if e is not None and e.get("header") is not False:
                            it.update(entry=e, label=t, quote=text[starts[prev]:starts[li] + len(line)].strip())
            hl = _header_labels(header)
            if all(it["entry"] is None for it in items) and len(hl) == len(items) and not _PROSE.search(header.strip()):
                for it, (e, t, _) in zip(items, hl):
                    it.update(entry=e, label=t, quote=text[starts[prev]:starts[li] + len(line)].strip())
            elif items[0]["entry"] is None and not _clean(items[0]["seg"]) and hl:
                e, t, s = hl[-1]
                tail = header[s:]
                if len(_clean(tail)) <= len(t) + 3:
                    items[0].update(entry=e, label=t, quote=text[starts[prev]:starts[li] + len(line)].strip())
        # ranges and compound labels on one line: "Treatment dates 30-Jun-2026 to 10-Aug-2026", "Admitted / Discharged d1 / d2"
        for i, it in enumerate(items[:-1]):
            nxt = items[i + 1]
            if it["entry"] is None or nxt["entry"] is not None or not _JOINERS.match(nxt["seg"]):
                continue
            if it["entry"].get("range_end"):
                end = next((x for x in lexicon()["labels"] if x["group"] == it["entry"]["range_end"]), None)
                if end is not None:
                    nxt.update(entry=end, label=f'{it["label"]} (end)')
                continue
            clause = _clean(_CLAUSE.split(_clean(it["near"]))[-1])
            run = _header_labels(clause)
            k = 1
            while k < len(run) and _SEP_ONLY.match(clause[run[-k - 1][2] + len(run[-k - 1][1]):run[-k][2]]):
                k += 1
            if k >= 2:
                chain = run[-k:]
                group = [it] + items[i + 1:i + k]
                if len(group) == k and all(g["entry"] is None and _JOINERS.match(g["seg"]) for g in group[1:]):
                    for g, (e, t, _) in zip(group, chain):
                        g.update(entry=e, label=t)
        for it in items:
            e = it["entry"]
            kind = e["kind"] if e else "unlabelled"
            rank = {"report": 1, "unspecified": 3}.get(kind, 0)
            label = it["label"]
            if kind == "unspecified":
                label = "Date (unspecified)"
                if any(signer[j] for j in range(max(0, li - 3), li)):
                    kind, rank, label = "report", 2, "signature line"
                else:
                    kind = "unlabelled"
            elif kind == "unlabelled" and signer[li]:
                kind, rank, label = "report", 2, "signature line"
            if not it["iso"]:
                continue
            if it["iso"] < "1990" and not (e and e["group"] == "date of birth"):
                continue  # years before 1990 are never document dates (births are kept for the DOB check)
            out.append({"iso": it["iso"], "kind": kind, "label": label, "quote": it["quote"], "page": page,
                        "_group": e["group"] if e else "", "_rank": rank, "_month_first": it["month_first"],
                        "_ambiguous": it["ambiguous"], "_pos": (page, starts[li] + it["m"].start())})
    return out


def _today(today):
    if today is None:
        return _date.today()
    if isinstance(today, str):
        return _date.fromisoformat(today[:10])
    return today


def document_dates(texts, filename="", doc_type="", model_date="", dob_iso="", today=None) -> dict:
    """Report and event date of one document, read from its page texts with their labels (never guessed).

    Returns report_date_iso / event_date_iso (+ _assumed when the other date stands in, _quote, _label),
    date_unconfirmed (no date found in the text), date_suggestion (from the filename, a suggestion only),
    date_flags (plain-English sanity flags), dates (every candidate seen, with its kind and quote) and model_date_iso
    (the model's date, only when found in the text and not on an ignore line)."""
    lex = lexicon()
    today = _today(today)
    texts = [t or "" for t in (texts or [])]
    cands = []
    for p, t in enumerate(texts):
        cands.extend(_scan_page(t, p))

    # report date: labelled report date (the latest) > signature-line date > a single bare "Date:" > the model's date
    report = None
    for rank in (1, 2):
        hits = [c for c in cands if c["kind"] == "report" and c["_rank"] == rank]
        if hits:
            report = max(hits, key=lambda c: c["iso"])
            break
    if report is None:
        bare = [c for c in cands if c["label"] == "Date (unspecified)"]
        if bare and len({c["iso"] for c in bare}) == 1:
            report = dict(bare[0], kind="report")

    # the model's date: only when its text is in the document and it is not a DOB / review / compared-with date
    model_iso = ""
    pm = next((m for m in docstatus._DATE_RX.finditer(model_date or "") if docstatus.match_iso(m)), None)
    if pm is not None:
        iso = docstatus.match_iso(pm)
        same = [c for c in cands if c["iso"] == iso]
        found = grounding.locate((model_date or "").strip(), texts) or grounding.locate(pm.group(0), texts)
        if found and same and any(c["kind"] != "ignore" for c in same):
            model_iso = iso
            if report is None:
                usable = [c for c in same if c["kind"] in ("report", "unlabelled")]
                if usable:
                    report = dict(usable[0], kind="report", label="model (found in text)")

    # event date: the doc type's label priority; event_low (received, registration) only for lab / pathology
    events = [c for c in cands if c["kind"] == "event"]
    event = None
    pri = lex["event_priority"].get(doc_type)
    if pri is None:
        event = min(events, key=lambda c: (c["iso"], c["_pos"])) if events else None
    else:
        for g in pri:
            hits = [c for c in events if c["_group"] == g]
            if hits:
                event = hits[0]
                break
    if event is None and doc_type in lex["event_low_doc_types"]:
        for g in lex["event_low_order"]:
            hits = [c for c in cands if c["kind"] == "event_low" and c["_group"] == g]
            if hits:
                event = hits[0]
                break

    out = {"report_date_iso": "", "event_date_iso": "", "report_date_assumed": False, "event_date_assumed": False,
           "report_date_quote": "", "event_date_quote": "", "report_date_label": "", "event_date_label": "",
           "date_unconfirmed": report is None and event is None,
           "date_suggestion": docstatus.parse_date((filename or "").replace("_", " ")),
           "date_flags": [], "model_date_iso": model_iso,
           "dates": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cands]}
    for key, c in (("report", report), ("event", event)):
        if c is not None:
            out.update({f"{key}_date_iso": c["iso"], f"{key}_date_quote": c["quote"], f"{key}_date_label": c["label"]})
    if report is None and event is not None:
        out.update(report_date_iso=event["iso"], report_date_quote=event["quote"], report_date_label=event["label"], report_date_assumed=True)
    if event is None and report is not None:
        out.update(event_date_iso=report["iso"], event_date_quote=report["quote"], event_date_label=report["label"], event_date_assumed=True)

    # sanity flags (plan 3.1 d)
    flags = out["date_flags"]
    found = [(k, c) for k, c in (("report", report), ("event", event)) if c is not None]
    for k, c in found:
        if c["iso"] > today.isoformat():
            flags.append(f"{k} date is after today")
    dob = (dob_iso or "")[:10] if re.match(r"\d{4}-\d{2}-\d{2}", dob_iso or "") else ""
    if not dob:
        dob = next((c["iso"] for c in cands if c["_group"] == "date of birth"), "")
    if dob and any(c["iso"] < dob for _, c in found):
        flags.append("date is before the date of birth")
    if any(c["_month_first"] for c in cands) and any(c.get("_ambiguous") for _, c in found):
        flags.append("day and month may be swapped: the document also has a month-first date")
    return out
