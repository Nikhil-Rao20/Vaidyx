"""The live end-to-end scenario of the new interface (SPEC.md section 8, brief Q1), run against the services already running on this
server: Vaidyx :7000, the demo HIMS :7130, Orthanc :8042, LiveKit :7880 and the models :8100 / :8101 (a few real model calls).

    python -m tumour_board.eval.e2e_nik            run it; the scenario's Case Files and meeting stay for the owner to look at
    python -m tumour_board.eval.e2e_nik --keep     also keep the Case Files and meetings of earlier E2E runs (default: removed first)
    python -m tumour_board.eval.e2e_nik --clean    remove this run's Case Files (and cancel its meeting when still planned) at the end

Every step goes through the APIs the screens use, as the person who would do it: the HIMS registration desk, OPD, laboratory,
radiology and pathology (JSON APIs with the write token data/his_mock/write_token, the OPD note and the pathology add-on and IHC through the screens with
a HIMS login and the form token); the PACS by DICOMweb; Vaidyx as the Breast Surgery consultant, a resident created for the run by the
Breast Surgery department admin, the Pathology head, the Radiology doctor and the MDT Coordinator (demo logins from
~/vaidyx/.tb_v2_demo_logins). Synthetic data only: the patient is registered fresh in the demo HIMS ("E2E ... (SYNTHETIC)"), the Case
File ids start with "E2E-", the meeting title with "E2E". Never touches the real case. Passwords, tokens and codes are read from their
files, kept in memory and never printed or logged.

The log of the run (step, check, result, evidence) is written to docs/ui/build/E2E_RESULT.md; a section of that file headed
"## Bugs found and fixed" is kept as it is between runs. Exit code 0 when every check passed."""
import argparse, json, os, re, secrets, sys, threading, time, urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
VAIDYX = "http://127.0.0.1:7000"
HIS = "http://127.0.0.1:7130"
ORTHANC = "http://127.0.0.1:8042"
LIVEKIT = "http://127.0.0.1:7880"
DEMO_LOGINS = Path.home() / "vaidyx" / ".tb_v2_demo_logins"
HIS_DATA = REPO / "data" / "his_mock"
LOG_PATH = REPO / "docs" / "ui" / "build" / "E2E_RESULT.md"
KEEP_MARK = "## Bugs found and fixed"
RESIDENT = "e2e.resident@vaidyx-demo.invalid"
RESIDENT_NAME = "Dr Asha (E2E resident, demo)"
PATIENT_NAME = "E2E Lakshmi R (SYNTHETIC)"
DEMO_PATIENT = "VXH/26/004219"   # P19 of the demo HIMS: its synthetic report PDFs are uploaded as outside reports (owner rule 5)
BREAST_CONSULTANT = "prac-vxreg-20104"   # Dr Kavitha Raghunathan, Breast Surgery (demo HIMS)
RADIOLOGIST = "prac-vxreg-20201"         # Dr Sanjay Joshi, Radiology
PATHOLOGIST = "prac-vxreg-20204"         # Dr Revathi Krishnan, Pathology
BIOCHEMIST = "prac-vxreg-20206"          # Dr Anil Saxena, Biochemistry (the lab doctor login)
HEADERS = {"X-Requested-With": "tb-nik"}


class Abort(Exception):
    """A step the rest of the scenario depends on failed."""


def _norm(s):
    return " ".join(str(s or "").split())


class Scenario:
    def __init__(self, args):
        self.args = args
        self.rows = []          # (step, check, ok, evidence)
        self.ids = {}           # what the run made: uhid, case ids, meeting id ...
        self.clients = {}
        self.t0 = time.time()
        self.today = date.today()
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.vx_logins = self._read_tsv(DEMO_LOGINS, 0, 1)
        self.his_logins = self._read_tsv(HIS_DATA / "logins.tsv", 0, 2)
        tok = HIS_DATA / "write_token"  # the JSON write APIs take the write token; the FHIR read token changes nothing (security review #13)
        self.his_token = tok.read_text(encoding="utf-8").strip() if tok.exists() else ""

    # ---- bookkeeping ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _read_tsv(path, key_col, val_col):
        out = {}
        if not path.exists():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) > max(key_col, val_col):
                out[parts[key_col].strip()] = parts[val_col].strip()
        return out

    def check(self, step, name, ok, evidence=""):
        ok = bool(ok)
        self.rows.append((step, name, ok, _norm(evidence)[:700]))
        print(("PASS " if ok else "FAIL ") + f"[{step}] {name}" + (f"  ({_norm(evidence)[:200]})" if evidence else ""), flush=True)
        return ok

    def need(self, step, name, ok, evidence=""):
        if not self.check(step, name, ok, evidence):
            raise Abort(f"{step}: {name}")

    # ---- HTTP ----------------------------------------------------------------------------------------------------------------
    def vx(self, user, password=None):
        """A Vaidyx client signed in as `user` (demo logins file, or the password given)."""
        if user in self.clients and password is None:
            return self.clients[user]
        c = httpx.Client(base_url=VAIDYX, timeout=180, headers=HEADERS)
        pw = password if password is not None else self.vx_logins.get(user)
        if not pw:
            raise Abort(f"no demo login for {user} in {DEMO_LOGINS}")
        for attempt in range(4):
            r = c.post("/api/auth/login", json={"username": user, "password": pw, "remember": True})
            if r.status_code != 429:
                break
            time.sleep(20)  # the sign-in limiter (15 per minute per address) is shared with whoever else signs in on this server
        if r.status_code != 200 or not c.cookies.get("vaidyx_session"):
            raise Abort(f"sign-in as {user} refused ({r.status_code})")
        self.clients[user] = c
        return c

    @staticmethod
    def j(r):
        try:
            return r.json()
        except ValueError:
            return {}

    def his(self):
        if "his" not in self.clients:
            self.clients["his"] = httpx.Client(base_url=HIS, timeout=120, headers={"Authorization": f"Bearer {self.his_token}"})
        return self.clients["his"]

    def his_screen(self, email):
        """A HIMS screen session (cookie) for one of the demo hospital's staff logins."""
        key = "his:" + email
        if key in self.clients:
            return self.clients[key]
        c = httpx.Client(base_url=HIS, timeout=120)
        pw = self.his_logins.get(email)
        if not pw:
            raise Abort(f"no HIMS login for {email} in data/his_mock/logins.tsv")
        r = c.post("/his/login", data={"email": email, "password": pw, "next": "/his"}, follow_redirects=False)
        if r.status_code != 303 or not c.cookies.get("vxhis_session"):
            raise Abort(f"HIMS sign-in as {email} refused ({r.status_code})")
        self.clients[key] = c
        return c

    @staticmethod
    def csrf(c, page):
        r = c.get(page)
        m = re.search(r'name="csrf" value="([^"]+)"', r.text)
        if not m:
            raise Abort(f"no form token on {page} ({r.status_code})")
        return m.group(1)

    def wait_job(self, c, jid, limit=900):
        t0 = time.time()
        while time.time() - t0 < limit:
            r = c.get(f"/api/tb/jobs/{jid}")
            j = self.j(r)
            if j.get("state") in ("finished", "failed", "interrupted"):
                return j, round(time.time() - t0, 1)
            time.sleep(2)
        return {"state": "timeout"}, round(time.time() - t0, 1)

    def doc_text(self, c, case_id, doc_id, cache={}):
        key = (case_id, doc_id)
        if key not in cache:
            d = self.j(c.get(f"/api/tb/cases/{case_id}/documents/{doc_id}"))
            cache[key] = "\n".join(p.get("text") or "" for p in d.get("pages") or [])
        return cache[key]

    def verbatim(self, c, case_id, quote):
        """True when the quote stands word for word (white space aside) in the text of its document."""
        if not quote or not quote.get("doc_id") or not _norm(quote.get("text") or quote.get("quote")):
            return False
        return _norm(quote.get("text") or quote.get("quote")) in _norm(self.doc_text(c, case_id, quote["doc_id"]))

    # ---- the run -------------------------------------------------------------------------------------------------------------
    def run(self):
        steps = [self.step0_services, self.step0_clean_earlier, self.step0_resident, self.step1_hims, self.step2_pacs, self.step3_casefile,
                 self.step4_ihc, self.step5_ask, self.step6_ready, self.step7_meeting, self.step8_outcome, self.step9_outside]
        state = Path(self.args.state) if self.args.state else None
        if self.args.start and state and state.exists():  # a debugging re-start: the ids of an earlier run (no secrets in that file)
            self.ids.update(json.loads(state.read_text(encoding="utf-8")))
            self.stamp = self.ids.get("stamp", self.stamp)
        self.ids["stamp"] = self.stamp
        for n, fn in enumerate(steps):
            if self.args.start and fn.__name__ not in ("step0_services", "step0_resident") and int(fn.__name__[4]) < self.args.start:
                continue
            try:
                fn()
                if state:
                    state.write_text(json.dumps(self.ids, indent=1, default=str), encoding="utf-8")
            except Abort as e:
                self.check("abort", f"the scenario stopped: {e}", False)
                break
            except Exception as e:  # a bug in the scenario itself or an unexpected answer: recorded, the run stops
                self.check("abort", f"{fn.__name__} raised {type(e).__name__}", False, str(e)[:300])
                break
        if self.args.clean:
            self.clean_this_run()
        self.write_log()
        for c in self.clients.values():
            try:
                c.close()
            except Exception:
                pass
        failed = [r for r in self.rows if not r[2]]
        print(f"\n{len(self.rows) - len(failed)} passed, {len(failed)} failed in {round(time.time() - self.t0)} s; log: {LOG_PATH}")
        return 0 if not failed else 1

    # ---- 0: services, earlier runs, the resident --------------------------------------------------------------------------------
    def step0_services(self):
        s = "0 services"
        ok = {}
        for name, url in (("Vaidyx", f"{VAIDYX}/api/health"), ("HIMS", f"{HIS}/health"), ("Orthanc", f"{ORTHANC}/system"), ("LiveKit", f"{LIVEKIT}/")):
            try:
                ok[name] = httpx.get(url, timeout=10).status_code == 200
            except httpx.HTTPError:
                ok[name] = False
        self.need(s, "Vaidyx, HIMS, Orthanc and LiveKit answer", all(ok.values()), ", ".join(f"{k} {'up' if v else 'DOWN'}" for k, v in ok.items()))
        self.need(s, "demo logins and the HIMS write token are on the server", bool(self.vx_logins) and bool(self.his_logins) and bool(self.his_token),
                  f"{len(self.vx_logins)} Vaidyx demo logins, {len(self.his_logins)} HIMS logins, write token present")
        models = {}
        for name, port in (("reasoner", 8100), ("reader", 8101)):
            try:
                models[name] = httpx.get(f"http://127.0.0.1:{port}/v1/models", timeout=10).status_code == 200
            except httpx.HTTPError:
                models[name] = False
        self.check(s, "models answer (reader Qwen3.5-4B, Chinese, non-medical; reasoner Gemma-4-31B, non-medical)", all(models.values()),
                   ", ".join(f"{k} {'up' if v else 'down'}" for k, v in models.items()))

    def step0_clean_earlier(self):
        s = "0 earlier runs"
        mdt = self.vx("tb-mdt")
        stale = [m for m in self.j(mdt.get("/api/tb/meetings")).get("meetings") or [] if str(m.get("title") or "").startswith("E2E")]
        ended = []
        for m in stale:  # an E2E meeting still running would hold the ready hook back: end it (and cancel the planned ones unless --keep)
            if m.get("status") == "in_session":
                mdt.post(f"/api/tb/meetings/{m['id']}/end"); ended.append(m["id"])
            elif m.get("status") == "planned" and not self.args.keep:
                mdt.post(f"/api/tb/meetings/{m['id']}/cancel", json={"reason": "E2E clean-up before a new run"}); ended.append(m["id"])
        removed = []
        if not self.args.keep:
            for row in self.j(mdt.get("/api/tb/cases")).get("cases") or []:
                cid = row.get("case_id") or ""
                if cid.startswith("E2E-"):
                    if mdt.delete(f"/api/tb/cases/{cid}").status_code == 200:
                        removed.append(cid)
        self.check(s, "Case Files and meetings of earlier E2E runs cleared" if not self.args.keep else "earlier E2E runs kept (--keep); running E2E meetings ended",
                   True, f"Case Files removed: {', '.join(removed) or 'none'}; meetings ended or cancelled: {', '.join(ended) or 'none'}")

    def step0_resident(self):
        s = "0 resident account"
        adm = self.vx("tb-breast-admin")
        r = adm.post("/api/tb/departments/breast_surgery/people",
                     json={"email": RESIDENT, "display_name": RESIDENT_NAME, "role": "resident", "end_date": (self.today + timedelta(days=180)).isoformat()})
        b = self.j(r)
        self.need(s, "Breast Surgery department admin places the resident (email login)", r.status_code == 200, f"HTTP {r.status_code}, created {b.get('created')}")
        mailto = b.get("mailto") or ""
        how = "new account"
        if not mailto:  # the account exists from an earlier run: a reset gives a new first password in a mailto
            r = adm.post(f"/api/tb/accounts/{urllib.parse.quote(RESIDENT)}/reset-password", json={"email": RESIDENT})
            mailto = self.j(r).get("mailto") or ""
            how = "existing account, password reset by the department admin"
            self.need(s, "department admin resets the resident's password (mailto)", r.status_code == 200 and mailto, f"HTTP {r.status_code}")
        body = urllib.parse.parse_qs(urllib.parse.urlsplit(mailto).query).get("body", [""])[0]
        m = re.search(r"First password: (\S+)", body)
        self.need(s, "the mailto carries the login name and a first password (kept in memory only)", m and RESIDENT in body and mailto.startswith(f"mailto:{RESIDENT}"),
                  f"{how}; mailto to {RESIDENT}, password not logged")
        first = m.group(1)
        res = self.vx(RESIDENT, first)
        me = self.j(res.get("/api/tb/me"))
        self.check(s, "first sign-in: the password must be changed", me.get("must_change_password") is True, f"must_change_password={me.get('must_change_password')}")
        blocked = res.get("/api/tb/case-list")
        self.check(s, "until then Case Files are refused (409 password_change_required)", blocked.status_code == 409 and "password_change_required" in blocked.text,
                   f"HTTP {blocked.status_code}")
        new = "E2e-" + secrets.token_urlsafe(12)
        r = res.post("/api/tb/me/password", json={"current_password": first, "new_password": new})
        self.need(s, "resident chooses a new password (forced change)", r.status_code == 200 and self.j(r).get("must_change_password") is False, f"HTTP {r.status_code}")
        me = self.j(res.get("/api/tb/me"))
        roles = me.get("roles") or {}
        self.check(s, "the resident is placed as resident of Breast Surgery", (roles.get("departments") or {}).get("breast_surgery") == "resident",
                   f"departments {roles.get('departments')}, primary role {me.get('primary_role')}")
        self.ids["resident"] = RESIDENT

    # ---- 1: the HIMS -------------------------------------------------------------------------------------------------------------
    def step1_hims(self):
        s = "1 HIMS"
        h = self.his()
        reg = {"name": PATIENT_NAME, "sex": "F", "age": "58", "kind": "permanent", "town": "Pune", "district": "Pune", "state": "Maharashtra", "pin": "411001"}
        r = h.post("/his/api/registrations", json=reg)
        note = "new registration"
        if r.status_code == 409 and self.j(r).get("error") == "duplicate":  # an earlier run registered the same synthetic name: a different person
            r = h.post("/his/api/registrations", json={**reg, "confirm_duplicate": "1"})
            note = "similar registration of an earlier run confirmed as a different person"
        p = self.j(r).get("patient") or {}
        self.need(s, "registration desk registers the patient (woman, 58) and gets a UHID", r.status_code == 200 and p.get("uhid"),
                  f"{p.get('name')}, {p.get('uhid')}, {p.get('age')} {p.get('sex')}; {note}")
        self.ids.update(uhid=p["uhid"], his_patient=p["id"])
        r = h.post(f"/his/api/patients/{p['id']}/visits", json={"department": "Breast Surgery", "consultant_id": BREAST_CONSULTANT, "unit": "Unit I", "visit_type": "new"})
        e = self.j(r).get("encounter") or {}
        self.need(s, "OPD visit opened in Breast Surgery (OP No.)", r.status_code == 200 and e.get("number"), f"{e.get('number')} with {(e.get('consultant') or {}).get('name') if isinstance(e.get('consultant'), dict) else e.get('consultant')}")
        self.ids.update(encounter=e["id"], op_no=e["number"])
        # the OPD note on the screen, as the OPD consultant (login + form token); no board question written: it is typed in Vaidyx later
        opd = self.his_screen("opd.doctor@vaidyx-demo.invalid")
        tok = self.csrf(opd, f"/his/encounters/{e['id']}")
        r = opd.post(f"/his/encounters/{e['id']}/notes", follow_redirects=False, data={
            "csrf": tok,
            "v_presenting_complaint": "Painless lump in the right breast for 3 months",
            "v_examination": "Postmenopausal woman. ECOG performance status 1. A 6 x 5 cm hard lump in the upper outer quadrant of the right breast "
                             "with peau d'orange of the overlying skin; a 2 cm firm mobile right axillary lymph node.",
            "v_plan": "Bilateral mammogram, core biopsy, CBC, LFT and CECT chest. Present at the Tumour Board when the reports are in."})
        loc = urllib.parse.unquote_plus(r.headers.get("location", ""))
        self.need(s, "OPD note signed on the screen by the OPD consultant", r.status_code == 303 and "OPD note signed" in loc, loc[:160])
        r = h.post(f"/his/api/encounters/{e['id']}/orders", json={"tests": ["mammogram", "hpe_biopsy", "cbc", "lft", "cect_chest_abdomen_pelvis"]})
        orders = {o["test"]: o for o in self.j(r).get("orders") or []}
        self.need(s, "orders placed: mammogram, core biopsy, CBC, LFT, CECT chest", r.status_code == 200 and len(orders) == 5,
                  "; ".join(f"{o['test']} {o.get('accession') or o['id']}" for o in orders.values()))
        self.ids["orders"] = {k: o["id"] for k, o in orders.items()}
        self.ids["accessions"] = {k: o.get("accession") for k, o in orders.items()}
        # laboratory: collect, results, sign (CBC by Pathology, LFT by the lab doctor of Biochemistry)
        for test, dept, signer, values in (("cbc", "PATH", PATHOLOGIST, {"haemoglobin": "11.8 gm%", "wbc": "7,900 /cumm", "platelets": "2.6 lakhs/cumm"}),
                                           ("lft", "BIO", BIOCHEMIST, {"bilirubin": "0.6 mg/dL", "sgot": "26 U/L", "sgpt": "22 U/L"})):
            oid = orders[test]["id"]
            a = h.post(f"/desk/api/{dept}/orders/{oid}/collect", json={"by": "lab technician"})
            b = h.post(f"/desk/api/{dept}/orders/{oid}/preliminary", json={"values": values, "reporter": signer})
            c = h.post(f"/desk/api/{dept}/orders/{oid}/sign", json={"signer": signer})
            rep = self.j(c)
            self.need(s, f"lab {test.upper()}: sample collected, results entered, verified and signed", a.status_code == b.status_code == c.status_code == 200
                      and rep.get("status") == "final" and rep.get("signature_id"), f"{rep.get('id')} {rep.get('status')} v{rep.get('current_version')}, signature {rep.get('signature_id')}")
        # radiology: schedule today, report, sign the mammogram; the image comes from the public library when the PACS import maps one
        oid = orders["mammogram"]["id"]
        a = h.post(f"/desk/api/RAD/orders/{oid}/schedule", json={"date": self.today.isoformat(), "by": "radiology technician"})
        b = h.post(f"/desk/api/RAD/orders/{oid}/preliminary", json={"reporter": RADIOLOGIST, "values": {
            "technique": "Bilateral digital mammography, craniocaudal and mediolateral oblique views.",
            "comparison": "No earlier study available.",
            "findings": "Right breast: an irregular high-density mass with spiculated margins in the upper outer quadrant measuring 5.8 x 4.9 cm, "
                        "with thickening of the overlying skin. No suspicious microcalcification. An enlarged right axillary lymph node of 2.1 cm. "
                        "Left breast: no mass.",
            "impression": "Right breast upper outer quadrant mass with skin thickening and an enlarged right axillary lymph node, BI-RADS 5."}})
        c = h.post(f"/desk/api/RAD/orders/{oid}/sign", json={"signer": RADIOLOGIST})
        rep = self.j(c)
        self.need(s, "radiology: mammogram scheduled today, reported and signed", a.status_code == b.status_code == c.status_code == 200 and rep.get("status") == "final",
                  f"{rep.get('id')} {rep.get('status')}; desk notes: {'; '.join(m.get('text', '') for m in rep.get('desk_messages') or [])[:120] or 'none'}")
        study = self._study(orders["mammogram"]["accession"])
        src = (study or {}).get("image_source") or {}
        self.check(s, "imaging study recorded with its image source", study and study.get("status") == "available",
                   f"study {(study or {}).get('study_uid', '')[:40]}..., {(study or {}).get('modality')}, {study.get('number_of_instances') if study else 0} images, "
                   f"source {src.get('kind')}{(' ' + src.get('collection', '') + ' (' + src.get('licence', '') + ')') if src.get('kind') == 'public' else (' (' + src.get('reason', 'synthetic') + ')')}")
        self.ids["study"] = study or {}
        # pathology: receive the biopsy (block No.), HPE final signed; IHC added on (left pending); CT chest left not done
        oid = orders["hpe_biopsy"]["id"]
        block = f"{orders['hpe_biopsy']['accession']}-A1"
        a = h.post(f"/desk/api/PATH/orders/{oid}/collect", json={"block_no": block, "by": "pathology technician"})
        c = h.post(f"/desk/api/PATH/orders/{oid}/sign", json={"signer": PATHOLOGIST, "values": {
            "specimen": "Core biopsy, right breast upper outer quadrant, in 10% buffered formalin",
            "gross": "Three linear grey-white cores, 1.1 to 1.5 cm, entirely submitted",
            "microscopy": "Cores show an infiltrating carcinoma arranged in nests and cords with moderate nuclear pleomorphism and occasional mitoses. "
                          "No lymphovascular invasion seen in the cores.",
            "histologic_type": "Invasive breast carcinoma of no special type",
            "grade": "Grade 2 (Nottingham score 6)",
            "diagnosis": "Right breast core biopsy: invasive breast carcinoma of no special type, grade 2. IHC for ER, PR, HER2 and Ki-67 to follow."}})
        rep = self.j(c)
        self.need(s, "pathology: biopsy received (block No.), HPE final signed", a.status_code == c.status_code == 200 and rep.get("status") == "final",
                  f"block {block}, {rep.get('id')} {rep.get('status')}")
        path = self.his_screen("pathologist@vaidyx-demo.invalid")
        tok = self.csrf(path, f"/his/pathology/orders/{oid}")
        r = path.post(f"/his/pathology/orders/{oid}/addon", data={"csrf": tok, "test": "ihc_breast"}, follow_redirects=False)
        loc = r.headers.get("location", "")
        m = re.search(r"/his/pathology/orders/([^/?]+)", loc)
        self.need(s, "IHC (ER, PR, HER2, Ki-67) added on by the pathologist on the screen, left pending", r.status_code == 303 and m and m.group(1) != oid,
                  urllib.parse.unquote_plus(loc)[:160])
        self.ids["orders"]["ihc_breast"] = m.group(1)
        enc = self.j(h.get(f"/his/api/encounters/{e['id']}"))
        st = {o["test"]: o["status"] for o in enc.get("orders") or []}
        self.check(s, "worklists as planned: IHC ordered, CECT chest not done", st.get("ihc_breast") == "ordered" and st.get("cect_chest_abdomen_pelvis") == "ordered",
                   json.dumps(st))

    def _study(self, accession):
        """The HIMS imaging study of an accession (the store, read only: the FHIR resource does not carry the image source)."""
        try:
            data = json.loads((HIS_DATA / "store.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return next((x for x in (data.get("imaging_studies") or {}).values() if x.get("accession") == accession), None)

    # ---- 2: the PACS -------------------------------------------------------------------------------------------------------------
    def step2_pacs(self):
        s = "2 PACS"
        acc, uhid = self.ids["accessions"]["mammogram"], self.ids["uhid"]
        r = httpx.get(f"{ORTHANC}/dicom-web/studies", params={"AccessionNumber": acc, "PatientID": uhid}, timeout=30)
        rows = self.j(r) if r.status_code == 200 else []
        rows = rows if isinstance(rows, list) else []
        uid = ((rows[0].get("0020000D") or {}).get("Value") or [""])[0] if rows else ""
        n = ((rows[0].get("00201208") or {}).get("Value") or [0])[0] if rows else 0
        mods = ((rows[0].get("00080061") or {}).get("Value") or []) if rows else []
        self.need(s, "the mammogram study is in Orthanc (QIDO by accession and PatientID = UHID)", len(rows) == 1 and uid == self.ids["study"].get("study_uid"),
                  f"{len(rows)} study, uid matches the HIMS ImagingStudy: {uid == self.ids['study'].get('study_uid')}, modalities {mods}, {n} instances")

    # ---- 3: the Case File --------------------------------------------------------------------------------------------------------
    def slots(self, c, cid):
        v = self.j(c.get(f"/api/tb/cases/{cid}/slots"))
        return v, {sl["id"]: sl for sec in v.get("sections") or [] for sl in sec.get("slots") or []}

    def step3_casefile(self):
        s = "3 Case File"
        doc = self.vx("tb-breast-doc")
        uhid = self.ids["uhid"]
        lk = self.j(doc.get("/api/tb/his/lookup", params={"identifier": uhid}))
        self.check(s, "Dr Breast looks the UHID up in the HIMS", lk.get("found") and (lk.get("patient") or {}).get("uhid") == uhid,
                   f"{(lk.get('patient') or {}).get('name')}, {lk.get('reports')} reports in the window, {lk.get('older')} older")
        cid = f"E2E-{self.stamp}-A"
        if self.args.start:  # a debugging re-start of this step: the Case File of the earlier attempt goes first
            self.vx("tb-mdt").delete(f"/api/tb/cases/{cid}")
        r = doc.post("/api/tb/cases/from-his", json={"identifier": uhid, "protocol": "breast", "setting": "locally_advanced", "board_date": self.today.isoformat(), "case_id": cid})
        b = self.j(r)
        self.need(s, "Case File created from the UHID (protocol breast, setting locally advanced, as recorded)", r.status_code == 200 and b.get("job"), f"{cid}: HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        self.ids["case_a"] = cid
        job, secs = self.wait_job(doc, b["job"])
        self.need(s, "the first fetch job finishes", job.get("state") == "finished", f"{job.get('state')} in {secs} s, {job.get('total')} records")
        v, sl = self.slots(doc, cid)
        self.ids["slots_first"] = {k: x.get("status") for k, x in sl.items()}
        img, lesion = sl.get("record:breast_imaging") or {}, sl.get("fact:lesion_size") or {}
        hpe, htype = sl.get("record:histopathology") or {}, sl.get("fact:histologic_type") or {}
        self.check(s, "slots: mammogram found with its quote", img.get("status") == "found" and img.get("quote"),
                   f"{img.get('value')}; lesion size {lesion.get('status')}: \"{lesion.get('value')}\"")
        self.check(s, "slots: lesion size quote is verbatim in the mammogram report", lesion.get("status") == "found" and self.verbatim(doc, cid, lesion.get("quote")),
                   f"quote \"{((lesion.get('quote') or {}).get('text') or '')[:120]}\"")
        self.check(s, "slots: HPE found, histological type quoted verbatim", hpe.get("status") == "found" and htype.get("status") == "found" and self.verbatim(doc, cid, htype.get("quote")),
                   f"\"{((htype.get('quote') or {}).get('text') or '')[:120]}\"")
        ihc = sl.get("record:receptor_status") or {}
        er = sl.get("fact:er") or {}
        self.check(s, "slots: IHC (receptor status) waiting or not found", ihc.get("status") in ("waiting", "not_found") and er.get("status") in ("waiting", "not_found"),
                   f"receptor status {ihc.get('status')} ({ihc.get('note', '')[:100]}); ER {er.get('status')}")
        ct = sl.get("record:cect_chest_abdomen") or {}
        mw = sl.get("record:metastatic_workup") or {}
        self.check(s, "slots: CT chest not found in the file (ordered, not done)", ct.get("status") == "not_found" and mw.get("status") == "not_found",
                   f"CECT chest and abdomen {ct.get('status')}: {ct.get('note', '')[:120]}; metastatic work-up {mw.get('status')}")
        self.check(s, "left before the board counted", isinstance(v.get("left_before_board"), int) and v["left_before_board"] > 0,
                   f"{v.get('left_before_board')} lines left; blockers: {'; '.join(x.get('why', '') for x in v.get('blockers') or [])[:160]}")
        # urgency, join code, the resident
        r = doc.put(f"/api/tb/cases/{cid}/urgency", json={"level": 4, "note": "E2E: set by the treating consultant"})
        u = self.j(r).get("urgency") or {}
        self.check(s, "urgency set to 4 by the consultant", r.status_code == 200 and u.get("level") == 4, f"level {u.get('level')} set by {u.get('set_by')}")
        r = doc.post(f"/api/tb/cases/{cid}/team/code")
        code = self.j(r).get("code") or ""
        self.need(s, "join code made (6 digits, not logged)", r.status_code == 200 and re.fullmatch(r"\d{6}", code), f"expires {self.j(r).get('expires_at')}")
        res = self.clients[RESIDENT]
        r = res.post("/api/tb/case-join", json={"code": code})
        self.need(s, "the resident joins with /case-join", r.status_code == 200 and self.j(r).get("status") == "joined", f"{self.j(r).get('status')}: {self.j(r).get('patient_line')}")
        team = self.j(doc.get(f"/api/tb/cases/{cid}/team"))
        self.check(s, "the team shows the resident", any(x.get("user") == RESIDENT for x in team.get("residents") or []),
                   ", ".join(f"{x.get('name')} until {x.get('end_date')}" for x in team.get("residents") or []))
        # the resident proposes "not needed" on one line; the consultant approves (the waive runs as the consultant)
        v, sl = self.slots(res, cid)
        avoid = {"record:cect_chest_abdomen", "record:metastatic_workup", "record:receptor_status", "record:ki67", "record:grade", "record:histopathology",
                 "record:breast_imaging", "record:clinical_history"}
        prefer = ["record:mri_breast", "record:pet_ct", "record:usg_axilla"]
        cand = [k for k in prefer if (sl.get(k) or {}).get("status") == "not_found" and any(a.get("kind") == "not_needed" for a in (sl.get(k) or {}).get("actions") or [])]
        cand += [k for k, x in sl.items() if x.get("kind") == "record" and x.get("required") and x.get("status") == "not_found" and k not in avoid and k not in cand]
        self.need(s, "a line the resident can propose as not needed", cand, f"candidates {cand[:4]}")
        line = cand[0]
        self.ids["waived_line"] = line
        reason = {"record:mri_breast": "MRI breast not needed before the first discussion: mammogram and core biopsy are in the file.",
                  "record:pet_ct": "PET-CT not needed before the first discussion: CECT chest and abdomen and bone scan are planned."}.get(
            line, "Not needed for this patient before the first board discussion (E2E scenario).")
        r = res.post(f"/api/tb/cases/{cid}/proposals", json={"action": "not_needed", "payload": {"slot": line, "reason": reason}, "note": "Please sign off"})
        p = self.j(r).get("proposal") or {}
        self.need(s, f"the resident proposes \"not needed\" on {sl[line]['label']}", r.status_code == 200 and p.get("status") == "pending", f"proposal {p.get('id')} by {p.get('by')}")
        w = self.j(doc.get("/api/tb/waiting")).get("items") or []
        self.check(s, "the consultant sees the sign-off in /waiting", any(x.get("case_id") == cid and x.get("kind") == "proposal" for x in w),
                   "; ".join(x.get("title", "") for x in w if x.get("case_id") == cid)[:200])
        direct = res.post(f"/api/tb/cases/{cid}/slots/{line}/not-needed", json={"reason": reason})
        self.check(s, "the resident cannot waive directly (403)", direct.status_code == 403, f"HTTP {direct.status_code}")
        r = doc.post(f"/api/tb/cases/{cid}/proposals/{p['id']}/approve", json={"note": "Agreed"})
        out = self.j(r)
        self.need(s, "the consultant approves the proposal", r.status_code == 200 and (out.get("proposal") or {}).get("status") == "approved", f"HTTP {r.status_code} {r.text[:160] if r.status_code != 200 else ''}")
        one = self.j(doc.get(f"/api/tb/cases/{cid}/slots/{line}"))
        audit = self.j(doc.get(f"/api/tb/cases/{cid}/audit")).get("events") or []
        conf = [e for e in audit if e.get("kind") == "confirmation" and e.get("type") == "waive"]
        self.check(s, "the line is not needed now, the waive recorded as the consultant", one.get("status") == "not_needed" and (one.get("waiver") or {}).get("by") == "tb-breast-doc"
                   and conf and conf[-1].get("by") == "tb-breast-doc", f"{one.get('status')}: {one.get('note', '')[:140]}")
        # the consultant asks Pathology for the IHC from the line; Pathology sees it in its inbox and acknowledges it
        r = doc.post(f"/api/tb/cases/{cid}/slots/record:receptor_status/ask-department", json={"message": "Please report the IHC (ER, PR, HER2, Ki-67) on the core biopsy block."})
        out = self.j(r)
        req = out.get("request") or {}
        self.need(s, "the consultant asks Pathology for the IHC (ask-department)", r.status_code == 200 and req.get("action_id") and req.get("department") == "Pathology",
                  f"HTTP {r.status_code}; request {req.get('action_id')} to {req.get('department')}, due {req.get('due_label')} {r.text[:120] if r.status_code != 200 else ''}")
        v, sl = self.slots(doc, cid)
        self.check(s, "the IHC lines now say waiting on Pathology", (out.get("slot") or {}).get("status") == "waiting" and (sl.get("fact:er") or {}).get("status") == "waiting",
                   f"receptor status {(out.get('slot') or {}).get('status')}, ER {(sl.get('fact:er') or {}).get('status')}, asked {((sl.get('fact:er') or {}).get('request') or {}).get('sent_at')}")
        self.ids["ihc_request"] = req.get("action_id")
        ph = self.vx("tb-path-head")
        inbox = self.j(ph.get("/api/tb/inbox"))
        mine = [q for d in inbox.get("departments") or [] for q in d.get("requests") or [] if q.get("case_id") == cid]
        self.need(s, "Pathology (tb-path-head) sees the request in GET /inbox", any(q.get("action_id") == req["action_id"] or q.get("id") == req["action_id"] for q in mine),
                  f"{len(mine)} request(s) for this Case File; UHID {mine[0].get('uhid') if mine else ''}, encounter {mine[0].get('encounter') if mine else ''}")
        r = ph.post(f"/api/tb/cases/{cid}/requests/{req['action_id']}/acknowledge")
        self.check(s, "Pathology acknowledges it", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        chats = ph.get(f"/api/tb/cases/{cid}/chats")
        self.check(s, "Pathology does not read the team chat", chats.status_code == 403, f"HTTP {chats.status_code}")

    # ---- 4: the IHC arrives --------------------------------------------------------------------------------------------------------
    def step4_ihc(self):
        s = "4 IHC"
        cid, oid = self.ids["case_a"], self.ids["orders"]["ihc_breast"]
        path = self.his_screen("pathologist@vaidyx-demo.invalid")
        tok = self.csrf(path, f"/his/pathology/orders/{oid}")
        block = f"{self.ids['accessions']['hpe_biopsy']}-A1"
        r1 = path.post(f"/his/pathology/orders/{oid}/receive", data={"csrf": tok, "block_no": block}, follow_redirects=False)
        tok = self.csrf(path, f"/his/pathology/orders/{oid}")
        r2 = path.post(f"/his/pathology/orders/{oid}/report", follow_redirects=False, data={
            "csrf": tok, "action": "sign", "v_er": "Positive (Allred score 8/8)", "v_pr": "Positive (Allred score 6/8)", "v_her2": "1+ (Negative)", "v_ki67": "20 %"})
        loc = urllib.parse.unquote_plus(r2.headers.get("location", ""))
        self.need(s, "the pathologist enters and signs the IHC on the screen", r1.status_code == 303 and r2.status_code == 303 and "final" in loc, loc[:160])
        doc = self.vx("tb-breast-doc")
        r = doc.post(f"/api/tb/cases/{cid}/his/refetch")
        b = self.j(r)
        self.need(s, "Vaidyx re-fetch started (POST his/refetch)", r.status_code == 200 and b.get("job"), f"HTTP {r.status_code}, {b.get('total')} new or changed record(s)")
        job, secs = self.wait_job(doc, b["job"])
        self.need(s, "the re-fetch job finishes", job.get("state") == "finished", f"{job.get('state')} in {secs} s; result {json.dumps(job.get('refetch_result') or {})[:160]}")
        st = self.j(doc.get(f"/api/tb/cases/{cid}")).get("state") or {}
        a = next((x for x in st.get("actions") or [] if x.get("id") == self.ids["ihc_request"]), {})
        self.check(s, "the request closed by itself", a.get("status") == "completed", f"status {a.get('status')} at {a.get('completed')}; the re-fetch closed {(job.get('refetch_result') or {}).get('closed')}")
        v, sl = self.slots(doc, cid)
        rs, er = sl.get("record:receptor_status") or {}, sl.get("fact:er") or {}
        self.check(s, "the IHC line is found now, ER quoted verbatim", rs.get("status") == "found" and er.get("status") == "found" and self.verbatim(doc, cid, er.get("quote")),
                   f"receptor status {rs.get('status')}; ER \"{er.get('value')}\" from \"{((er.get('quote') or {}).get('text') or '')[:100]}\"")
        n = self.j(doc.get("/api/tb/notifications", params={"limit": 50})).get("notifications") or []
        self.check(s, "the owner is told what closed", any(x.get("case_id") == cid and x.get("kind") == "request_closed" for x in n),
                   next((x.get("title") for x in n if x.get("case_id") == cid and x.get("kind") == "request_closed"), "no notice"))

    # ---- 5: Ask this Case File ------------------------------------------------------------------------------------------------------
    def step5_ask(self):
        s = "5 Ask"
        cid = self.ids["case_a"]
        doc = self.vx("tb-breast-doc")
        q = "What is the histological type and grade on the core biopsy, and what are the ER, PR and HER2 results?"
        t0 = time.time()
        r = doc.post(f"/api/tb/cases/{cid}/chats", json={"question": q})
        t = self.j(r)
        self.need(s, "a question through POST chats (real model) is answered", r.status_code == 200 and t.get("status") == "answered",
                  f"{t.get('status')} in {round(time.time() - t0)} s, {len(t.get('statements') or [])} statement(s), {t.get('dropped_unverified')} dropped as unverified")
        cites = [c for st in t.get("statements") or [] for c in st.get("citations") or []]
        bad = [c for c in cites if not self.verbatim(doc, cid, c)]
        self.check(s, "every citation is a verbatim quote of a report", cites and not bad,
                   f"{len(cites)} citation(s), {len(bad)} not verbatim; first: \"{(cites[0].get('quote') if cites else '')[:100]}\"")
        self.ids["thread"] = t.get("id")
        res = self.clients[RESIDENT]
        th = self.j(res.get(f"/api/tb/cases/{cid}/chats")).get("threads") or []
        self.check(s, "shared with the team: the resident sees the thread", any(x.get("id") == t.get("id") for x in th), f"{len(th)} thread(s) for the resident")

    # ---- 6: ready -------------------------------------------------------------------------------------------------------------------
    def step6_ready(self):
        s = "6 Ready"
        cid = self.ids["case_a"]
        doc = self.vx("tb-breast-doc")
        self.ids["board_question"] = "Locally advanced breast cancer as recorded: neoadjuvant systemic therapy first, or upfront surgery?"
        r = doc.post(f"/api/tb/cases/{cid}/slots/fact:clinical_question/value", json={"value": self.ids["board_question"]})
        q = self.j(r)
        self.need(s, "the board question is typed on its line", r.status_code == 200 and q.get("status") == "entered", f"{q.get('status')}: {q.get('note', '')[:120]}")
        v, sl = self.slots(doc, cid)
        self.check(s, "Mark ready is allowed", v.get("ready_allowed") is True, f"left before the board {v.get('left_before_board')}; blockers {[b.get('why') for b in v.get('blockers') or []]}")
        r = doc.post(f"/api/tb/cases/{cid}/ready", json={"ready": True, "note": "E2E: ready for the board"})
        self.need(s, "Mark ready (POST ready)", r.status_code == 200 and (self.j(r).get("board_ready") or {}).get("by") == "tb-breast-doc", f"HTTP {r.status_code}")
        t0 = time.time()
        prose = {}
        while time.time() - t0 < 180:
            prose = self.j(doc.get(f"/api/tb/cases/{cid}/slots")).get("prose") or {}
            if prose.get("status") == "ready":
                break
            time.sleep(5)
        secs = round(time.time() - t0)
        self.check(s, "the ready hook prepared the summary within 3 minutes (AI draft, not reviewed)", prose.get("status") == "ready" and prose.get("paragraphs"),
                   f"{prose.get('status')} after {secs} s: {len(prose.get('paragraphs') or [])} section(s), label \"{prose.get('label')}\", model {prose.get('model')}")
        hl = self.j(doc.get(f"/api/tb/cases/{cid}/helpers")).get("helpers") or []
        heads = {x.get("role"): (x.get("brief") or {}).get("status") for x in hl}
        five = [heads.get(k) for k in ("radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology")]
        self.check(s, "the five heads' briefs are queued or ready", all(x in ("preparing", "ready") for x in five) or (secs < 180 and any(x == "ready" for x in five)),
                   json.dumps(heads))

    # ---- 7: the meeting -------------------------------------------------------------------------------------------------------------
    def step7_meeting(self):
        s = "7 Meeting"
        cid = self.ids["case_a"]
        mdt = self.vx("tb-mdt")
        at = (datetime.now() + timedelta(minutes=10)).strftime("%H:%M")
        r = mdt.post("/api/tb/meetings", json={"date": self.today.isoformat(), "time": at, "room": "Seminar room 2", "video": True, "title": f"E2E scenario {self.stamp}"})
        m = self.j(r).get("meeting") or {}
        self.need(s, "the coordinator creates a meeting today with video", r.status_code == 200 and m.get("id") and m.get("video"), f"{m.get('id')} {m.get('date')} {m.get('time')}, video {m.get('video')}")
        mid = self.ids["meeting"] = m["id"]
        r = mdt.put(f"/api/tb/meetings/{mid}/agenda", json={"discussion": [cid], "noting": []})
        ag = self.j(r).get("agenda") or {}
        self.need(s, "the Case File is put in For discussion", r.status_code == 200 and any(x.get("case_id") == cid for x in ag.get("discussion") or []),
                  "; ".join(f"{x.get('patient_line')}" for x in ag.get("discussion") or [])[:200])
        row = next((x for x in ag.get("discussion") or [] if x.get("case_id") == cid), {})
        self.check(s, "the agenda row shows the board question as typed", row.get("board_question") == self.ids.get("board_question"), f"\"{row.get('board_question')}\"")
        r = mdt.post(f"/api/tb/meetings/{mid}/send-agenda")
        self.check(s, "agenda sent", r.status_code == 200, f"HTTP {r.status_code} {json.dumps(self.j(r))[:160]}")
        r = mdt.post(f"/api/tb/meetings/{mid}/code")
        code = self.j(r).get("value") or ""
        self.need(s, "meeting code made (6 digits, not logged)", r.status_code == 200 and re.fullmatch(r"\d{6}", code), f"expires {self.j(r).get('expires_at')}")
        rad, ph = self.vx("tb-rad-doc"), self.vx("tb-path-head")
        j1, j2 = rad.post("/api/tb/meetings/join", json={"code": code}), ph.post("/api/tb/meetings/join", json={"code": code})
        self.need(s, "two members join with the code and wait to be admitted", j1.status_code == j2.status_code == 200 and self.j(j1).get("status") == self.j(j2).get("status") == "waiting",
                  f"tb-rad-doc {self.j(j1).get('status')}, tb-path-head {self.j(j2).get('status')}")
        p1 = rad.post(f"/api/tb/meetings/{mid}/present", json={"mode": "room"})
        p2 = ph.post(f"/api/tb/meetings/{mid}/present", json={"mode": "remote"})
        a1 = self.j(mdt.post(f"/api/tb/meetings/{mid}/admit", json={"user": "tb-rad-doc"}))
        a2 = self.j(mdt.post(f"/api/tb/meetings/{mid}/admit", json={"user": "tb-path-head"}))
        self.check(s, "the coordinator admits them: one in the room, one remote", p1.status_code == p2.status_code == 200 and a1.get("status") == "present" and a2.get("status") == "remote",
                   f"tb-rad-doc {a1.get('status')}, tb-path-head {a2.get('status')}")
        room = Socket(mid, mdt.cookies.get("vaidyx_session"))
        remote = Socket(mid, ph.cookies.get("vaidyx_session"))
        st = room.wait(lambda e: e.get("type") == "state", 15)
        st2 = remote.wait(lambda e: e.get("type") == "state", 15)
        self.need(s, "WebSocket (cookie auth) for the room screen and a remote member receives the state", st and st2,
                  f"room screen: {len((st or {}).get('attendance') or [])} attendance rows; remote member: state {'received' if st2 else 'missing'}")
        bad = Socket(mid, mdt.cookies.get("vaidyx_session"), origin="http://evil.example")
        self.check(s, "a socket from another origin is refused", bad.closed_without_state(5), "closed with code 1008")
        bad.close()
        try:
            r = mdt.post(f"/api/tb/meetings/{mid}/start")
            self.need(s, "the meeting starts", r.status_code == 200, f"HTTP {r.status_code}; {self.j(r).get('preparing')} stand-in brief(s) preparing")
            r = mdt.post(f"/api/tb/meetings/{mid}/current", json={"case_id": cid})
            ev = room.wait(lambda e: e.get("type") == "current" and e.get("case_id") == cid, 15)
            self.check(s, "the coordinator sets the current Case File (current event on the socket)", r.status_code == 200 and ev, f"HTTP {r.status_code}; event {'received' if ev else 'missing'}")
            full = self.j(mdt.get(f"/api/tb/cases/{cid}"))
            mammo = next((d for d in full.get("documents") or [] if (d.get("classification") or {}).get("doc_type") == "mammogram" or "mammo" in str(d.get("rel_path") or "").lower()), None)
            self.need(s, "the mammogram record is in the Case File", mammo, (mammo or {}).get("rel_path", "none"))
            hpe = next((d for d in full.get("documents") or [] if (d.get("classification") or {}).get("doc_type") == "histopathology"), None)
            if hpe:
                r = mdt.post(f"/api/tb/meetings/{mid}/open", json={"kind": "record", "doc_id": hpe["doc_id"]})
                ev = remote.wait(lambda e: e.get("type") == "open" and (e.get("opened") or {}).get("kind") == "record", 15)
                page = rad.get(f"/api/tb/cases/{cid}/documents/{hpe['doc_id']}/file", params={"render": 1, "page": 0})
                other = rad.get(f"/api/tb/cases/{cid}/documents/{mammo['doc_id']}/file", params={"render": 1, "page": 0})
                self.check(s, "a record on the shared screen: the members follow it (only that record)", r.status_code == 200 and ev and page.status_code == 200
                           and other.status_code == 403, f"HPE report page for tb-rad-doc HTTP {page.status_code} ({page.headers.get('content-type')}); "
                           f"a record not on the screen HTTP {other.status_code}")
            r = mdt.post(f"/api/tb/meetings/{mid}/open", json={"kind": "images", "doc_id": mammo["doc_id"]})
            opened = self.j(r).get("opened") or {}
            ev = room.wait(lambda e: e.get("type") == "open" and (e.get("opened") or {}).get("kind") == "images" and (e.get("opened") or {}).get("url"), 15)
            ev2 = remote.wait(lambda e: e.get("type") == "open" and (e.get("opened") or {}).get("kind") == "images" and (e.get("opened") or {}).get("url"), 15)
            url = (ev or {}).get("opened", {}).get("url") or opened.get("url") or ""
            self.need(s, "images opened on the shared screen: the viewer url arrives on the socket", r.status_code == 200 and ev and ev2 and url.startswith("/api/tb/pacs/"),
                      f"{url[:90]}; granted {opened.get('granted')}")
            g = rad.get(url)
            self.check(s, "GET of the viewer url through /api/tb/pacs answers 200 for an admitted member", g.status_code == 200, f"tb-rad-doc HTTP {g.status_code}, {len(g.content)} bytes")
            uid = opened.get("study_uid") or ""
            q = rad.get(f"/api/tb/pacs/dicom-web/studies/{uid}/series")
            self.check(s, "the study's DICOMweb series answer through the proxy for that member", q.status_code == 200, f"HTTP {q.status_code}")
            other = self.vx("tb-medonc-doc").get(url)
            self.check(s, "a doctor not admitted to the meeting gets no viewer (403)", other.status_code == 403, f"tb-medonc-doc HTTP {other.status_code}")
            r = ph.post(f"/api/tb/meetings/{mid}/questions", json={"text": "Is the IHC on the same block as the core biopsy?"})
            ev = room.wait(lambda e: e.get("type") == "question", 15)
            self.check(s, "a member types a question; it reaches the room screen", r.status_code == 200 and ev, f"HTTP {r.status_code}; event {'received' if ev else 'missing'}")
            text = "Neoadjuvant systemic therapy as per the Medical Oncology unit, then re-assessment for surgery; CECT chest and abdomen and bone scan before the first cycle."
            r = mdt.put(f"/api/tb/meetings/{mid}/decision-live", json={"text": text})
            ev = room.wait(lambda e: e.get("type") == "decision_live" and e.get("text") == text, 15)
            self.check(s, "the decision is typed live (decision_live broadcast, not saved)", r.status_code == 200 and ev and ev.get("saved") is False, f"event {'received' if ev else 'missing'}")
            r = mdt.post(f"/api/tb/meetings/{mid}/cases/{cid}/decision", json={
                "outcome": "decision", "decision_text": text, "rationale": "As discussed by the board, read back to the members before saving.",
                "intent_as_stated": "curative", "responsible_doctor": "Dr Breast Surgery (demo)", "next_step": "Surgery date to be fixed in the OPD",
                "next_step_date": (self.today + timedelta(days=7)).isoformat(), "members_present": ["Dr Radiology (demo)", "Dr Pathology head (demo)", "MDT Coordinator (demo)"]})
            out = self.j(r)
            self.need(s, "the decision is saved after the read-back (outcome decision)", r.status_code == 200 and (out.get("outcome") or {}).get("outcome") == "decision",
                      f"HTTP {r.status_code}; record {(out.get('record') or {}).get('id')} {r.text[:160] if r.status_code != 200 else ''}")
            r = mdt.post(f"/api/tb/meetings/{mid}/cases/{cid}/end")
            ev = room.wait(lambda e: e.get("type") == "end_case", 15)
            self.check(s, "end of the case: cards requested from the heads", r.status_code == 200 and self.j(r).get("cards_requested"), f"{self.j(r).get('cards_requested')}")
            r = ph.post(f"/api/tb/meetings/{mid}/cases/{cid}/card", json={"agree": True, "note": "Agree; IHC reviewed."})
            card = self.j(r).get("card") or {}
            self.check(s, "a head gives a card", r.status_code == 200 and card.get("agree") is True and card.get("head") is True, f"{card.get('name')} ({card.get('department')}), head {card.get('head')}")
            cards = self.j(self.vx("tb-breast-doc").get(f"/api/tb/meetings/{mid}/cards")).get("cards") or {}
            self.check(s, "the owner's team reads the cards", cid in cards and any(c.get("user") == "tb-path-head" for c in cards[cid].get("cards") or []),
                       f"{len((cards.get(cid) or {}).get('cards') or [])} card(s), missing {(cards.get(cid) or {}).get('missing')}")
            r = ph.post(f"/api/tb/meetings/{mid}/video-token")
            vt = self.j(r)
            ok = r.status_code == 200 and vt.get("token")
            val = httpx.get(f"{LIVEKIT}/rtc/validate", params={"access_token": vt.get("token", "")}, timeout=15) if ok else None
            self.check(s, "LiveKit: video token for a member validates against /rtc/validate", ok and val is not None and val.status_code == 200,
                       f"room {vt.get('room')}, identity {vt.get('identity')}, LiveKit {val.status_code if val is not None else 'not asked'} {val.text[:40] if val is not None else ''}")
            nt = self.vx("tb-medonc-doc").post(f"/api/tb/meetings/{mid}/video-token")
            self.check(s, "no video token for someone not admitted (403)", nt.status_code == 403, f"HTTP {nt.status_code}")
            r = mdt.post(f"/api/tb/meetings/{mid}/end")
            ev = room.wait(lambda e: e.get("type") == "ended", 15)
            self.check(s, "the coordinator ends the meeting", r.status_code == 200 and (self.j(r).get("meeting") or {}).get("status") == "closed", f"status {(self.j(r).get('meeting') or {}).get('status')}")
        finally:
            room.close(); remote.close()

    # ---- 8: the outcome --------------------------------------------------------------------------------------------------------------
    def step8_outcome(self):
        s = "8 Outcome"
        cid = self.ids["case_a"]
        doc = self.vx("tb-breast-doc")
        n = self.j(doc.get("/api/tb/notifications", params={"limit": 50})).get("notifications") or []
        hit = next((x for x in n if x.get("case_id") == cid and x.get("kind") == "outcome"), None)
        self.check(s, "the owner gets the outcome notification", hit, (hit or {}).get("title", "none"))
        rows = self.j(doc.get("/api/tb/case-list")).get("cases") or []
        row = next((x for x in rows if x.get("case_id") == cid), {})
        self.check(s, "GET /case-list shows the Case File as decided", (row.get("status") or {}).get("key") == "decided",
                   f"{(row.get('status') or {}).get('label')}; urgency {(row.get('urgency') or {}).get('level')}; residents {row.get('residents_count')}")

    # ---- 9: owner rule 5, outside reports ---------------------------------------------------------------------------------------------
    def step9_outside(self):
        s = "9 Outside reports"
        sr = self.j(self.his().get("/his/api/search", params={"q": DEMO_PATIENT}))
        p = (sr.get("patients") or [{}])[0]
        self.need(s, f"the demo patient {DEMO_PATIENT} is in the HIMS", p.get("uhid") == DEMO_PATIENT, f"{p.get('name')}, {p.get('age')} {p.get('sex')}")
        files = sorted((HIS_DATA / "documents").glob("p19-*.pdf"))
        self.need(s, "the demo documents of that patient are on disk", files, f"{len(files)} PDFs: {', '.join(f.name for f in files)}")
        doc = self.vx("tb-breast-doc")
        cid = f"E2E-{self.stamp}-B"
        sex = {"F": "F", "M": "M"}.get(str(p.get("sex") or "").upper()[:1], "F")
        r = doc.post("/api/tb/cases", json={"case_id": cid, "patient": {"name": p.get("name"), "mrn": DEMO_PATIENT, "agesex": f"{p.get('age')} Y / {sex}"},
                                             "protocol": "breast", "setting": "early", "board_date": (self.today + timedelta(days=7)).isoformat()})
        self.need(s, "a second fresh Case File for that patient", r.status_code == 200, f"{cid}: HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        self.ids["case_b"] = cid
        up = [("files", (f.name, f.read_bytes(), "application/pdf")) for f in files]
        r = doc.post(f"/api/tb/cases/{cid}/documents", files=up, data={"paths": json.dumps([f.name for f in files]), "outside": "1"})
        b = self.j(r)
        self.need(s, "the PDFs are uploaded as outside reports (POST documents)", r.status_code == 200 and b.get("job"), f"{b.get('total')} file(s), warnings {b.get('warnings')}")
        job, secs = self.wait_job(doc, b["job"])
        self.need(s, "the reading job finishes", job.get("state") == "finished", f"{job.get('state')} in {secs} s")
        d = self.j(doc.get(f"/api/tb/cases/{cid}"))
        docs = d.get("documents") or []
        types = {x.get("filename"): ((x.get("classification") or {}).get("doc_type"), x.get("state")) for x in docs}
        ready = [x for x in docs if x.get("state") == "ready" and (x.get("classification") or {}).get("doc_type")]
        self.check(s, "every document is read and filed with a type", len(docs) == len(files) and len(ready) == len(files),
                   "; ".join(f"{k}: {v[0]} ({v[1]})" for k, v in sorted(types.items())))
        outside = [x for x in docs if x.get("outside") or (x.get("source") == "outside")]
        self.check(s, "they are labelled outside reports", len(outside) == len(files), f"{len(outside)} of {len(docs)} labelled outside")
        gate = (d.get("state") or {}).get("gate") or {}
        self.check(s, "the Pre-Authorization gate ran on them", gate.get("total"), f"{gate.get('satisfied')} of {gate.get('total')} records met")

    # ---- clean-up and the log ----------------------------------------------------------------------------------------------------------
    def clean_this_run(self):
        mdt = self.vx("tb-mdt")
        gone = []
        for key in ("case_a", "case_b"):
            cid = self.ids.get(key)
            if cid and mdt.delete(f"/api/tb/cases/{cid}").status_code == 200:
                gone.append(cid)
        mid = self.ids.get("meeting")
        note = ""
        if mid:
            st = (self.j(mdt.get(f"/api/tb/meetings/{mid}")).get("meeting") or {}).get("status")
            if st == "planned":
                mdt.post(f"/api/tb/meetings/{mid}/cancel", json={"reason": "E2E clean-up"}); note = f"meeting {mid} cancelled"
            else:
                note = f"meeting {mid} stays ({st}; a held meeting is kept in the history)"
        self.check("clean-up", "--clean: this run's Case Files removed", True, f"removed {', '.join(gone) or 'none'}; {note}")

    def write_log(self):
        keep = ""
        if LOG_PATH.exists():
            old = LOG_PATH.read_text(encoding="utf-8")
            if KEEP_MARK in old:
                keep = old[old.index(KEEP_MARK):].rstrip() + "\n"
        passed = sum(1 for r in self.rows if r[2])
        ids = self.ids
        lines = ["# End-to-end scenario: result of the last run", "",
                 f"Run {self.stamp} on {self.today.strftime('%d/%m/%Y')}, {round(time.time() - self.t0)} s, by `python -m tumour_board.eval.e2e_nik`"
                 + (" --keep" if self.args.keep else "") + (" --clean" if self.args.clean else "") + ". Synthetic data only; no passwords, tokens or codes are logged.",
                 "", f"**{passed} of {len(self.rows)} checks passed.**", "",
                 "| What | Value |", "|---|---|",
                 f"| Patient (demo HIMS) | {PATIENT_NAME}, UHID {ids.get('uhid', '')}, OP No. {ids.get('op_no', '')} |",
                 f"| Case File (scenario) | {ids.get('case_a', '')} |", f"| Case File (outside reports of {DEMO_PATIENT}) | {ids.get('case_b', '')} |",
                 f"| Meeting | {ids.get('meeting', '')} (E2E scenario {self.stamp}) |", f"| Resident login | {RESIDENT} |",
                 f"| Mammogram image | {self._image_line()} |", f"| Line marked not needed (resident proposal) | {ids.get('waived_line', '')} |",
                 f"| Models | reader Qwen3.5-4B (Chinese, non-medical), reasoner Gemma-4-31B (non-medical) |", "",
                 "| Step | Check | Result | Evidence |", "|---|---|---|---|"]
        for step, name, ok, ev in self.rows:
            lines.append(f"| {step} | {name.replace('|', '/')} | {'PASS' if ok else 'FAIL'} | {ev.replace('|', '/')} |")
        lines += ["", "How to look at it: sign in at http://127.0.0.1:7000/tb-nik as tb-breast-doc (the Case File), tb-mdt (the meeting), tb-path-head "
                  "(the request and the card); the HIMS at http://127.0.0.1:7130/his (search the UHID).", ""]
        text = "\n".join(lines) + ("\n" + keep if keep else "")
        LOG_PATH.write_text(text.replace("\u2014", ",").replace("\u2013", ","), encoding="utf-8")

    def _image_line(self):
        st = self.ids.get("study") or {}
        src = st.get("image_source") or {}
        if not st:
            return ""
        if src.get("kind") == "public":
            return f"public library: {src.get('collection')} ({src.get('licence')}, {src.get('doi')}), relabelled with the demo IDs"
        return f"synthetic ({src.get('reason') or 'no public series mapped'})"


class Socket:
    """The meeting's WebSocket as a browser opens it: the vaidyx_session cookie and the app's Origin; a thread collects the events."""

    def __init__(self, mid, cookie, origin=VAIDYX):
        from websockets.sync.client import connect
        self.events, self.code = [], None
        self._lock = threading.Lock()
        self.ws = None
        try:
            self.ws = connect(f"ws://127.0.0.1:7000/api/tb/meetings/{mid}/ws", origin=origin, additional_headers={"Cookie": f"vaidyx_session={cookie}"},
                              open_timeout=15, ping_interval=None)
        except Exception as e:  # refused before the handshake completed
            self.code = getattr(getattr(e, "response", None), "status_code", None) or 1008
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                msg = self.ws.recv()
                try:
                    ev = json.loads(msg)
                except ValueError:
                    continue
                with self._lock:
                    self.events.append(ev)
        except Exception as e:
            self.code = getattr(getattr(e, "rcvd", None), "code", None) or getattr(e, "code", None) or 1000

    def wait(self, pred, timeout):
        t0, seen = time.time(), 0
        while time.time() - t0 < timeout:
            with self._lock:
                for ev in self.events[seen:]:
                    if pred(ev):
                        return ev
                seen = len(self.events)
            time.sleep(0.2)
        return None

    def closed_without_state(self, timeout):
        """A refused socket: closed (or never opened) without a state event."""
        if self.ws is None:
            return True
        t0 = time.time()
        while time.time() - t0 < timeout and self.code is None:
            time.sleep(0.2)
        return self.code is not None and not any(e.get("type") == "state" for e in self.events)

    def close(self):
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tumour_board.eval.e2e_nik", description=__doc__.split("\n\n")[0])
    ap.add_argument("--keep", action="store_true", help="keep the Case Files and meetings of earlier E2E runs (default: removed before the run)")
    ap.add_argument("--clean", action="store_true", help="remove this run's Case Files at the end (the meeting is cancelled when still planned)")
    ap.add_argument("--start", type=int, default=0, help=argparse.SUPPRESS)   # debugging: start at step N with the ids saved in --state
    ap.add_argument("--state", default="", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    return Scenario(args).run()


if __name__ == "__main__":
    sys.exit(main())
