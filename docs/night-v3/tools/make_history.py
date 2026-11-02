"""Makes the synthetic history of plan item 7.4 (night-v3): decided Case Files across cancers, each with a Case summary, so the similar
Case Files search has past files to show.

    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py --dry-run          the plan and the calls, nothing sent
    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py --dry-run --check  the same plus the preflight (GET only, no login)
    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py                    everything (idempotent: what is done is skipped)
    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py --only HIST-01,HIST-04
    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py --summaries-only
    /data/vaidyx/venv/app/bin/python docs/night-v3/tools/make_history.py --cleanup          archives (never deletes) the HIST files

How (fact sheet /data/vaidyx/night-v3/runs/briefs/7_facts_history.md; research note 07_similar_cases.md section 8.7): no seed change and no
demo HIS rebuild. The running demo HIS (:7130) gets a few reports and two new registrations through its JSON API (write token read in code)
and its screens (the HIS login read in code); Vaidyx (:7000) is used through the normal API with the demo logins read in code from
~/vaidyx/.tb_v2_demo_logins (tb-mdt and the treating doctors; never the Vaidyx admin). Case Files HIST-01 to HIST-13 are made from the HIS,
listed on meetings titled "History (SYNTHETIC) <date>" that are never started (no agent briefs are queued), the outcome of each is recorded
as a plain fixture (no model text, no advice for anyone), the meetings are ended, the Case summaries are built on demand and one decided
file is archived. Seed patients (reports dated Aug to Sep 2026) go to a meeting dated 15/10/2026, so a report added now falls after the
board; run-time patients go to a meeting dated today.

Synthetic data only. Never the real case: every Case File id this script calls is checked against its own allow list first. No password,
token or patient name is printed or written to the report (ids, protocol, setting and seed slot numbers only). Plain words, no em dashes.
Exit code 0 when at least ten eligible decided Case Files with a Case summary exist at the end, else 1 (2 when a preflight check fails).
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
VAIDYX = os.environ.get("TBNIK_BASE_URL", "http://127.0.0.1:7000")
HIS = os.environ.get("TB_HIS_URL", "http://127.0.0.1:7130")
MODELS = (("reasoner", "http://127.0.0.1:8100/v1/models"), ("reader", "http://127.0.0.1:8101/v1/models"))
DEMO_LOGINS = Path.home() / "vaidyx" / ".tb_v2_demo_logins"
HIS_DATA = Path(os.environ.get("TB_HIS_MOCK_DATA") or (REPO / "data" / "his_mock"))
OUT_DIR = Path("/data/vaidyx/night-v3/runs/history")
HEADERS = {"X-Requested-With": "tb-nik"}

PAST_BOARD = "2026-10-15"
HIS_MARK_DATE = "2026-10-16"   # a HIS encounter of a seed patient opened on or after this day was made by this script
TITLE = "History (SYNTHETIC)"
ROOM = "Board room"
MINUTES_PER_CASE = 10
MEETING_TIME = {"past": "10:00", "today": "17:00"}
JOB_POLL, JOB_LIMIT = 3, 20 * 60

# The demo HIS practitioners (Reg. No. VXREG-nnnnn -> prac-vxreg-nnnnn); synthetic people of the fictitious demo hospital.
BREAST_CONSULTANT = "prac-vxreg-20104"   # Breast Surgery, the consultant of the HIS login below
SURG_ONC_CONSULTANT = "prac-vxreg-20101"  # Surgical Oncology
RADIOLOGIST = "prac-vxreg-20201"
PATHOLOGIST = "prac-vxreg-20204"
BIOCHEMIST = "prac-vxreg-20206"
ANAESTHETIST = "prac-vxreg-20210"
HIS_CONSULTANT_LOGIN = "opd.doctor@vaidyx-demo.invalid"  # the only HIS consultant login (Breast Surgery): OPD notes and discharge summaries
HIS_CONSULTANT_DEPARTMENT = "Breast Surgery"

# test key -> (desk department code, the practitioner who reports and signs, the desk flow)
DESK = {
    "mammogram": ("RAD", RADIOLOGIST, "imaging"), "usg_breast_axilla": ("RAD", RADIOLOGIST, "imaging"),
    "mri_brain": ("RAD", RADIOLOGIST, "imaging"), "mri_pelvis": ("RAD", RADIOLOGIST, "imaging"), "cect_neck_tap": ("RAD", RADIOLOGIST, "imaging"),
    "hpe_biopsy": ("PATH", PATHOLOGIST, "block"), "ihc_breast": ("PATH", PATHOLOGIST, "block"),
    "cbc": ("PATH", PATHOLOGIST, "lab"), "lft": ("BIO", BIOCHEMIST, "lab"), "rft": ("BIO", BIOCHEMIST, "lab"),
    "pre_anaesthetic_check": ("ANS", ANAESTHETIST, "consult"),
}

DOCTOR_LOGINS = ("tb-breast-doc", "tb-medonc-doc", "tb-gynonc-doc", "tb-crs-doc", "tb-pulmo-doc")
COORDINATOR = "tb-mdt"
# Existing decided Case Files that only need their Case summary (fact sheet section 2), and the ones counted at the end.
EXISTING_FOR_SUMMARY = ("TB-P01-BOARD", "TB-DEMO-P19", "TB-2026-0002")
ALSO_COUNTED = ("TB-2026-0005", "TB-2026-0006", "TB-2026-0007", "TB-2026-0008")
FORBIDDEN_ID = re.compile(r"^(TB-00[1-8]$|TB-TEST$|E2E-)|bharath", re.I)
SEED_UHID = re.compile(r"^VXH/26/0042(0[1-9]|1\d|2[0-3])$")

RATIONALE = "As recorded by the board (fixture, SYNTHETIC)"
NEXT_STEP = "Treatment dates to be fixed in the OPD (fixture)"
MEMBERS = ["MDT Coordinator (demo)", "Dr Radiology (demo)", "Dr Pathology (demo)", "Dr Medical Oncology (demo)", "Dr Radiation Oncology (demo)"]


def _dec(text, intent, modalities, doctor, sequence=""):
    return {"outcome": "decision", "decision_text": f"The board recorded: {text} as the plan (fixture, SYNTHETIC)", "intent": intent,
            "modalities": list(modalities), "sequence": sequence, "responsible_doctor": doctor}


# ---- the plan table (the orchestrator may edit it) ------------------------------------------------------------------------------------
# meeting: "past" (15/10/2026) or "today". his_before: HIS work done before the Case File is made (only when it does not exist yet).
# post_board: HIS work after the decision, then a re-fetch by the owner's doctor and the Case summary built again with force.
# A visit's "note" is an OPD note on the HIS screen (Breast Surgery visits only: the one HIS consultant login).
PLAN = [
    {"id": "HIST-01", "slot": "P02", "uhid": "VXH/26/004202", "protocol": "breast", "setting": "metastatic", "creator": COORDINATOR,
     "department": "Surgical Oncology", "meeting": "today",
     "his_before": [{"visit": {"department": "Surgical Oncology", "consultant_id": SURG_ONC_CONSULTANT, "visit_type": "follow_up"},
                     "tests": [("mri_brain", {
                         "technique": "MRI brain with intravenous gadolinium contrast (SYNTHETIC).",
                         "comparison": "No earlier study available.",
                         "findings": "Multiple enhancing lesions in both cerebral hemispheres, suspicious for metastases (SYNTHETIC). "
                                     "The largest lesion is 1.8 cm in the right frontal lobe with surrounding oedema. No midline shift.",
                         "impression": "Multiple enhancing lesions in both cerebral hemispheres, suspicious for metastases."})]}],
     "decision": _dec("anti-HER2 systemic therapy and whole-brain radiotherapy", "palliative", ["targeted", "radiotherapy"],
                      "Dr Surgical Oncology (demo)"),
     "post_board": None, "archive": None},
    {"id": "HIST-02", "slot": "P03", "uhid": "VXH/26/004203", "protocol": "breast", "setting": "early", "creator": "tb-breast-doc",
     "meeting": "past",
     "decision": _dec("surgery followed by endocrine therapy", "curative", ["surgery", "endocrine"], "Dr Breast Surgery (demo)",
                      "Surgery, then endocrine therapy"),
     "post_board": {"kind": "discharge_summary", "bed": "2-21",
                    "diagnosis": "Carcinoma breast, early (as recorded) (SYNTHETIC)",
                    "course": "Completed the planned treatment; tolerated well (SYNTHETIC).",
                    "treatment_received": "Wide local excision with sentinel lymph node biopsy on 20/10/2026 (fixture)",
                    "advice": "Review in the Breast Surgery OPD with the final histopathology report (SYNTHETIC)."},
     "archive": None},
    {"id": "HIST-03", "slot": "P04", "uhid": "VXH/26/004204", "protocol": "breast", "setting": "locally_advanced", "creator": "tb-breast-doc",
     "meeting": "past",
     "decision": _dec("neoadjuvant chemotherapy, then surgery", "curative", ["chemotherapy", "surgery"], "Dr Breast Surgery (demo)",
                      "Chemotherapy, then surgery"),
     "post_board": {"kind": "discharge_summary", "bed": "2-22",
                    "diagnosis": "Carcinoma breast, locally advanced (as recorded) (SYNTHETIC)",
                    "course": "Completed the planned treatment for this admission; tolerated well (SYNTHETIC).",
                    "treatment_received": "Doxorubicin and cyclophosphamide, cycle 1 on 21/10/2026 (fixture)",
                    "advice": "Next cycle as planned in the day care unit (SYNTHETIC)."},
     "archive": None},
    {"id": "HIST-04", "slot": None, "uhid": None, "protocol": "breast", "setting": "early", "creator": "tb-breast-doc", "meeting": "today",
     "register": {"name": "Sunita History (SYNTHETIC)", "sex": "F", "age": "44", "kind": "permanent", "town": "Pune", "district": "Pune",
                  "state": "Maharashtra", "pin": "411001"},
     "his_before": [{"visit": {"department": "Breast Surgery", "consultant_id": BREAST_CONSULTANT, "visit_type": "new"},
                     "note": {"presenting_complaint": "Painless lump in the left breast for 2 months",
                              "examination": "Premenopausal woman. ECOG performance status 1. A 2.5 x 2 cm firm lump in the upper outer quadrant "
                                             "of the left breast. No palpable axillary lymph node.",
                              "clinical_question": "Primary management plan",
                              "plan": "Mammogram, USG of both breasts and axillae, core biopsy with IHC, CBC, LFT and RFT. Present at the "
                                      "Tumour Board when the reports are in (SYNTHETIC)."},
                     "tests": [
                         ("mammogram", {"technique": "Bilateral digital mammography, craniocaudal and mediolateral oblique views.",
                                        "comparison": "No earlier study available.",
                                        "findings": "Left breast: an irregular high-density mass with spiculated margins in the upper outer quadrant "
                                                    "measuring 2.6 x 2.2 cm. No suspicious microcalcification. Right breast: no mass.",
                                        "impression": "Left breast upper outer quadrant mass of 2.6 cm, BI-RADS 5."}),
                         ("usg_breast_axilla", {"technique": "High-resolution ultrasound of both breasts and axillae.",
                                                "comparison": "Mammogram of the same day.",
                                                "findings": "Left breast: an irregular hypoechoic mass at 2 o'clock measuring 2.5 x 2.1 cm. "
                                                            "Both axillae: no suspicious lymph node.",
                                                "impression": "Left breast mass, BI-RADS 5. No suspicious axillary lymph node."}),
                         ("hpe_biopsy", {"specimen": "Core biopsy, left breast upper outer quadrant, in 10% buffered formalin",
                                         "gross": "Three linear grey-white cores, 1.0 to 1.4 cm, entirely submitted",
                                         "microscopy": "Cores show an infiltrating carcinoma in solid sheets with marked nuclear pleomorphism "
                                                       "and frequent mitoses.",
                                         "histologic_type": "Invasive breast carcinoma of no special type",
                                         "grade": "Grade 3 (Nottingham score 8)",
                                         "diagnosis": "Left breast core biopsy: invasive breast carcinoma of no special type, grade 3 (SYNTHETIC)."}),
                         ("ihc_breast", {"er": "Negative (Allred score 0/8)", "pr": "Negative (Allred score 0/8)", "her2": "0 (Negative)",
                                         "ki67": "60 %"}),
                         ("cbc", {"haemoglobin": "12.4 gm%", "wbc": "7,200 /cumm", "platelets": "2.8 lakhs/cumm"}),
                         ("lft", {"bilirubin": "0.5 mg/dL", "sgot": "24 U/L", "sgpt": "20 U/L"}),
                         ("rft", {"urea": "22 mg/dL", "creatinine": "0.8 mg/dL"})]}],
     "decision": _dec("chemotherapy and surgery", "curative", ["chemotherapy", "surgery"], "Dr Breast Surgery (demo)"),
     "post_board": None, "archive": None},
    {"id": "HIST-05", "slot": "P05", "uhid": "VXH/26/004205", "protocol": "oral_cavity", "setting": "locally_advanced", "creator": COORDINATOR,
     "department": "ENT / Head and Neck Surgery", "meeting": "past",
     "decision": _dec("surgery with adjuvant radiotherapy", "curative", ["surgery", "radiotherapy"], "Dr ENT / Head and Neck Surgery (demo)",
                      "Surgery, then radiotherapy"),
     "post_board": None, "archive": None},
    {"id": "HIST-06", "slot": "P07", "uhid": "VXH/26/004207", "protocol": "oral_cavity", "setting": "locally_advanced", "creator": COORDINATOR,
     "department": "ENT / Head and Neck Surgery", "meeting": "past",
     "decision": _dec("surgery", "curative", ["surgery"], "Dr ENT / Head and Neck Surgery (demo)"),
     "post_board": None, "archive": "history fixture: archived file for the exclusion test"},
    {"id": "HIST-07", "slot": "P08", "uhid": "VXH/26/004208", "protocol": "cervix", "setting": "locally_advanced", "creator": "tb-gynonc-doc",
     "meeting": "past",
     "decision": _dec("concurrent chemoradiation", "curative", ["chemotherapy", "radiotherapy"], "Dr Gynaecologic Oncology (demo)"),
     "post_board": {"kind": "report",
                    "visit": {"department": "Gynaecologic Oncology", "consultant_id": "", "visit_type": "follow_up"},
                    "tests": [("mri_pelvis", {
                        "technique": "MRI pelvis with intravenous contrast (SYNTHETIC).",
                        "comparison": "Baseline MRI pelvis of September 2026.",
                        "findings": "Interim study during chemoradiation started on 19/10/2026 (fixture). The cervical mass is smaller than on "
                                    "the baseline study. No new pelvic lymph node. No hydronephrosis. (SYNTHETIC)",
                        "impression": "Interim study: the cervical mass is smaller than on the baseline study (SYNTHETIC)."})]},
     "archive": None},
    {"id": "HIST-08", "slot": "P10", "uhid": "VXH/26/004210", "protocol": "cervix", "setting": "locally_advanced", "creator": "tb-gynonc-doc",
     "meeting": "past",
     "decision": {"outcome": "deferred", "awaited": "MRI pelvis report", "awaited_from": "Radiology",
                  "decision_text": "Deferred until the MRI pelvis report is in the Case File (fixture, SYNTHETIC)",
                  "responsible_doctor": "Dr Gynaecologic Oncology (demo)"},
     "post_board": None, "archive": None},
    {"id": "HIST-09", "slot": "P12", "uhid": "VXH/26/004212", "protocol": "lung_nsclc", "setting": "non_metastatic", "creator": "tb-medonc-doc",
     "meeting": "past",
     "decision": _dec("surgery", "curative", ["surgery"], "Dr Medical Oncology (demo)"), "post_board": None, "archive": None},
    {"id": "HIST-10", "slot": "P13", "uhid": "VXH/26/004213", "protocol": "lung_nsclc", "setting": "non_metastatic", "creator": "tb-medonc-doc",
     "meeting": "past",
     "decision": _dec("chemotherapy and radiotherapy", "curative", ["chemotherapy", "radiotherapy"], "Dr Medical Oncology (demo)"),
     "post_board": None, "archive": None},
    {"id": "HIST-11", "slot": "P16", "uhid": "VXH/26/004216", "protocol": "colorectal_rectum", "setting": "non_metastatic", "creator": "tb-crs-doc",
     "meeting": "past",
     "decision": _dec("chemoradiation, then surgery", "curative", ["chemotherapy", "radiotherapy", "surgery"], "Dr Colorectal Surgery (demo)",
                      "Chemotherapy and radiotherapy, then surgery"),
     "post_board": None, "archive": None},
    {"id": "HIST-12", "slot": None, "uhid": None, "protocol": "generic", "setting": "as_recorded", "cancer_name": "Papillary thyroid carcinoma",
     "creator": COORDINATOR, "department": "Surgical Oncology", "meeting": "today",
     "register": {"name": "Prakash History (SYNTHETIC)", "sex": "M", "age": "62", "kind": "permanent", "town": "Nashik", "district": "Nashik",
                  "state": "Maharashtra", "pin": "422001"},
     "his_before": [{"visit": {"department": "Surgical Oncology", "consultant_id": SURG_ONC_CONSULTANT, "visit_type": "new"},
                     "tests": [
                         ("hpe_biopsy", {"specimen": "Core biopsy, right lobe of thyroid, in 10% buffered formalin",
                                         "gross": "Two linear grey-white cores, 0.8 and 1.0 cm, entirely submitted",
                                         "microscopy": "Papillary architecture with nuclear clearing, nuclear grooves and pseudo-inclusions.",
                                         "histologic_type": "Papillary thyroid carcinoma, classic type",
                                         "diagnosis": "Right thyroid lobe core biopsy: papillary thyroid carcinoma, classic type (SYNTHETIC)."}),
                         ("cect_neck_tap", {"technique": "CECT of the neck, thorax, abdomen and pelvis with intravenous contrast.",
                                            "comparison": "No earlier study available.",
                                            "findings": "A 2.4 cm heterogeneously enhancing nodule in the right lobe of the thyroid. No enlarged "
                                                        "cervical lymph node. No lung nodule. No liver or bone lesion. No distant disease seen.",
                                            "impression": "Right thyroid lobe nodule of 2.4 cm without cervical lymph nodes or distant disease.",
                                            "recorded_stage": "cT2 N0 M0 (as recorded)"}),
                         ("pre_anaesthetic_check", {"presenting_complaint": "Pre-operative assessment, swelling in the front of the neck for 4 months",
                                                    "examination": "ECOG performance status 1. Airway assessment normal. Heart and lungs normal.",
                                                    "plan": "Fit for general anaesthesia (SYNTHETIC).", "ecog": "1"})]}],
     "decision": _dec("surgery", "curative", ["surgery"], "Dr Surgical Oncology (demo)"), "post_board": None, "archive": None},
    {"id": "HIST-13", "slot": "P15", "uhid": "VXH/26/004215", "protocol": "lung_nsclc", "setting": "non_metastatic", "creator": "tb-medonc-doc",
     "meeting": "past",
     "decision": _dec("radiotherapy", "curative", ["radiotherapy"], "Dr Medical Oncology (demo)"), "post_board": None, "archive": None},
]


# ---- pure helpers (unit tested) -----------------------------------------------------------------------------------------------------

def meeting_date(key, today=None):
    return PAST_BOARD if key == "past" else (today or date.today()).isoformat()


def meeting_title(key, today=None):
    d = meeting_date(key, today)
    return f"{TITLE} {d[8:10]}/{d[5:7]}/{d[:4]}"


def decision_body(row, today=None):
    """The fixture body for POST /meetings/{mid}/cases/{cid}/decision: the row's fields plus the fixed ones. The dates: tell the patient by
    the board date plus one day; told on that day, or today when that day is still ahead (never before the board date, never in the
    future); the next step one week after the board."""
    today = today or date.today()
    board = date.fromisoformat(meeting_date(row["meeting"], today))
    told = min(board + timedelta(days=1), max(today, board))
    doctor = row["decision"]["responsible_doctor"]
    body = {"rationale": RATIONALE, "members_present": list(dict.fromkeys(MEMBERS + [doctor])),
            "informed_by": doctor, "inform_by_date": (board + timedelta(days=1)).isoformat(), "patient_informed_date": told.isoformat(),
            "next_step": NEXT_STEP if row["decision"]["outcome"] == "decision" else "Re-list at the next board when the report is in (fixture)",
            "next_step_date": (board + timedelta(days=7)).isoformat()}
    body.update({k: v for k, v in row["decision"].items() if v not in ("", None)})
    return body


def discharge_course(pb):
    """The discharge summary screen takes diagnosis, course and advice only: the treatment received joins the course."""
    return f"{pb['course']} Treatment received: {pb['treatment_received']}." if pb.get("treatment_received") else pb["course"]


def owner_login(row):
    return row["creator"]


def allowed_ids(plan=None):
    return {r["id"] for r in (plan or PLAN)} | set(EXISTING_FOR_SUMMARY) | set(ALSO_COUNTED)


def check_id(cid, plan=None):
    """Every Case File id this script calls passes here first: its own HIST ids and the named demo files only, never the real case."""
    cid = str(cid or "")
    if FORBIDDEN_ID.search(cid) or cid not in allowed_ids(plan):
        raise SystemExit(f"make_history: refused to touch Case File {cid!r} (not on the script's own list)")
    return cid


def select(only):
    """The plan rows and the existing files named by --only (all when empty)."""
    if not only:
        return list(PLAN), list(EXISTING_FOR_SUMMARY)
    want = [x.strip() for x in only.split(",") if x.strip()]
    unknown = [x for x in want if x not in allowed_ids() or x in ALSO_COUNTED]
    if unknown:
        raise SystemExit(f"make_history: unknown id in --only: {', '.join(unknown)}")
    return [r for r in PLAN if r["id"] in want], [x for x in EXISTING_FOR_SUMMARY if x in want]


def plan_lines(rows, existing, today=None):
    """The dry-run text: one block per row with the calls it would make (no names, no UHIDs beyond the seed slot)."""
    out = []
    for r in rows:
        who = r["creator"] + (f" for {r['department']}" if r.get("department") else "")
        src = f"seed {r['slot']}" if r.get("slot") else "run-time registration"
        out.append(f"{r['id']}: {r['protocol']} / {r['setting']}" + (f" ({r['cancer_name']})" if r.get("cancer_name") else "")
                   + f", {src}, created by {who}, meeting {meeting_title(r['meeting'], today)}")
        if r.get("register"):
            out.append(f"  HIS  GET /his/api/search (by the synthetic name); POST /his/api/registrations ({r['register']['sex']}, {r['register']['age']}) if absent")
        for blk in r.get("his_before") or []:
            out.append(f"  HIS  POST /his/api/patients/{{pid}}/visits ({blk['visit']['department']}) if no visit of this script exists")
            if blk.get("note"):
                out.append(f"  HIS  POST /his/encounters/{{eid}}/notes (OPD note on the screen, HIS login read in code)")
            for test, _ in blk.get("tests") or []:
                dept, _, flow = DESK[test]
                steps = {"imaging": "schedule, preliminary, sign", "lab": "collect, preliminary, sign", "block": "collect (block No.), sign",
                         "consult": "sign"}[flow]
                out.append(f"  HIS  order {test}; /desk/api/{dept}/orders/{{oid}}: {steps}")
        out.append(f"  VX   POST /api/tb/cases/from-his {{identifier, protocol {r['protocol']}, setting {r['setting']}, case_id {r['id']}"
                   + (f", department {r['department']}" if r.get("department") else "") + (", cancer_name" if r.get("cancer_name") else "")
                   + f", board_date {meeting_date(r['meeting'], today)}}} as {r['creator']}; GET /api/tb/jobs/{{job}} every {JOB_POLL} s")
        out.append(f"  VX   PUT /api/tb/meetings/{{mid}}/agenda (discussion) as {COORDINATOR}")
        body = decision_body(r, today)
        out.append(f"  VX   POST /api/tb/meetings/{{mid}}/cases/{r['id']}/decision outcome {body['outcome']}"
                   + (f", intent {body['intent']}, modalities {', '.join(body['modalities'])}" if body["outcome"] == "decision" else
                      f", awaited {body['awaited']} from {body['awaited_from']}"))
        pb = r.get("post_board")
        if pb:
            if pb["kind"] == "discharge_summary":
                out.append(f"  HIS  POST /his/api/patients/{{pid}}/admissions ({HIS_CONSULTANT_DEPARTMENT}, bed {pb['bed']}); "
                           "POST /his/encounters/{eid}/discharge-summary (screen); POST /his/api/encounters/{eid}/discharge")
            else:
                out.append(f"  HIS  POST /his/api/patients/{{pid}}/visits ({pb['visit']['department']}); "
                           + "; ".join(f"order {t} and report it at /desk/api/{DESK[t][0]}" for t, _ in pb["tests"]))
            out.append(f"  VX   POST /api/tb/cases/{r['id']}/his/refetch as {owner_login(r)}; wait for the job")
        out.append(f"  VX   POST /api/tb/cases/{r['id']}/case-summary" + (" {force: true}" if pb else "") + f" as {COORDINATOR}")
        if r.get("archive"):
            out.append(f"  VX   POST /api/tb/cases/{r['id']}/archive {{reason}} as {COORDINATOR}")
    for cid in existing:
        out.append(f"{cid}: existing decided Case File: POST /api/tb/cases/{cid}/case-summary as {COORDINATOR} when none exists")
    for key in sorted({r["meeting"] for r in rows}):
        out.append(f"meeting {meeting_title(key, today)}: POST /api/tb/meetings {{date {meeting_date(key, today)}, time {MEETING_TIME[key]}, "
                   f"room {ROOM}, video false, minutes_per_case {MINUTES_PER_CASE}}} when none is planned; never started; POST /end after the decisions")
    return out


# ---- secrets, read in code and never printed ------------------------------------------------------------------------------------------

def demo_password(user):
    """The demo login's password (the file is whitespace separated: username, password, then words)."""
    if not DEMO_LOGINS.exists():
        raise Failed(f"the demo logins file {DEMO_LOGINS} is missing")
    for line in DEMO_LOGINS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == user:
            return parts[1]
    raise Failed(f"no demo login for {user} in {DEMO_LOGINS}")


def his_write_token():
    tok = HIS_DATA / "write_token"
    if not tok.exists():
        raise Failed("the demo HIS write token is missing")
    return tok.read_text(encoding="utf-8").strip()


def his_login_password(email):
    """data/his_mock/logins.tsv: email, roles, password (tab separated), as tumour_board/eval/e2e_nik.py reads it."""
    path = HIS_DATA / "logins.tsv"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if line.strip() and not line.startswith("#") and len(parts) > 2 and parts[0].strip() == email:
                return parts[2].strip()
    raise Failed(f"no demo HIS login for {email}")


class Failed(Exception):
    """A step failed; the message is plain words and never carries a password, a token or a patient name."""


def j(r):
    try:
        return r.json()
    except ValueError:
        return {}


def detail(r):
    b = j(r)
    d = b.get("detail") if isinstance(b, dict) else None
    if isinstance(d, list):
        d = "; ".join(str(x.get("msg") if isinstance(x, dict) else x) for x in d)
    return str(d or b.get("error") if isinstance(b, dict) else "")[:200] if (d or isinstance(b, dict)) else ""


# ---- the run ------------------------------------------------------------------------------------------------------------------------

class Run:
    def __init__(self, args, rows, existing):
        self.args, self.rows, self.existing = args, rows, existing
        self.today = date.today()
        self.vx = {}
        self.his_c = None
        self.his_screen_c = None
        self.depts = {}
        self.report = {r["id"]: {"id": r["id"], "slot": r.get("slot") or "run-time", "protocol": r["protocol"], "setting": r["setting"],
                                 "department": r.get("department") or "", "creator": r["creator"], "meeting": meeting_title(r["meeting"], self.today),
                                 "steps": []} for r in rows}
        self.state = self._load_state()
        self.failures = []

    # -- bookkeeping
    def note(self, cid, text):
        print(f"{cid}: {text}", flush=True)
        if cid in self.report:
            self.report[cid]["steps"].append(text)

    def fail(self, cid, text):
        self.failures.append(f"{cid}: {text}")
        self.note(cid, "FAILED " + text)

    def _load_state(self):
        try:
            return json.loads((OUT_DIR / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = OUT_DIR / "state.json.tmp"
        tmp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        tmp.replace(OUT_DIR / "state.json")

    # -- clients
    def login(self, user):
        if user in self.vx:
            return self.vx[user]
        if user not in (COORDINATOR,) + DOCTOR_LOGINS:
            raise Failed(f"{user} is not a login this script uses")
        c = httpx.Client(base_url=VAIDYX, timeout=120, headers=HEADERS)
        r = None
        for _ in range(4):
            r = c.post("/api/auth/login", json={"username": user, "password": demo_password(user), "remember": False})
            if r.status_code != 429:
                break
            time.sleep(20)  # the sign-in limiter (15 a minute per address)
        if r.status_code != 200 or not c.cookies.get("vaidyx_session"):
            c.close()
            raise Failed(f"sign-in as {user} refused (HTTP {r.status_code})")
        self.vx[user] = c
        return c

    def his(self):
        if self.his_c is None:
            self.his_c = httpx.Client(base_url=HIS, timeout=120, headers={"Authorization": f"Bearer {his_write_token()}"})
        return self.his_c

    def his_screen(self):
        if self.his_screen_c is None:
            c = httpx.Client(base_url=HIS, timeout=120)
            r = c.post("/his/login", data={"email": HIS_CONSULTANT_LOGIN, "password": his_login_password(HIS_CONSULTANT_LOGIN), "next": "/his"},
                       follow_redirects=False)
            if r.status_code != 303 or not c.cookies.get("vxhis_session"):
                c.close()
                raise Failed(f"HIS screen sign-in refused (HTTP {r.status_code})")
            self.his_screen_c = c
        return self.his_screen_c

    def close(self):
        for c in list(self.vx.values()) + [self.his_c, self.his_screen_c]:
            if c is not None:
                c.close()

    # -- Vaidyx calls on a Case File (always through check_id)
    def case_get(self, user, cid, suffix=""):
        return self.login(user).get(f"/api/tb/cases/{check_id(cid)}{suffix}")

    def case_post(self, user, cid, suffix, body=None, timeout=None):
        kw = {"json": body if body is not None else {}}
        if timeout:
            kw["timeout"] = timeout
        return self.login(user).post(f"/api/tb/cases/{check_id(cid)}{suffix}", **kw)

    def wait_job(self, user, jid):
        c, t0 = self.login(user), time.time()
        while time.time() - t0 < JOB_LIMIT:
            b = j(c.get(f"/api/tb/jobs/{jid}"))
            if b.get("state") in ("finished", "failed", "interrupted"):
                return b, round(time.time() - t0)
            time.sleep(JOB_POLL)
        return {"state": "timeout"}, round(time.time() - t0)

    # -- preflight (GET only)
    def preflight(self, with_login=True):
        ok = True
        for name, url in (("Vaidyx", f"{VAIDYX}/api/health"), ("demo HIS", f"{HIS}/health")) + tuple(MODELS):
            try:
                up = httpx.get(url, timeout=10).status_code == 200
            except httpx.HTTPError:
                up = False
            print(f"preflight: {name} {'up' if up else 'DOWN'}")
            ok = ok and up
        if not ok:
            return False
        if not with_login:
            return True
        ms = j(self.login(COORDINATOR).get("/api/tb/meetings")).get("meetings") or []
        running = [m["id"] for m in ms if m.get("status") == "in_session"]
        ours_running = [m["id"] for m in ms if m.get("status") == "in_session" and str(m.get("title") or "").startswith(TITLE)]
        ours = [m["id"] for m in ms if str(m.get("title") or "").startswith(TITLE)]
        print(f"preflight: {len(ms)} meetings, {len(running)} in session ({', '.join(running) or 'none'}), {len(ours)} of this script")
        if ours_running:
            print(f"preflight: a meeting titled {TITLE!r} is in session ({', '.join(ours_running)}): end it first; nothing done")
            return False
        org = j(self.login(COORDINATOR).get("/api/tb/org")).get("departments") or {}
        rows = org.values() if isinstance(org, dict) else org
        self.depts = {str(d.get("name") or ""): d for d in rows if isinstance(d, dict) and d.get("group", "treating") == "treating"}
        return True

    def department(self, name):
        """The department name the organisation knows; Surgical Oncology when the row's name is not one."""
        if not name or not self.depts or name in self.depts:
            return name
        low = name.lower()
        hit = next((n for n in self.depts if n.lower().startswith(low) or low.startswith(n.lower())), None)
        got = hit or "Surgical Oncology"
        print(f"department {name!r} not known by that name: using {got!r}")
        return got

    # -- the demo HIS
    def his_patient(self, row):
        """(pid, uhid) of the row's HIS registration; a run-time one is found by its synthetic name or registered."""
        h = self.his()
        q = row["uhid"] or row["register"]["name"]
        b = j(h.get("/his/api/search", params={"q": q}))
        pats = [p for p in b.get("patients") or [] if (p.get("uhid") == row["uhid"] if row["uhid"] else p.get("name") == row["register"]["name"])]
        if pats:
            p = sorted(pats, key=lambda x: x.get("registered_on") or "")[0]
            return p["id"], p["uhid"]
        if row["uhid"]:
            raise Failed(f"seed patient {row['slot']} not found in the demo HIS")
        r = h.post("/his/api/registrations", json=row["register"])
        if r.status_code == 409 and j(r).get("error") == "duplicate":  # a similar synthetic registration: confirmed as a different person
            r = h.post("/his/api/registrations", json={**row["register"], "confirm_duplicate": "1"})
        p = j(r).get("patient") or {}
        if r.status_code != 200 or not p.get("uhid"):
            raise Failed(f"HIS registration refused (HTTP {r.status_code}: {detail(r)})")
        self.note(row["id"], "HIS: run-time patient registered")
        return p["id"], p["uhid"]

    def _our_encounter(self, pid, kind, department, first_test=None):
        encs = (j(self.his().get(f"/his/api/patients/{pid}")).get("encounters") or [])
        for e in encs:
            day = str(e.get("date") or e.get("admitted") or "")[:10]
            if e.get("kind") != kind or e.get("department") != department or day < HIS_MARK_DATE:
                continue
            tests = {o.get("test") for o in e.get("orders") or []}
            if first_test is None or first_test in tests:
                return e
        return None

    def his_block(self, cid, pid, blk):
        """A visit with its orders (and an OPD note), each reported and signed at the desk; what is already done is skipped."""
        h = self.his()
        v = blk["visit"]
        first = (blk.get("tests") or [(None, None)])[0][0] or ("opd_note" if blk.get("note") else None)
        e = self._our_encounter(pid, "OP", v["department"], first)
        if e is None:
            body = {k: x for k, x in {"department": v["department"], "consultant_id": v.get("consultant_id"), "unit": "Unit I",
                                      "visit_type": v.get("visit_type") or "new"}.items() if x}
            r = h.post(f"/his/api/patients/{pid}/visits", json=body)
            e = j(r).get("encounter") or {}
            if r.status_code != 200 or not e.get("id"):
                raise Failed(f"HIS visit refused (HTTP {r.status_code}: {detail(r)})")
            self.note(cid, f"HIS: OP visit opened in {v['department']}")
        eid = e["id"]
        have = {o.get("test"): o for o in e.get("orders") or []}
        if blk.get("note") and not have.get("opd_note"):
            if v["department"] != HIS_CONSULTANT_DEPARTMENT:
                raise Failed(f"no HIS consultant login for {v['department']}: the OPD note cannot be signed")
            s = self.his_screen()
            m = re.search(r'name="csrf" value="([^"]+)"', s.get(f"/his/encounters/{eid}").text)
            if not m:
                raise Failed("no form token on the HIS encounter page")
            r = s.post(f"/his/encounters/{eid}/notes", follow_redirects=False,
                       data={"csrf": m.group(1), **{f"v_{k}": x for k, x in blk["note"].items()}})
            if r.status_code != 303 or "error" in r.headers.get("location", "").lower():
                raise Failed(f"OPD note refused on the HIS screen (HTTP {r.status_code})")
            self.note(cid, "HIS: OPD note signed")
        new = [t for t, _ in blk.get("tests") or [] if t not in have]
        if new:
            r = h.post(f"/his/api/encounters/{eid}/orders", json={"tests": new})
            if r.status_code != 200:
                raise Failed(f"HIS orders refused (HTTP {r.status_code}: {detail(r)})")
            for o in j(r).get("orders") or []:
                have[o["test"]] = o
        for test, values in blk.get("tests") or []:
            self.desk(cid, have[test], test, values)
        return eid

    def desk(self, cid, order, test, values):
        dept, prac, flow = DESK[test]
        status = order.get("status") or "ordered"
        rep = (order.get("report") or {}) if isinstance(order.get("report"), dict) else {}
        if rep.get("status") in ("final", "amended"):
            return
        h, oid, base = self.his(), order["id"], f"/desk/api/{dept}/orders/{order['id']}"
        calls = []
        if rep.get("status") != "preliminary":
            if flow == "imaging" and status == "ordered":
                calls.append(("schedule", {"date": self.today.isoformat(), "by": "radiology technician"}))
            if flow == "lab" and status == "ordered":
                calls.append(("collect", {"by": "lab technician"}))
            if flow == "block" and status == "ordered":
                calls.append(("collect", {"block_no": f"{order.get('accession') or oid}-A1", "by": "pathology technician"}))
            if flow in ("imaging", "lab"):
                calls.append(("preliminary", {"reporter": prac, "values": values}))
        calls.append(("sign", {"signer": prac} if flow in ("imaging", "lab") else {"signer": prac, "values": values}))
        for step, body in calls:
            r = h.post(f"{base}/{step}", json=body)
            if r.status_code != 200:
                raise Failed(f"HIS {test} {step} refused (HTTP {r.status_code}: {detail(r)})")
        self.note(cid, f"HIS: {test} reported and signed")

    def his_post_board(self, row, pid):
        pb, cid = row["post_board"], row["id"]
        if pb["kind"] == "report":
            self.his_block(cid, pid, {"visit": pb["visit"], "tests": pb["tests"]})
            return
        h = self.his()
        e = self._our_encounter(pid, "IP", HIS_CONSULTANT_DEPARTMENT)
        if e is None:
            r = h.post(f"/his/api/patients/{pid}/admissions", json={"department": HIS_CONSULTANT_DEPARTMENT, "consultant_id": BREAST_CONSULTANT,
                                                                 "unit": "Unit I", "ward": "Surgical Ward 2", "bed": pb["bed"]})
            e = j(r).get("encounter") or {}
            if r.status_code != 200 or not e.get("id"):
                raise Failed(f"HIS admission refused (HTTP {r.status_code}: {detail(r)})")
            self.note(cid, f"HIS: admitted in {HIS_CONSULTANT_DEPARTMENT}")
        eid = e["id"]
        if not any(o.get("test") == "discharge_summary" for o in e.get("orders") or []):
            s = self.his_screen()
            m = re.search(r'name="csrf" value="([^"]+)"', s.get(f"/his/encounters/{eid}").text)
            if not m:
                raise Failed("no form token on the HIS admission page")
            r = s.post(f"/his/encounters/{eid}/discharge-summary", follow_redirects=False,
                       data={"csrf": m.group(1), "v_diagnosis": pb["diagnosis"], "v_course": discharge_course(pb), "v_advice": pb["advice"]})
            if r.status_code != 303 or "Discharge summary signed" not in httpx.QueryParams(r.headers.get("location", "").partition("?")[2]).get("msg", "") \
                    and "Discharge+summary+signed" not in r.headers.get("location", "") and "Discharge%20summary%20signed" not in r.headers.get("location", ""):
                raise Failed(f"discharge summary refused on the HIS screen (HTTP {r.status_code})")
            self.note(cid, "HIS: discharge summary signed")
        e = j(h.get(f"/his/api/encounters/{eid}"))
        if e.get("status") == "in-progress":
            r = h.post(f"/his/api/encounters/{eid}/discharge", json={})
            if r.status_code != 200:
                raise Failed(f"HIS discharge refused (HTTP {r.status_code}: {detail(r)})")
            self.note(cid, "HIS: discharged")

    # -- Vaidyx steps
    def exists(self, cid):
        r = self.case_get(COORDINATOR, cid)
        return j(r) if r.status_code == 200 else None

    def make_files(self):
        jobs = {}
        for row in self.rows:
            cid = row["id"]
            try:
                if self.exists(cid):
                    self.note(cid, "Case File exists: creation skipped")
                    continue
                pid, uhid = self.his_patient(row)
                for blk in row.get("his_before") or []:
                    self.his_block(cid, pid, blk)
                body = {"identifier": uhid, "protocol": row["protocol"], "setting": row["setting"], "hospital_level": "optimal",
                        "case_id": cid, "board_date": meeting_date(row["meeting"], self.today)}
                if row.get("department"):
                    body["department"] = self.department(row["department"])
                if row.get("cancer_name"):
                    body["cancer_name"] = row["cancer_name"]
                r = self.login(row["creator"]).post("/api/tb/cases/from-his", json=body)
                b = j(r)
                if r.status_code == 409 and isinstance(b.get("existing"), dict):
                    self.fail(cid, f"the patient has a Case File already under {b['existing'].get('case_id')}: skipped")
                    continue
                if r.status_code != 200 or not b.get("job"):
                    self.fail(cid, f"from-his refused (HTTP {r.status_code}: {detail(r)})")
                    continue
                jobs[cid] = (row["creator"], b["job"])
                self.note(cid, f"Case File created, reading {b.get('total')} records")
            except Failed as e:
                self.fail(cid, str(e))
        for cid, (user, jid) in jobs.items():
            job, secs = self.wait_job(user, jid)
            d = j(self.case_get(COORDINATOR, cid)).get("documents") or []
            errs = sum(1 for x in d if x.get("state") == "error")
            self.report[cid].update(documents=len(d), document_errors=errs, read_seconds=job.get("seconds") or secs)
            self.note(cid, f"reading {job.get('state')}: {len(d)} documents, {errs} in error, {job.get('seconds') or secs} s")

    def _history_meetings(self):
        return [m for m in j(self.login(COORDINATOR).get("/api/tb/meetings")).get("meetings") or []
                if str(m.get("title") or "").startswith(TITLE) and m.get("status") != "cancelled"]

    def _view(self, mid):
        return j(self.login(COORDINATOR).get(f"/api/tb/meetings/{mid}"))

    @staticmethod
    def _agenda_ids(view):
        return [x.get("case_id") for k in ("discussion", "noting") for x in (view.get("agenda") or {}).get(k) or [] if x.get("case_id")]

    def meetings_and_decisions(self):
        mdt = self.login(COORDINATOR)
        by_key = {}
        for row in self.rows:
            by_key.setdefault(row["meeting"], []).append(row)
        for key, rows in by_key.items():
            title, day = meeting_title(key, self.today), meeting_date(key, self.today)
            ours = [m for m in self._history_meetings() if str(m.get("title") or "").startswith(title)]
            views = {m["id"]: self._view(m["id"]) for m in ours}
            todo, place = [], {}
            for row in rows:
                cid = row["id"]
                st = self.exists(cid)
                if not st:
                    continue
                if any(cid in (v.get("outcomes") or {}) for v in views.values()) or self._decided(st):
                    self.note(cid, "outcome recorded already: skipped")
                    self.report[cid]["outcome"] = row["decision"]["outcome"]
                    continue
                on = next((mid for mid, v in views.items() if cid in self._agenda_ids(v)), None)
                if on:
                    place[cid] = on
                else:
                    todo.append(cid)
            if todo:
                planned = next((m for m in ours if m.get("status") == "planned"), None)
                if planned is None:
                    t = title if not ours else f"{title} ({len(ours) + 1})"
                    r = mdt.post("/api/tb/meetings", json={"date": day, "time": MEETING_TIME[key], "room": ROOM, "video": False,
                                                           "minutes_per_case": MINUTES_PER_CASE, "title": t})
                    if r.status_code != 200:
                        for cid in todo:
                            self.fail(cid, f"meeting not created (HTTP {r.status_code}: {detail(r)})")
                        continue
                    planned = j(r)["meeting"]
                    print(f"meeting {planned['id']} created: {t}")
                    views[planned["id"]] = self._view(planned["id"])
                mid = planned["id"]
                keep = self._agenda_ids(views[mid])
                r = mdt.put(f"/api/tb/meetings/{mid}/agenda", json={"discussion": list(dict.fromkeys(keep + todo)), "noting": []})
                if r.status_code != 200:
                    for cid in todo:
                        self.fail(cid, f"agenda refused (HTTP {r.status_code}: {detail(r)})")
                    continue
                for cid in todo:
                    place[cid] = mid
            for row in rows:
                cid = row["id"]
                if cid not in place:
                    continue
                mid = place[cid]
                r = mdt.post(f"/api/tb/meetings/{mid}/cases/{check_id(cid)}/decision", json=decision_body(row, self.today))
                if r.status_code == 200 or (r.status_code == 409 and j(r).get("code") == "already_recorded") \
                        or (r.status_code == 409 and "already_recorded" in r.text):
                    self.report[cid].update(outcome=row["decision"]["outcome"], meeting_id=mid)
                    self.note(cid, f"outcome {row['decision']['outcome']} recorded on {mid}" + (" (already)" if r.status_code == 409 else ""))
                else:
                    self.fail(cid, f"decision refused (HTTP {r.status_code}: {detail(r)})")
            for mid in sorted(set(place.values())):
                if (self._view(mid).get("meeting") or {}).get("status") in ("planned", "in_session"):
                    r = mdt.post(f"/api/tb/meetings/{mid}/end", json={})
                    print(f"meeting {mid}: " + ("ended" if r.status_code == 200 else f"not ended (HTTP {r.status_code}: {detail(r)})"))

    @staticmethod
    def _decided(case_view):
        recs = (case_view.get("state") or {}).get("board_records") or []
        return any(isinstance(x, dict) for x in recs)

    def post_board(self):
        for row in self.rows:
            cid = row["id"]
            if not row.get("post_board") or self.state.get(cid, {}).get("post_board_summary"):
                continue
            st = self.exists(cid)
            if not st or not self._decided(st):
                continue
            try:
                pid, _ = self.his_patient(row)
                self.his_post_board(row, pid)
            except Failed as e:
                self.fail(cid, str(e))
                continue
            r = self.case_post(owner_login(row), cid, "/his/refetch")
            if r.status_code != 200:
                self.fail(cid, f"re-fetch refused (HTTP {r.status_code}: {detail(r)})")
                continue
            b = j(r)
            if b.get("job") and b.get("total"):
                job, secs = self.wait_job(owner_login(row), b["job"])
                self.note(cid, f"re-fetch {job.get('state')}: {b.get('total')} new or changed records, {secs} s")
            else:
                self.note(cid, "re-fetch: nothing new")
            self.summary(cid, force=True)
            if self.report[cid].get("summary_version"):
                self.state.setdefault(cid, {})["post_board_summary"] = self.report[cid]["summary_version"]
                self._save_state()

    def summary(self, cid, force=False):
        if not force:
            g = j(self.case_get(COORDINATOR, cid, "/case-summary"))
            if g.get("current"):
                self._record_summary(cid, g, "exists")
                return
        r = self.case_post(COORDINATOR, cid, "/case-summary", {"force": True} if force else {}, timeout=600)
        if r.status_code != 200:
            self.fail(cid, f"Case summary refused (HTTP {r.status_code}: {detail(r)})")
            return
        self._record_summary(cid, j(self.case_get(COORDINATOR, cid, "/case-summary")), f"built in {j(r).get('seconds')} s")

    def _record_summary(self, cid, g, how):
        vs = g.get("versions") or []
        cur = next((v for v in vs if v.get("n") == g.get("current")), vs[-1] if vs else {})
        if cid in self.report:
            self.report[cid].update(summary_version=g.get("current"), summary_sentences=cur.get("sentences"))
        print(f"{cid}: Case summary version {g.get('current')} ({cur.get('sentences')} sentences), {how}", flush=True)

    def summaries(self):
        for row in self.rows:
            cid = row["id"]
            st = self.exists(cid)
            if st and self._decided(st) and not self._archived(st):
                self.summary(cid)
        for cid in self.existing:
            if self.exists(cid):
                self.summary(cid)

    @staticmethod
    def _archived(case_view):
        c = case_view.get("case") or {}
        a = c.get("archived")
        return bool(a.get("at") if isinstance(a, dict) else a) or (c.get("listing") or {}).get("status") == "archived"

    def archive(self, rows, reason=None):
        for row in rows:
            cid = row["id"]
            why = reason or row.get("archive")
            st = self.exists(cid)
            if not why or not st:
                continue
            if self._archived(st):
                self.note(cid, "archived already")
                self.report.get(cid, {})["archived"] = True
                continue
            r = self.case_post(COORDINATOR, cid, "/archive", {"reason": why})
            if r.status_code == 200:
                self.report.get(cid, {})["archived"] = True
                self.note(cid, "archived")
            else:
                self.fail(cid, f"archive refused (HTTP {r.status_code}: {detail(r)})")

    def cancel_planned(self):
        mdt = self.login(COORDINATOR)
        for m in self._history_meetings():
            if m.get("status") == "planned":
                r = mdt.post(f"/api/tb/meetings/{m['id']}/cancel", json={"reason": "history fixture: clean-up"})
                print(f"meeting {m['id']}: " + ("cancelled" if r.status_code == 200 else f"not cancelled (HTTP {r.status_code}: {detail(r)})"))

    def count_eligible(self):
        """Eligible past files (research note 8.1 point 2): listed, not archived, an outcome "decision", plus a Case summary. Only the
        ids on this script's own list are opened."""
        ids, out = [r["id"] for r in PLAN] + list(EXISTING_FOR_SUMMARY) + list(ALSO_COUNTED), []
        for cid in ids:
            st = self.exists(cid)
            if not st or self._archived(st) or ((st.get("case") or {}).get("listing") or {"status": "listed"}).get("status") != "listed":
                continue
            recs = (st.get("state") or {}).get("board_records") or []
            if not any((x.get("outcome_type") or x.get("outcome") or "decision") == "decision" for x in recs if isinstance(x, dict)):
                continue
            if j(self.case_get(COORDINATOR, cid, "/case-summary")).get("current"):
                out.append(cid)
        return out

    def write_report(self, eligible, mode):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        rows = list(self.report.values())
        data = {"made_at": datetime.now().isoformat(timespec="seconds"), "mode": mode, "rows": rows, "existing_for_summary": list(self.existing),
                "eligible": len(eligible), "eligible_ids": eligible, "failures": self.failures, "ok": len(eligible) >= 10}
        (OUT_DIR / "report.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        md = [f"# History (SYNTHETIC), item 7.4", "", f"Made {data['made_at']} ({mode}). Synthetic demo data only; ids, protocol and seed slots, no names.", "",
              "| Case File | Seed slot | Protocol | Setting | Owner | Documents | Outcome | Case summary | Archived |", "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            md.append(f"| {r['id']} | {r['slot']} | {r['protocol']} | {r['setting']} | {r['department'] or r['creator']} | {r.get('documents', '')} | "
                      f"{r.get('outcome', '')} | {('version ' + str(r['summary_version'])) if r.get('summary_version') else ''} | "
                      f"{'yes' if r.get('archived') else ''} |")
        md += ["", f"Eligible decided Case Files with a Case summary: {len(eligible)} ({', '.join(eligible) or 'none'}).", ""]
        if self.failures:
            md += ["What failed:", ""] + [f"- {x}" for x in self.failures] + [""]
        (OUT_DIR / "report.md").write_text("\n".join(md), encoding="utf-8")
        print(f"report: {OUT_DIR / 'report.json'} and report.md; eligible {len(eligible)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make the synthetic decided history of item 7.4 (night-v3).")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the calls; nothing is sent, no login")
    ap.add_argument("--check", action="store_true", help="with --dry-run: also the preflight GET calls (no login)")
    ap.add_argument("--only", default="", help="a comma separated subset of the ids")
    ap.add_argument("--summaries-only", action="store_true", help="only the Case summaries (and the report)")
    ap.add_argument("--cleanup", action="store_true", help="archive the HIST files (never delete) and cancel the planned history meetings")
    a = ap.parse_args(argv)
    rows, existing = select(a.only)
    if a.dry_run:
        print(f"make_history dry run: {len(rows)} plan rows, {len(existing)} existing files; nothing is sent")
        for line in plan_lines(rows, existing):
            print(line)
        if a.check:
            return 0 if Run(a, rows, existing).preflight(with_login=False) else 2
        return 0
    run = Run(a, rows, existing)
    try:
        if a.cleanup:
            run.archive(rows, reason="history fixture: clean-up")
            run.cancel_planned()
            return 0
        if not run.preflight():
            return 2
        if not a.summaries_only:
            run.make_files()
            run.meetings_and_decisions()
            run.post_board()
        run.summaries()
        if not a.summaries_only:
            run.archive(rows)
        eligible = run.count_eligible()
        run.write_report(eligible, "summaries-only" if a.summaries_only else ("only " + a.only if a.only else "all"))
        return 0 if len(eligible) >= 10 else 1
    finally:
        run.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failed as e:
        print(f"make_history: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"make_history: a service did not answer ({type(e).__name__})", file=sys.stderr)
        sys.exit(1)
