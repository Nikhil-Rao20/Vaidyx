"""Builders for synthetic doc.json records and the small test protocol used by the rules tests."""
import copy

from tumour_board import store

PATIENT = {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-900001", "agesex": "60 Y / M"}

UNIT_PROTOCOL = {
    "id": "unit", "label": "Unit test protocol", "version": "0.0",
    "mandatory": [
        {"id": "histopathology", "label": "Histopathology report", "doc_types": ["histopathology"], "department": "Pathology",
         "required_facts": ["histologic_type"], "sla_days": 5},
        {"id": "ct_thorax", "label": "Diagnostic CT thorax report", "doc_types": ["ct"], "region": "thorax|chest|lung", "department": "Radiology",
         "required_facts": ["lesion_size"], "sla_days": 3},
        {"id": "pdl1", "label": "PD-L1 result", "facts_only": True, "fact_doc_types": ["histopathology", "ihc"], "department": "Pathology",
         "required_facts": ["pdl1"], "sla_days": 7},
        {"id": "restaging_mri", "label": "Restaging MRI pelvis", "doc_types": ["mri"], "region": "pelvis|rect", "department": "Radiology",
         "required_facts": [], "must_postdate_doc_type": "treatment_summary", "applies_if_doc_type_present": "treatment_summary", "sla_days": 7},
    ],
    "optional": [{"id": "prior_imaging", "label": "Prior imaging", "doc_types": ["xray"]}],
    "core_data": [{"id": "diagnosis", "label": "Diagnosis", "facts": ["histologic_type"]}],
}


def unit_protocol():
    return copy.deepcopy(UNIT_PROTOCOL)


def fact(value, verification="verified", state="present", quote=None):
    q = value if quote is None else quote
    return {"value": value, "quote": q, "verification": verification, "reason": None,
            "location": {"page": 0, "start": 0, "end": len(q), "score": 100.0, "matched": q}, "state": state, "polarity": "affirmed"}


def make_doc(doc_id, doc_type, status="FINAL", signed="yes", date="2026-09-01", facts=None, state="ready", title=None, region="",
             identity="match", filename=None, text=None, status_notes=None):
    title = title or f"{doc_type.upper()} REPORT {doc_id}"
    return {"doc_id": doc_id, "filename": filename or f"{doc_type}_{date}.pdf", "rel_path": filename or f"{doc_id}_{doc_type}.pdf", "ext": ".pdf",
            "state": state, "identity": identity, "processed": "2026-10-01T10:00:00",
            "pages": [{"text": text or f"SYNTHETIC\n{title}\nReport status: {status}", "method": "text-layer"}],
            "classification": {"title": title, "department": "", "doc_type": doc_type, "body_region": region, "report_date": date,
                               "status": status, "status_quote": f"Report status: {status}" if status != "UNSTATED" else "",
                               "signed": signed, "signature_quote": "Reported by: Dr. Test" if signed == "yes" else "",
                               "status_notes": status_notes or [], "report_date_iso": date},
            "facts": facts or {}}


def add(case_id, *docs):
    for d in docs:
        store.save_doc(case_id, d)
    store._docs_cache.clear()


def req(gate, rid):
    return next(r for r in gate["requirements"] if r["id"] == rid)


# ---- a synthetic lab report for extract.process_document (model calls replaced by fakes, see conftest.run) ----
TEXT = ("Sahyadri Cancer Institute (SYNTHETIC)\nHAEMATOLOGY REPORT\nPatient SYNTHETIC, Test Patient\nUHID SYN-900001\n"
        "Haemoglobin 11.8 g/dL\nPlatelets 2.45 lakhs/cumm\nWBC Not reported\nReport status: FINAL\n"
        "Reported by: Dr. A. Menon, Consultant Pathologist\nReported on 04/09/2026")
CLS = {"title": "HAEMATOLOGY REPORT", "department": "Laboratory", "doc_type": "lab", "body_region": "", "report_date": "04-Sep-2026",
       "status_quote": "", "signature_quote": "", "signer": "", "patient_name": "Test Patient", "patient_id": "SYN-900001"}
RAW = {"haemoglobin": {"found": True, "value": "11.8 g/dL", "quote": "Haemoglobin 11.8 g/dL"},
       "wbc": {"found": True, "value": "Not reported", "quote": "WBC Not reported"},
       "platelets": {"found": True, "value": "2.45 lakhs/cumm", "quote": "Platelet count 2.45 lakhs/cumm"},
       "creatinine": {"found": True, "value": "0.9 mg/dL", "quote": "Creatinine 0.9 mg/dL"},
       "bilirubin": {"found": False, "value": "", "quote": ""}}
