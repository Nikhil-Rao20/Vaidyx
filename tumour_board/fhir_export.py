"""FHIR R4 document bundle and the registry abstract of a Case File (12 Oct). Plain code, no model.

What is exported is what the Case File holds: the documents (DocumentReference, with their status as classified), the verified
primary fields (Observation, each with its quote and the report it came from), the primary cancer as the signed histopathology
records it (Condition, with the stage as recorded copied into Condition.stage.summary, never derived), the open requests and the
board actions (Task), the Tumour Board records (CarePlan) and the patient-communication record (Communication), under a
Composition that follows the NCG Virtual Tumour Board sections of the stored summary.

Standards: FHIR R4 (CC0), shaped after the mCODE STU4 profiles (CancerPatient, PrimaryCancerCondition, TNMStageGroup,
ECOGPerformanceStatus, TumorMarkerTest) and India's ABDM / NRCeS record types (DiagnosticReportRecord, OPConsultRecord). The bundle
is mCODE-informed, not validated against the profiles: SNOMED CT and ICD-O codes are not assigned (the hospital's coder does that;
SNOMED CT is free in India through the NRC affiliate licence), LOINC codes are given only where the mapping is standard.

Registry abstract: the HBCR (ICMR-NCDIR) procedure manual 2025 mandatory items that the records document, each with its source
quote; items the system never derives (clinical extent, composite stage, ICD-O topography / morphology) are given as recorded or
marked not coded.
"""
import base64, hashlib, html, json, mimetypes, uuid

from . import config, dates, decision_record, postboard, protocol, rules, store, units

BASE_URL = "https://vaidyx.local"  # placeholder identifier and extension base; the hospital sets its own on deployment
LOINC = {  # standard mappings only; every other field is exported with a text code
    "ecog": ("89247-1", "ECOG Performance Status score"), "haemoglobin": ("718-7", "Hemoglobin [Mass/volume] in Blood"),
    "wbc": ("6690-2", "Leukocytes [#/volume] in Blood by Automated count"), "platelets": ("777-3", "Platelets [#/volume] in Blood by Automated count"),
    "creatinine": ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma"), "bilirubin": ("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma"),
    "cea": ("2039-6", "Carcinoembryonic Ag [Mass/volume] in Serum or Plasma")}
CATEGORY = {"lab": "laboratory", "histopathology": "laboratory", "ihc": "laboratory", "molecular": "laboratory", "cytology": "laboratory",
            "ct": "imaging", "mri": "imaging", "pet_ct": "imaging", "xray": "imaging", "ultrasound": "imaging", "mammogram": "imaging", "bone_scan": "imaging"}
DOC_STATUS = {"FINAL": "final", "AMENDED": "amended", "CORRECTED": "amended", "PRELIMINARY": "preliminary", "DRAFT": "preliminary", "CANCELLED": "entered-in-error"}
STAGE_FIELDS = ("recorded_stage", "figo_stage")
NOTE = ("Exported by Vaidyx-TB from the Tumour Board Case File: values are verbatim from the records with their quotes; the stage is copied as recorded, never "
        "derived; no diagnosis, interpretation or treatment advice is produced by the system. mCODE-informed, not validated against profiles; SNOMED CT and ICD-O codes not assigned.")


def _uuid(*parts) -> str:
    return str(uuid.UUID(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]))


def _ref(kind, rid):
    return {"reference": f"urn:uuid:{rid}", "type": kind}


def _xhtml(text: str) -> str:
    return f'<div xmlns="http://www.w3.org/1999/xhtml">{html.escape(text or "")}</div>'


def _gender(agesex: str) -> str:
    s = (agesex or "").strip().upper()
    if s.endswith("/ M") or s.endswith("/M") or s.endswith(" M"):
        return "male"
    if s.endswith("/ F") or s.endswith("/F") or s.endswith(" F"):
        return "female"
    return "unknown"


def _quantity(value: str):
    """valueQuantity when the value carries exactly one number with a recognised unit ("11.8 g/dL", "TPS 60%"); None for anything
    else ("5.2 x 4.1 cm", "cT3 N2 M0", text): valueString then keeps the value as written."""
    try:
        qs = [q for q in units.parse_quantity(value or "") if q.get("family") and q.get("unit")]
    except Exception:
        return None
    if len(qs) != 1 or qs[0].get("value") is None:
        return None
    return {"value": qs[0]["value"], "unit": str(qs[0]["unit"])}


CAREPLAN_FIELDS = ("intent", "modalities", "sequence", "alternatives_discussed", "stage_as_agreed", "trial_considered", "referrals", "pmjay_plan_approval",
                   "responsible_doctor", "key_worker", "informed_by")


def care_plan_lines(b: dict) -> list[str]:
    """The decision record fields of night-v3 item 3.1 as CarePlan notes, as the board recorded them (labels from decision_record):
    the stage with its source, the trial with its name, PM-JAY with its reference, who tells the patient with the date."""
    vals = {x["key"]: x["text"] for x in decision_record.display_lines(b)}
    out = []
    for k in CAREPLAN_FIELDS:
        t = vals.get(k)
        if not t:
            continue
        extra = {"stage_as_agreed": vals.get("stage_source"), "trial_considered": vals.get("trial_name"), "pmjay_plan_approval": vals.get("pmjay_plan_note"),
                 "informed_by": (f"by {vals['inform_by_date']}" if vals.get("inform_by_date") else "")}.get(k)
        out.append(f"{decision_record.label(k)}: {t}" + (f" ({extra})" if extra else ""))
    if not vals.get("informed_by") and vals.get("inform_by_date"):
        out.append(f"{decision_record.label('inform_by_date')}: {vals['inform_by_date']}")
    if b.get("corrected"):
        out.append(decision_record.corrected_line(b))
    return out


def bundle(case_id: str) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise KeyError(case_id)
    st = store.get_state(case_id)
    docs = rules.case_docs(case_id, st)
    facts = rules.resolve_facts(docs, st.get("overrides"))
    cat = protocol.facts()
    now = store.now_iso()
    pat = case.get("patient") or {}
    entries = []

    def add(res):
        entries.append({"fullUrl": f"urn:uuid:{res['id']}", "resource": res})
        return res
    patient_id = _uuid(case_id, "Patient")
    patient = add({"resourceType": "Patient", "id": patient_id, "meta": {"profile": ["http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-cancer-patient"]},
                   "identifier": [{"system": f"{BASE_URL}/identifiers/hospital-number", "value": pat.get("mrn") or case_id}]
                   + [{"system": f"{BASE_URL}/identifiers/{(x.get('kind') or 'id').lower()}", "value": x.get("value")} for x in (pat.get("ids") or []) if isinstance(x, dict) and x.get("value")],
                   "name": [{"text": pat.get("name") or ""}], "gender": _gender(pat.get("agesex", "")),
                   "extension": [{"url": f"{BASE_URL}/fhir/StructureDefinition/age-sex-as-recorded", "valueString": pat.get("agesex") or ""}]})
    device_id = _uuid("Vaidyx-TB", "Device")
    add({"resourceType": "Device", "id": device_id, "deviceName": [{"name": "Vaidyx-TB (AI support for the Tumour Board)", "type": "user-friendly-name"}],
         "note": [{"text": "Models: " + "; ".join(f"{k}: {v.get('label')} ({v.get('origin')}, {'medical' if v.get('medical') else 'non-medical'})" for k, v in config.models().items() if v.get("label"))}]})
    orgs = {}

    def org_ref(name):
        if not name:
            return None
        if name not in orgs:
            orgs[name] = add({"resourceType": "Organization", "id": _uuid(case_id, "Organization", name), "name": name})
        return _ref("Organization", orgs[name]["id"])
    # documents
    doc_refs = {}
    for d in docs:
        cl = d.get("classification") or {}
        dd = dates.doc_dates(d)
        rid = _uuid(case_id, "DocumentReference", d["doc_id"])
        doc_refs[d["doc_id"]] = rid
        res = {"resourceType": "DocumentReference", "id": rid, "status": "current", "docStatus": DOC_STATUS.get((cl.get("status") or "").upper(), "preliminary"),
               "type": {"text": cl.get("doc_type") or "other"}, "category": [{"text": cl.get("department") or ""}] if cl.get("department") else [],
               "subject": _ref("Patient", patient_id), "date": (dd.get("report") or dd.get("event") or d.get("added") or now),
               "description": cl.get("title") or d.get("filename"),
               "content": [{"attachment": {"contentType": mimetypes.guess_type(d.get("filename") or "")[0] or "application/octet-stream",
                                           "url": f"/api/tb/cases/{case_id}/documents/{d['doc_id']}/file", "title": d.get("rel_path") or d.get("filename")}}],
               "extension": [{"url": f"{BASE_URL}/fhir/StructureDefinition/sha256", "valueString": d.get("sha256") or ""},
                             {"url": f"{BASE_URL}/fhir/StructureDefinition/signed-as-classified", "valueString": cl.get("signed") or "unknown"},
                             {"url": f"{BASE_URL}/fhir/StructureDefinition/read-by", "valueString": ", ".join(sorted({p.get("method") or "" for p in d.get("pages") or []}))}]}
        if dd.get("event"):
            res["context"] = {"period": {"start": dd["event"]}}
        add(res)
    # verified fields as Observations (every verified entry, not only the current one)
    obs_by_field = {}
    for fid, f in facts.items():
        for e in f.get("history") or []:
            if e.get("verification") not in rules.VERIFIED or e.get("state", "present") != "present" or not e.get("value") or fid in STAGE_FIELDS:
                continue
            rid = _uuid(case_id, "Observation", fid, e["doc_id"])
            code = {"text": cat.get(fid, {}).get("label", fid)}
            if fid in LOINC:
                code["coding"] = [{"system": "http://loinc.org", "code": LOINC[fid][0], "display": LOINC[fid][1]}]
            res = {"resourceType": "Observation", "id": rid, "status": "final" if e.get("doc_final") else "preliminary", "code": code,
                   "subject": _ref("Patient", patient_id), "effectiveDateTime": e.get("date") or None,
                   "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": CATEGORY.get(e.get("doc_type") or "", "exam")}]}],
                   "derivedFrom": [_ref("DocumentReference", doc_refs[e["doc_id"]])] if e["doc_id"] in doc_refs else [],
                   "note": [{"text": f"Quote from the report: \"{e.get('quote') or ''}\"" + (f" (confirmed by {e['confirmed_by']})" if e.get("confirmed_by") else "")}]}
            q = _quantity(e["value"])
            if fid == "ecog" and str(e["value"]).strip().isdigit():
                res["valueInteger"] = int(str(e["value"]).strip())
            elif q:
                res["valueQuantity"] = q
                res["note"].append({"text": f"Value as written: {e['value']}"})
            else:
                res["valueString"] = e["value"]
            if fid == "ecog":
                res["meta"] = {"profile": ["http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-ecog-performance-status"]}
            elif fid in ("pdl1", "egfr", "alk", "ros1", "met", "kras", "er", "pr", "her2", "ki67", "mmr", "ras_braf"):
                res["meta"] = {"profile": ["http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-tumor-marker-test"]}
            res = {k: v for k, v in res.items() if v is not None}
            add(res); obs_by_field.setdefault(fid, []).append(rid)
    # the primary cancer as recorded, with the stage as recorded
    cond_id = None
    hist = (facts.get("histologic_type") or {}).get("current")
    if hist and hist.get("verification") in rules.VERIFIED and hist.get("doc_final"):
        cond_id = _uuid(case_id, "Condition")
        cond = {"resourceType": "Condition", "id": cond_id, "meta": {"profile": ["http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-primary-cancer-condition"]},
                "code": {"text": hist["value"]}, "subject": _ref("Patient", patient_id), "recordedDate": hist.get("date") or None,
                "evidence": [{"detail": [_ref("DocumentReference", doc_refs[hist["doc_id"]])]}] if hist["doc_id"] in doc_refs else [],
                "note": [{"text": f"Histologic type as recorded in {hist.get('doc_title')}: \"{hist.get('quote') or ''}\". Protocol: {case.get('protocol') or 'not listed'}."}]}
        stage = postboard.recorded_stage(facts)
        if stage:
            cond["stage"] = [{"summary": {"text": stage["value"]}, "type": {"text": "stage as recorded in a signed report (copied, never derived)"},
                              "assessment": [_ref("DocumentReference", doc_refs[stage["doc_id"]])] if stage["doc_id"] in doc_refs else []}]
        cond = {k: v for k, v in cond.items() if v is not None}
        add(cond)
    # open requests and board actions as Tasks
    task_ids = []
    for a in st.get("actions") or []:
        rid = _uuid(case_id, "Task", a["id"])
        task = {"resourceType": "Task", "id": rid, "status": "completed" if a.get("status") == "completed" else "requested", "intent": "order",
                "code": {"text": a.get("label") or ""}, "description": a.get("what") or "", "for": _ref("Patient", patient_id),
                "authoredOn": a.get("created") or now, "restriction": {"period": {"end": a.get("due")}} if a.get("due") else None,
                "reasonCode": {"text": "Pre-Authorization gap" if a.get("source") == "pre_authorization" else "Tumour Board action"}}
        o = org_ref(a.get("department"))
        if o:
            task["owner"] = o
        task = {k: v for k, v in task.items() if v is not None}
        add(task); task_ids.append((a, rid))
    # board records as CarePlans (the clinicians' record, exported as written) and the patient communication
    plan_ids = []
    for b in st.get("board_records") or []:
        rid = _uuid(case_id, "CarePlan", b["id"])
        plan = {"resourceType": "CarePlan", "id": rid, "status": "active" if (b.get("outcome_type") or "decision") == "decision" else "draft", "intent": "plan",
                "title": f"Tumour Board record {b.get('board_date') or (b.get('recorded_at') or '')[:10]} ({decision_record.OUTCOMES.get(b.get('outcome_type') or 'decision', 'Decision recorded')})",
                "description": b.get("decision_text") or "", "subject": _ref("Patient", patient_id), "created": b.get("recorded_at"),
                "author": {"display": b.get("recorded_by") or b.get("entered_by") or ""},
                "activity": [{"reference": _ref("Task", t)} for a, t in task_ids if a.get("board_record") == b["id"]],
                "note": [{"text": f"Participants: {b.get('participants') or ''}"}, {"text": f"Version {b.get('version', 1)}; adjudication status: {(b.get('adjudication') or {}).get('status')}"}]
                        + ([{"text": f"Divergent opinions: {b['divergent_opinions']}"}] if b.get("divergent_opinions") else [])
                        + [{"text": line} for line in care_plan_lines(b)]}
        if cond_id:
            plan["addresses"] = [_ref("Condition", cond_id)]
        add(plan); plan_ids.append(rid)
        if b.get("patient_informed_date"):
            add({"resourceType": "Communication", "id": _uuid(case_id, "Communication", b["id"]), "status": "completed", "subject": _ref("Patient", patient_id),
                 "sent": b["patient_informed_date"], "basedOn": [_ref("CarePlan", rid)],
                 "note": [{"text": f"Patient informed of the Tumour Board outcome by {b.get('informed_by') or 'the lead clinician'}" + (f"; key worker: {b['key_worker']}" if b.get("key_worker") else "")}]})
    # Composition: the NCG sections from the stored summary (sentences with quotes), plus the check, the records and the registry abstract
    summ = (st.get("artefacts") or {}).get("summary") or {}
    sections = []
    for sec in summ.get("sections") or []:
        lines = [x["text"] + " " + " ".join(f"[{c.get('doc_title') or c.get('doc_id')}: \"{c.get('quote')}\"]" for c in x.get("citations") or []) for x in sec.get("sentences") or []]
        sections.append({"title": sec.get("title"), "text": {"status": "generated", "div": _xhtml("\n".join(lines) or "Not documented")}})
    gate = st.get("gate") or {}
    if gate:
        lines = [f"{r['label']} ({r['department']}): {r['status']}" + (f"; {'; '.join(r.get('problems') or [])}" if r.get("problems") else "") for r in gate.get("requirements") or []]
        sections.append({"title": f"Pre-Authorization check: {gate.get('satisfied')} of {gate.get('total')} required records met ({'passed' if gate.get('passed') else 'open'})",
                         "text": {"status": "generated", "div": _xhtml("\n".join(lines))}, "entry": [_ref("Task", t) for a, t in task_ids if a.get("source") == "pre_authorization" and a.get("status") != "completed"]})
    if plan_ids:
        sections.append({"title": "Tumour Board records", "text": {"status": "generated", "div": _xhtml(f"{len(plan_ids)} record(s); see the CarePlan resources")}, "entry": [_ref("CarePlan", p) for p in plan_ids]})
    reg = registry_abstract(case_id, st, facts, cat)
    sections.append({"title": "Registry abstract (HBCR 2025 items, as recorded)", "text": {"status": "generated", "div": _xhtml("\n".join(f"{i['label']}: {i['value']}" + (f" [{i['source']}]" if i.get("source") else "") for i in reg["items"]))}})
    reviewed = (summ.get("review") or {}).get("status") == "reviewed"
    comp = {"resourceType": "Composition", "id": _uuid(case_id, "Composition"), "status": "final" if reviewed else "preliminary",
            "type": {"coding": [{"system": "http://loinc.org", "code": "34133-9", "display": "Summarization of episode note"}], "text": "Tumour Board Case File summary"},
            "subject": _ref("Patient", patient_id), "date": now, "author": [_ref("Device", device_id)], "title": f"Tumour Board Case File {case_id}",
            "confidentiality": "R", "section": sections,
            "event": [{"period": {"start": case.get("board_date")}}] if case.get("board_date") else None}
    comp = {k: v for k, v in comp.items() if v is not None}
    entries.insert(0, {"fullUrl": f"urn:uuid:{comp['id']}", "resource": comp})
    out = {"resourceType": "Bundle", "id": _uuid(case_id, "Bundle", now), "type": "document", "timestamp": now, "entry": entries,
           "meta": {"tag": [{"system": f"{BASE_URL}/fhir/tags", "code": "synthetic" if "SYNTHETIC" in (pat.get("name") or "").upper() else "case-file"}]},
           "identifier": {"system": f"{BASE_URL}/fhir/bundle", "value": case_id}}
    out["_note"] = NOTE
    store.audit(case_id, {"kind": "export_fhir", "resources": len(entries), "observations": sum(1 for e in entries if e["resource"]["resourceType"] == "Observation")})
    return out


HBCR_ITEMS = [  # HBCR procedure manual 2025 (ICMR-NCDIR), mandatory items the records can carry; "as recorded" throughout
    ("date_of_first_diagnosis", "Date of first diagnosis (as recorded)", "diagnosis_date_mode"),
    ("method_of_diagnosis", "Method of diagnosis (most valid basis present in the records)", None),
    ("topography_morphology", "Topography and morphology (ICD-O-3)", None),
    ("histologic_type_as_recorded", "Histologic type as recorded", "histologic_type"),
    ("grade_as_recorded", "Grade as recorded", "grade"),
    ("laterality", "Laterality", None),
    ("clinical_extent", "Clinical extent of disease", None),
    ("staging_system_and_stage", "Staging system and stage as recorded", None),
    ("performance_status", "Performance status (ECOG) as recorded", "ecog"),
    ("intention_to_treat", "Intention to treat (as recorded by the board)", None),
]


def registry_abstract(case_id: str, st: dict = None, facts: dict = None, cat: dict = None) -> dict:
    st = st if st is not None else store.get_state(case_id)
    docs = rules.case_docs(case_id, st)
    facts = facts if facts is not None else rules.resolve_facts(docs, st.get("overrides"))
    cat = cat or protocol.facts()
    types = {(d.get("classification") or {}).get("doc_type") for d in docs if d.get("state") == "ready" and rules._is_final(d, st.get("overrides"))}
    items = []

    def cur(fid):
        c = (facts.get(fid) or {}).get("current")
        return c if c and c.get("verification") in rules.VERIFIED and c.get("state", "present") == "present" and c.get("doc_final") else None
    for key, label, fid in HBCR_ITEMS:
        if fid:
            c = cur(fid)
            items.append({"item": key, "label": label, "value": c["value"] if c else "not recorded", "source": f"{c.get('doc_title')} ({c.get('date') or 'date not stated'}): \"{c.get('quote') or ''}\"" if c else "", "doc_id": c["doc_id"] if c else None})
        elif key == "method_of_diagnosis":
            basis = "histology of primary (histopathology report present)" if "histopathology" in types else "cytology (cytology report present)" if "cytology" in types else "clinical / imaging only (no final pathology report in the Case File)"
            items.append({"item": key, "label": label, "value": basis, "source": "which final reports the Case File holds (HBCR item 20 basis order: histology, cytology, clinical)", "doc_id": None})
        elif key == "staging_system_and_stage":
            stage = postboard.recorded_stage(facts)
            items.append({"item": key, "label": label, "value": stage["value"] if stage else "not recorded in a signed report", "source": f"{stage.get('doc_title')}: \"{stage.get('quote') or ''}\"" if stage else "", "doc_id": stage["doc_id"] if stage else None,
                          "note": "copied as recorded; the system never derives a stage"})
        elif key == "intention_to_treat":
            recs = [b for b in st.get("board_records") or [] if b.get("intent_as_recorded")]
            items.append({"item": key, "label": label, "value": recs[-1]["intent_as_recorded"] if recs else "not recorded by the board", "source": f"Tumour Board record {recs[-1]['id']}" if recs else "", "doc_id": None})
        else:
            items.append({"item": key, "label": label, "value": "not coded by the system (hospital coder)", "source": "", "doc_id": None})
    return {"case_id": case_id, "standard": "HBCR procedure manual 2025 (ICMR-NCDIR), mandatory items; values as recorded, never derived",
            "items": items, "generated": store.now_iso()}


def registry_csv(case_id: str) -> str:
    import csv, io
    reg = registry_abstract(case_id)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["case_id", "item", "label", "value", "source", "doc_id"])
    for i in reg["items"]:
        w.writerow([case_id, i["item"], i["label"], i["value"], i.get("source", ""), i.get("doc_id") or ""])
    return buf.getvalue()
