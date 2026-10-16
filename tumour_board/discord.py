"""Discordances between reports, and the watch over values a recorded decision cited (12 Oct). Plain code, no model.

Before and during the board: the same primary field verified in two signed reports with different values is listed with both
quotes, so the board sees the disagreement instead of one value chosen silently. The system never says which value is right.
  - a STABLE field (histologic type, grade, a biomarker result, margins ...) that differs between two final reports: review;
  - a TIME_VARYING field (lesion size, stage as recorded, ECOG, a lab value ...) that differs between reports of different dates:
    information (the newest counts; the earlier value stays in the history); on the same date: review;
  - an AMENDED or CORRECTED report whose value differs from the earlier version of the same report: review ("the amendment changed ...");
  - a draft or preliminary report that disagrees with the final one the gate uses: review (the final stands; the draft may be newer);
  - a polarity flip (positive in one report, negative in another) is always review.
After the board: every value the recorded decision cited (the adjudication's value checks) is compared with the current verified
value; when a later final report records a different value, the record carries a "decision watch" flag and the coordinators are told
once ("the decision of 24 Sep cited PD-L1 60 % from report D1; the amended report D2 of 28 Sep records 6 %").

A person marks a discordance as noted (a `note_discordance` confirmation: audited, undoable); noted items stay listed, greyed.
Narrative fields (presenting complaint, comorbidities, imaging findings in prose) are not compared: prose differs without conflicting.
"""
import re

from . import grounding, protocol, store, units

STABLE = {"histologic_type", "grade", "lvi", "pni", "margins", "ene", "pdl1", "egfr", "alk", "ros1", "met", "kras", "er", "pr", "her2", "ki67",
          "mmr", "ras_braf", "hiv_status", "menopausal_status", "diagnosis_date_mode"}
TIME_VARYING = {"lesion_size", "suv_max", "recorded_stage", "figo_stage", "ecog", "mrf_status", "emvi", "distance_from_anal_verge", "depth_of_invasion",
                "parametrial_involvement", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "cea", "treatment_completion_date", "smoking_history"}
CODE_FIELDS = {"recorded_stage", "figo_stage"}  # stage strings are codes (T3b is not T3c): equal or prefix only, no numeric leniency
AMENDED = {"AMENDED", "CORRECTED"}
SEVERITY = {"conflict": "review", "amended": "review", "non_final_differs": "review", "polarity": "review", "changed": "info", "decision_watch": "review"}
LABEL = {"conflict": "Reports disagree", "amended": "Amendment changed a value", "non_final_differs": "A non-final report differs from the final one",
         "polarity": "Reports disagree (positive / negative)", "changed": "Changed between reports", "decision_watch": "A later report changed a value the decision cited"}
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")


def _polarity(s):
    from .postboard import _polarity as pol
    return pol(s)


def _nums(s):
    out = set()
    for x in grounding.numbers(s or ""):
        try:
            out.add(float(x.replace(",", "")))
        except ValueError:
            continue
    return out


def same(a: str, b: str, field: str = None) -> bool:
    """Whether two verified values say the same thing: equal after normalising; a longer wording that starts with the shorter value
    ("Adenocarcinoma, acinar predominant" and "Adenocarcinoma"), but not a value found later inside the other ("favour adenocarcinoma"
    is not "Adenocarcinoma"); a labelled number whose tokens all appear in the other ("TPS 60%" in "PD-L1 TPS 60 %"); the same quantity in
    other units (2.45 lakhs/cumm = 245 x10^3/uL). A polarity flip is never the same; a stage code is compared as written."""
    na, nb = grounding.norm(a or "").strip(" .;:"), grounding.norm(b or "").strip(" .;:")
    if not na or not nb:
        return na == nb
    pa, pb = _polarity(a), _polarity(b)
    if pa and pb and pa != pb:
        return False
    if na == nb or nb.startswith(na) or na.startswith(nb):
        return True
    if field in CODE_FIELDS:
        return False
    ta, tb = _TOKEN.findall(na), _TOKEN.findall(nb)
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if any(t[0].isdigit() for t in short) and set(short) <= set(long_):
        return True
    xa, xb = _nums(a), _nums(b)
    return bool(xa and xb) and units.numbers_equivalent(a, b) and units.numbers_equivalent(b, a)


def _cite(e: dict) -> dict:
    loc = e.get("location") or {}
    c = {"doc_id": e["doc_id"], "doc_title": e.get("doc_title") or e["doc_id"], "date": e.get("date"), "status": e.get("doc_status"), "quote": e.get("quote") or "",
         "value": e.get("value"), "final": bool(e.get("doc_final"))}
    if loc:
        c.update(page=loc.get("page"), start=loc.get("start"), end=loc.get("end"))
    if e.get("source_method"):
        c["source_method"] = e["source_method"]
    if e.get("confirmed_by"):
        c["confirmed_by"] = e["confirmed_by"]
    return c


def _key(kind, fid, a, b):
    return f"{kind}:{fid}:{a}:{b}"


def _item(kind, fid, label, a, b, text):
    return {"key": _key(kind, fid, a["doc_id"], b["doc_id"]), "kind": kind, "kind_label": LABEL[kind], "severity": SEVERITY[kind], "field": fid, "label": label,
            "text": text, "citations": [_cite(a), _cite(b)]}


def _when(e):
    return e.get("date") or "date not stated"


def items(case_id: str, state: dict = None) -> list:
    """Every discordance of the Case File (review first, then information, noted last); noted ones carry `noted` (who, when)."""
    from . import rules
    st = state if state is not None else store.get_state(case_id)
    docs = rules.case_docs(case_id, st)
    facts = rules.resolve_facts(docs, st.get("overrides"))
    cat = protocol.facts()
    out = []
    for fid in sorted(STABLE | TIME_VARYING):
        hist = [e for e in (facts.get(fid) or {}).get("history") or [] if e.get("verification") in rules.VERIFIED and e.get("state", "present") == "present" and e.get("value")]
        if len(hist) < 2:
            continue
        label = cat.get(fid, {}).get("label", fid)
        final = [e for e in hist if e.get("doc_final")]
        cur = final[-1] if final else None
        # 1. amendments: a corrected or amended report against the earlier version of the same report type
        for e in final:
            if (e.get("doc_status") or "").upper() in AMENDED:
                earlier = [x for x in hist if x["doc_id"] != e["doc_id"] and x.get("doc_type") == e.get("doc_type") and (x.get("date") or "") <= (e.get("date") or "")]
                for x in earlier[-1:]:
                    if not same(x["value"], e["value"], fid):
                        out.append(_item("amended", fid, label, x, e, f"{label}: the {e.get('doc_status', '').lower()} report ({e.get('doc_title')}, {_when(e)}) records "
                                                                     f"\"{e['value']}\"; the earlier report ({x.get('doc_title')}, {_when(x)}) recorded \"{x['value']}\"."))
        # 2. final reports that disagree
        seen = set()
        for i, a in enumerate(final):
            for b in final[i + 1:]:
                if a["doc_id"] == b["doc_id"] or same(a["value"], b["value"], fid):
                    continue
                if (b.get("doc_status") or "").upper() in AMENDED and a.get("doc_type") == b.get("doc_type"):
                    continue  # listed as an amendment above
                pair = (a["doc_id"], b["doc_id"])
                if pair in seen:
                    continue
                seen.add(pair)
                pa, pb = _polarity(a["value"]), _polarity(b["value"])
                if pa and pb and pa != pb:
                    kind = "polarity"
                elif fid in STABLE or (a.get("date") and a.get("date") == b.get("date")):
                    kind = "conflict"
                else:
                    kind = "changed"
                out.append(_item(kind, fid, label, a, b, f"{label}: \"{a['value']}\" ({a.get('doc_title')}, {_when(a)}) and \"{b['value']}\" ({b.get('doc_title')}, {_when(b)})"
                                                        + ("; the newer value counts, the earlier one stays in the history." if kind == "changed" else ".")))
        # 3. a non-final report that disagrees with the final value the gate uses
        for e in hist:
            if e.get("doc_final") or not cur or same(e["value"], cur["value"], fid):
                continue
            out.append(_item("non_final_differs", fid, label, cur, e, f"{label}: the {(e.get('doc_status') or 'non-final').lower()} report ({e.get('doc_title')}, {_when(e)}) "
                                                                    f"records \"{e['value']}\"; the final report ({cur.get('doc_title')}, {_when(cur)}) records \"{cur['value']}\" and is the one used."))
    out += decision_watch(case_id, st, facts, cat)
    notes = st.get("discordance_notes") or {}
    for it in out:
        if it["key"] in notes:
            it["noted"] = notes[it["key"]]
    out.sort(key=lambda it: (bool(it.get("noted")), it["severity"] != "review"))
    return out


def decision_watch(case_id: str, st: dict = None, facts: dict = None, cat: dict = None) -> list:
    """Values a recorded decision cited whose current verified value, from a later final report, differs."""
    from . import rules
    st = st if st is not None else store.get_state(case_id)
    if facts is None:
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    cat = cat or protocol.facts()
    out = []
    for rec in st.get("board_records") or []:
        when = (rec.get("board_date") or rec.get("recorded_at") or "")[:10]
        for vc in (rec.get("adjudication") or {}).get("value_checks") or []:
            src = vc.get("source") or {}
            fid = vc.get("fact")
            if not src.get("doc_id") or not fid:
                continue
            cur = (facts.get(fid) or {}).get("current")
            if not cur or cur.get("verification") not in rules.VERIFIED or not cur.get("doc_final") or cur.get("state", "present") != "present":
                continue
            if cur["doc_id"] == src["doc_id"] or same(cur["value"], src.get("value") or "", fid):
                continue
            src_e = next((e for e in (facts.get(fid) or {}).get("history") or [] if e["doc_id"] == src["doc_id"]), None)
            if src_e and (cur.get("date") or "") < (src_e.get("date") or ""):
                continue  # the differing value is older than the one the decision cited: not a later change
            a = src_e or {"doc_id": src["doc_id"], "doc_title": src.get("doc_title") or src["doc_id"], "value": src.get("value"), "quote": src.get("quote"), "date": None, "doc_final": True}
            label = cat.get(fid, {}).get("label", fid)
            it = _item("decision_watch", fid, label, a, cur, f"The Tumour Board record of {when} cited {label} \"{vc.get('value_as_written') or src.get('value')}\" from {a.get('doc_title')}; "
                                                              f"a later final report ({cur.get('doc_title')}, {_when(cur)}) records \"{cur['value']}\".")
            it["record"] = rec.get("id"); it["record_date"] = when
            out.append(it)
    return out


def summary(case_id: str, state: dict = None) -> dict:
    its = items(case_id, state)
    return {"items": its, "open_review": sum(1 for x in its if x["severity"] == "review" and not x.get("noted")),
            "info": sum(1 for x in its if x["severity"] == "info" and not x.get("noted")), "noted": sum(1 for x in its if x.get("noted")),
            "decision_watch": sum(1 for x in its if x["kind"] == "decision_watch" and not x.get("noted"))}


def points(case_id: str, state: dict = None) -> list:
    """Code-made points for review for the summary and the briefs: the open review discordances, each citing both reports."""
    out = []
    for it in items(case_id, state):
        if it["severity"] != "review" or it.get("noted"):
            continue
        cites = [{k: c[k] for k in ("doc_id", "quote", "page", "start", "end", "doc_title", "date", "status") if k in c} for c in it["citations"] if c.get("quote")]
        out.append({"text": it["text"], "citations": cites, "from_rules": True, "kind": it["kind"]})
    return out


def text(case_id: str, state: dict = None) -> str:
    """A prompt block for the agents (the system's own findings; the brief still needs quotes for anything it states)."""
    its = [it for it in items(case_id, state) if not it.get("noted")]
    if not its:
        return ""
    return "DISCORDANCES FOUND BY THE SYSTEM (reports that disagree; a point for review may restate one with its quotes):\n" + "\n".join(f"- {it['text']}" for it in its[:12])


NOTIFY_KIND = "decision_value_changed"


def notify_decision_watch(case_id: str) -> int:
    """Tell the coordinators once per decision-watch item (kept in state.discord_notified); returns how many were sent."""
    from . import notify
    state = store.get_state(case_id)
    done = set(state.get("discord_notified") or [])
    sent = 0
    case = store.get_case(case_id)
    patient = (case.get("patient") or {}).get("name") or case_id
    for it in decision_watch(case_id, state):
        if it["key"] in done:
            continue
        try:
            notify.notify({"role": "coordinator"}, NOTIFY_KIND, case_id, f"A later report changed a value the Tumour Board record cited: {patient} ({case_id})", it["text"], record=it.get("record"))
        except Exception:
            continue
        done.add(it["key"]); sent += 1
    if sent:
        state["discord_notified"] = sorted(done)
        store.save_state(case_id, state)
        store.audit(case_id, {"kind": "decision_watch_notified", "items": sent})
    return sent
