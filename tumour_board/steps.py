"""The guided Case File (21 Oct 2026, docs/ui/casefile-steps/DESIGN.md): six sections in working order (Overview, Question, Reports,
Check, Pre-Authorization, Summary), each with its status, the one next action behind "Continue", the To do and Waiting lists, the
warnings (the cancer chosen against the report titles, a patient who does not match, a report that is only preliminary), the patient at
a glance, and the check of every document ("Checked by Vaidyx": read, type found, final and signed found, patient matched, every value
matched to its report line word for word; it is the machine's check, never a person's review).

Built from slots.build and the stored documents; no model call. Nothing here diagnoses, stages or advises: the lines are the records,
their gaps and what the doctor typed (always shown "entered by Dr X, no report").

open_count() is the one count of what is left before the board; the Case File, the Case Files list and the meetings all use it."""
import re

from . import access, after_send, dates, dept_requests, discord, his_case, org, proposals, protocol, rules, slots, store

SECTIONS = [("overview", "Overview"), ("question", "Question"), ("reports", "Reports"), ("check", "Check"),
            ("pre_authorization", "Pre-Authorization"), ("summary", "Summary")]
READ_SECTIONS = ("overview", "reports", "summary")  # board members and other departments (B8)

# The reason for discussion, one tap (B3; Victoria MDM framework "reason for discussion").
REASONS = {"new_diagnosis": "New diagnosis: plan first treatment", "after_surgery": "After surgery: plan next",
           "recurrence": "Recurrence or progression", "diagnosis_unclear": "Diagnosis not clear", "other": "Other"}

# The patient at a glance (B2): four groups of protocol facts, in board order. A fact the protocol does not carry is left out.
GLANCE = [
    ("diagnosis", "Diagnosis", ["presenting_complaint", "histologic_type", "grade", "er", "pr", "her2", "ki67", "pdl1", "egfr", "alk", "ros1", "met",
                                "kras", "mmr", "ras_braf", "lvi", "pni", "margins", "depth_of_invasion", "cea"]),
    ("extent", "Extent", ["lesion_size", "nodal_findings", "ene", "distant_findings", "parametrial_involvement", "mrf_status", "emvi",
                          "distance_from_anal_verge", "suv_max", "recorded_stage", "figo_stage"]),
    ("fitness", "Fitness", ["ecog", "comorbidities", "menopausal_status", "haemoglobin", "wbc", "platelets", "creatinine", "bilirubin", "hiv_status"]),
    ("background", "Treatment so far and wishes", ["treatment_received", "treatment_completion_date", "diagnosis_date_mode", "patient_preference",
                                                   "patient_awareness"]),
]
STAGE_FACTS = ("recorded_stage", "figo_stage")
# Key values a doctor confirms one by one in Check (B5), whatever the quote check said: the diagnosis and the critical biomarkers and stage.
KEY_ALWAYS = ("histologic_type", "grade")

# Report groups by type (B4); an outside report is its own group.
DOC_GROUPS = [("pathology", "Pathology", {"histopathology", "cytology", "ihc", "molecular"}),
              ("imaging", "Imaging", {"ct", "mri", "xray", "ultrasound", "mammogram", "pet_ct", "bone_scan"}),
              ("labs", "Labs", {"lab"}),
              ("notes", "Clinical notes", {"clinical_note", "referral", "discharge_summary", "operative_note", "endoscopy", "treatment_summary",
                                           "tumour_board_record", "pulmonary_function"}),
              ("other", "Other reports", set())]  # an outside report keeps its type group, with an "Outside report" tag

# The cancer chosen against the report titles (B2 warning). Words a report title uses for a site; only titles are read, never the text.
SITE_WORDS = {"breast": ("breast", "mammo", "axilla"),
              "cervix": ("cervix", "cervical", "colposcop", "pap smear", "vulva", "vagina"),
              "lung_nsclc": ("lung", "thorax", "thoracic", "bronch", "ebus", "pleura"),
              "colorectal_rectum": ("rectum", "rectal", "colon", "colonoscop", "sigmoid", "anal verge", "proctos"),
              "oral_cavity": ("oral", "tongue", "buccal", "mandib", "gingiva", "palate", "lip ")}
SITE_NAME = {"breast": "the breast", "cervix": "the cervix", "lung_nsclc": "the lung", "colorectal_rectum": "the colon or rectum",
             "oral_cavity": "the oral cavity"}

FINAL = {"FINAL", "AMENDED", "CORRECTED"}
VERIFIED = ("verified", "confirmed")


class StepError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---- documents ---------------------------------------------------------------------------------------------------------------------

def _title(d) -> str:
    c = d.get("classification") or {}
    return str(c.get("title") or (d.get("his") or {}).get("title") or d.get("filename") or "Report")


def final_status(d) -> dict:
    """Final and signed as the report states it (the stricter of the text and the hospital system). A signature flag alone never makes a
    draft final (trust fix 1, 21 Oct): {final, signed, preliminary, label, warn}."""
    c = d.get("classification") or {}
    st = str(c.get("status") or "").upper()
    his = d.get("his") or {}
    hs = str(his.get("status") or "").upper()
    if hs in ("PRELIMINARY", "DRAFT", "REGISTERED") and st in FINAL:
        st = "PRELIMINARY" if hs != "DRAFT" else "DRAFT"
    signed = c.get("signed") == "yes" or (c.get("signed") not in ("no",) and bool(his.get("signed")) and st in FINAL)
    final = st in FINAL
    prelim = st == "PRELIMINARY"
    if final and signed:
        label, warn = "Final, signed", False
    elif final:
        label, warn = "Final, not signed", True
    elif prelim:
        label, warn = ("Preliminary, signed" if signed else "Preliminary, not signed yet"), True
    elif st == "CANCELLED":
        label, warn = "Cancelled", True
    else:
        label, warn = "Status not stated", True
    return {"final": final, "signed": signed, "preliminary": prelim, "status": st or "UNSTATED", "label": label, "warn": warn}


def doc_group(d) -> str:
    t = (d.get("classification") or {}).get("doc_type") or ""
    for gid, _, types in DOC_GROUPS:
        if t in types:
            return gid
    return "other"


def doc_check(d, case, cat=None) -> dict:
    """One document's check: {status: checked | please_check | reading | failed | dismissed, reasons[], values[]}. Checked by Vaidyx means
    read, type found, final and signed found, patient matched and every value it read matched to its line word for word."""
    cat = cat if cat is not None else protocol.facts()
    state = d.get("state")
    values = []
    unclear = unmatched = 0
    for fid, f in (d.get("facts") or {}).items():
        if not isinstance(f, dict):
            continue
        ver = f.get("verification")
        if ver in VERIFIED and f.get("state") in ("present", None):
            loc = f.get("location") if isinstance(f.get("location"), dict) else {}
            values.append({"fact_id": fid, "label": (cat.get(fid) or {}).get("label") or fid.replace("_", " "), "value": f.get("value") or "",
                           "quote": f.get("quote") or "", "page": loc.get("page"), "confirmed_by": f.get("confirmed_by") or ""})
        elif ver == "needs_review":
            unclear += 1
        elif ver == "unverified" and f.get("value"):
            unmatched += 1
    if d.get("dismissed"):
        return {"status": "dismissed", "reasons": [f"Set aside: {(d['dismissed'] or {}).get('reason') or 'no reason given'}"], "values": values}
    if state == "error":
        return {"status": "failed", "reasons": [f"Could not be read: {d.get('error') or 'error'}"], "values": values}
    if state != "ready":
        return {"status": "reading", "reasons": ["Being read"], "values": values}
    reasons = []
    ident = d.get("identity")
    if ident in ("id_differs", "mismatch_or_missing") and not d.get("identity_confirmed_by"):
        reasons.append("The patient's name or number does not match this Case File")
    elif ident == "name_match" and not d.get("identity_confirmed_by"):
        reasons.append("Matched by name only: check the patient on the report")
    c = d.get("classification") or {}
    if c.get("doc_type_disagreement") and not c.get("doc_type_confirmed_by"):
        reasons.append("The type of report is not clear")
    if c.get("date_unconfirmed") and not c.get("dates_confirmed_by"):
        reasons.append("The report date is not clear")
    spans = sum(len(p.get("ocr_uncertain_spans") or []) for p in d.get("pages") or [] if isinstance(p, dict))
    lines = unclear + (1 if spans and not unclear else 0)
    if lines:
        reasons.append(f"{lines} {'line' if lines == 1 else 'lines'} unclear")
    if unmatched:
        reasons.append(f"{unmatched} {'value' if unmatched == 1 else 'values'} could not be matched to a line")
    prot = case.get("protocol") or ""
    if prot and d.get("extracted_under") and d.get("extracted_under") != prot:
        reasons.append("Read before the cancer was changed: read it again for this cancer")
    return {"status": "please_check" if reasons else "checked", "reasons": reasons, "values": values}


def documents(case_id, case, st=None, docs=None) -> list[dict]:
    """Every current document with its group, date, final status, check and images, newest first; earlier versions folded under the one
    that replaced them."""
    st = store.get_state(case_id) if st is None else st
    docs = rules.case_docs(case_id, st) if docs is None else docs
    cat = protocol.facts()
    by_id = {d["doc_id"]: d for d in docs}
    out = []
    earlier = {}
    for d in docs:
        sup = d.get("superseded") or {}
        if sup.get("by_doc") in by_id:
            head, hops = sup["by_doc"], 0
            while (by_id[head].get("superseded") or {}).get("by_doc") in by_id and hops < 20:
                head = by_id[head]["superseded"]["by_doc"]; hops += 1
            earlier.setdefault(head, []).append(d)
    for d in docs:
        view = his_case.doc_view(d) or {}
        if (d.get("superseded") or {}).get("by_doc") in by_id:
            continue
        his = view.get("his") or d.get("his") or {}
        dd = {**d, "his": his, "outside": view.get("outside") or d.get("outside")}
        dt = dates.doc_dates(dd)
        fs = final_status(dd)
        out.append({"doc_id": d["doc_id"], "title": _title(dd), "doc_type": (d.get("classification") or {}).get("doc_type") or "", "group": doc_group(dd),
                    "date": dt.get("event") or dt.get("report") or "", "department": d.get("department") or his.get("performer_department") or "",
                    "accession": his.get("accession") or "", "final": fs, "check": doc_check(dd, case, cat), "images": bool(his.get("imaging_study_ref")),
                    "outside": bool(dd.get("outside")), "state": d.get("state"),
                    "earlier": [{"doc_id": e["doc_id"], "title": _title(e), "version": ((his_case.doc_view(e) or {}).get("his") or {}).get("version"),
                                 "status": final_status({**e, "his": (his_case.doc_view(e) or {}).get("his") or {}})["label"]} for e in earlier.get(d["doc_id"], [])]})
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


# ---- warnings ----------------------------------------------------------------------------------------------------------------------

SITE_FACTS = ("histologic_type", "presenting_complaint", "lesion_size", "nodal_findings")  # verified values that name a site


def _mentions(docs, by_fact) -> dict:
    """Where each site is named: report titles and the verified values that name a site (the histology, the presenting complaint, the
    lesion). Only words the reports print; nothing is inferred."""
    out = {site: [] for site in SITE_WORDS}
    for d in docs:
        t = " " + d["title"].lower() + " "
        for site, words in SITE_WORDS.items():
            if any(w in t for w in words):
                out[site].append(slots_title(d["title"]))
    for fid in SITE_FACTS:
        sl = by_fact.get(fid) or {}
        if sl.get("status") not in ("found", "needs_confirmation") or not sl.get("value"):
            continue
        v = " " + str(sl["value"]).lower() + " "
        for site, words in SITE_WORDS.items():
            if any(w in v for w in words):
                val = str(sl["value"])
                val = val if len(val) <= 60 else val[:57].rsplit(" ", 1)[0] + "..."
                out[site].append(f"{(sl.get('label') or fid).split(' (')[0].lower()}: \"{val}\"")
    return out


def slots_title(t) -> str:
    """"BILATERAL MAMMOGRAPHY REPORT" -> "Bilateral mammography report" (a sentence reads better than a shouted title)."""
    t = str(t or "")
    return t[:1] + t[1:].lower() if t.isupper() else t


def warnings(case, docs, view) -> list[dict]:
    """Plain sentences with their fix (B2). Only what the records show; a dismissed warning stays dismissed for the same facts."""
    out = []
    dismissed = case.get("warnings_dismissed") if isinstance(case.get("warnings_dismissed"), dict) else {}
    prot = case.get("protocol") or ""
    by_fact = {s.get("fact_id"): s for s in slots._all_slots(view) if s.get("kind") == "fact"}
    if prot in SITE_WORDS:
        m = _mentions(docs, by_fact)
        other = max((s for s in SITE_WORDS if s != prot), key=lambda s: len(m[s]))
        if not m[prot] and len(m[other]) >= 2:
            key = f"cancer:{prot}:{other}"
            if key not in dismissed:
                label = (protocol.get(prot) or {}).get("label") or prot
                where = "; ".join(m[other][:3])
                out.append({"id": key, "kind": "cancer_mismatch", "section": "overview", "severity": "warn",
                            "text": f"The reports mention {SITE_NAME[other]} ({where}); none mention {SITE_NAME[prot]}. This Case File is set to {label}.",
                            "fixes": [{"kind": "change_cancer", "label": "Change the cancer"}, {"kind": "dismiss", "label": "It is correct"}]})
    for d in docs:
        if d["check"]["status"] == "please_check" and any("does not match" in r for r in d["check"]["reasons"]):
            out.append({"id": f"identity:{d['doc_id']}", "kind": "identity", "section": "reports", "severity": "bad", "doc_id": d["doc_id"],
                        "text": f"The patient's name or number on {slots_title(d['title'])} ({_dmy(d['date'])}) does not match this Case File.",
                        "fixes": [{"kind": "open_report", "label": "Open the report", "doc_id": d["doc_id"]}]})
    drafts = {}
    for s in slots._all_slots(view):
        dr = s.get("draft") or {}
        if dr.get("doc_id") and s.get("required"):
            drafts.setdefault(dr["doc_id"], s)
    for d in docs:
        if d["final"]["preliminary"] and d["doc_id"] in drafts:
            s = drafts[d["doc_id"]]
            ask = next((a for a in s.get("actions") or [] if a.get("kind") == "ask_department"), None)
            fixes = [{"kind": "open_report", "label": "Open the report", "doc_id": d["doc_id"]}]
            if ask and s.get("status") == "not_found":
                fixes.insert(0, {"kind": "ask_department", "label": f"Send request to {_dept_words(ask.get('department'))}", "slot_id": s["id"],
                                 "department": ask.get("department")})
            out.append({"id": f"preliminary:{d['doc_id']}", "kind": "preliminary", "section": "pre_authorization", "severity": "warn", "doc_id": d["doc_id"],
                        "text": f"{slots_title(d['title'])} ({_dmy(d['date'])}) is only preliminary" + (": a request is waiting on the department." if s.get("status") == "waiting" else "."),
                        "fixes": fixes})
    return out


def dismiss_warning(case_id, key, user) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise StepError("Case File not found.", 404)
    key = str(key or "")[:200]
    if not key.startswith("cancer:"):
        raise StepError("Only the cancer check can be set aside; the others go once the report is settled.", 409)
    rec = {"by": user, "at": store.now_iso()}
    case.setdefault("warnings_dismissed", {})[key] = rec
    store.save_case(case)
    store.audit(case_id, {"kind": "warning_dismissed", "key": key, "by": user})
    return rec


# ---- the reason for discussion and the key-value checks ------------------------------------------------------------------------------

def set_reason(case_id, value, user) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise StepError("Case File not found.", 404)
    v = str(value or "")
    if v not in REASONS:
        raise StepError("Choose one of the listed reasons.", 400)
    before = case.get("board_reason")
    rec = {"value": v, "label": REASONS[v], "by": user, "at": store.now_iso()}
    case["board_reason"] = rec
    store.save_case(case)
    store.audit(case_id, {"kind": "board_reason", "value": v, "before": before, "by": user})
    return rec


def key_facts(prot) -> list[str]:
    """The key values of a protocol, in board order: histology and grade, then every critical fact it carries (receptors, biomarkers,
    the stage as recorded)."""
    cat = protocol.facts()
    have = set(prot.get("extract_facts") or []) | {f for r in protocol.records(prot) for f in r.get("required_facts") or []}
    have |= {f for c in prot.get("core_data") or [] for f in c.get("facts") or []}
    order = [f for _, _, fs in GLANCE for f in fs]
    keys = [f for f in order if f in have and (f in KEY_ALWAYS or (cat.get(f) or {}).get("critical"))]
    return keys + sorted(f for f in have if (cat.get(f) or {}).get("critical") and f not in keys)


def confirm_key(case_id, fact_id, value, doc_id, user) -> dict:
    """The doctor read a key value against its report line (B5): kept while the same value from the same report stands; a new report or
    a different value makes it a to-do again. Never changes the value."""
    case = store.get_case(case_id)
    if not case:
        raise StepError("Case File not found.", 404)
    fid = str(fact_id or "")
    if not re.fullmatch(r"[a-z0-9_]{1,64}", fid):
        raise StepError("Unknown value.", 400)
    rec = {"value": str(value or "")[:500], "doc_id": str(doc_id or "")[:64], "by": user, "at": store.now_iso()}
    st = store.get_state(case_id)
    st.setdefault("key_checks", {})[fid] = rec
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "key_value_confirmed", "fact": fid, "value": rec["value"], "doc_id": rec["doc_id"], "by": user})
    return rec


def undo_key(case_id, fact_id, user) -> None:
    st = store.get_state(case_id)
    if (st.get("key_checks") or {}).pop(str(fact_id or ""), None) is None:
        raise StepError("That value was not confirmed.", 404)
    store.save_state(case_id, st)
    store.audit(case_id, {"kind": "key_value_unconfirmed", "fact": str(fact_id), "by": user})


# ---- the view ----------------------------------------------------------------------------------------------------------------------

def _dmy(iso) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else s


def _dept_words(name) -> str:
    """"Pathology" -> "Pathology department"; the MDT Coordinator stays as it is."""
    n = str(name or "").strip() or "the department"
    if n == org.COORDINATOR_NAME or n.lower().endswith("department") or n == "the department":
        return n
    return f"{n} department"


def _row(s) -> dict:
    """A slot as a line of the guided Case File (value, its quote, who typed it), never more than the slot says."""
    out = {"slot_id": s["id"], "fact_id": s.get("fact_id"), "label": s.get("label") or "", "status": s.get("status"), "value": s.get("value") or "",
           "unit": s.get("unit") or "", "as_of": s.get("as_of"), "quote": s.get("quote"), "note": slots_note(s), "required": bool(s.get("required"))}
    if s.get("status") == "entered":
        out["entered_by"] = s.get("typed_by_name") or s.get("typed_by") or ""
        out["entered_at"] = s.get("typed_at")
        if s.get("report_value"):
            out["report_value"] = s["report_value"]
    if s.get("confirmed_by"):
        out["corrected_by"] = slots.display_name(s["confirmed_by"])
    return out


def slots_note(s) -> str:
    n = str(s.get("note") or "")
    return "" if n in ("Not found in the file",) else n


def _receiving(s, acts_by_id) -> dict | None:
    """The department that will really receive the request for a line (trust fix 2, 21 Oct): the suggested request's own department,
    not the record's routed name."""
    ask = next((a for a in s.get("actions") or [] if a.get("kind") in ("ask_department", "remind")), None)
    aid = (ask or {}).get("action_id") or (s.get("request") or {}).get("action_id")
    a = acts_by_id.get(aid) if aid else None
    name = (a or {}).get("department") or (ask or {}).get("department") or s.get("department") or ""
    if not name:
        return None
    return {"name": name, "label": _dept_words(name), "id": (a or {}).get("department_id") or rules._dept_id(name), "action_id": aid,
            "phone": org.department_phone((a or {}).get("department_id") or rules._dept_id(name)) or ""}


def build(case_id, roles=None) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise StepError("Case File not found.", 404)
    view = slots.build(case_id, roles)
    st = store.get_state(case_id)
    cdocs = rules.case_docs(case_id, st)
    docs = documents(case_id, case, st, cdocs)
    prot = protocol.get(case["protocol"]) if case.get("protocol") and protocol.exists(case["protocol"]) else None
    all_slots = slots._all_slots(view)
    by_fact = {s.get("fact_id"): s for s in all_slots if s.get("kind") == "fact"}
    acts_by_id = {a["id"]: a for a in st.get("actions") or [] if isinstance(a, dict) and a.get("id")}
    r = roles if isinstance(roles, dict) else {}
    consultant = bool(r) and access.is_owner_consultant(r, case)
    resident = bool(r) and access.is_team_resident(r, case) and not consultant
    prepare = consultant or resident  # the owner's team prepares; the coordinator, board members and other departments read (B8)
    perms = view.get("permissions") or {}
    today = store.now_iso()[:10]

    # Question (B3): the doctor's own words; a question copied from a note does not count.
    q = by_fact.get("clinical_question") or {}
    question = {"text": q.get("value") if q.get("status") == "entered" else "", "by": q.get("typed_by_name") or "", "at": q.get("typed_at"),
                "note_text": (q.get("report_value") or {}).get("value") or (q.get("value") if q.get("status") == "found" else ""),
                "reason": case.get("board_reason") or None, "urgency": case.get("urgency") or None,
                "extras": [_row(by_fact[f]) for f in ("patient_preference", "comorbidities", "patient_awareness") if f in by_fact]}
    question_done = bool(question["text"])

    # Check (B5): problem values one at a time, then the key values with a one-tap confirm.
    key_checks = st.get("key_checks") if isinstance(st.get("key_checks"), dict) else {}
    problems, keys = [], []
    for s in all_slots:
        picked = s.get("picked") if s.get("status") == "found" else None  # two reports differ and a doctor picked the value the board uses (1.7)
        if s.get("kind") == "fact" and (s.get("status") == "needs_confirmation" or picked) and s.get("fact_id") != "clinical_question":
            conf = s.get("confirmation") or {}
            row = {**_row(s), "kind": "problem", "confirmation": conf or None, "why": _problem_words(conf), "detail": conf.get("why") or s.get("note") or ""}
            if picked:  # settled: still listed, with the pick and its Undo, never counted as left
                row.update(picked=picked, resolved=True, why=f"Picked: {picked.get('value')} from {picked.get('doc_title')}, by {picked.get('by_name') or picked.get('by')}")
            elif s.get("pick_stale"):  # the doctor's pick no longer matches its report (item 1.7): said, never dropped silently
                row.update(pick_stale=s["pick_stale"], why=discord.stale_why(s["pick_stale"]))
            problems.append(row)
    for fid in key_facts(prot) if prot else []:
        s = by_fact.get(fid)
        if not s or s.get("status") != "found" or any(p["fact_id"] == fid for p in problems):
            continue
        k = key_checks.get(fid) or {}
        doc_id = (s.get("quote") or {}).get("doc_id") or ""
        done = k.get("value") == (s.get("value") or "") and k.get("doc_id") == doc_id
        keys.append({**_row(s), "kind": "key", "confirmed": done, "confirmed_by": slots.display_name(k.get("by")) if done else "", "confirmed_at": k.get("at") if done else None})
    open_problems = [p for p in problems if not p.get("resolved")]
    check_todo = len(open_problems) + sum(1 for k in keys if not k["confirmed"])

    # Pre-Authorization (B6): what the board still needs, grouped by the department that will receive the request.
    missing, waiting, optional = [], [], []
    for s in all_slots:
        if s.get("kind") == "prose" or s.get("fact_id") == "clinical_question" or s.get("facts_only"):
            continue
        if s.get("status") not in ("not_found", "waiting"):
            continue
        item = {**_row(s), "kind": s.get("kind"), "department": _receiving(s, acts_by_id), "typable": bool(s.get("typable")) or any(a.get("kind") == "enter_value" for a in s.get("actions") or []),
                "can_not_needed": any(a.get("kind") == "not_needed" for a in s.get("actions") or []),
                "draft": s.get("draft"), "pending": bool(s.get("pending"))}
        if s["status"] == "waiting":
            rq = s.get("request") or {}
            due = rq.get("due") or ""
            item["request"] = {**rq, "overdue": rq.get("status") == "overdue" or bool(due and due[:10] < today)}
            (waiting if s.get("required") else optional).append(item)
        else:
            (missing if s.get("required") else optional).append(item)
    groups = {}
    for it in missing:
        dep = it["department"] or {"name": "", "label": "No department named", "id": "", "action_id": None, "phone": ""}
        g = groups.setdefault(dep["label"], {"department": dep, "items": []})
        g["items"].append(it)

    # Reports (B4).
    doc_todo = [d for d in docs if d["check"]["status"] in ("please_check", "failed")]
    reading = sum(1 for d in docs if d["check"]["status"] == "reading")

    # Summary (B7): written before sending, read, then sent.
    prose = view.get("prose") or {}
    sent = case.get("board_ready") or None

    # Sign-offs for the consultant (B9).
    signoffs = [p for p in proposals.list_(case) if p.get("status") == proposals.PENDING] if consultant else []

    left = (0 if question_done else 1) + check_todo + len(missing) + len(waiting) + len(doc_todo)

    # ---- the six sections and their status words (B9) ----
    def sec(sid, status, detail="", count=None):
        return {"id": sid, "label": dict(SECTIONS)[sid], "status": status, "detail": detail, "count": count}

    overdue = [w for w in waiting if w["request"]["overdue"]]
    if missing:
        pa = sec("pre_authorization", "todo", f"{len(missing)} to do", len(missing))
    elif overdue:
        pa = sec("pre_authorization", "overdue", f"Overdue: {overdue[0]['department']['label'] if overdue[0]['department'] else 'a department'}", len(overdue))
    elif waiting:
        deps = list(dict.fromkeys((w["department"] or {}).get("label") or "a department" for w in waiting))
        pa = sec("pre_authorization", "waiting", "Waiting on " + deps[0] + (f" and {len(deps) - 1} more" if len(deps) > 1 else ""), len(waiting))
    else:
        pa = sec("pre_authorization", "done", "Done")
    if prose.get("status") in ("ready",) and prose.get("reviewed"):
        sm = sec("summary", "done", "Done")
    elif prose.get("status") == "ready":
        sm = sec("summary", "todo", "Read it", 1)
    elif prose.get("status") == "stale":
        sm = sec("summary", "todo", "Records changed: write it again", 1)
    elif prose.get("status") == "pending" or prose.get("preparing"):
        sm = sec("summary", "working", "Being written")
    else:
        sm = sec("summary", "not_started", "Not started")
    sections = [
        sec("overview", "home", ""),
        sec("question", "done" if question_done else "not_started", "Done" if question_done else "Not started"),
        sec("reports", "todo" if doc_todo else ("working" if reading else "done"),
            f"{len(doc_todo)} to check" if doc_todo else (f"Reading {reading}" if reading else ""), len(docs)),
        sec("check", "todo" if check_todo else ("done" if keys or problems else "empty"), f"{check_todo} to do" if check_todo else ("Done" if keys else "Nothing to check"), check_todo),
        pa,
        sm,
    ]
    if not prepare:
        sections = [s for s in sections if s["id"] in READ_SECTIONS]

    # ---- To do and Waiting on the Overview (B2), and the next action behind Continue ----
    todo = []
    if signoffs:
        todo.append({"id": "signoffs", "section": "overview", "label": f"Sign-offs from your team ({len(signoffs)})", "action": {"kind": "signoffs", "label": "Review"}})
    if not question_done:
        todo.append({"id": "question", "section": "question", "label": "Write the question for the board", "action": {"kind": "go", "label": "Write it"}})
    for g in groups.values():
        n = len(g["items"])
        dep = g["department"]
        what = ", ".join(i["label"] for i in g["items"][:2]) + (f" and {n - 2} more" if n > 2 else "")
        todo.append({"id": f"request:{dep['label']}", "section": "pre_authorization", "label": what, "why": "Not found in the reports",
                     "action": {"kind": "ask_department", "label": f"Send request to {dep['label']}", "department": dep, "slot_ids": [i["slot_id"] for i in g["items"]]}})
    for d in doc_todo:
        todo.append({"id": f"doc:{d['doc_id']}", "section": "reports", "label": d["title"], "why": d["check"]["reasons"][0],
                     "action": {"kind": "open_report", "label": "Check", "doc_id": d["doc_id"]}})
    # a report that came after sending differs from an earlier one (night-v3 item 1.5, B8): one task "Check N values", first in the list
    fresh = after_send.since_sent(case_id, case, open_problems) if sent else []
    for p in fresh:
        p["since_sent"] = True
    for p in open_problems:
        if p.get("since_sent"):
            continue
        todo.append({"id": f"check:{p['slot_id']}", "section": "check", "label": p["label"], "why": p["why"] or "Please check", "action": {"kind": "check", "label": "Check", "slot_id": p["slot_id"]}})
    unconfirmed = [k for k in keys if not k["confirmed"]]
    if unconfirmed:
        todo.append({"id": "keys", "section": "check", "label": f"Confirm {len(unconfirmed)} key {'value' if len(unconfirmed) == 1 else 'values'}",
                     "why": ", ".join(k["label"] for k in unconfirmed[:4]) + ("..." if len(unconfirmed) > 4 else ""), "action": {"kind": "go", "label": "Confirm"}})
    if not todo and not sent:
        if prose.get("status") in ("none", "stale"):
            todo.append({"id": "summary", "section": "summary", "label": "Write the summary", "action": {"kind": "go", "label": "Write it"}})
        elif prose.get("status") == "ready" and not prose.get("reviewed"):
            todo.append({"id": "summary", "section": "summary", "label": "Read the summary", "action": {"kind": "go", "label": "Read it"}})
    if fresh:
        n = len(fresh)
        todo.insert(0, {"id": "since_sent", "section": "check", "label": f"Check {n} {'value' if n == 1 else 'values'}", "since_sent": True,
                        "why": ("A report that came after sending differs from an earlier one or is only preliminary: " if any((p.get("confirmation") or {}).get("kind") == "preliminary" for p in fresh)
                                else "A report that came after sending differs from an earlier one: ") + ", ".join(p["label"] for p in fresh[:3]) + ("..." if n > 3 else ""),
                        "action": {"kind": "check", "label": "Check", "slot_id": fresh[0]["slot_id"]}})
    waiting_rows = [{"id": f"wait:{w['slot_id']}", "section": "pre_authorization", "label": w["label"], "department": w["department"], "request": w["request"],
                     "action": {"kind": "remind", "label": "Send reminder", "action_id": (w["request"] or {}).get("action_id")}} for w in waiting]

    warnings_list = warnings(case, docs, view)
    nxt = _next(missing, groups, doc_todo, open_problems, unconfirmed, question_done, prose, sent, warnings_list)
    glance = _glance(prot, by_fact)
    return {"case_id": case_id, "mode": "prepare" if prepare else "read", "role": "consultant" if consultant else "resident" if resident else "reader",
            "sections": sections, "next": nxt if prepare else None, "todo": todo if prepare else [], "waiting": waiting_rows if prepare else [],
            "warnings": warnings_list, "question": question, "glance": glance, "documents": docs,
            "check": {"problems": problems, "keys": keys}, "pre_authorization": {"groups": list(groups.values()), "waiting": waiting, "optional": optional},
            "summary": {"prose": prose, "sent": sent}, "left": left, "permissions": perms, "signoffs": len(signoffs),
            "protocol": case.get("protocol") or "", "protocol_label": view.get("protocol_label") or "", "reasons": [{"id": k, "label": v} for k, v in REASONS.items()],
            "blockers": view.get("blockers") or []}


def _problem_words(conf) -> str:
    """A problem value in a few plain words (the long reason stays in the detail)."""
    t = (conf or {}).get("type")
    why = str((conf or {}).get("why") or "").lower()
    if t == "note_discordance" and (conf or {}).get("kind") == "preliminary":
        return "Only a preliminary report since sending"
    if t == "note_discordance" or "differs" in why or "disagree" in why:
        return "Two reports differ"
    if t == "confirm_value" and "scan" in why:
        return "Read from a scan: check the line"
    if t == "confirm_value" and "approximately" in why:
        return "Matched its report line only approximately"
    return "Please check against the report"


def _next(missing, groups, doc_todo, problems, unconfirmed, question_done, prose, sent, warns) -> dict | None:
    """The one next thing (B1 Continue). Order: the cancer check, the question (research: the question first), requests to other departments
    (they take days, so they go out early), reports to check, values to check, the summary, then Send to the board."""
    w = next((x for x in warns if x["kind"] == "cancer_mismatch"), None)
    if w:
        return {"section": "overview", "label": "Check the cancer chosen", "target": w["id"]}
    if not question_done:
        return {"section": "question", "label": "Write the question for the board"}
    if missing:
        n = len(groups)
        return {"section": "pre_authorization", "label": f"Send {n} {'request' if n == 1 else 'requests'}" if n else "Settle what is missing"}
    if doc_todo:
        return {"section": "reports", "label": f"Check {len(doc_todo)} {'report' if len(doc_todo) == 1 else 'reports'}", "target": doc_todo[0]["doc_id"]}
    if problems:
        return {"section": "check", "label": f"Check {len(problems)} {'value' if len(problems) == 1 else 'values'}", "target": problems[0]["slot_id"]}
    if unconfirmed:
        return {"section": "check", "label": f"Confirm {len(unconfirmed)} key {'value' if len(unconfirmed) == 1 else 'values'}"}
    if sent:
        return {"section": "summary", "label": "Sent to the board", "done": True}
    if prose.get("status") in ("none", "stale"):
        return {"section": "summary", "label": "Write the summary"}
    if prose.get("status") == "pending" or prose.get("preparing"):
        return {"section": "summary", "label": "The summary is being written"}
    if not prose.get("reviewed"):
        return {"section": "summary", "label": "Read the summary"}
    return {"section": "summary", "label": "Send to the board", "send": True}


def _glance(prot, by_fact) -> list[dict]:
    out = []
    for gid, label, facts in GLANCE:
        rows = []
        for fid in facts:
            s = by_fact.get(fid)
            if not s:
                continue
            row = _row(s)
            if fid in STAGE_FACTS:
                row["label"] = f"{s.get('label') or 'Stage'} (as written in a report)"
                if s.get("status") not in ("found", "entered"):
                    row["note"] = "Not written in any report (Vaidyx never works out a stage)"
            rows.append(row)
        if rows:
            out.append({"id": gid, "label": label, "rows": rows})
    return out


_COUNTS: dict = {}


def _files_key(case_id) -> tuple:
    """What the count is built from on disk: case.json, state.json and every doc.json, by modification time."""
    d = store.case_dir(case_id)
    parts = []
    for name in ("case.json", "state.json"):
        try:
            parts.append((d / name).stat().st_mtime_ns)
        except FileNotFoundError:
            parts.append(0)
    docs = []
    for p in (d / "docs").glob("*/doc.json"):
        try:
            docs.append((p.parent.name, p.stat().st_mtime_ns))
        except FileNotFoundError:
            pass
    parts.append(tuple(sorted(docs)))
    return tuple(parts)


def open_count(case_id) -> int | None:
    """What is left before the board, the one count used everywhere (trust fix 3, 21 Oct): the question when it is not written, the values
    to check, what the board still needs (asked or not) and the reports to check. None when the Case File has no cancer yet. Kept until
    one of its files changes."""
    try:
        case = store.get_case(case_id)
        if not case or not case.get("protocol"):
            return None
        key = _files_key(case_id)
        hit = _COUNTS.get(case_id)
        if hit and hit[0] == key:
            return hit[1]
        n = build(case_id, None)["left"]
        if len(_COUNTS) > 4000:
            _COUNTS.clear()
        _COUNTS[case_id] = (key, n)
        return n
    except Exception:
        return None
