"""Agenda readiness, the chase list and the hospital's Tumour Board quality dashboard (12 Oct). Plain code over the Case Files,
the board sessions and the audit logs; no model, no clinical judgement. Every number is a count of what the records and the
system's own events show, with the standard it is measured against named beside it.

Standards used for the reference lines (RESEARCH.md round 3): NHS England, Streamlining MDT meetings 2020 (quorate on 95 % of
meetings; minimum core data; clinical trials considered); Victorian cancer MDM quality framework 2018 (core specialties attend
90 % of meetings; minimum dataset and recorded recommendations at 80 % of the last 20 patients; recommendations recorded within
24 hours and communicated within a week); Manual for Cancer Services 2013 (key worker recorded); PM-JAY HBP 2.2 s 3.9 (surgical,
radiation and medical oncologist on the board); Abuelgasim and Jazieh 2024 (time per case, attendance per specialty); HBCR 2025
(intention to treat recorded); Konzmann 2026 (no published study quantified time to MDT: measured here).
"""
import csv, io, statistics
from datetime import date, datetime, timedelta

from . import board, config, discord, org, postboard, rules, store

REFERENCES = [
    {"metric": "quorum", "label": "Board quorate (surgical, radiation and medical oncologist present)", "target": 95, "unit": "%", "source": "NHS England 2020 (95 % of meetings quorate); PM-JAY HBP 2.2 s 3.9 (composition)"},
    {"metric": "attendance", "label": "Core specialty attendance", "target": 90, "unit": "%", "source": "Victorian MDM framework 2018, 3.3"},
    {"metric": "ready_before_board", "label": "Case Files ready (Pre-Authorization met) before the board date", "target": 80, "unit": "%", "source": "Victorian MDM framework 2018, 4.4 (minimum dataset completeness 80 %)"},
    {"metric": "decision_recorded_same_day", "label": "Decision recorded on the board day", "target": 80, "unit": "%", "source": "Victorian MDM framework 2018, 8.4 (within 24 hours) and 4.4 (recorded recommendations 80 %)"},
    {"metric": "patient_informed_7d", "label": "Patient informed within 7 days of the board", "target": 80, "unit": "%", "source": "Victorian MDM framework 2018, 8.4 / 8.5 (within one week)"},
    {"metric": "trial_considered", "label": "Clinical trial availability recorded as considered", "target": 80, "unit": "%", "source": "NHS England 2020 (minimum core data); Victorian 8.3"},
    {"metric": "key_worker", "label": "Key worker recorded", "target": 80, "unit": "%", "source": "Manual for Cancer Services 2013, 13-2N-113"},
    {"metric": "intent_recorded", "label": "Intention to treat recorded by the board", "target": 80, "unit": "%", "source": "HBCR procedure manual 2025 (mandatory item)"},
]
PMJAY = postboard.PMJAY_BOARD


def _today() -> date:
    return date.fromisoformat(store.now_iso()[:10])


def _d(s):
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def _dt(s):
    try:
        return datetime.fromisoformat(str(s or "")[:19])
    except ValueError:
        return None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _pct(n, d):
    return round(100.0 * n / d) if d else None


# ---- agenda readiness and the chase list -----------------------------------------------------------------------------------

def bd_soon(board_day, today, days: int = 3) -> bool:
    """A board within `days`: a suggested request nobody sent is then a risk, not a routine."""
    return bool(board_day) and (board_day - today).days <= days


def _case_readiness(c: dict, st: dict, today: date, board_day) -> dict:
    gate = st.get("gate") or {}
    acts = [a for a in st.get("actions") or [] if a.get("status") != "completed"]
    pre = [a for a in acts if a.get("source") == "pre_authorization"]
    unsent = [a for a in pre if a.get("status") == "suggested"]  # suggested by the gate, not sent by the doctor yet (V2 item 4.2)
    overdue = [a for a in acts if _d(a.get("due")) and _d(a["due"]) < today]
    after_board = [a for a in pre if board_day and _d(a.get("due")) and _d(a["due"]) > board_day]
    arts = st.get("artefacts") or {}
    sig = rules.case_signature(c["case_id"], st)
    summ = arts.get("summary")
    stale = bool(summ and summ.get("signature") and rules.stale_reason(summ["signature"], sig))
    briefs = {k[6:]: (rules.stale_reason(v["signature"], sig) if v.get("signature") else "unknown") for k, v in arts.items() if k.startswith("brief_") and isinstance(v, dict)}
    disc = discord.summary(c["case_id"], st) if c.get("protocol") else {"open_review": 0, "decision_watch": 0}
    if not c.get("protocol"):
        forecast, why = "not_listed", "awaiting listing: no cancer protocol yet"
    elif gate.get("passed"):
        forecast, why = "ready", "every required record met"
    elif gate.get("blockers"):
        forecast, why = "blocked", f"{len(gate['blockers'])} document(s) failed to read: re-process or dismiss"
    elif after_board:
        forecast, why = "at_risk", f"{len(after_board)} request(s) due after the board date"
    elif overdue:
        forecast, why = "at_risk", f"{len(overdue)} request(s) overdue"
    elif unsent:
        forecast, why = "at_risk" if bd_soon(board_day, today) else "on_track", f"{len(unsent)} suggested request(s) not sent yet" + (f", {len(pre) - len(unsent)} sent" if len(pre) > len(unsent) else "")
    elif pre:
        forecast, why = "on_track", f"{len(pre)} request(s) open, all due before the board"
    else:
        forecast, why = "on_track", "re-check pending"
    return {"case_id": c["case_id"], "patient": (c.get("patient") or {}).get("name") or c["case_id"], "protocol": c.get("protocol"), "board_date": c.get("board_date"),
            "owner": c.get("department") or None, "owner_name": org.department_name(c["department"]) if c.get("department") else "",  # the owning treating department (V2 item 5.1)
            "ready": c.get("board_ready") or None,  # marked ready for the board by the owner (V2 item 6.1)
            "reminders": len(c.get("reminders") or []),
            "readiness": gate.get("readiness"), "passed": bool(gate.get("passed")), "satisfied": gate.get("satisfied"), "total": gate.get("total"),
            "level1_open": (gate.get("levels") or {}).get("1", {}).get("open", 0), "level2_open": (gate.get("levels") or {}).get("2", {}).get("open", 0),
            "open_requests": len(pre), "unsent_requests": len(unsent), "overdue": len(overdue), "due_after_board": len(after_board), "blockers": len(gate.get("blockers") or []),
            "summary": "none" if not summ else ("stale" if stale else "ready"), "briefs": briefs,
            "discordances_open": disc.get("open_review", 0), "decision_watch": disc.get("decision_watch", 0),
            "forecast": forecast, "why": why,
            "gaps": [{"label": r["label"], "department": r["department"], "status": r["status"], "level": r.get("level")} for r in gate.get("requirements") or [] if r["status"] not in ("satisfied", "not_applicable", "waived")]}


def agenda(board_date: str) -> dict:
    """Readiness of every Case File listed for a board date, and the chase list: what to ask which department before the board."""
    today = _today()
    bd = _d(board_date)
    cases = [c for c in store.list_cases() if (c.get("board_date") or "")[:10] == (board_date or "")[:10] and c.get("case_id") not in config.PROTECTED_CASES]
    rows, chase = [], {}
    for c in cases:
        st = store.get_state(c["case_id"])
        rows.append(_case_readiness(c, st, today, bd))
        for a in st.get("actions") or []:
            if a.get("status") == "completed":
                continue
            due = _d(a.get("due"))
            dept = a.get("department") or org.COORDINATOR_NAME
            chase.setdefault(dept, []).append({"case_id": c["case_id"], "action_id": a.get("id"), "patient": rows[-1]["patient"], "label": a.get("label"), "what": a.get("what"), "due": a.get("due"),
                                               "reminders": len(a.get("reminders") or []),  # reminders sent so far (V2 item 6.1)
                                               "days_left": (due - today).days if due else None, "overdue": bool(due and due < today), "after_board": bool(due and bd and due > bd),
                                               "source": a.get("source"), "level": a.get("level_label"),
                                               "unsent": a.get("status") == "suggested", "sent_by": (a.get("sent") or {}).get("by") if isinstance(a.get("sent"), dict) else None})
    for v in chase.values():
        v.sort(key=lambda x: (x["due"] or "9999", x["case_id"]))
    order = {"blocked": 0, "at_risk": 1, "on_track": 2, "not_listed": 3, "ready": 4}
    rows.sort(key=lambda r: (order.get(r["forecast"], 9), r["case_id"]))
    counts = {k: sum(1 for r in rows if r["forecast"] == k) for k in ("ready", "on_track", "at_risk", "blocked", "not_listed")}
    return {"board_date": board_date, "days_to_board": (bd - today).days if bd else None, "cases": rows, "counts": counts,
            "chase": [{"department": d, "items": v, "overdue": sum(x["overdue"] for x in v)} for d, v in sorted(chase.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
            "requests_open": sum(len(v) for v in chase.values()), "requests_overdue": sum(x["overdue"] for v in chase.values() for x in v),
            "requests_unsent": sum(1 for v in chase.values() for x in v if x["unsent"])}


# ---- the hospital's quality dashboard -----------------------------------------------------------------------------------

def _first_ready(case_id: str):
    """When the Pre-Authorization first passed, from the audit log (ingestion / re-check events carry the result)."""
    for e in store.read_audit(case_id, limit=5000):
        if e.get("kind") in ("ingestion_finished", "recheck") and (e.get("gate_passed") is True or e.get("passed") is True):
            return _dt(e.get("ts"))
    return None


def dashboard(start: str = None, end: str = None) -> dict:
    """Counts and medians across Case Files created (or listed for a board) in the window, closed board sessions, decisions and
    follow-ups; each KPI beside its reference line. Returns a dict the UI shows as tiles and tables; `csv()` flattens it."""
    today = _today()
    s, e = _d(start), _d(end)

    def in_window(d):
        d = _d(d)
        return bool(d) and (not s or d >= s) and (not e or d <= e)
    cases = [c for c in store.list_cases() if c.get("case_id") not in config.PROTECTED_CASES and (not (s or e) or in_window(c.get("created")) or in_window(c.get("board_date")))]
    before = {"cases": len(cases), "listed": 0, "awaiting_listing": 0, "ready_now": 0, "readiness": [], "ready_before_board_n": 0, "ready_before_board_d": 0,
              "days_listed_to_ready": [], "documents": 0, "final_signed": 0, "scanned": 0, "dates_unconfirmed": 0, "identity_flags": 0, "discordances_open": 0,
              "requests_open": 0, "requests_overdue": 0, "requests_closed": 0, "hours_to_close": [], "by_department": {}}
    after = {"records": 0, "decisions": 0, "outcomes": {}, "final": 0, "flags_open": 0, "flags_resolved": 0, "flags_by_kind": {}, "composition_checked": 0, "composition_complete": 0,
             "same_day": 0, "informed_7d_n": 0, "informed_7d_d": 0, "trial_considered": 0, "key_worker": 0, "intent_recorded": 0, "consent_recorded": 0,
             "board_actions_open": 0, "board_actions_overdue": 0, "board_actions_closed": 0, "days_to_close_action": [], "decision_watch_open": 0}
    for c in cases:
        cid = c["case_id"]
        st = store.get_state(cid)
        gate = st.get("gate") or {}
        if c.get("protocol"):
            before["listed"] += 1
        else:
            before["awaiting_listing"] += 1
        if gate.get("passed"):
            before["ready_now"] += 1
        if gate.get("readiness") is not None:
            before["readiness"].append(gate["readiness"])
        bd = _d(c.get("board_date"))
        if bd and bd <= today and c.get("protocol"):
            before["ready_before_board_d"] += 1
            fr = _first_ready(cid)
            if fr and fr.date() <= bd:
                before["ready_before_board_n"] += 1
        la = _dt((c.get("listing") or {}).get("listed_at"))
        fr = _first_ready(cid) if la else None
        if la and fr and fr >= la:
            before["days_listed_to_ready"].append(round((fr - la).total_seconds() / 86400, 2))
        for d in rules.case_docs(cid, st):
            if d.get("state") != "ready":
                continue
            before["documents"] += 1
            cl = d.get("classification") or {}
            if rules._is_final(d, st.get("overrides")) and cl.get("signed") == "yes":
                before["final_signed"] += 1
            if any((p.get("method") or "").startswith("vision") for p in d.get("pages") or []):
                before["scanned"] += 1
        docs_info = gate.get("documents") or {}
        before["dates_unconfirmed"] += len(docs_info.get("date_unconfirmed") or [])
        before["identity_flags"] += len(docs_info.get("identity_flags") or [])
        if c.get("protocol"):
            before["discordances_open"] += discord.summary(cid, st).get("open_review", 0)
        for a in st.get("actions") or []:
            dep = a.get("department") or "unassigned"
            bd_ = before["by_department"].setdefault(dep, {"open": 0, "overdue": 0, "closed": 0, "hours": []})
            due = _d(a.get("due"))
            if a.get("source") == "pre_authorization":
                if a.get("status") == "completed":
                    before["requests_closed"] += 1; bd_["closed"] += 1
                    t0, t1 = _dt(a.get("created")), _dt(a.get("completed"))
                    if t0 and t1:
                        h = round((t1 - t0).total_seconds() / 3600, 1); before["hours_to_close"].append(h); bd_["hours"].append(h)
                else:
                    before["requests_open"] += 1; bd_["open"] += 1
                    if due and due < today:
                        before["requests_overdue"] += 1; bd_["overdue"] += 1
            elif a.get("source") == "board":
                if a.get("status") == "completed":
                    after["board_actions_closed"] += 1
                    t0, t1 = _dt(a.get("created")), _dt(a.get("completed"))
                    if t0 and t1:
                        after["days_to_close_action"].append(round((t1 - t0).total_seconds() / 86400, 1))
                else:
                    after["board_actions_open"] += 1
                    if due and due < today:
                        after["board_actions_overdue"] += 1
        for b in st.get("board_records") or []:
            oc = b.get("outcome_type") or "decision"
            after["records"] += 1  # every board record (night-v3 item 3.1: a noted, deferred or referred case is not a decision)
            after["decisions"] += oc == "decision"
            after["outcomes"][oc] = after["outcomes"].get(oc, 0) + 1
            res = b.get("resolution") or postboard.resolution_status(b)
            after["final"] += bool(res.get("final"))
            for f in (b.get("adjudication") or {}).get("flags") or []:
                k = f.get("kind") or "other"
                after["flags_by_kind"].setdefault(k, {"open": 0, "resolved": 0, "info": 0})
                if not postboard.needs_resolution(f):
                    after["flags_by_kind"][k]["info"] += 1
                elif f.get("resolution"):
                    after["flags_resolved"] += 1; after["flags_by_kind"][k]["resolved"] += 1
                else:
                    after["flags_open"] += 1; after["flags_by_kind"][k]["open"] += 1
            comp = (b.get("adjudication") or {}).get("composition") or {}
            if comp.get("checked"):
                after["composition_checked"] += 1
                after["composition_complete"] += not comp.get("missing")
            bday, rday = _d(b.get("board_date")), _dt(b.get("recorded_at"))
            if bday and rday and rday.date() == bday:
                after["same_day"] += 1
            if oc == "decision":
                after["informed_7d_d"] += 1
                pi = _d(b.get("patient_informed_date"))
                if pi and bday and (pi - bday).days <= 7:
                    after["informed_7d_n"] += 1
                after["trial_considered"] += bool(b.get("trial_considered"))
                after["key_worker"] += bool(b.get("key_worker"))
                after["intent_recorded"] += bool(b.get("intent") or b.get("intent_as_recorded"))
                after["consent_recorded"] += bool(b.get("consent_recorded"))
        if c.get("protocol"):
            after["decision_watch_open"] += discord.summary(cid, st).get("decision_watch", 0)
    # during: sessions
    sessions = []
    for sm in board.list_sessions():
        sess = board.get(sm["id"]) if isinstance(sm, dict) and sm.get("id") else None
        if sess and (not (s or e) or in_window(sess.get("date"))):
            sessions.append(sess)
    closed = [x for x in sessions if x.get("status") == "closed"]
    specs = board.specialties()
    att = {}
    for d in specs:
        did = d["id"]
        present = sum(1 for x in closed if board.attendance(x).get(did) == "present")
        marked = sum(1 for x in closed if board.attendance(x).get(did) in ("present", "absent"))
        att[did] = {"department": d.get("name") or did, "present": present, "sessions": len(closed), "marked": marked, "rate": _pct(present, len(closed))}
    empanelled = bool(org.hospital().get("pmjay_empanelled", True))  # the PM-JAY composition applies to an empanelled hospital only (V2 item 6.4)
    quorate = sum(1 for x in closed if postboard.pmjay_present({d for d, v in board.attendance(x).items() if v == "present"}, board.session_surgical(x)) >= set(PMJAY)) if empanelled else 0  # the seat by the agenda's own surgeons (6.2)
    minutes = [v / 60 for x in closed for v in (x.get("timing") or {}).values() if v]
    briefs = sum(1 for x in sessions for cs in (x.get("agents") or {}).values() for r in cs.values() if isinstance(r, dict) and r.get("status") in ("done", "reused"))
    questions = sum(1 for x in sessions for en in x.get("log") or [] if en.get("kind") == "answer")
    during = {"sessions": len(sessions), "closed": len(closed), "cases_discussed": sum(len(x.get("decisions") or {}) for x in closed),
              "quorate_n": quorate if empanelled else None, "quorate_pct": _pct(quorate, len(closed)) if empanelled else None, "pmjay_empanelled": empanelled, "attendance": att,
              "minutes_per_case_median": _median(minutes), "minutes_per_case_max": round(max(minutes), 1) if minutes else None,
              "agent_briefs": briefs, "agent_questions": questions}
    kpis = {
        "before": {"cases": before["cases"], "listed": before["listed"], "awaiting_listing": before["awaiting_listing"], "ready_now": before["ready_now"],
                   "ready_now_pct": _pct(before["ready_now"], before["listed"]), "readiness_median": _median(before["readiness"]),
                   "ready_before_board_pct": _pct(before["ready_before_board_n"], before["ready_before_board_d"]), "ready_before_board_n": before["ready_before_board_n"], "ready_before_board_d": before["ready_before_board_d"],
                   "days_listed_to_ready_median": _median(before["days_listed_to_ready"]), "documents": before["documents"],
                   "final_signed_pct": _pct(before["final_signed"], before["documents"]), "scanned_pct": _pct(before["scanned"], before["documents"]),
                   "dates_unconfirmed": before["dates_unconfirmed"], "identity_flags": before["identity_flags"], "discordances_open": before["discordances_open"],
                   "requests_open": before["requests_open"], "requests_overdue": before["requests_overdue"], "requests_closed": before["requests_closed"],
                   "hours_to_close_median": _median(before["hours_to_close"]),
                   "by_department": [{"department": k, "open": v["open"], "overdue": v["overdue"], "closed": v["closed"], "hours_to_close_median": _median(v["hours"])}
                                     for k, v in sorted(before["by_department"].items(), key=lambda kv: (-kv[1]["open"], kv[0]))]},
        "during": during,
        "after": {"records": after["records"], "decisions": after["decisions"], "outcomes": after["outcomes"], "final": after["final"], "final_pct": _pct(after["final"], after["records"]),
                  "flags_open": after["flags_open"], "flags_resolved": after["flags_resolved"], "flags_by_kind": after["flags_by_kind"],
                  "composition_complete_pct": _pct(after["composition_complete"], after["composition_checked"]), "composition_checked": after["composition_checked"],
                  "decision_recorded_same_day_pct": _pct(after["same_day"], after["records"]),
                  "patient_informed_7d_pct": _pct(after["informed_7d_n"], after["informed_7d_d"]), "patient_informed_7d_n": after["informed_7d_n"], "patient_informed_7d_d": after["informed_7d_d"],
                  "trial_considered_pct": _pct(after["trial_considered"], after["informed_7d_d"]), "key_worker_pct": _pct(after["key_worker"], after["informed_7d_d"]),
                  "intent_recorded_pct": _pct(after["intent_recorded"], after["informed_7d_d"]), "consent_recorded_pct": _pct(after["consent_recorded"], after["informed_7d_d"]),
                  "board_actions_open": after["board_actions_open"], "board_actions_overdue": after["board_actions_overdue"], "board_actions_closed": after["board_actions_closed"],
                  "days_to_close_action_median": _median(after["days_to_close_action"]), "decision_watch_open": after["decision_watch_open"]},
    }
    refs = []
    for r in REFERENCES:
        val = {"quorum": during["quorate_pct"], "attendance": _median([v["rate"] for v in att.values() if v["rate"] is not None]), "ready_before_board": kpis["before"]["ready_before_board_pct"],
               "decision_recorded_same_day": kpis["after"]["decision_recorded_same_day_pct"], "patient_informed_7d": kpis["after"]["patient_informed_7d_pct"],
               "trial_considered": kpis["after"]["trial_considered_pct"], "key_worker": kpis["after"]["key_worker_pct"], "intent_recorded": kpis["after"]["intent_recorded_pct"]}[r["metric"]]
        refs.append({**r, "value": val, "met": (val is not None and val >= r["target"]) if val is not None else None})
    return {"window": {"start": start or "", "end": end or ""}, "generated": store.now_iso(), "kpis": kpis, "references": refs,
            "note": "Counts of what the records and the system's events show; no clinical judgement. Reference lines are the published standards named beside them."}


def csv_text(d: dict) -> str:
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["section", "metric", "value", "target", "source"])
    for sec in ("before", "during", "after"):
        for k, v in d["kpis"][sec].items():
            if isinstance(v, (int, float, str)) or v is None:
                w.writerow([sec, k, "" if v is None else v, "", ""])
    for r in d["references"]:
        w.writerow(["reference", r["metric"], "" if r["value"] is None else r["value"], r["target"], r["source"]])
    for dep in d["kpis"]["before"]["by_department"]:
        w.writerow(["department", dep["department"], f"open {dep['open']}, overdue {dep['overdue']}, closed {dep['closed']}", "", f"median hours to close {dep['hours_to_close_median']}"])
    for did, v in d["kpis"]["during"]["attendance"].items():
        w.writerow(["attendance", v["department"], "" if v["rate"] is None else v["rate"], 90, "Victorian MDM framework 2018, 3.3"])
    return buf.getvalue()
