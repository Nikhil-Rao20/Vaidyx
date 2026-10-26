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
A doctor may instead pick the report whose value the board uses (a `board_uses` confirmation, night-v3 item 1.7): the item stays listed,
carries `picked` and reads as settled; the summary keeps the line "Two reports differ on ...; the board uses ... (picked by Dr X)".
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
SEVERITY = {"conflict": "review", "amended": "review", "non_final_differs": "review", "polarity": "review", "changed": "info", "decision_watch": "review",
            "preliminary": "review"}
LABEL = {"conflict": "Reports disagree", "amended": "Amendment changed a value", "non_final_differs": "A non-final report differs from the final one",
         "polarity": "Reports disagree (positive / negative)", "changed": "Changed between reports", "decision_watch": "A later report changed a value the decision cited",
         "preliminary": "Only a preliminary report since sending", "pick_stale": "Your pick no longer matches the report"}
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
         "value": e.get("value"), "final": bool(e.get("doc_final")), "verification": e.get("verification")}
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


def _pick_of(cur: dict) -> dict | None:
    """The doctor's pick on a fact's current value (rules.resolve_facts), in the shape the items, the slots and the steps show."""
    p = (cur or {}).get("picked")
    if not p:
        return None
    from .slots import display_name  # slots imports this module
    return {"doc_id": p.get("doc_id"), "doc_title": cur.get("doc_title") or p.get("doc_id"), "value": p.get("value"), "by": p.get("by"),
            "by_name": display_name(p.get("by")) or p.get("by") or "", "at": p.get("at"), "confirmation": p.get("confirmation")}


def picked_text(it: dict) -> str:
    """The line the summary keeps for a difference the doctor settled by picking a value: both values stay named."""
    p = it.get("picked") or {}
    a, b = (it.get("citations") or [{}, {}])[:2]
    return (f"Two reports differ on {it.get('label')}: \"{a.get('value')}\" ({a.get('doc_title')}) and \"{b.get('value')}\" ({b.get('doc_title')}); "
            f"the board uses \"{p.get('value')}\" (picked by {p.get('by_name') or p.get('by') or 'a doctor'}).")


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
    for it in out:  # a value picked for the board settles every difference on that field; the items stay listed (night-v3 item 1.7)
        pk = _pick_of((facts.get(it["field"]) or {}).get("current"))
        if pk:  # the text then says which value the board uses ("the newer value counts" / "is the one used" would no longer be true)
            it["picked"] = pk
            it["text_before_pick"] = it["text"]
            it["text"] = picked_text(it)
    out += decision_watch(case_id, st, facts, cat)
    notes = st.get("discordance_notes") or {}
    for it in out:
        if it["key"] in notes:
            it["noted"] = notes[it["key"]]
    out.sort(key=lambda it: (bool(it.get("noted") or it.get("picked")), it["severity"] != "review"))
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
    return {"items": its, "open_review": sum(1 for x in its if x["severity"] == "review" and not x.get("noted") and not x.get("picked")),
            "info": sum(1 for x in its if x["severity"] == "info" and not x.get("noted") and not x.get("picked")), "noted": sum(1 for x in its if x.get("noted")),
            "picked": sum(1 for x in its if x.get("picked")),
            "decision_watch": sum(1 for x in its if x["kind"] == "decision_watch" and not x.get("noted"))}


def points(case_id: str, state: dict = None) -> list:
    """Code-made points for review for the summary and the briefs: the open review discordances, each citing both reports. A difference settled
    by a pick stays, as the line "Two reports differ on ...; the board uses ... (picked by Dr X)" (night-v3 item 1.7)."""
    out = []
    for it in items(case_id, state):
        if it["severity"] != "review" or (it.get("noted") and not it.get("picked")):
            continue
        cites = [{k: c[k] for k in ("doc_id", "quote", "page", "start", "end", "doc_title", "date", "status") if k in c} for c in it["citations"] if c.get("quote")]
        pt = {"text": picked_text(it) if it.get("picked") else it["text"], "citations": cites, "from_rules": True, "kind": it["kind"]}
        if it.get("picked"):
            pt["picked"] = it["picked"]
        out.append(pt)
    return out


def text(case_id: str, state: dict = None) -> str:
    """A prompt block for the agents (the system's own findings; the brief still needs quotes for anything it states)."""
    its = [it for it in items(case_id, state) if not it.get("noted")]
    if not its:
        return ""
    return "DISCORDANCES FOUND BY THE SYSTEM (reports that disagree; a point for review may restate one with its quotes):\n" + "\n".join(
        f"- {picked_text(it) if it.get('picked') else it['text']}" for it in its[:12])


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


# ---- both values while a difference is open (night-v3 item 1.5, design B8) ------------------------------------------------------------
# Until the treating doctor picks a value (item 1.7) or notes the difference, the summary and the slides show the two values side by side,
# each with its own verbatim quote; Vaidyx never picks. The case of a newer report that is only preliminary (or a draft) and disagrees with
# the final one is the kind "non_final_differs" above. After the ready mark two more cases wait on the doctor (after_send_items): a
# time-varying value that a newer final report changed (kind "changed", both values), and a value that only a preliminary report read after
# sending gives (kind "preliminary", one value shown "(preliminary)" with its quote; it clears when the final report lands).
WAITING_LINE = "two reports differ: waiting on the treating doctor's check"
PRELIM_LINE = "only a preliminary report so far: waiting on the treating doctor's check"
STALE_LINE = "no longer matches the report: the pick needs renewing"
OPEN_KINDS = ("conflict", "amended", "non_final_differs", "polarity")  # review differences between reports (decision_watch is after the board)
AFTER_SEND_KINDS = ("changed", "preliminary")  # counted only when a report read after the ready mark brought them


def status_word(c: dict) -> str:
    """How a value's report reads beside it: "final", else its own status in lower case (preliminary, draft), else "not final"."""
    return "final" if c.get("final") else ((c.get("status") or "").strip().lower() or "not final")


def _usable(e: dict) -> bool:
    from . import rules
    return bool(e.get("value")) and e.get("verification") in rules.VERIFIED and e.get("state", "present") == "present" and not e.get("superseded")


def after_send_items(case_id: str, state: dict = None, its: list = None, facts: dict = None) -> list:
    """The differences a report read after the ready mark brought that the review kinds do not cover, in items() shape with `after_send`:
    (a) "changed": a time-varying fact whose newest final report, read after sending, gives another value than the newest final report read
        before sending (the item of items() for that pair, so a note or a pick on it counts);
    (b) "preliminary": a fact whose current value comes from a non-final report read after sending, no final report giving it.
    [] when the Case File is not sent or nothing new was read since."""
    from . import after_send, rules
    case = store.get_case(case_id)
    fresh = set(after_send.new_docs(case_id, case)) if case else set()
    if not fresh:
        return []
    st = state if state is not None else store.get_state(case_id)
    if facts is None:
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    its = items(case_id, st) if its is None else its
    cat = protocol.facts()
    notes = st.get("discordance_notes") or {}
    out = []
    for fid in sorted(TIME_VARYING):  # (a)
        final = [e for e in (facts.get(fid) or {}).get("history") or [] if _usable(e) and e.get("doc_final")]
        before = [e for e in final if e["doc_id"] not in fresh]
        if not final or final[-1]["doc_id"] not in fresh or not before or same(before[-1]["value"], final[-1]["value"], fid):
            continue
        pair = {before[-1]["doc_id"], final[-1]["doc_id"]}
        it = next((x for x in its if x.get("field") == fid and x.get("kind") == "changed" and {c.get("doc_id") for c in x.get("citations") or []} == pair), None)
        if it:  # a review kind for the same pair (same date, polarity) is listed already and counted the old way
            out.append({**it, "after_send": True})
    for fid, f in sorted(facts.items()):  # (b)
        cur = f.get("current") or {}
        if not _usable(cur) or cur.get("doc_final") or cur.get("doc_id") not in fresh or not cur.get("quote"):
            continue
        if any(_usable(e) and e.get("doc_final") for e in f.get("history") or []):
            continue
        label = cat.get(fid, {}).get("label", fid)
        status = (cur.get("doc_status") or "non-final").lower()
        it = {"key": _key("preliminary", fid, cur["doc_id"], cur["doc_id"]), "kind": "preliminary", "kind_label": LABEL["preliminary"], "severity": SEVERITY["preliminary"],
              "field": fid, "label": label, "after_send": True, "citations": [_cite(cur)],
              "text": f"{label}: \"{cur['value']}\" comes only from a {status} report ({cur.get('doc_title')}, {_when(cur)}) read after the Case File was sent; "
                      f"no final report gives it yet."}
        pk = _pick_of(cur)
        if pk:
            it["picked"] = pk
        if it["key"] in notes:
            it["noted"] = notes[it["key"]]
        out.append(it)
    return out


def stale_picks(case_id: str, state: dict = None, facts: dict = None) -> dict:
    """{fact_id: {doc_id, doc_title, value, by, by_name, at, confirmation, key, noted?}} for every pick for the board (item 1.7) that no longer
    matches its report (rules.resolve_facts `pick_stale`: the report was replaced, dismissed or now reads another value). Never dropped silently:
    the slot, the Check step and the summary's difference line say the pick needs renewing until the doctor picks again, undoes it or notes it."""
    from . import rules
    from .slots import display_name  # slots imports this module
    st = state if state is not None else store.get_state(case_id)
    if facts is None:
        facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    notes = st.get("discordance_notes") or {}
    out = {}
    for fid, f in facts.items():
        cur = f.get("current") or {}
        sp = cur.get("stale_pick") if cur.get("pick_stale") else None
        if not isinstance(sp, dict):
            continue
        title = next((e.get("doc_title") for e in f.get("history") or [] if e.get("doc_id") == sp.get("doc_id") and e.get("doc_title")), "")
        if not title and sp.get("doc_id"):
            try:
                d = store.get_doc(case_id, sp["doc_id"]) or {}
                title = (d.get("classification") or {}).get("title") or d.get("filename") or ""
            except Exception:
                title = ""
        key = _key("pick_stale", fid, sp.get("doc_id") or "", sp.get("confirmation") or "")
        out[fid] = {"doc_id": sp.get("doc_id"), "doc_title": title or sp.get("doc_id") or "the report", "value": sp.get("value"), "by": sp.get("by"),
                    "by_name": display_name(sp.get("by")) or sp.get("by") or "", "at": sp.get("at"), "confirmation": sp.get("confirmation"), "key": key}
        if key in notes:
            out[fid]["noted"] = notes[key]
    return out


def stale_why(sp: dict) -> str:
    """The Check row's line for a pick that no longer matches its report."""
    return f"Your pick of {sp.get('value')} from {sp.get('doc_title') or 'the report'} no longer matches the report: pick again"


def stale_text(sp: dict) -> str:
    """The summary's words for a pick that no longer matches its report."""
    return f"the pick of \"{sp.get('value')}\" from {sp.get('doc_title') or 'the report'} by {sp.get('by_name') or 'a doctor'} {STALE_LINE}"


def _values(it: dict) -> list:
    return [{"value": c.get("value"), "doc_id": c.get("doc_id"), "doc_title": c.get("doc_title"), "date": c.get("date"), "final": bool(c.get("final")),
             "status": status_word(c), "quote": c.get("quote") or "", "verification": c.get("verification"),
             **{k: c[k] for k in ("page", "start", "end", "source_method") if k in c}} for c in it.get("citations") or []]


def open_differences(case_id: str, state: dict = None) -> dict:
    """{fact_id: {fact_id, key, kind, label, line, waiting, values, pick_stale?}} for every difference still open: review, not noted, not picked; the
    first per fact, as the Check step lists it (slots). After sending also a value a newer final report changed and a value only a preliminary
    report gives (after_send_items); a pick that no longer matches its report is named in the line (and listed on its own, with the current
    value, when nothing else is open on that fact). `values` is both_values' list."""
    from . import rules
    st = state if state is not None else store.get_state(case_id)
    facts = rules.resolve_facts(rules.case_docs(case_id, st), st.get("overrides"))
    its = items(case_id, st)
    try:
        extra = after_send_items(case_id, st, its, facts)
    except Exception:
        extra = []
    stale = {fid: sp for fid, sp in stale_picks(case_id, st, facts).items() if not sp.get("noted")}
    out = {}
    for it in its + extra:
        kind = it.get("kind")
        if it.get("severity") != "review" and not it.get("after_send"):
            continue
        if (kind not in OPEN_KINDS and not (it.get("after_send") and kind in AFTER_SEND_KINDS)) or it.get("noted") or it.get("picked") or it.get("field") in out:
            continue
        vals = _values(it)
        if len(vals) < (1 if kind == "preliminary" else 2) or not all(v["quote"] for v in vals):
            continue  # a side without its quote is never shown as a value
        waiting = PRELIM_LINE if kind == "preliminary" else WAITING_LINE
        line = f"{it['label']}: " + " and ".join(f"\"{v['value']}\" ({v['doc_title']}, {v['status']})" for v in vals) + f"; {waiting}."
        d = {"fact_id": it["field"], "key": it["key"], "kind": kind, "label": it["label"], "waiting": waiting, "values": vals}
        if it.get("after_send"):
            d["after_send"] = True
        sp = stale.get(it["field"])
        if sp:
            line += f" {stale_text(sp)[0].upper()}{stale_text(sp)[1:]}."
            d["pick_stale"] = sp
        d["line"] = line[0].upper() + line[1:]
        out[it["field"]] = d
    cat = protocol.facts()
    for fid, sp in stale.items():  # a stale pick with nothing else open on the fact: the current value, and the pick needs renewing
        cur = (facts.get(fid) or {}).get("current") or {}
        if fid in out or not _usable(cur) or not cur.get("quote"):
            continue
        label = cat.get(fid, {}).get("label", fid)
        vals = _values({"citations": [_cite(cur)]})
        line = f"{label}: \"{cur['value']}\" ({cur.get('doc_title')}, {vals[0]['status']}); {stale_text(sp)}."
        out[fid] = {"fact_id": fid, "key": sp["key"], "kind": "pick_stale", "label": label, "waiting": STALE_LINE, "values": vals, "pick_stale": sp,
                    "line": line[0].upper() + line[1:]}
    return out


def both_values(case_id: str, fact_id: str, state: dict = None) -> list:
    """The two values of an open difference on one fact, each with its report and quote:
    [{value, doc_id, doc_title, date, final, status, quote, verification, page?, start?, end?}]; one value for a value only a preliminary report
    gives after sending; [] when nothing is open on that fact."""
    return (open_differences(case_id, state).get(fact_id) or {}).get("values") or []


def summary_sentence(diff: dict) -> dict:
    """The summary's line for an open difference: both values with both quotes (the fact line of fill_from_facts gives way to it)."""
    cites = [{k: v[k] for k in ("doc_id", "quote", "page", "start", "end", "doc_title", "date", "source_method") if k in v} for v in diff["values"]]
    for c, v in zip(cites, diff["values"]):
        c["status"] = v["status"]
    return {"text": diff["line"], "citations": cites, "from_fields": True, "differ": True, "fact_id": diff.get("fact_id") or ""}


def slide_rows(fact_id: str, diff: dict, history: int = 0) -> list:
    """The values slide rows for an open difference (meetings.slides): one row per value with its own quote and its own verification, in the
    slide's value shape; the first row names the difference and who it waits on."""
    rows = []
    for i, v in enumerate(diff["values"]):
        rows.append({"id": fact_id if i == 0 else f"{fact_id}#{i + 1}", "fact_id": fact_id,
                     "label": f"{diff['label']}, {diff.get('waiting') or WAITING_LINE}" if i == 0 else diff["label"],
                     "value": f"{v['value']} ({v['status']})", "quote": v["quote"], "doc_id": v["doc_id"], "doc_title": v["doc_title"], "date": v.get("date"),
                     "verification": v.get("verification"), "final": v["final"], "page": v.get("page"), "source_method": v.get("source_method"),
                     "history": history, "differ": diff["line"]})
    return rows
