"""V2 item 8.1: the end-to-end demo of Vaidyx-TB V2 on the mock Indian hospital, with the role logins (SYNTHETIC data only).

It runs the plan's six steps through the HTTP API of the running app (the same calls as the browser), checks the outcome of
each step and says what to look at in the browser as each role, so a presenter can follow along (--pause waits for Enter
between steps):

  1  A Breast Surgery doctor (tb-breast-doc) creates a Case File from the UHID VXH/26/004219 (Priya Venkatesan, SYNTHETIC).
  2  The Pre-Authorization check shows the mammogram (and the ultrasound) as preliminary reports; the doctor notifies Radiology
     (in-app, with the editable mail draft).
  3  A Radiology doctor (tb-rad-doc) acknowledges, sends "done" back, and the consultant signs both reports on the RIS desk.
  4  The Breast Surgery doctor re-fetches from the hospital system: the requests close themselves, the check passes, the
     Case File summary is compiled and the Case File is marked ready for the board.
  5  The MDT Coordinator (tb-mdt) puts it on a board session; the Pathology head is absent, so the Pathology agent is active.
  6  The images open in OHIF through the app, the decision is recorded; then a referral case (VXH/26/004214, lung work-up
     that turns out to be a colorectal primary: tb-pulmo-doc refers, tb-crs-doc accepts) and a two-primaries case
     (VXH/26/004218: tb-crs-doc and tb-breast-doc, two linked Case Files).

    /data/vaidyx/venv/app/bin/python -m tumour_board.eval.demo_v2 [--fresh] [--pause] [--board-date YYYY-MM-DD] [--steps 1-6]
    /data/vaidyx/venv/app/bin/python -m tumour_board.eval.demo_v2 --reset      # remove the demo Case Files and session

--fresh rebuilds the mock hospital first (python -m his_mock.build --upload, then his_mock/serve.sh restart) so the two radiology
reports are preliminary again; it also removes an earlier run's Case Files. Never run it while the e2e, the browser test or the gate
runs. The logins come from ~/vaidyx/.tb_v2_demo_logins (tab-separated: username, password, display name, roles; mode 600); passwords
are never printed. The model servers (reader :8101, reasoner :8100), the app (:7000), the mock HIS (:7130) and Orthanc (:8042, for
step 6's images) must be running. Prints PASS / FAIL per check and exits 1 if any check failed; the Case Files and the session stay
on the app for the presenter (--reset removes them)."""
import argparse, datetime, json, os, re, subprocess, sys, time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LOGINS = os.path.expanduser("~/vaidyx/.tb_v2_demo_logins")
DEFAULT_BASE = "http://127.0.0.1:7000"
DEFAULT_HIS = "http://127.0.0.1:7130"
ORTHANC = "http://127.0.0.1:8042"
PY = sys.executable

UHID_P19, UHID_P14, UHID_P18 = "VXH/26/004219", "VXH/26/004214", "VXH/26/004218"
CASES = {"p19": "TB-DEMO-P19", "p14": "TB-DEMO-P14", "p18a": "TB-DEMO-P18A", "p18b": "TB-DEMO-P18B"}
SESSION_TITLE = "Tumour Board demo (SYNTHETIC)"
ROLES = {"breast": "tb-breast-doc", "rad": "tb-rad-doc", "mdt": "tb-mdt", "pulmo": "tb-pulmo-doc", "crs": "tb-crs-doc"}
RAD_SIGNER = "prac-vxreg-20201"  # Dr Sanjay Joshi, consultant radiologist of the mock (SYNTHETIC)
MG_ACCESSION, US_ACCESSION = "RAD/26/01019", "RAD/26/01020"
STEPS = (1, 2, 3, 4, 5, 6)

OK, FAIL = [], []


# ---- pure helpers (unit-tested in tests/test_demo_v2.py) -----------------------------------------------------------------------

def read_logins(path) -> dict:
    """{username: (password, display name)} from the tab-separated demo logins file; comment and blank lines skipped."""
    out = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and parts[0].strip():
            out[parts[0].strip()] = (parts[1], parts[2].strip() if len(parts) > 2 else parts[0].strip())
    return out


def parse_steps(text) -> list:
    """'1-6' | '1,2,5' | '4-' -> the ordered list of step numbers (each at most once); ValueError on anything else."""
    chosen = set()
    for part in str(text or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)?(-)?(\d+)?$", part)
        if not m or (m.group(2) is None and m.group(1) is None):
            raise ValueError(f"bad step spec {part!r}")
        lo = int(m.group(1)) if m.group(1) else STEPS[0]
        hi = int(m.group(3)) if m.group(3) else (STEPS[-1] if m.group(2) else lo)
        if lo > hi or lo < STEPS[0] or hi > STEPS[-1]:
            raise ValueError(f"steps must lie within {STEPS[0]}-{STEPS[-1]}: {part!r}")
        chosen.update(range(lo, hi + 1))
    return sorted(chosen) or list(STEPS)


def gaps(detail) -> list:
    """[(requirement id, level)] of the open Pre-Authorization rows of a Case File detail (GET /api/tb/cases/<id>)."""
    reqs = ((detail.get("state") or {}).get("gate") or {}).get("requirements") or []
    return sorted((x["id"], x.get("level")) for x in reqs if x.get("status") not in ("satisfied", "not_applicable", "waived"))


def row(detail, requirement) -> dict:
    reqs = ((detail.get("state") or {}).get("gate") or {}).get("requirements") or []
    return next((x for x in reqs if x.get("id") == requirement), {})


def action_for(detail, requirement) -> dict:
    """The Pre-Authorization request (action) of a requirement, newest first."""
    acts = [a for a in (detail.get("state") or {}).get("actions") or [] if a.get("requirement") == requirement]
    return acts[-1] if acts else {}


def names_preliminary_mammogram(r) -> bool:
    """The breast imaging row reads as 'the mammogram is PRELIMINARY'."""
    text = " ".join(r.get("problems") or [])
    return "PRELIMINARY" in text.upper() and "MAMMO" in text.upper()


def every_sentence_cited(summary) -> bool:
    paras = summary.get("paragraphs") or []
    return bool(paras) and all(x.get("citations") for p in paras for x in p)


def default_board_date(today=None) -> str:
    """The next Friday at least two days ahead (the board meets on Fridays in the demo hospital)."""
    today = today or datetime.date.today()
    d = today + datetime.timedelta(days=2)
    while d.weekday() != 4:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def order_id(accession) -> str:
    """'RAD/26/01019' -> 'rad-26-01019' (the mock's order id slug)."""
    return re.sub(r"[^a-z0-9]+", "-", accession.lower()).strip("-")


# ---- output -------------------------------------------------------------------------------------------------------------------

def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not cond else ""), flush=True)
    return bool(cond)


def head(n, title):
    print(f"\n== Step {n}: {title}", flush=True)


def look(lines):
    print("  Look at:", flush=True)
    for ln in lines:
        print(f"    - {ln}", flush=True)


def pause(enabled, what="the next step"):
    if enabled:
        try:
            input(f"  [Enter] to continue with {what} ")
        except EOFError:
            pass


# ---- API helpers --------------------------------------------------------------------------------------------------------------

def login(base, logins, name):
    if name not in logins:
        raise SystemExit(f"demo login {name!r} missing from the logins file")
    c = httpx.Client(base_url=base, timeout=900)
    r = c.post("/api/auth/login", json={"username": name, "password": logins[name][0]})
    if r.status_code != 200:
        raise SystemExit(f"login as {name} refused ({r.status_code}); check the logins file and the app")
    return c


def wait_job(c, jid):
    t0 = time.time()
    while True:
        j = c.get(f"/api/tb/jobs/{jid}").json()
        if j.get("state") in ("finished", "failed", "interrupted"):
            return j, round(time.time() - t0, 1)
        time.sleep(1)


def case(c, cid):
    r = c.get(f"/api/tb/cases/{cid}")
    return r.json() if r.status_code == 200 else {"_status": r.status_code, "_text": r.text[:200]}


def create_from_his(c, ident, protocol, setting, cid, board_date="", tag=""):
    r = c.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": "optimal",
                                             "case_id": cid, "board_date": board_date})
    if r.status_code != 200:
        check(f"{tag} create {cid} from {ident}", False, f"{r.status_code} {r.text[:200]}")
        return None, None
    j, secs = wait_job(c, r.json()["job"])
    check(f"{tag} the records of {ident} are fetched and read ({secs} s)", j.get("state") == "finished", json.dumps(j)[:200])
    return case(c, cid), j


def notes(c, cid, kind):
    return [n for n in c.get("/api/tb/notifications", params={"limit": 200}).json().get("notifications") or [] if n.get("case_id") == cid and n.get("kind") == kind]


def inbox_rows(c, dept, cid):
    ib = c.get("/api/tb/inbox").json()
    return [q for d in ib.get("departments") or [] if d.get("id") == dept for q in d.get("requests") or [] if q.get("case_id") == cid]


def his_url(c) -> str:
    try:
        return ((c.get("/api/tb/his").json().get("settings") or {}).get("url") or DEFAULT_HIS).rstrip("/")
    except Exception:
        return DEFAULT_HIS


def orthanc_up() -> bool:
    try:
        return httpx.get(f"{ORTHANC}/system", timeout=3).status_code == 200
    except Exception:
        return False


# ---- the steps ----------------------------------------------------------------------------------------------------------------

def step1(cl, base, board_date, pause_on):
    head(1, "a Breast Surgery doctor creates the Case File from the UHID")
    breast = cl["breast"]
    d, j = create_from_his(breast, UHID_P19, "breast", "early", CASES["p19"], board_date, "1")
    if not d or d.get("_status"):
        return None
    check("1 eight hospital-system records, each with its OP No. and accession, filed under Breast Surgery", len(d.get("documents") or []) == 8 and d["case"].get("department") == "breast_surgery"
          and all((x.get("his") or {}).get("encounter_number") for x in d["documents"]), f"{len(d.get('documents') or [])} documents, owner {d['case'].get('department')}")
    g = gaps(d)
    check("1 the Pre-Authorization check has two Level 1 gaps: the breast imaging report and the USG axilla, both preliminary", g == [("breast_imaging", 1), ("usg_axilla", 1)] and not d["state"]["gate"]["passed"], json.dumps(g))
    r = row(d, "breast_imaging")
    check("1 the breast imaging row names the preliminary mammogram with its accession No.", names_preliminary_mammogram(r) and r.get("accession") == MG_ACCESSION, json.dumps({"problems": r.get("problems"), "accession": r.get("accession")})[:300])
    check("1 nothing was sent: two suggested requests to Radiology, no inbox row, no notification", (d.get("requests") or {}).get("suggested") == 2 and (d.get("requests") or {}).get("sent") == 0
          and not inbox_rows(cl["rad"], "radiology", CASES["p19"]), json.dumps(d.get("requests")))
    look([f"as tb-breast-doc: {base}/tb (Home shows the Case File under My Case Files), then {base}/tb#case={CASES['p19']}",
          "the Pre-Authorization tab: Level 1 shows the mammogram and the ultrasound as PRELIMINARY (RAD/26/01019, RAD/26/01020) with 'Notify Radiology'",
          "the Documents tab: eight records grouped under the OP visit OP/26/118725, each Final / Digitally signed or Preliminary as the hospital system says",
          f"the hospital system itself: {his_url(breast)}/his (search {UHID_P19})"])
    pause(pause_on, "step 2 (notify Radiology)")
    return d


def step2(cl, base, pause_on):
    head(2, "the doctor notifies Radiology (in-app, with the editable mail draft)")
    breast, rad = cl["breast"], cl["rad"]
    d = case(breast, CASES["p19"])
    a_mg, a_us = action_for(d, "breast_imaging"), action_for(d, "usg_axilla")
    if not (a_mg and a_us):
        check("2 the two suggested requests exist", False, json.dumps([a_mg, a_us])[:200]); return
    dr = breast.get(f"/api/tb/cases/{CASES['p19']}/requests/{a_mg['id']}/draft")
    dj = dr.json() if dr.status_code == 200 else {}
    body = dj.get("body") or ""
    check("2 the draft names the patient, the UHID, the OP No., the record, what is missing, the accession No. and the due date",
          dr.status_code == 200 and f"UHID {UHID_P19}" in body and "OP No. OP/26/" in body and "Required record: " in body and "What is missing: " in body
          and f"Accession / order No.: {MG_ACCESSION}" in body and "Needed by: " in body and (dj.get("mailto") or "").startswith("mailto:"), (dr.text if dr.status_code != 200 else body)[:300])
    print("  The draft (as the doctor sees it before editing):")
    for ln in body.splitlines()[:12]:
        print(f"    | {ln}")
    sent = {}
    for key, a in (("mammogram", a_mg), ("ultrasound", a_us)):
        drj = breast.get(f"/api/tb/cases/{CASES['p19']}/requests/{a['id']}/draft").json()
        r = breast.post(f"/api/tb/cases/{CASES['p19']}/requests/{a['id']}/send", json={"message": (drj.get("body") or "") + "\nPlease sign before the board (demo, SYNTHETIC)."})
        sent[key] = r.json().get("action") if r.status_code == 200 else {"_status": r.status_code, "_text": r.text[:200]}
    check("2 both requests are sent in-app by the treating doctor: pending, with a due date, audited", all(x.get("status") == "pending" and x.get("due") and (x.get("sent") or {}).get("by") == ROLES["breast"] for x in sent.values()),
          json.dumps(sent)[:300])
    rows = inbox_rows(rad, "radiology", CASES["p19"])
    check("2 the Radiology inbox shows them with the UHID, the OP No. and the accession Nos.", len(rows) == 2 and all(q.get("uhid") == UHID_P19 and str((q.get("encounter") or {}).get("op_no") or "").startswith("OP/26/") for q in rows)
          and {q.get("accession") for q in rows} == {MG_ACCESSION, US_ACCESSION}, json.dumps(rows)[:300])
    check("2 Radiology is notified (the bell)", len(notes(rad, CASES["p19"], "request")) >= 2)
    look(["as tb-breast-doc: the Pre-Authorization tab's 'Requests to departments' card shows both requests as Sent (press 'Notify Radiology' on a suggested request to see the draft, 'Open in mail' and 'Copy draft')",
          f"as tb-rad-doc: {base}/tb (Home shows the Radiology inbox with the two requests, the bell shows the notifications)"])
    pause(pause_on, "step 3 (Radiology acknowledges and signs)")


def step3(cl, base, pause_on):
    head(3, "Radiology acknowledges, sends 'done' back, and the consultant signs on the RIS desk")
    breast, rad = cl["breast"], cl["rad"]
    d = case(breast, CASES["p19"])
    a_mg, a_us = action_for(d, "breast_imaging"), action_for(d, "usg_axilla")
    ack = [rad.post(f"/api/tb/cases/{CASES['p19']}/requests/{a['id']}/acknowledge") for a in (a_mg, a_us) if a]
    check("3 Radiology acknowledges both requests; the owning department is told", len(ack) == 2 and all(r.status_code == 200 for r in ack) and len(notes(breast, CASES["p19"], "request_acknowledged")) >= 2,
          " ".join(f"{r.status_code} {r.text[:80]}" for r in ack))
    r = rad.post(f"/api/tb/cases/{CASES['p19']}/requests/{a_mg['id']}/done", json={"note": "Reported and signed in the RIS (demo, SYNTHETIC)"})
    check("3 'done' back with a note: the request stays open until the signed report arrives; the owner is told to re-fetch", r.status_code == 200 and r.json().get("action", {}).get("status") == "pending"
          and any(n.get("refetch_offer") for n in notes(breast, CASES["p19"], "request_done")), r.text[:200])
    his = his_url(breast)
    signed = {}
    for acc in (MG_ACCESSION, US_ACCESSION):
        try:
            rs = httpx.post(f"{his}/desk/api/RAD/orders/{order_id(acc)}/sign", json={"signer": RAD_SIGNER}, timeout=120)
            signed[acc] = (rs.status_code, rs.text[:160])
        except Exception as e:
            signed[acc] = (0, str(e)[:160])
    check("3 the consultant radiologist completes and signs both reports on the RIS desk (final, digitally signed, demo CA)", all(v[0] == 200 for v in signed.values()), json.dumps(signed)[:300])
    look([f"the RIS desk: {his}/desk/RAD (the two reports now under 'Signed', with the signed PDF; this is what 'Complete and sign' does as Dr Sanjay Joshi)",
          "as tb-rad-doc: the inbox rows read Acknowledged and Done; as tb-breast-doc the bell shows 'Request acknowledged' and 'Done by the department' with the re-fetch hint"])
    pause(pause_on, "step 4 (re-fetch, summary, ready for the board)")


def step4(cl, base, pause_on):
    head(4, "re-fetch: the requests close themselves, the check passes, the summary is compiled, the Case File is marked ready")
    breast = cl["breast"]
    d0 = case(breast, CASES["p19"])
    ids = [action_for(d0, k).get("id") for k in ("breast_imaging", "usg_axilla")]
    r = breast.post(f"/api/tb/cases/{CASES['p19']}/his/refetch")
    if r.status_code != 200:
        check("4 re-fetch from the hospital system", False, f"{r.status_code} {r.text[:200]}"); return
    body, j, secs = r.json(), *wait_job(breast, r.json()["job"])
    d = case(breast, CASES["p19"])
    closed = (j.get("refetch_result") or {}).get("closed") or []
    check(f"4 the re-fetch brings only the two changed reports ({secs} s), closes both requests and the check passes", (body.get("his") or {}).get("added", 0) >= 2 and sorted(closed) == sorted(x for x in ids if x)
          and d["state"]["gate"]["passed"] and all(action_for(d, k).get("status") == "completed" for k in ("breast_imaging", "usg_axilla")), json.dumps({"his": body.get("his"), "closed": closed, "gaps": gaps(d)})[:300])
    check("4 the owner is told what closed; Radiology sees its requests closed", any(n.get("refetch") for n in notes(breast, CASES["p19"], "request_closed"))
          and all(q.get("status") == "completed" for q in inbox_rows(cl["rad"], "radiology", CASES["p19"])))
    t0 = time.time()
    sm = breast.post(f"/api/tb/cases/{CASES['p19']}/summary", json={}).json()
    stale = (case(breast, CASES["p19"]).get("stale") or {}).get("summary")
    check(f"4 the Case File summary compiles once the check is met ({round(time.time() - t0)} s): every sentence cited, not stale", sm.get("status") == "ready" and every_sentence_cited(sm) and stale == "",
          f"{sm.get('status')} stale {stale!r} {json.dumps(sm)[:160]}")
    r = breast.post(f"/api/tb/cases/{CASES['p19']}/ready", json={"ready": True, "note": "Summary compiled (demo)"})
    check("4 the owning department marks the Case File ready for the board (audited; the coordinator is told)", r.status_code == 200 and (r.json().get("board_ready") or {}).get("by") == ROLES["breast"]
          and any(n.get("case_id") == CASES["p19"] for n in notes(cl["mdt"], CASES["p19"], "board_ready")), r.text[:200])
    look([f"as tb-breast-doc: {base}/tb#case={CASES['p19']}: the header reads 'Pre-Authorization met' and 'Ready for the board (by tb-breast-doc)'; the Pre-Authorization card shows both requests Closed",
          "the Documents tab: the mammogram and the ultrasound are now Final / Digitally signed (version 2), the earlier preliminary version superseded",
          "the Summary tab: the Case File summary in the NCG Virtual Tumour Board structure, every sentence with its quote"])
    pause(pause_on, "step 5 (the coordinator's session)")


def step5(cl, base, board_date, pause_on, ctx):
    head(5, "the MDT Coordinator puts it on a session; the Pathology head is absent, so the Pathology agent is active")
    mdt = cl["mdt"]
    cand = {x["case_id"]: x for x in mdt.get("/api/tb/sessions/candidates", params={"date": board_date}).json().get("cases") or []}
    c19 = cand.get(CASES["p19"]) or {}
    check("5 the candidate list for the board date shows the Case File ready (by tb-breast-doc), the check met and the summary compiled", (c19.get("ready") or {}).get("by") == ROLES["breast"]
          and c19.get("gate_passed") is True and c19.get("summary") == "ready", json.dumps(c19)[:300])
    existing = [s for s in mdt.get("/api/tb/sessions").json().get("sessions") or [] if s.get("title") == SESSION_TITLE and s.get("status") != "closed"]
    if existing:
        sid = existing[0]["id"]
        print(f"  (reusing the open session {sid})")
    else:
        s = mdt.post("/api/tb/sessions", json={"date": board_date, "title": SESSION_TITLE}).json()
        sid = s.get("id")
        check("5 a session for the board date takes the Case Files the owners marked ready", bool(sid) and CASES["p19"] in [a.get("case_id") for a in s.get("agenda") or []], json.dumps(s)[:200])
    if not sid:
        return
    ctx["sid"] = sid
    for dept, st in (("radiology", "present"), ("medical_oncology", "present"), ("surgical_oncology", "present"), ("pathology", "absent")):
        mdt.post(f"/api/tb/sessions/{sid}/attendance", json={"department": dept, "status": st})
    rm = mdt.get(f"/api/tb/sessions/{sid}").json()
    sheet = [x.get("id") for x in rm.get("attendance_list") or []]
    check("5 the attendance sheet lists the four heads first; Pathology marked absent makes its agent active for the Case File", sheet[:4] == ["radiology", "medical_oncology", "surgical_oncology", "pathology"]
          and (rm.get("absent_roles_by_case") or {}).get(CASES["p19"]) == ["pathology"], json.dumps({"sheet": sheet, "absent": rm.get("absent_roles_by_case")})[:300])
    t0 = time.time()
    st = mdt.post(f"/api/tb/sessions/{sid}/start").json()
    check("5 starting the session prepares the Pathology agent's brief for the Case File (records + Indian guidelines; no diagnosis)", st.get("preparing") == 1, json.dumps(st)[:200])
    while True:
        rm = mdt.get(f"/api/tb/sessions/{sid}").json()
        ag = (rm.get("session") or {}).get("agents") or {}
        states = {(cid, role): x.get("status") for cid, by in ag.items() for role, x in by.items()}
        if states and all(v not in ("queued", "running") for v in states.values()) or time.time() - t0 > 1200:
            break
        time.sleep(3)
    pst = states.get((CASES["p19"], "pathology"))
    check(f"5 the Pathology brief is ready ({round(time.time() - t0)} s) and shown in the room", pst in ("ready", "no_documents") and "pathology" in ((rm.get("cases") or {}).get(CASES["p19"]) or {}).get("briefs", {}),
          json.dumps({f"{k[0]}:{k[1]}": v for k, v in states.items()}))
    look([f"as tb-mdt: {base}/tb, 'Board sessions' (or Home: next board {board_date}): the session '{SESSION_TITLE}'",
          "the Board room: the attendance sheet (Radiology, Medical Oncology, Surgical Oncology present; Pathology absent), the AI support card says the Pathology agent stands in, its brief under the Case File",
          "as tb-path-head (the absent head) the room still opens read-only for its department"])
    pause(pause_on, "step 6 (images, the decision, a referral, two primaries)")


def step6(cl, base, board_date, pause_on, ctx):
    head(6, "images in OHIF, the decision; then a referral case and a two-primaries case")
    mdt, breast = cl["mdt"], cl["breast"]
    sid = ctx.get("sid")
    if not sid:
        sess = [s for s in mdt.get("/api/tb/sessions").json().get("sessions") or [] if s.get("title") == SESSION_TITLE]
        sid = sess[0]["id"] if sess else None
    # ---- images through the app's audited route (OHIF + DICOMweb behind the login) ----
    if sid:
        rm = mdt.get(f"/api/tb/sessions/{sid}").json()
        recs = ((rm.get("cases") or {}).get(CASES["p19"]) or {}).get("records") or []
        img = [x for x in recs if x.get("images") and (x.get("his") or {}).get("accession") == MG_ACCESSION] or [x for x in recs if x.get("images")]
        if not orthanc_up():
            print("  (Orthanc :8042 is not answering: the image step is skipped; start it with his_mock/orthanc.sh start)")
        elif check("6 the room's Records card marks the mammogram as a report with images in the PACS", bool(img), f"{len(recs)} records"):
            doc_id = img[0]["doc_id"]
            r = mdt.post(f"/api/tb/cases/{CASES['p19']}/documents/{doc_id}/images")
            j = r.json() if r.status_code == 200 else {}
            v = mdt.get(j.get("viewer_url", "/api/tb/pacs/ohif/viewer")) if j.get("viewer_url") else None
            q = mdt.get("/api/tb/pacs/dicom-web/studies", params={"StudyInstanceUID": j.get("study_uid", "")}) if j.get("study_uid") else None
            check("6 'Open images' finds the study in the hospital system and opens OHIF through the app (granted to this login, audited); the study's DICOMweb data comes through the app too",
                  r.status_code == 200 and j.get("available") is True and str(j.get("viewer_url", "")).startswith("/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=") and v is not None and v.status_code == 200
                  and q is not None and q.status_code == 200 and len(q.json()) == 1, json.dumps(j)[:200] + (f" viewer {v.status_code}" if v is not None else ""))
            check("6 nobody else reaches that study (a login that did not open it is refused)", cl["rad"].get("/api/tb/pacs/dicom-web/studies", params={"StudyInstanceUID": j.get("study_uid", "x")}).status_code == 403)
            ctx["viewer_url"] = j.get("viewer_url")
        # ---- the decision ----
        due = (datetime.date.fromisoformat(board_date) + datetime.timedelta(days=10)).isoformat()
        dec = mdt.post(f"/api/tb/sessions/{sid}/cases/{CASES['p19']}/decision",
                       json={"decision_text": "Breast conservation surgery with sentinel node biopsy; adjuvant plan after the final histopathology (as dictated; SYNTHETIC demo).",
                             "recorded_by": "Dr Chair (demo, SYNTHETIC)", "intent_as_recorded": "curative", "actions": [{"department": "Radiology", "task": "MRI breast before surgery", "due": due}]}).json()
        rec = dec.get("record") or {}
        comp = (rec.get("adjudication") or {}).get("composition") or {}
        html = mdt.get(f"/api/tb/sessions/{sid}/minutes").text
        check("6 the decision is recorded as dictated with its follow-up action; the PM-JAY composition check ran (the hospital is empanelled); the minutes carry it",
              bool(rec) and comp.get("checked") is True and "MRI breast before surgery" in html and "Tumour Board minutes" in html, json.dumps(dec)[:300])
        look([f"as tb-mdt, in the Board room: the Records card, 'Open images' on the mammogram opens OHIF in a new tab at {base}{ctx.get('viewer_url') or '/api/tb/pacs/ohif/viewer?...'} (the synthetic MG study; 127.0.0.1:8042 directly does not route)",
              "'Record decision' shows the decision as dictated, the agent points beside it, the composition line; 'Minutes' downloads the minutes; the Follow-up card lists the MRI action (it also sits in Radiology's inbox)"])
    else:
        check("6 the board session exists (run step 5 first)", False)
    pause(pause_on, "the referral case")
    # ---- a referral case: the lung work-up turns out to be a colorectal primary (P14) ----
    pulmo, crs = cl["pulmo"], cl["crs"]
    d, j = create_from_his(pulmo, UHID_P14, "lung_nsclc", "metastatic", CASES["p14"], "", "6 referral:")
    if d and not d.get("_status"):
        sug = ((d.get("referral") or {}).get("suggestions") or [])
        check("6 referral: the hospital system's own referral (Pulmonology to Colorectal Surgery) is shown as a suggestion, never applied by itself", len(sug) == 1 and sug[0].get("to") == "colorectal_surgery"
              and d["case"].get("department") == "pulmonology", json.dumps(sug)[:200])
        r = pulmo.post(f"/api/tb/cases/{CASES['p14']}/referrals", json={"to": "Colorectal Surgery", "reason": "Lung biopsy reported as metastatic adenocarcinoma of colorectal origin; colonoscopy shows a rectal growth (demo, SYNTHETIC)",
                                                                       **({"his_ref": sug[0]["his_ref"]} if sug else {})})
        ref = r.json().get("referral") if r.status_code == 200 else {}
        check("6 referral: the owning doctor refers with a reason; Colorectal Surgery is told and may read the Case File while it waits", r.status_code == 200 and (ref or {}).get("status") == "requested"
              and crs.get(f"/api/tb/cases/{CASES['p14']}").status_code == 200 and len(notes(crs, CASES["p14"], "referral")) >= 1, r.text[:200])
        if ref:
            r = crs.post(f"/api/tb/cases/{CASES['p14']}/referrals/{ref['id']}/accept", json={"protocol": "colorectal_rectum", "setting": "metastatic", "hospital_level": "optimal", "note": "accepted: rectal primary with lung metastases (demo, SYNTHETIC)"})
            if r.status_code == 200 and r.json().get("job"):
                wait_job(crs, r.json()["job"])
            d2 = case(crs, CASES["p14"])
            acc = d2.get("access") or {}
            hist = (d2.get("state") or {}).get("gate_history") or []
            check("6 referral: on acceptance ownership moves to Colorectal Surgery with the rectal protocol on the same records; Pulmonology stays a participant; the lung check is kept as read-only history",
                  r.status_code == 200 and d2["case"].get("department") == "colorectal_surgery" and ((d2.get("state") or {}).get("gate") or {}).get("protocol") == "colorectal_rectum"
                  and [x.get("id") for x in acc.get("participants") or []] == ["pulmonology"] and hist and hist[0].get("protocol") == "lung_nsclc", r.text[:200] + json.dumps(gaps(d2)))
        look([f"as tb-pulmo-doc: {base}/tb#case={CASES['p14']}: the Pre-Authorization tab's 'Ownership and referral' card (Referral accepted; the bell shows 'Referral answered')",
              f"as tb-crs-doc: the same Case File, now owned by Colorectal Surgery: the rectal check (MRI pelvis Level 1; CEA, MMR, RAS / BRAF Level 2 as suggested requests), 'Earlier protocol (read-only history)' with the lung check; the Board tab's timeline shows the move"])
    pause(pause_on, "the two-primaries case")
    # ---- two primaries: two linked Case Files under one UHID (P18) ----
    da, ja = create_from_his(crs, UHID_P18, "colorectal_rectum", "non_metastatic", CASES["p18a"], "", "6 two primaries:")
    db, jb = create_from_his(breast, UHID_P18, "breast", "early", CASES["p18b"], "", "6 two primaries:")
    if da and db and not da.get("_status") and not db.get("_status"):
        da = case(crs, CASES["p18a"])
        la = [x.get("case_id") for x in (da.get("access") or {}).get("linked_cases") or []]
        lb = [x.get("case_id") for x in (db.get("access") or {}).get("linked_cases") or []]
        check("6 two primaries: the second cancer of the same patient gets its own Case File, linked both ways, each with its own owner and protocol; both checks pass on their own episode's reports",
              la == [CASES["p18b"]] and lb == [CASES["p18a"]] and da["state"]["gate"]["passed"] and db["state"]["gate"]["passed"] and db["case"].get("department") == "breast_surgery",
              json.dumps({"a": la, "b": lb, "gaps_a": gaps(da), "gaps_b": gaps(db)})[:300])
        look([f"as tb-crs-doc: {base}/tb#case={CASES['p18a']} (header 'Linked Case File'; the Pre-Authorization card lists the breast Case File of the same patient; the breast one opens read-only)",
              f"as tb-breast-doc: {base}/tb#case={CASES['p18b']}: the Documents tab shows the histopathology requirement met by the breast biopsy, the rectal report set aside for review"])


# ---- reset / fresh ------------------------------------------------------------------------------------------------------------

def reset(cl, quiet=False):
    """Remove the demo Case Files and the demo session (the MDT Coordinator may delete Case Files; the session file goes like the e2e's)."""
    mdt = cl["mdt"]
    removed = []
    for cid in CASES.values():
        r = mdt.delete(f"/api/tb/cases/{cid}")
        if r.status_code == 200:
            removed.append(cid)
    gone = []
    for s in mdt.get("/api/tb/sessions").json().get("sessions") or []:
        if s.get("title") == SESSION_TITLE:
            try:
                mdt.post(f"/api/tb/sessions/{s['id']}/close")
            except Exception:
                pass
            try:
                from tumour_board import board
                board._path(s["id"]).unlink(missing_ok=True)
                board.audit_session(s["id"], {"kind": "demo_removed", "by": ROLES["mdt"]})
                gone.append(s["id"])
            except Exception as e:
                print(f"  could not remove the session file of {s['id']}: {e}")
    if not quiet:
        print(f"reset: removed Case Files {removed or 'none'}; sessions {gone or 'none'}")
    return removed, gone


def fresh_mock():
    """Rebuild the live mock hospital (documents, HL7, DICOM uploaded to Orthanc) and restart it: the radiology reports are preliminary again."""
    print("== rebuilding the mock hospital (python -m his_mock.build --upload; his_mock/serve.sh restart) ...", flush=True)
    r = subprocess.run([PY, "-m", "his_mock.build", "--upload"], cwd=str(REPO), capture_output=True, text=True)
    print("  " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
    if r.returncode != 0:
        print(r.stderr[-2000:]); raise SystemExit("the mock build failed")
    r = subprocess.run(["bash", str(REPO / "his_mock" / "serve.sh"), "restart"], cwd=str(REPO), capture_output=True, text=True)
    print("  " + " ".join(r.stdout.split())[:200])
    for _ in range(60):
        try:
            if httpx.get(f"{DEFAULT_HIS}/health", timeout=2).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit("the mock hospital did not come back on 127.0.0.1:7130")


# ---- main ---------------------------------------------------------------------------------------------------------------------

def preflight(cl, base, steps):
    bad = []
    try:
        if httpx.get(f"{base}/tb", timeout=5, follow_redirects=True).status_code != 200:
            bad.append("the app does not answer")
    except Exception as e:
        bad.append(f"the app does not answer: {e}")
    his = cl["breast"].get("/api/tb/his").json()
    if not ((his.get("status") or {}).get("ok")):
        bad.append(f"the hospital system does not answer: {json.dumps(his.get('status'))[:160]}")
    if 1 in steps:
        for cid in CASES.values():
            if cl["mdt"].get(f"/api/tb/cases/{cid}").status_code == 200:
                bad.append(f"{cid} already exists: run --reset (or --fresh) first, or start at a later step with --steps")
                break
    if 6 in steps and not orthanc_up():
        print("note: Orthanc (:8042) is not answering; the image step will be skipped")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--logins", default=DEFAULT_LOGINS, help="the demo logins file (default ~/vaidyx/.tb_v2_demo_logins)")
    ap.add_argument("--board-date", default="", help="YYYY-MM-DD (default: the next Friday at least two days ahead)")
    ap.add_argument("--steps", default="1-6", help="which steps to run, e.g. 1-4 or 5,6 (later steps need the earlier ones' state)")
    ap.add_argument("--pause", action="store_true", help="wait for Enter between steps (presenter mode)")
    ap.add_argument("--fresh", action="store_true", help="rebuild and restart the mock hospital first and remove an earlier run's Case Files")
    ap.add_argument("--reset", action="store_true", help="only remove the demo Case Files and session, then exit")
    ap.add_argument("--out", default="", help="write report.json here (default data/tumour_board/eval/demo_v2/<timestamp>/)")
    args = ap.parse_args(argv)
    try:
        steps = parse_steps(args.steps)
    except ValueError as e:
        ap.error(str(e))
    board_date = args.board_date or default_board_date()
    logins = read_logins(args.logins)
    missing = [u for u in ROLES.values() if u not in logins]
    if missing:
        print(f"demo logins missing from {args.logins}: {missing}", file=sys.stderr)
        return 2
    cl = {k: login(args.base, logins, u) for k, u in ROLES.items()}
    if args.reset:
        reset(cl)
        return 0
    if args.fresh:
        reset(cl)
        fresh_mock()
    bad = preflight(cl, args.base, steps)
    if bad:
        for b in bad:
            print("pre-flight:", b, file=sys.stderr)
        return 2
    print(f"Vaidyx-TB V2 demo on the mock Indian hospital (SYNTHETIC). App {args.base}, board date {board_date}, steps {steps}.")
    print("Roles: " + ", ".join(f"{u} ({logins[u][1]})" for u in ROLES.values()))
    t0 = time.time()
    ctx = {}
    if 1 in steps:
        step1(cl, args.base, board_date, args.pause)
    if 2 in steps:
        step2(cl, args.base, args.pause)
    if 3 in steps:
        step3(cl, args.base, args.pause)
    if 4 in steps:
        step4(cl, args.base, args.pause)
    if 5 in steps:
        step5(cl, args.base, board_date, args.pause, ctx)
    if 6 in steps:
        step6(cl, args.base, board_date, args.pause, ctx)
    secs = round(time.time() - t0)
    print(f"\n{len(OK)} passed, {len(FAIL)} failed in {secs} s" + (f": {FAIL}" if FAIL else ""))
    print(f"The Case Files {', '.join(CASES.values())} and the session '{SESSION_TITLE}' stay on the app. To run again: --reset (or --fresh to rebuild the mock so the reports are preliminary again).")
    out = Path(args.out) if args.out else REPO / "data" / "tumour_board" / "eval" / "demo_v2" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps({"item": "V2-8.1", "base": args.base, "board_date": board_date, "steps": steps, "seconds": secs, "passed": OK, "failed": FAIL,
                                                     "cases": CASES, "session": ctx.get("sid")}, indent=1))
        print(f"report: {out / 'report.json'}")
    except OSError as e:
        print(f"report not written: {e}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
