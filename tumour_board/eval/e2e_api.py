"""End-to-end test through the HTTP API of the running app (same calls as the UI). Usage:
  python -m tumour_board.eval.e2e_api --base http://127.0.0.1:7000 --password <admin password>"""
import argparse, json, os, sys, time

import httpx

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def wait_job(c, jid):
    t0 = time.time()
    while True:
        j = c.get(f"/api/tb/jobs/{jid}").json()
        if j["state"] == "finished":
            return j, round(time.time() - t0, 1)
        time.sleep(0.5)


E2E_USERS = {"tb-e2e-radio": "Radio-e2e-2026!", "tb-e2e-pathhead": "Path-e2e-2026!"}  # throw-away Vaidyx accounts, created and deleted by this script


def phase2(c, base):
    """V1 Phase 2: departments and roles (2.1), confirmations (2.2). Runs as admin on `c`; department users get their own clients."""
    o = c.get("/api/tb/org").json()
    check("org: admin sees departments, users and own roles", o["me"]["admin"] and len(o["departments"]) >= 12 and "users" in o and "vaidyx_users" in o,
          f"{len(o.get('departments', []))} departments")
    for u, pw in E2E_USERS.items():
        c.request("DELETE", "/api/auth/users", json={"username": u})
        r = c.post("/api/auth/users", json={"username": u, "password": pw, "is_admin": False})
        check(f"create test account {u}", r.status_code == 200, r.text[:80])
    users = dict(o.get("users") or {})
    users["tb-e2e-radio"] = {"departments": {"radio_diagnosis": "member"}, "coordinator": False}
    users["tb-e2e-pathhead"] = {"departments": {"pathology": "head"}, "coordinator": False}
    r = c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "admins")}, "users": users})
    check("org: admin saves users with department roles", r.status_code == 200 and r.json()["users"]["tb-e2e-radio"]["departments"] == {"radio_diagnosis": "member"}, r.text[:120])
    m = httpx.Client(base_url=base, timeout=120); h = httpx.Client(base_url=base, timeout=120)
    check("department users log in", m.post("/api/auth/login", json={"username": "tb-e2e-radio", "password": E2E_USERS["tb-e2e-radio"]}).status_code == 200
          and h.post("/api/auth/login", json={"username": "tb-e2e-pathhead", "password": E2E_USERS["tb-e2e-pathhead"]}).status_code == 200)
    me = m.get("/api/tb/org").json()
    check("member sees only own roles, no user map", me["me"]["departments"] == {"radio_diagnosis": "member"} and not me["me"]["admin"] and "users" not in me and [d["id"] for d in me["my_departments"]] == ["radio_diagnosis"])
    check("member: PUT /org forbidden", m.put("/api/tb/org", json=o).status_code == 403)
    check("member: create Case File forbidden", m.post("/api/tb/cases", json={"case_id": "TB-FORBID", "protocol": "lung_nsclc"}).status_code == 403)
    check("member: upload straight into a Case File forbidden", m.post("/api/tb/cases/TB-001/documents", files=[("files", ("x.txt", b"synthetic"))], data={"paths": "[]"}).status_code == 403)
    check("member: delete Case File forbidden", m.delete("/api/tb/cases/TB-001").status_code == 403)
    d = m.get("/api/tb/cases/TB-001").json()
    perm = d.get("permissions", {})
    check("member: can view the Case File, actions hidden", d["case"]["case_id"] == "TB-001" and perm.get("upload") is False and perm.get("board_record") is False
          and not any(perm.get("waive", {}).values()) and not any(perm.get("delete_document", {}).values()), json.dumps({k: v for k, v in perm.items() if not isinstance(v, dict)}))
    req_ids = [r["id"] for r in d["state"]["gate"]["requirements"]]
    rad = next((r for r in d["state"]["gate"]["requirements"] if r["department"] == "Radiology"), None)
    path_req = next((r for r in d["state"]["gate"]["requirements"] if r["department"] == "Pathology"), None)
    check("member: waive forbidden (403) even in own department", m.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": rad["id"], "reason": "e2e"}).status_code == 403 if rad else False)
    hd = h.get("/api/tb/cases/TB-001").json()["permissions"]
    check("head: may waive only own department's requirements", hd["waive"].get(path_req["id"]) is True and hd["waive"].get(rad["id"]) is False, json.dumps(hd["waive"]))
    check("head: waive outside own department forbidden (403)", h.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": rad["id"], "reason": "e2e"}).status_code == 403)
    check("head: waive without a reason refused (400)", h.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": path_req["id"], "reason": ""}).status_code == 400)
    r = h.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": path_req["id"], "reason": "e2e: slides reviewed outside"}).json()
    st = {x["id"]: x["status"] for x in r["state"]["gate"]["requirements"]}
    check("head: waive in own department recorded and applied", st[path_req["id"]] == "waived" and r["confirmation"]["by"] == "tb-e2e-pathhead" and r["confirmation"]["type"] == "waive", st.get(path_req["id"]))
    r2 = h.post(f"/api/tb/cases/TB-001/confirmations/{r['confirmation']['id']}/undo").json()
    check("head: undo restores the requirement", {x["id"]: x["status"] for x in r2["state"]["gate"]["requirements"]}[path_req["id"]] != "waived" and r2["confirmation"]["undone"]["by"] == "tb-e2e-pathhead")
    au = c.get("/api/tb/cases/TB-001/audit").json()["events"]
    check("confirmation and undo audited with the user", any(e["kind"] == "confirmation" and e["by"] == "tb-e2e-pathhead" for e in au) and any(e["kind"] == "confirmation_undone" for e in au))
    check("undo twice refused (409)", h.post(f"/api/tb/cases/TB-001/confirmations/{r['confirmation']['id']}/undo").status_code == 409)
    check("unknown confirmation type refused (400)", c.post("/api/tb/cases/TB-001/confirmations", json={"type": "bless", "key": "x"}).status_code == 400)
    # value confirmation (mechanism check): a clinician records a value against a FINAL report after reading the source (here the WBC
    # that the synthetic CBC scan reports as "Not reported"); it counts for the gate, is shown as "confirmed" and names the clinician.
    # A value confirmed on a DRAFT report would still not count: the gate's final-signed rule is unchanged.
    doc = next(x for x in d["documents"] if "cbc" in (x.get("rel_path") or ""))
    r = c.post("/api/tb/cases/TB-001/confirmations", json={"type": "confirm_value", "key": f"{doc['doc_id']}:wbc", "fields": {"value": "6,200 /cumm"}}).json()
    ev = next((x for x in r["state"]["gate"]["requirements"] if x["id"] == "baseline_labs"), {})
    check("confirmed value counts for the gate with the clinician named", any(e.get("fact") == "wbc" and e.get("value") == "6,200 /cumm" for e in ev.get("evidence", [])) and ev["status"] == "satisfied", ev.get("status"))
    d2 = c.get("/api/tb/cases/TB-001").json()
    check("confirmed value shown in the Case File facts as confirmed", d2["facts"].get("wbc", {}).get("current", {}).get("verification") == "confirmed" and d2["facts"]["wbc"]["current"].get("confirmed_by") == "admin")
    draft = next(x for x in d["documents"] if (x.get("classification") or {}).get("status") == "DRAFT")
    r3 = c.post("/api/tb/cases/TB-001/confirmations", json={"type": "confirm_value", "key": f"{draft['doc_id']}:pdl1", "fields": {"value": "TPS 60%"}}).json()
    check("a value confirmed on a DRAFT report still does not pass the gate", next(x["status"] for x in r3["state"]["gate"]["requirements"] if x["id"] == "pdl1") == "missing_field")
    c.post(f"/api/tb/cases/TB-001/confirmations/{r3['confirmation']['id']}/undo")
    c.post(f"/api/tb/cases/TB-001/confirmations/{r['confirmation']['id']}/undo")
    check("legacy /overrides alias still records a confirmation", "attest_final" in {x["type"] for x in c.post("/api/tb/cases/TB-001/overrides", json={"kind": "documents", "key": doc["doc_id"], "value": {"attested_final": True, "reason": "e2e"}}).json().get("confirmations", [])})
    c.post("/api/tb/cases/TB-001/overrides", json={"kind": "documents", "key": doc["doc_id"], "value": None})
    # ---- 2.3 department uploads: a member uploads without a Case File; the record waits in the queue tagged with department and user
    corpus = "/data/vaidyx/tb_demo_corpus/intake"
    xray = open(f"{corpus}/radio_diagnosis/xray_chest_pa_2026-09-03.pdf", "rb").read()
    note = b"SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nX-RAY CHEST PA VIEW\nPatient name Kumar R\nAge / Sex 62 Y / M\nStudy date 03/09/2026\nFindings: no change.\nReport status: FINAL\nReported by: Dr. Shalini Rao, MD (Radio-diagnosis)\n"
    check("member: upload for another department forbidden (403)", m.post("/api/tb/intake/documents", files=[("files", ("x.txt", note))], data={"paths": "[]", "department": "pathology"}).status_code == 403)
    r = m.post("/api/tb/intake/documents", files=[("files", ("xray_followup.txt", note)), ("files", ("old.doc", b"x"))], data={"paths": json.dumps(["xray_followup.txt", "old.doc"]), "department": "Radio-diagnosis"})
    check("member: upload for own department accepted", r.status_code == 200 and r.json()["department"] == "radio_diagnosis", r.text[:120])
    jj, secs = wait_job(c, r.json()["job"])
    check("intake job read the record and refused the .doc", jj["state"] == "finished" and jj["total"] == 1 and jj["unsupported"] and jj["gate"] is None, f"{secs}s")
    q = m.get("/api/tb/intake").json()
    mine = [d for d in q["documents"] if d.get("uploaded_by") == "tb-e2e-radio"]
    check("member sees own department's intake records, tagged with department and user", len(mine) >= 1 and mine[0]["department"] == "radio_diagnosis" and mine[0]["added"]
          and mine[0]["state"] in ("needs_matching", "filed") and not q["can_match"], json.dumps({k: mine[0].get(k) for k in ("state", "department")}) if mine else "none")
    check("head of another department does not see it", not any(d.get("uploaded_by") == "tb-e2e-radio" for d in h.get("/api/tb/intake").json()["documents"]))
    qa = c.get("/api/tb/intake").json()
    rec = next((d for d in qa["documents"] if d.get("uploaded_by") == "tb-e2e-radio"), None)
    check("coordinator / admin sees the whole queue with the intake log", rec is not None and qa["can_match"] and isinstance(qa.get("audit"), list))
    if rec and rec["state"] == "needs_matching":
        check("record was read and classified in the intake area", (rec.get("classification") or {}).get("doc_type") == "xray" and rec.get("identity_read") is not None, json.dumps(rec.get("classification", {}).get("doc_type")))
        check("member cannot file (403)", m.post(f"/api/tb/intake/{rec['doc_id']}/file-to-case", json={"case_id": "TB-001"}).status_code == 403)
        r = c.post(f"/api/tb/intake/{rec['doc_id']}/file-to-case", json={"case_id": "TB-001", "reason": "e2e: checked with the department"}).json()
        jj, secs = wait_job(c, r["job"])
        d1 = c.get("/api/tb/cases/TB-001").json()
        filed = next((x for x in d1["documents"] if x["doc_id"] == rec["doc_id"]), None)
        check("filed into TB-001 with the uploader's department recorded", filed is not None and filed["department"] == "radio_diagnosis" and filed["uploaded_by"] == "tb-e2e-radio" and filed["state"] == "ready", f"{secs}s")
        check("filing recorded as a confirm_match in the Case File", any(x["type"] == "confirm_match" and x["key"] == rec["doc_id"] for x in d1["state"].get("confirmations", [])))
        check("record left the queue", not any(d["doc_id"] == rec["doc_id"] for d in c.get("/api/tb/intake").json()["documents"]))
        c.delete(f"/api/tb/cases/TB-001/documents/{rec['doc_id']}")
    # a record that belongs to nobody: new Case File, awaiting listing
    r = c.post("/api/tb/intake/documents", files=[("files", ("pap.pdf", open(f"{corpus}/pathology/pap_smear_2026-09-15.pdf", "rb").read()))], data={"paths": json.dumps(["pap.pdf"]), "department": "pathology"}).json()
    jj, _ = wait_job(c, r["job"])
    new_cid = None
    if jj.get("filed"):
        new_cid = list(jj["filed"].values())[0]
        check("record with an unknown hospital ID opened a new Case File automatically (2.4)", bool(new_cid), new_cid)
    else:
        rec = next((d for d in c.get("/api/tb/intake").json()["documents"] if d["rel_path"] == "pap.pdf"), None)
        r2 = c.post(f"/api/tb/intake/{rec['doc_id']}/new-case", json={"reason": "e2e"}).json() if rec else {}
        if r2.get("job"):
            wait_job(c, r2["job"]); new_cid = r2["case_id"]
        check("coordinator starts a new Case File from the queue", bool(new_cid), new_cid or "")
    if new_cid:
        nc = c.get(f"/api/tb/cases/{new_cid}").json()
        check("new Case File waits for listing: records shown, no gate", nc["case"]["listing"]["status"] == "awaiting_listing" and nc["state"]["gate"] is None and len(nc["documents"]) == 1 and nc["documents"][0]["state"] == "ready")
        check("new Case File carries the printed identity (UHID, age / sex), never Aadhaar", nc["case"]["patient"].get("mrn") == "SYN-500911" and "aadhaar" not in json.dumps(nc["case"]["patient"]).lower(), json.dumps(nc["case"]["patient"])[:160])
        # ---- 2.5 listing: the coordinator lists the Case File; Pre-Authorization starts
        check("member cannot list a Case File (403)", m.post(f"/api/tb/cases/{new_cid}/listing", json={"protocol": "breast"}).status_code == 403)
        check("listing with an unknown setting refused (400)", c.post(f"/api/tb/cases/{new_cid}/listing", json={"protocol": "breast", "setting": "non_metastatic"}).status_code == 400)
        r = c.post(f"/api/tb/cases/{new_cid}/listing", json={"protocol": "breast", "setting": "early", "board_date": "18/10/2026", "hospital_level": "essential"}).json()
        if r.get("total"):
            wait_job(c, r["job"])
        nc2 = c.get(f"/api/tb/cases/{new_cid}").json()
        g = nc2["state"]["gate"]
        check("listed: protocol, NCG setting, board date and level saved; gate evaluated", nc2["case"]["listing"]["status"] == "listed" and nc2["case"]["setting"] == "early" and nc2["case"]["board_date"] == "2026-10-18"
              and g is not None and g["protocol"] == "breast" and g["setting"] == "early" and g["hospital_level"] == "essential" and g["total"] > 0, json.dumps({k: (g or {}).get(k) for k in ("protocol", "setting", "satisfied", "total")}))
        check("listing audited and the record extracted under the protocol from its stored pages", any(e["kind"] == "case_listed" for e in c.get(f"/api/tb/cases/{new_cid}/audit").json()["events"])
              and nc2["documents"][0]["state"] == "ready" and "facts" in nc2["documents"][0])
        c.delete(f"/api/tb/cases/{new_cid}")
    for d in c.get("/api/tb/intake").json()["documents"]:
        if d.get("uploaded_by") in E2E_USERS or d["rel_path"] in ("pap.pdf",):
            c.delete(f"/api/tb/intake/{d['doc_id']}?reason=e2e+cleanup")
    m.close(); h.close()
    # ---- 2.4 patient matching: the whole synthetic intake batch (3 departments, 8 records, 5 patients) against the answer key
    truth = json.load(open("/data/vaidyx/tb_demo_corpus/truth/intake.json"))["files"]
    have = {x["case_id"] for x in c.get("/api/tb/cases").json()["cases"]}
    if {"TB-004", "TB-005", "TB-006"} <= have:
        jj, secs = wait_job(c, c.post("/api/tb/cases/TB-004/reprocess", json={"which": "all"}).json()["job"])  # the Case File learns its CR No. and ABHA from its own records
        p4 = c.get("/api/tb/cases/TB-004").json()["case"]["patient"]
        check("TB-004 learned its CR No. and ABHA from its own documents", {x["kind"] for x in p4.get("ids", [])} >= {"cr_no", "abha"}, json.dumps(p4.get("ids", []))[:200] + f" ({secs}s)")
        filed, waiting = {}, {}
        for dept, folder in (("Radio-diagnosis", "radio_diagnosis"), ("Pathology", "pathology"), ("Laboratory Medicine", "laboratory_medicine")):
            files = [(f, open(f"{corpus}/{folder}/{f}", "rb").read()) for f in sorted(os.listdir(f"{corpus}/{folder}"))]
            r = c.post("/api/tb/intake/documents", files=[("files", (f, b)) for f, b in files], data={"paths": json.dumps([f"{folder}/{f}" for f, _ in files]), "department": dept}).json()
            jj, secs = wait_job(c, r["job"])
            for did, cid in (jj.get("filed") or {}).items():
                filed[did] = cid
            for did in jj.get("needs_matching") or []:
                waiting[did] = folder
        # where did each file go
        where = {}
        for cid in sorted({x for x in filed.values() if x}):
            for x in c.get(f"/api/tb/cases/{cid}").json()["documents"]:
                if x["doc_id"] in filed:
                    where[x["rel_path"]] = cid
        queue = {d["rel_path"]: d for d in c.get("/api/tb/intake").json()["documents"]}
        new_ids = sorted({x for x in filed.values() if x and x not in have})
        ok_auto, bad = [], []
        for rel, t in truth.items():
            exp = t.get("expected_case")
            if exp:
                (ok_auto if where.get(rel) == exp else bad).append(f"{rel} -> {where.get(rel) or queue.get(rel, {}).get('state')} (expected {exp})")
        check("one patient's records from several departments auto-link to the right Case Files", not bad and len(ok_auto) == 5, "; ".join(bad) or f"{len(ok_auto)} auto-linked")
        same_name = ["pathology/pap_smear_2026-09-15.pdf", "laboratory_medicine/cbc_2026-09-15.png"]
        check("same name, different UHID: never filed into TB-005, one new Case File for both records", all(where.get(r) not in ("TB-005", None) for r in same_name)
              and len({where.get(r) for r in same_name}) == 1 and len(new_ids) == 1, json.dumps({r: where.get(r) for r in same_name}))
        rbs = queue.get("laboratory_medicine/rbs_2026-09-16_no_id.pdf")
        check("no identifier: waits for a person with the same-name Case Files listed, never linked", rbs is not None and rbs["match"]["decision"] == "needs_matching"
              and {x["case_id"] for x in rbs["match"]["candidates"]} >= {"TB-001", "TB-004"}, json.dumps((rbs or {}).get("match", {}).get("reason", ""))[:160])
        if new_ids:
            nc = c.get(f"/api/tb/cases/{new_ids[0]}").json()
            cbc = next((x for x in nc["documents"] if "cbc" in x["rel_path"]), None)
            check("new Case File registered without the title, with UHID and age / sex", nc["case"]["patient"]["name"] == "Sunita Devi" and nc["case"]["patient"]["mrn"] == "SYN-500911" and "67" in nc["case"]["patient"].get("agesex", ""), json.dumps(nc["case"]["patient"])[:160])
            if cbc:
                full = c.get(f"/api/tb/cases/{new_ids[0]}/documents/{cbc['doc_id']}").json()
                txt = " ".join(pg["text"] for pg in full["pages"])
                check("Aadhaar masked in the stored scan text, never in the patient record", "7395 8406 1180" not in txt and "XXXX XXXX 1180" in txt and (full.get("identity_read") or {}).get("aadhaar_seen") is True
                      and "aadhaar" not in json.dumps(nc["case"]["patient"]).lower(), txt[:0] + ("masked" if "XXXX XXXX 1180" in txt else "NOT masked"))
        d2 = c.get("/api/tb/cases/TB-002").json()
        mam = next((x for x in d2["documents"] if "mammogram_followup" in x["rel_path"]), None)
        full = c.get(f"/api/tb/cases/TB-002/documents/{mam['doc_id']}").json() if mam else {}
        check("name variant (Laxmi / Lakshmi) linked on the UHID and recorded as a variant match", mam is not None and mam.get("identity") == "match"
              and (full.get("match") or {}).get("decision") == "auto_link" and "variant" in (full.get("match") or {}).get("reason", ""), (full.get("match") or {}).get("reason", "")[:120])
        # clean up: filed records out of the Case Files, the new Case File, the waiting record
        for rel, cid in where.items():
            did = next(x["doc_id"] for x in c.get(f"/api/tb/cases/{cid}").json()["documents"] if x["rel_path"] == rel)
            if cid in have:
                c.delete(f"/api/tb/cases/{cid}/documents/{did}")
        for cid in new_ids:
            c.delete(f"/api/tb/cases/{cid}")
        for d in c.get("/api/tb/intake").json()["documents"]:
            c.delete(f"/api/tb/intake/{d['doc_id']}?reason=e2e+cleanup")
    else:
        print("SKIP 2.4 intake batch: TB-004..006 not imported (python -m tumour_board.eval.prepare_cases TB-004 TB-005 TB-006)")


def phase2_cleanup(c):
    """Remove the throw-away accounts and their org roles."""
    try:
        o = c.get("/api/tb/org").json()
        users = {k: v for k, v in (o.get("users") or {}).items() if k not in E2E_USERS}
        c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "admins")}, "users": users})
    except Exception as e:
        print("cleanup org failed:", e)
    for u in E2E_USERS:
        c.request("DELETE", "/api/auth/users", json={"username": u})


def main(base, pw, only=None):
    c = httpx.Client(base_url=base, timeout=600)
    check("login", c.post("/api/auth/login", json={"username": "admin", "password": pw}).status_code == 200)
    if only == "phase2":
        try:
            phase2(c, base)
        finally:
            phase2_cleanup(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    # 1. import lung case (incomplete)
    j, s = wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])
    g = c.get("/api/tb/cases/TB-001").json()["state"]["gate"]
    check("TB-001 ingest + gate", not g["passed"] and g["satisfied"] == 3, f"{j['total']} docs in {s}s, gate {g['satisfied']}/{g['total']}")
    st = {r["id"]: r["status"] for r in g["requirements"]}
    check("draft histopathology blocked as not final", st["histopathology"] == "not_final")
    check("brain MRI missing", st["brain_mri"] == "missing_record")
    check("PD-L1 pending", st["pdl1"] == "missing_field")
    acts = c.get("/api/tb/cases/TB-001").json()["state"]["actions"]
    check("gaps routed to departments", {a["department"] for a in acts} >= {"Pathology", "Radiology", "Molecular Pathology", "Laboratory Medicine"}, ", ".join(sorted({a["department"] for a in acts})))
    # 2. search + ask
    t0 = time.time(); r = c.post("/api/tb/cases/TB-001/search", json={"query": "PD-L1"}).json()
    check("instant value search", any("PD-L1" in h["text"] for h in r["values"]["hits"]), f"{r['ms_values']} ms values, {round((time.time() - t0) * 1000)} ms round trip")
    a = c.post("/api/tb/cases/TB-001/ask", json={"question": "What is the haemoglobin and when was it measured?"}).json()
    check("ask answered with citation", a["status"] == "answered" and "11.8" in json.dumps(a["statements"]), f"{a['seconds']} s")
    a = c.post("/api/tb/cases/TB-001/ask", json={"question": "Which chemotherapy regimen should we start?"}).json()
    check("treatment question refused", a["status"] == "out_of_scope", a.get("category", ""))
    a = c.post("/api/tb/cases/TB-001/ask", json={"question": "What is the patient's HbA1c?"}).json()
    check("absent value -> not documented", a["status"] == "not_documented")
    # 3. role agent (stream)
    t0 = time.time(); brief = None; steps = 0
    with c.stream("POST", "/api/tb/cases/TB-001/agents/pathology", json={}) as resp:
        for line in resp.iter_lines():
            if line.strip():
                ev = json.loads(line); steps += ev["type"] == "step"
                if ev["type"] == "brief":
                    brief = ev["brief"]
    items = sum(len(s["items"]) for s in brief["sections"]) if brief else 0
    check("pathology agent brief", brief is not None and items > 0, f"{steps} steps, {items} cited items, {len(brief['points_for_review']) if brief else 0} points for review, {round(time.time() - t0, 1)} s")
    txt = json.dumps(brief).lower() if brief else ""
    check("brief mentions draft/pending status", "draft" in txt or "pending" in txt)
    # 4. new reports arrive -> re-check closes gaps
    j, s = wait_job(c, c.post("/api/tb/cases/TB-001/demo-arrivals").json()["job"])
    d = c.get("/api/tb/cases/TB-001").json(); g = d["state"]["gate"]
    check("arrivals close every gap", g["passed"], f"{j['total']} new docs in {s}s, gate {g['satisfied']}/{g['total']}")
    check("routed actions auto-completed", all(a["status"] == "completed" for a in d["state"]["actions"] if a["source"] == "pre_authorization"))
    check("PD-L1 now 60% from FINAL report", "60" in d["facts"]["pdl1"]["current"]["value"], d["facts"]["pdl1"]["current"]["value"])
    g = d["state"]["gate"]
    check("MDT minimum core data checklist present", len(g.get("core_data", [])) == 10 and sum(x["present"] for x in g["core_data"]) >= 5,
          f"{sum(x['present'] for x in g.get('core_data', []))}/10 documented")
    scan = [x for x in d["documents"] if "vision-transcription" in (x.get("methods") or [])]
    check("scanned pages read twice (OCR disagreement check)", bool(scan) and all(x["pages"] >= 1 for x in scan), f"{len(scan)} scanned documents")
    # 5. summary (NCG Virtual Tumour Board sections)
    sm = c.post("/api/tb/cases/TB-001/summary", json={}).json()
    sents = sum(len(p) for p in sm.get("paragraphs", []))
    check("case file summary compiled", sm.get("status") == "ready" and sents >= 4, f"{sents} cited sentences, {sm.get('seconds')} s, dropped {sm.get('dropped_unverified')}")
    secs = {x["id"]: len(x["sentences"]) for x in sm.get("sections", [])}
    check("summary follows the NCG VTB sections", len(secs) == 6 and secs.get("investigations", 0) > 0 and secs.get("imaging", 0) > 0 and secs.get("questions", 0) > 0, json.dumps(secs))
    check("stage only as recorded", bool(sm.get("stage_as_recorded")) and "T3" in sm["stage_as_recorded"]["value"], (sm.get("stage_as_recorded") or {}).get("value", ""))
    # 6. board record with a transcription error (6% instead of 60%)
    rec = c.post("/api/tb/cases/TB-001/board-records", json={"board_date": "2026-09-18", "recorded_by": "Dr. Tumour Board Coordinator (synthetic)",
           "decision_text": "Discussed at the Tumour Board. PD-L1 TPS 6% noted. EGFR, ALK and ROS1 negative; KRAS G12C detected. No distant metastasis on PET. Plan as per board discussion. Re-discuss after review.",
           "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Radiology), Dr D (Pathology)",
           "actions": [{"department": "Medical Oncology", "task": "Discuss plan with patient", "due": "2026-09-22"}], "next_review": "2026-10-16"}).json()
    flags = rec["adjudication"]["flags"]
    check("participants recorded: no documentation flag for them", not any("participants" in f["text"] for f in flags))
    check("transcription discrepancy flagged (6% vs 60%)", any(f["kind"] == "transcription" and "60" in f.get("source_value", "") for f in flags),
          "; ".join(f["text"] for f in flags)[:200])
    # 6b. a CORRECT value in the decision must not be flagged (regression: "60%" vs source "TPS 60%")
    rec3 = c.post("/api/tb/cases/TB-001/board-records", json={"board_date": "2026-09-18", "recorded_by": "Dr. Coordinator (synthetic)", "participants": "Dr A, Dr B",
           "decision_text": "EGFR mutation detected per molecular report. Pathology to issue a correction of the PD-L1 value.", "actions": []}).json()
    f3 = rec3["adjudication"]["flags"]
    check("polarity flip flagged (EGFR 'detected' vs source 'No mutation detected')", any("polarity" in f["text"].lower() for f in f3), "; ".join(f["text"] for f in f3)[:200])
    check("unrecorded report correction flagged", any("Report corrections raised" in f["text"] for f in f3))
    rec2 = c.post("/api/tb/cases/TB-001/board-records", json={"board_date": "2026-09-18", "recorded_by": "Dr. Coordinator (synthetic)", "participants": "Dr A, Dr B",
           "decision_text": "PD-L1 TPS 60% noted. KRAS G12C detected. Haemoglobin 12.1 g/dL. Plan as per board discussion.",
           "actions": [{"department": "Medical Oncology", "task": "Counsel patient", "due": "2026-09-22"}]}).json()
    check("correct values not flagged as discrepancies", not any(f["kind"] == "transcription" for f in rec2["adjudication"]["flags"]),
          "; ".join(f["text"] for f in rec2["adjudication"]["flags"])[:160] or "no flags")
    # 6c. re-check detail, duplicate upload, delete, reprocess
    st = c.post("/api/tb/cases/TB-001/recheck").json()
    check("re-check reports what it checked", st.get("recheck", {}).get("documents_checked", 0) >= 12 and "changed" in st["recheck"], json.dumps(st["recheck"])[:160])
    one = c.get("/api/tb/cases/TB-001").json()["documents"][0]
    raw = c.get(f"/api/tb/cases/TB-001/documents/{one['doc_id']}/file").content
    j = c.post("/api/tb/cases/TB-001/documents", files=[("files", (one["filename"], raw))], data={"paths": json.dumps([one["rel_path"]])}).json()
    jj, _ = wait_job(c, j["job"])
    check("identical upload skipped as duplicate", jj["total"] == 0 and len(jj.get("skipped_duplicates", [])) == 1)
    n_before = len(c.get("/api/tb/cases/TB-001").json()["documents"])
    c.delete(f"/api/tb/cases/TB-001/documents/{one['doc_id']}")
    n_after = len(c.get("/api/tb/cases/TB-001").json()["documents"])
    check("document removed and gate re-checked", n_after == n_before - 1)
    j = c.post("/api/tb/cases/TB-001/reprocess", json={"which": "errors"}).json()
    check("reprocess errors with none failed is a no-op job", j["total"] == 0)
    # 6d. unstated status -> confirm; waiver
    c.delete("/api/tb/cases/TB-TEST")
    c.post("/api/tb/cases", json={"case_id": "TB-TEST", "protocol": "lung_nsclc", "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-999", "agesex": "60 Y / F"}})
    note = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nMEDICAL ONCOLOGY OPD NOTE\nPatient: SYNTHETIC, Test Patient  UHID: SYN-999  60 Y / F\nVisit date: 20-Sep-2026\n"
            "History: cough for 2 months, ex-smoker 20 pack-years.\nECOG performance status: 1\nQuestion for the Tumour Board: staging and management plan.\n").encode()
    j = c.post("/api/tb/cases/TB-TEST/documents", files=[("files", ("opd_note.txt", note))], data={"paths": json.dumps(["opd_note.txt"])}).json()
    wait_job(c, j["job"])
    g = c.get("/api/tb/cases/TB-TEST").json()["state"]["gate"]
    req = {r["id"]: r for r in g["requirements"]}
    check("unstated status asks for confirmation (not blocked, not passed)", req["clinical_history"]["status"] == "needs_confirmation", req["clinical_history"]["status"])
    did = req["clinical_history"]["evidence"][0]["doc_id"]
    st = c.post("/api/tb/cases/TB-TEST/overrides", json={"kind": "documents", "key": did, "value": {"attested_final": True, "reason": "verified with department"}}).json()
    req = {r["id"]: r for r in st["gate"]["requirements"]}
    check("attested document satisfies the requirement", req["clinical_history"]["status"] == "satisfied", "; ".join(req["clinical_history"]["problems"]))
    j = c.post("/api/tb/cases/TB-TEST/reprocess", json={"which": "all"}).json()
    jj, secs = wait_job(c, j["job"])
    g2 = c.get("/api/tb/cases/TB-TEST").json()["state"]["gate"]
    check("re-process all re-reads documents and keeps the attestation", jj["state"] == "finished" and jj["total"] == 1 and {r["id"]: r["status"] for r in g2["requirements"]}["clinical_history"] == "satisfied", f"{secs}s")
    st = c.post("/api/tb/cases/TB-TEST/overrides", json={"kind": "requirements", "key": "brain_mri", "value": {"waived": True, "reason": "not indicated per treating team"}}).json()
    req = {r["id"]: r for r in st["gate"]["requirements"]}
    check("waived requirement excluded from the gate", req["brain_mri"]["status"] == "waived" and st["gate"]["total"] == 7)
    # 7. expert review + audit
    rv = c.post("/api/tb/cases/TB-001/review", json={"artefact": "summary", "status": "reviewed", "comment": "Checked against source reports"}).json()
    check("expert review recorded", rv["status"] == "reviewed")
    au = c.get("/api/tb/cases/TB-001/audit").json()["events"]
    kinds = {e["kind"] for e in au}
    check("audit trail complete", {"llm_call", "fact_verification", "action_created", "action_completed", "board_record", "expert_review", "document_duplicate_skipped", "document_deleted", "recheck"} <= kinds, f"{len(au)} events")
    au2 = {e["kind"] for e in c.get("/api/tb/cases/TB-TEST/audit").json()["events"]}
    check("overrides audited", "override" in au2)
    # 8. TB-002 Indian-format lab report with no status line must be read as final (end-of-report marker + Sd/-)
    j, s = wait_job(c, c.post("/api/tb/demo/TB-002").json()["job"])
    j2, _ = wait_job(c, c.post("/api/tb/cases/TB-002/demo-arrivals").json()["job"])
    d2 = c.get("/api/tb/cases/TB-002").json()
    lab = [d for d in d2["documents"] if "pre_chemo" in (d.get("rel_path") or "")]
    cl = lab[0]["classification"] if lab else {}
    check("Indian-format report (no status line) read as FINAL and signed", cl.get("status") == "FINAL" and cl.get("signed") == "yes", f"{cl.get('status')} / {cl.get('signed')} / {cl.get('signature_quote', '')[:60]}")
    check("latest lab values come from the new report", "12.4" in d2["facts"].get("haemoglobin", {}).get("current", {}).get("value", ""), d2["facts"].get("haemoglobin", {}).get("current", {}).get("value"))
    # 9. V1 Phase 2: departments, roles and confirmations
    try:
        phase2(c, base)
    finally:
        phase2_cleanup(c)
    # leave the demo Case Files in their fresh state for the next user / test
    for cid in ("TB-001", "TB-002", "TB-003"):
        wait_job(c, c.post(f"/api/tb/demo/{cid}").json()["job"])
    c.delete("/api/tb/cases/TB-TEST")
    print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:7000"); ap.add_argument("--password", required=True)
    ap.add_argument("--only", default=None, help="run one section only (phase2)")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.only))
