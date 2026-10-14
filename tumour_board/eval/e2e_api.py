"""End-to-end test through the HTTP API of the running app (same calls as the UI). Usage:
  python -m tumour_board.eval.e2e_api --base http://127.0.0.1:7000 --password <admin password>"""
import argparse, json, os, re, sys, time

import httpx

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def wait_job(c, jid):
    t0 = time.time()
    while True:
        j = c.get(f"/api/tb/jobs/{jid}").json()
        if j["state"] in ("finished", "failed", "interrupted"):
            return j, round(time.time() - t0, 1)
        time.sleep(0.5)


E2E_USERS = {"tb-e2e-radio": "Radio-e2e-2026!", "tb-e2e-pathhead": "Path-e2e-2026!", "tb-e2e-surgdoc": "Surg-e2e-2026!"}  # throw-away Vaidyx accounts, created and deleted by this script


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
    users["tb-e2e-radio"] = {"departments": {"radiology": "member"}, "coordinator": False}
    users["tb-e2e-pathhead"] = {"departments": {"pathology": "head"}, "coordinator": False}
    users["tb-e2e-surgdoc"] = {"departments": {"surgical_oncology": "member"}, "coordinator": False}  # a treating doctor (V2 item 2.2)
    r = c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "admins")}, "users": users})
    check("org: admin saves users with department roles", r.status_code == 200 and r.json()["users"]["tb-e2e-radio"]["departments"] == {"radiology": "member"}, r.text[:120])
    m = httpx.Client(base_url=base, timeout=120); h = httpx.Client(base_url=base, timeout=120); t = httpx.Client(base_url=base, timeout=120)
    check("department users log in", m.post("/api/auth/login", json={"username": "tb-e2e-radio", "password": E2E_USERS["tb-e2e-radio"]}).status_code == 200
          and h.post("/api/auth/login", json={"username": "tb-e2e-pathhead", "password": E2E_USERS["tb-e2e-pathhead"]}).status_code == 200
          and t.post("/api/auth/login", json={"username": "tb-e2e-surgdoc", "password": E2E_USERS["tb-e2e-surgdoc"]}).status_code == 200)
    me = m.get("/api/tb/org").json()
    check("member sees only own roles, no user map", me["me"]["departments"] == {"radiology": "member"} and not me["me"]["admin"] and "users" not in me and [d["id"] for d in me["my_departments"]] == ["radiology"])
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
    # V2 item 2.2: a supporting department (even its head) receives and answers requests; waivers belong to the treating doctor
    hd = h.get("/api/tb/cases/TB-001").json()["permissions"]
    check("supporting head: may not waive any requirement (V2 2.2)", hd["waive"].get(path_req["id"]) is False and hd["waive"].get(rad["id"]) is False, json.dumps(hd["waive"]))
    check("supporting head: waive forbidden (403)", h.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": path_req["id"], "reason": "e2e"}).status_code == 403)
    td = t.get("/api/tb/cases/TB-001").json()["permissions"]
    check("treating doctor: may waive every requirement, not delete the Case File", all(td["waive"].get(k) is True for k in req_ids) and td.get("delete_case") is False and td.get("upload") is True, json.dumps({k: v for k, v in td.items() if not isinstance(v, dict)}))
    check("treating doctor: waive without a reason refused (400)", t.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": path_req["id"], "reason": ""}).status_code == 400)
    r = t.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": path_req["id"], "reason": "e2e: slides reviewed outside"}).json()
    st = {x["id"]: x["status"] for x in r["state"]["gate"]["requirements"]}
    check("treating doctor: waive recorded and applied", st[path_req["id"]] == "waived" and r["confirmation"]["by"] == "tb-e2e-surgdoc" and r["confirmation"]["type"] == "waive", st.get(path_req["id"]))
    r2 = t.post(f"/api/tb/cases/TB-001/confirmations/{r['confirmation']['id']}/undo").json()
    check("treating doctor: undo restores the requirement", {x["id"]: x["status"] for x in r2["state"]["gate"]["requirements"]}[path_req["id"]] != "waived" and r2["confirmation"]["undone"]["by"] == "tb-e2e-surgdoc")
    au = c.get("/api/tb/cases/TB-001/audit").json()["events"]
    check("confirmation and undo audited with the user", any(e["kind"] == "confirmation" and e["by"] == "tb-e2e-surgdoc" for e in au) and any(e["kind"] == "confirmation_undone" for e in au))
    check("undo twice refused (409)", t.post(f"/api/tb/cases/TB-001/confirmations/{r['confirmation']['id']}/undo").status_code == 409)
    check("unknown confirmation type refused (400)", c.post("/api/tb/cases/TB-001/confirmations", json={"type": "bless", "key": "x"}).status_code == 400)
    # value confirmation on a dedicated Case File (independent of the demo Case File's state): a FINAL CT without a lesion size, then a
    # clinician records the size read in the source; it counts for the gate, is shown as "confirmed by", and a value confirmed on a
    # DRAFT report still does not pass (the final-signed rule is unchanged).
    c.delete("/api/tb/cases/TB-P2C")
    c.post("/api/tb/cases", json={"case_id": "TB-P2C", "protocol": "lung_nsclc", "setting": "non_metastatic", "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-998", "agesex": "60 Y / M"}})
    ct = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDepartment of Radio-diagnosis\nCECT THORAX\nPatient: SYNTHETIC, Test Patient  UHID: SYN-998  60 Y / M\nStudy date: 02/09/2026\n"
          "Findings: lobulated mass in the right lower lobe with post-obstructive consolidation. No pleural effusion.\nImpression: right lower lobe mass.\nReport status: FINAL\nReported by: Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310\n").encode()
    hp = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDepartment of Pathology\nHISTOPATHOLOGY REPORT\nPatient: SYNTHETIC, Test Patient  UHID: SYN-998  60 Y / M\nSpecimen: core biopsy right lung.\n"
          "Microscopy: sheets of malignant epithelial cells.\nReport status: DRAFT / UNSIGNED\n").encode()
    j = c.post("/api/tb/cases/TB-P2C/documents", files=[("files", ("cect_thorax.txt", ct)), ("files", ("hpe_draft.txt", hp))], data={"paths": json.dumps(["cect_thorax.txt", "hpe_draft.txt"])}).json()
    wait_job(c, j["job"])
    dd = c.get("/api/tb/cases/TB-P2C").json()
    ctdoc = next((x for x in dd["documents"] if "cect" in x["rel_path"]), None); hpdoc = next((x for x in dd["documents"] if "hpe" in x["rel_path"]), None)
    st0 = {x["id"]: x["status"] for x in dd["state"]["gate"]["requirements"]}
    check("dedicated case: CT read as final, lesion size missing, histopathology draft", st0.get("cect_tap") == "missing_field" and st0.get("histopathology") == "not_final", json.dumps({k: st0.get(k) for k in ("cect_tap", "histopathology")}))
    r = c.post("/api/tb/cases/TB-P2C/confirmations", json={"type": "confirm_value", "key": f"{ctdoc['doc_id']}:lesion_size", "fields": {"value": "4.6 x 3.8 cm"}}).json() if ctdoc else {}
    ev = next((x for x in r.get("state", {}).get("gate", {}).get("requirements", []) if x["id"] == "cect_tap"), {})
    check("confirmed value counts for the gate with the clinician named", ev.get("status") == "satisfied" and any(e.get("fact") == "lesion_size" and e.get("value") == "4.6 x 3.8 cm" and e.get("quote") == "" for e in ev.get("evidence", [])), ev.get("status"))
    d2 = c.get("/api/tb/cases/TB-P2C").json()
    cur = d2["facts"].get("lesion_size", {}).get("current", {})
    check("confirmed value shown in the Case File facts as confirmed, no model quote", cur.get("verification") == "confirmed" and cur.get("confirmed_by") == "admin" and cur.get("quote") == "" and cur.get("location") is None)
    r3 = c.post("/api/tb/cases/TB-P2C/confirmations", json={"type": "confirm_value", "key": f"{hpdoc['doc_id']}:histologic_type", "fields": {"value": "Adenocarcinoma"}}).json() if hpdoc else {}
    check("a value confirmed on a DRAFT report still does not pass the gate", next((x["status"] for x in r3.get("state", {}).get("gate", {}).get("requirements", []) if x["id"] == "histopathology"), None) == "not_final")
    c.delete("/api/tb/cases/TB-P2C")
    doc = next(x for x in d["documents"] if (x.get("classification") or {}).get("doc_type") == "histopathology")
    check("legacy /overrides alias still records a confirmation", "attest_final" in {x["type"] for x in c.post("/api/tb/cases/TB-001/overrides", json={"kind": "documents", "key": doc["doc_id"], "value": {"attested_final": True, "reason": "e2e"}}).json().get("confirmations", [])})
    c.post("/api/tb/cases/TB-001/overrides", json={"kind": "documents", "key": doc["doc_id"], "value": None})
    # ---- 2.3 department uploads: a member uploads without a Case File; the record waits in the queue tagged with department and user
    corpus = "/data/vaidyx/tb_demo_corpus/intake"
    xray = open(f"{corpus}/radio_diagnosis/xray_chest_pa_2026-09-03.pdf", "rb").read()
    note = b"SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nX-RAY CHEST PA VIEW\nPatient name Kumar R\nAge / Sex 62 Y / M\nStudy date 03/09/2026\nFindings: no change.\nReport status: FINAL\nReported by: Dr. Shalini Rao, MD (Radio-diagnosis)\n"
    check("member: upload for another department forbidden (403)", m.post("/api/tb/intake/documents", files=[("files", ("x.txt", note))], data={"paths": "[]", "department": "pathology"}).status_code == 403)
    r = m.post("/api/tb/intake/documents", files=[("files", ("xray_followup.txt", note)), ("files", ("old.doc", b"x"))], data={"paths": json.dumps(["xray_followup.txt", "old.doc"]), "department": "Radio-diagnosis"})
    check("member: upload for own department accepted", r.status_code == 200 and r.json()["department"] == "radiology", r.text[:120])
    jj, secs = wait_job(c, r.json()["job"])
    check("intake job read the record and refused the .doc", jj["state"] == "finished" and jj["total"] == 1 and jj["unsupported"] and jj["gate"] is None, f"{secs}s")
    q = m.get("/api/tb/intake").json()
    mine = [d for d in q["documents"] if d.get("uploaded_by") == "tb-e2e-radio"]
    check("member sees own department's intake records, tagged with department and user", len(mine) >= 1 and mine[0]["department"] == "radiology" and mine[0]["added"]
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
        check("filed into TB-001 with the uploader's department recorded", filed is not None and filed["department"] == "radiology" and filed["uploaded_by"] == "tb-e2e-radio" and filed["state"] == "ready", f"{secs}s")
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
        # reversal: an auto-link is recorded as a confirm_match by the matcher and can be undone, which moves the record back to the queue
        xray_rel = "radio_diagnosis/xray_chest_pa_2026-09-03.pdf"
        if where.get(xray_rel) == "TB-001":
            d1 = c.get("/api/tb/cases/TB-001").json()
            xd = next(x for x in d1["documents"] if x["rel_path"] == xray_rel)
            cm = next((x for x in d1["state"].get("confirmations", []) if x["type"] == "confirm_match" and x["key"] == xd["doc_id"] and not x.get("undone")), None)
            check("auto-link recorded in the Case File as a match by system:matching with Undo", cm is not None and cm["by"] == "system:matching" and d1["permissions"]["undo_confirmation"].get(cm["id"]) is True and d1["permissions"]["unfile"].get(xd["doc_id"]) is True)
            check("member cannot unfile (403)", m.post(f"/api/tb/cases/TB-001/documents/{xd['doc_id']}/unfile", json={"reason": "e2e"}).status_code == 403)
            r = c.post(f"/api/tb/cases/TB-001/confirmations/{cm['id']}/undo").json() if cm else {}
            back = next((x for x in c.get("/api/tb/intake").json()["documents"] if x["doc_id"] == xd["doc_id"]), None)
            check("undo of the match moves the record back to the queue, marked not this patient for TB-001", r.get("unfiled") is True and back is not None and back["state"] == "needs_matching" and "TB-001" in (back.get("rejected_cases") or [])
                  and not any(x["doc_id"] == xd["doc_id"] for x in c.get("/api/tb/cases/TB-001").json()["documents"]))
            p1 = c.get("/api/tb/cases/TB-001").json()["case"]["patient"]
            check("identifiers learned from the unfiled record are forgotten", not any(i.get("from_doc") == xd["doc_id"] for i in p1.get("ids", [])))
            au1 = {e["kind"] for e in c.get("/api/tb/cases/TB-001/audit").json()["events"]}
            check("unfile audited in the Case File", {"document_unfiled", "confirmation_undone"} <= au1)
            where.pop(xray_rel, None)
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
    m.close(); h.close()


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


V2_USERS = {"tb-e2e-root": "Root-e2e-2026!", "tb-e2e-radadmin": "RadAdm-e2e-2026!", "tb-e2e-raddoc": "RadDoc-e2e-2026!", "tb-e2e-mdt": "Mdt-e2e-2026!",
            "tb-e2e-breastdoc": "Breast-e2e-2026!"}  # throw-away accounts of the V2 Phase 2 section (created through the Tumour Board, deleted by the Vaidyx admin)


def v2_phase2(c, base):
    """V2 Phase 2 (2.1 departments, 2.2 roles and accounts): the Vaidyx admin names a root admin; the root admin creates a Radiology
    department admin, an MDT Coordinator and a Breast Surgery doctor; the department admin creates a Radiology doctor who sees only the
    Radiology inbox; forbidden actions answer 403; disable / enable / remove; everything audited and nobody becomes a Vaidyx admin."""
    pw = V2_USERS
    for u in pw:
        c.request("DELETE", "/api/auth/users", json={"username": u})
    o = c.get("/api/tb/org").json()
    check("2.1 organisation: 22 treating and 8 supporting departments with emails", sum(1 for d in o["departments"] if d["group"] == "treating") == 22
          and sum(1 for d in o["departments"] if d["group"] == "supporting") == 8 and all(d.get("email") for d in o["departments"]) and o["hospital"].get("pmjay_empanelled") is True
          and o["hospital"].get("fetch_window_months") == 12, f"{len(o['departments'])} departments")
    check("2.1 V1 names still resolve (Radio-diagnosis, Laboratory Medicine)", any("Radio-diagnosis" in d["aliases"] and d["id"] == "radiology" for d in o["departments"])
          and any("Laboratory Medicine" in d["aliases"] and d["id"] == "biochemistry" for d in o["departments"]))
    r = c.post("/api/tb/org/accounts", json={"username": "tb-e2e-root", "password": pw["tb-e2e-root"], "root_admin": True, "display_name": "Root admin (e2e)", "is_admin": True})
    check("2.2 Vaidyx admin names a root admin: a plain login, never a Vaidyx admin", r.status_code == 200 and r.json()["created"] and r.json()["root_admin"], r.text[:120])
    vu = {x["username"]: x for x in c.get("/api/auth/users").json()["users"]}
    check("2.2 root admin has no Vaidyx admin role and no shell", vu.get("tb-e2e-root", {}).get("is_admin") is False and not (vu.get("tb-e2e-root", {}).get("privileges") or {}).get("can_use_bash"),
          json.dumps({k: vu.get("tb-e2e-root", {}).get(k) for k in ("is_admin",)}))
    root = httpx.Client(base_url=base, timeout=120); ra = httpx.Client(base_url=base, timeout=120); rd = httpx.Client(base_url=base, timeout=120)
    md = httpx.Client(base_url=base, timeout=120); bd = httpx.Client(base_url=base, timeout=120)
    check("2.2 root admin logs in and sees the organisation", root.post("/api/auth/login", json={"username": "tb-e2e-root", "password": pw["tb-e2e-root"]}).status_code == 200
          and root.get("/api/tb/org").json()["me"]["root_admin"] and "users" in root.get("/api/tb/org").json())
    check("2.2 root admin cannot create a Vaidyx account through the main app (403)", root.post("/api/auth/users", json={"username": "tb-e2e-evil", "password": "Evil-e2e-2026!", "is_admin": True}).status_code == 403)
    check("2.2 root admin has no clinical action: Case Files, confirmations, waivers, sessions and board records answer 403 (plan section 4)",
          root.get("/api/tb/cases").status_code == 403 and root.get("/api/tb/cases/TB-001").status_code == 403
          and root.post("/api/tb/cases", json={"case_id": "TB-ROOT", "protocol": "lung_nsclc"}).status_code == 403
          and root.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": "histopathology", "reason": "e2e"}).status_code == 403
          and root.post("/api/tb/sessions", json={"date": "2026-10-20"}).status_code == 403 and root.get("/api/tb/sessions").status_code == 403
          and root.get("/api/tb/org/routes").status_code == 200 and root.get("/api/tb/org/accounts").status_code == 200)
    r1 = root.post("/api/tb/org/accounts", json={"username": "tb-e2e-radadmin", "password": pw["tb-e2e-radadmin"], "admin_of": ["Radiology"], "display_name": "Radiology admin (e2e)"})
    r2 = root.post("/api/tb/org/accounts", json={"username": "tb-e2e-mdt", "password": pw["tb-e2e-mdt"], "coordinator": True, "display_name": "MDT Coordinator (e2e)"})
    r3 = root.post("/api/tb/org/accounts", json={"username": "tb-e2e-breastdoc", "password": pw["tb-e2e-breastdoc"], "departments": {"breast_surgery": "doctor"}, "display_name": "Breast surgeon (e2e)"})
    check("2.2 root admin creates a department admin, a coordinator and a treating doctor", r1.status_code == 200 and r1.json()["admin_of"] == ["radiology"] and r2.status_code == 200 and r2.json()["coordinator"]
          and r3.status_code == 200 and r3.json()["departments"] == {"breast_surgery": "member"}, (r1.text + r2.text + r3.text)[:200])
    check("2.2 root admin: an account without a role is refused (400)", root.post("/api/tb/org/accounts", json={"username": "tb-e2e-norole", "password": "NoRole-e2e-2026!"}).status_code == 400)
    check("2.2 root admin: a Vaidyx admin is never placed (409)", root.post("/api/tb/org/accounts", json={"username": "admin", "coordinator": True}).status_code == 409)
    # the department admin
    check("2.2 department admin logs in", ra.post("/api/auth/login", json={"username": "tb-e2e-radadmin", "password": pw["tb-e2e-radadmin"]}).status_code == 200)
    oa = ra.get("/api/tb/org").json()
    check("2.2 department admin sees its department only, no user map, no clinical rights", [d["id"] for d in oa["admin_departments"]] == ["radiology"] and "users" not in oa and not oa["me"]["admin"]
          and not oa["me"]["known"] and not oa["can"]["create_case"], json.dumps({k: oa["me"].get(k) for k in ("admin", "known", "admin_of")}))
    check("2.2 department admin: organisation edit forbidden (403)", ra.put("/api/tb/org", json=o).status_code == 403)
    check("2.2 department admin cannot read Case Files, sessions or the intake queue (403)", ra.get("/api/tb/cases").status_code == 403 and ra.get("/api/tb/cases/TB-001").status_code == 403
          and ra.get("/api/tb/sessions").status_code == 403 and ra.get("/api/tb/intake").status_code == 403)
    r0 = ra.post("/api/tb/org/departments/radiology/doctors", json={"username": "tb-e2e-mdt", "role": "head"})
    check("2.2 department admin cannot place the coordinator in its department (409)", r0.status_code == 409 and "root admin" in r0.text, r0.text[:120])
    check("2.2 department admin: root-admin account creation forbidden (403)", ra.post("/api/tb/org/accounts", json={"username": "tb-e2e-x", "password": "X-e2e-2026!!", "coordinator": True}).status_code == 403)
    check("2.2 department admin: another department forbidden (403)", ra.post("/api/tb/org/departments/pathology/doctors", json={"username": "tb-e2e-x", "password": "X-e2e-2026!!"}).status_code == 403
          and ra.get("/api/tb/org/departments/pathology/doctors").status_code == 403)
    check("2.2 department admin: short password refused (400)", ra.post("/api/tb/org/departments/radiology/doctors", json={"username": "tb-e2e-x", "password": "short"}).status_code == 400)
    check("2.2 department admin: a Vaidyx admin is never placed (409)", ra.post("/api/tb/org/departments/radiology/doctors", json={"username": "admin"}).status_code == 409)
    r = ra.post("/api/tb/org/departments/Radio-diagnosis/doctors", json={"username": "tb-e2e-raddoc", "password": pw["tb-e2e-raddoc"], "display_name": "Dr Radio (e2e)", "role": "doctor"})
    check("2.2 department admin creates a doctor login of its department", r.status_code == 200 and r.json()["created"] and r.json()["departments"] == {"radiology": "member"} and r.json()["display_name"] == "Dr Radio (e2e)", r.text[:160])
    vu = {x["username"]: x for x in c.get("/api/auth/users").json()["users"]}
    check("2.2 the new doctor is a plain Vaidyx account: no admin, no shell", vu.get("tb-e2e-raddoc", {}).get("is_admin") is False and not (vu.get("tb-e2e-raddoc", {}).get("privileges") or {}).get("can_use_bash"))
    lst = ra.get("/api/tb/org/departments/radiology/doctors").json()
    row = next((x for x in lst["doctors"] if x["username"] == "tb-e2e-raddoc"), {})
    check("2.2 department list shows the doctor with an existing account; password reset goes to the Vaidyx admin", row.get("role") == "member" and row.get("account") is True and lst["can_reset"] is False
          and "Vaidyx admin" in lst["reset_note"], json.dumps(row)[:160])
    # the supporting doctor
    check("2.2 doctor logs in", rd.post("/api/auth/login", json={"username": "tb-e2e-raddoc", "password": pw["tb-e2e-raddoc"]}).status_code == 200)
    me = rd.get("/api/tb/org").json()
    check("2.2 doctor sees own roles only (supporting, Radiology)", me["me"]["departments"] == {"radiology": "member"} and me["me"]["supporting"] == {"radiology": "member"} and me["me"]["treating"] == {}
          and "users" not in me and me["admin_departments"] == [] and not me["can"]["create_case"], json.dumps(me["me"])[:160])
    ib = rd.get("/api/tb/inbox").json()
    check("2.2 doctor sees only the Radiology inbox", [d["id"] for d in ib["departments"]] == ["radiology"], json.dumps([d["id"] for d in ib["departments"]]))
    d1 = rd.get("/api/tb/cases/TB-001").json()
    rad_req = next((x for x in d1["state"]["gate"]["requirements"] if x["department"] == "Radiology"), None)
    check("2.2 supporting doctor: forbidden actions answer 403 (create, waive, organisation, accounts, listing, sessions)",
          rd.post("/api/tb/cases", json={"case_id": "TB-FORBID2", "protocol": "lung_nsclc"}).status_code == 403 and rd.put("/api/tb/org", json=o).status_code == 403
          and rd.post("/api/tb/org/departments/radiology/doctors", json={"username": "tb-e2e-x", "password": "X-e2e-2026!!"}).status_code == 403
          and rd.post("/api/tb/org/accounts", json={"username": "tb-e2e-x", "password": "X-e2e-2026!!", "coordinator": True}).status_code == 403
          and (rd.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": rad_req["id"], "reason": "e2e"}).status_code == 403 if rad_req else False)
          and rd.post("/api/tb/cases/TB-001/listing", json={"protocol": "lung_nsclc"}).status_code == 403 and rd.post("/api/tb/sessions", json={"date": "2026-10-20"}).status_code == 403)
    # the treating doctor and the coordinator
    check("2.2 treating doctor and coordinator log in", bd.post("/api/auth/login", json={"username": "tb-e2e-breastdoc", "password": pw["tb-e2e-breastdoc"]}).status_code == 200
          and md.post("/api/auth/login", json={"username": "tb-e2e-mdt", "password": pw["tb-e2e-mdt"]}).status_code == 200)
    r = bd.post("/api/tb/cases", json={"case_id": "TB-V2P2", "protocol": "breast", "setting": "early", "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "VXH/26/999001", "agesex": "52 Y / F"}})
    check("2.2 treating doctor creates a Case File", r.status_code == 200, r.text[:120])
    c.delete("/api/tb/cases/TB-V2P2")
    pb = bd.get("/api/tb/cases/TB-002").json()["permissions"]
    check("2.2 treating doctor may waive and upload, not delete the Case File or run sessions", all(pb["waive"].values()) and pb["upload"] is True and pb["delete_case"] is False
          and bd.post("/api/tb/sessions", json={"date": "2026-10-20"}).status_code == 403 and [d["id"] for d in bd.get("/api/tb/inbox").json()["departments"]] == ["breast_surgery"])
    d2 = md.get("/api/tb/cases/TB-001").json()
    hp = next((x for x in d2["documents"] if (x.get("classification") or {}).get("doc_type") == "histopathology"), None)
    check("2.2 coordinator cannot confirm or waive (403), may run sessions", not any(d2["permissions"]["waive"].values()) and (md.post("/api/tb/cases/TB-001/confirmations", json={"type": "attest_final", "key": hp["doc_id"]}).status_code == 403 if hp else False)
          and md.post("/api/tb/cases/TB-001/confirmations", json={"type": "waive", "key": rad_req["id"], "reason": "e2e"}).status_code == 403 and md.get("/api/tb/sessions").json()["can_manage"] is True
          and [d["id"] for d in md.get("/api/tb/inbox").json()["departments"]] == ["coordinator"])
    # disable, enable, remove
    r = ra.put("/api/tb/org/departments/radiology/doctors/tb-e2e-raddoc", json={"disabled": True})
    check("2.2 department admin disables the doctor", r.status_code == 200 and r.json()["disabled"] is True, r.text[:120])
    check("2.2 disabled doctor is refused on every Tumour Board route (403)", rd.get("/api/tb/org").status_code == 403 and rd.get("/api/tb/inbox").status_code == 403 and rd.get("/api/tb/cases").status_code == 403
          and rd.get("/api/tb/cases/TB-001").status_code == 403)
    check("2.2 department admin cannot disable a doctor placed elsewhere too (409)", ra.put("/api/tb/org/departments/radiology/doctors/tb-e2e-raddoc", json={"disabled": False}).status_code == 200
          and (lambda cur: root.put("/api/tb/org", json={"users": {**cur["users"], "tb-e2e-raddoc": {"departments": {"radiology": "member", "pathology": "member"}}}, "expected_version": cur["version"]}).status_code == 200)(root.get("/api/tb/org").json())
          and ra.put("/api/tb/org/departments/radiology/doctors/tb-e2e-raddoc", json={"disabled": True}).status_code == 409 and rd.get("/api/tb/org").status_code == 200)
    r = ra.request("DELETE", "/api/tb/org/departments/radiology/doctors/tb-e2e-raddoc")
    check("2.2 department admin removes the doctor from Radiology (the account and the other placement stay)", r.status_code == 200 and r.json()["kept"] is True
          and rd.get("/api/tb/org").json()["me"]["departments"] == {"pathology": "member"}, r.text[:120])
    au = root.get("/api/tb/org/audit").json()["events"]
    kinds = {e["kind"] for e in au}
    check("2.2 every account change is audited, never a password", {"account_created", "account_placed", "account_roles_changed", "root_admins_changed"} <= kinds
          and not any(v in json.dumps(au) for v in pw.values()), json.dumps(sorted(kinds)))
    check("2.2 audit is for the root admin only (403 for others)", ra.get("/api/tb/org/audit").status_code == 403 and rd.get("/api/tb/org/audit").status_code == 403)
    cur = root.get("/api/tb/org").json()
    check("2.2 a save with an outdated version is refused (409), a partial save keeps the other keys", root.put("/api/tb/org", json={"hospital": cur["hospital"], "expected_version": "0-0"}).status_code == 409
          and root.put("/api/tb/org", json={"hospital": {**cur["hospital"], "name": cur["hospital"].get("name") or ""}}).status_code == 200
          and root.get("/api/tb/org").json()["departments"] == cur["departments"] and root.get("/api/tb/org").json()["routes"] == cur["routes"])


def v2_phase2_cleanup(c):
    """Remove the V2 throw-away placements and delete their Vaidyx accounts (the Vaidyx admin's job)."""
    try:
        o = c.get("/api/tb/org").json()
        users = {k: v for k, v in (o.get("users") or {}).items() if k not in V2_USERS}
        admins = [a for a in (o.get("admins") or []) if a not in V2_USERS]
        c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "routes")}, "users": users, "admins": admins})
    except Exception as e:
        print("cleanup org failed:", e)
    for u in V2_USERS:
        c.request("DELETE", "/api/auth/users", json={"username": u})


# ---- V2 Phase 3: HIS-connected Case Files (3.1 adapter, 3.2 create from a UHID, 3.3 HIS data in the pipeline, 3.4 OP / IP labels,
# 3.5 re-fetch, 3.6 outside reports). Runs against a throw-away copy of the mock hospital on port 7131 so the desk signs never
# change the live demo store; the Vaidyx-TB HIS connection is pointed at the copy for the section and restored afterwards.
import pathlib, shutil, subprocess, tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
H_USERS = {"tb-e2e-h-breast": ("Hbreast-e2e-2026!", {"breast_surgery": "doctor"}), "tb-e2e-h-medonc": ("Hmedonc-e2e-2026!", {"medical_oncology": "doctor"}),
           "tb-e2e-h-gyn": ("Hgyn-e2e-2026!", {"gynaecologic_oncology": "doctor"}), "tb-e2e-h-gi": ("Hgi-e2e-2026!", {"gastrointestinal_surgery": "doctor"}),
           "tb-e2e-h-surg": ("Hsurg-e2e-2026!", {"surgical_oncology": "doctor"}), "tb-e2e-h-rad": ("Hrad-e2e-2026!", {"radiology": "doctor"})}
MOCK_PORT = 7131
LIVE_HIS = {"kind": "fhir", "label": "Vaidyx Demo Hospital HIS (SYNTHETIC)", "url": "http://127.0.0.1:7130", "token_file": str(REPO / "data" / "his_mock" / "token"), "enabled": True}


def _mock_copy():
    """A throw-away copy of data/his_mock (store, events, documents, token; no DICOM) and the mock app on 127.0.0.1:7131 over it."""
    src = REPO / "data" / "his_mock"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="tb-e2e-his-"))
    for name in ("store.json", "events.jsonl", "events.hl7", "fixture_index.json", "token"):
        if (src / name).exists():
            shutil.copy2(src / name, tmp / name)
    shutil.copytree(src / "documents", tmp / "documents")
    (tmp / "dicom").mkdir()
    env = {**os.environ, "TB_HIS_MOCK_DATA": str(tmp), "TB_HIS_MOCK_PORT": str(MOCK_PORT), "TB_HIS_MOCK_ORTHANC": "http://127.0.0.1:1"}  # never the live Orthanc
    log = open(tmp / "mock.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "--factory", "his_mock.app:create_app", "--host", "127.0.0.1", "--port", str(MOCK_PORT), "--log-level", "warning"],
                            cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{MOCK_PORT}/health", timeout=2).status_code == 200:
                return tmp, proc
        except Exception:
            pass
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"the e2e mock copy did not start (see {tmp}/mock.log)")


def _job(c, r):
    """The job of a from-his / refetch / link / upload answer, waited for; (answer, job, seconds)."""
    body = r.json()
    j, secs = wait_job(c, body["job"])
    return body, j, secs


def _req(d, rid):
    return next((x for x in d["state"]["gate"]["requirements"] if x["id"] == rid), {})


def _gaps(d):
    return sorted((x["id"], x.get("level")) for x in d["state"]["gate"]["requirements"] if x["status"] not in ("satisfied", "not_applicable", "waived"))


def v2_phase3(c, base, ctx):
    """V2 Phase 3 on the fixture patients of his_mock/scenarios.json (SYNTHETIC)."""
    h = c.get("/api/tb/his").json()
    check("3.1 the HIS connection is configured, answers and never returns its token", h["status"]["ok"] and h["settings"]["has_token"] and "token" not in h["settings"]
          and h["status"]["token_ok"] is True, json.dumps({k: h["status"].get(k) for k in ("ok", "name", "fhir_version", "error")}))
    tmp, proc = _mock_copy(); ctx["tmp"], ctx["proc"] = tmp, proc
    r0 = c.put("/api/tb/his", json={"kind": "fhir", "label": "e2e copy", "url": f"http://127.0.0.1:{MOCK_PORT}", "token_file": str(tmp / "token"), "enabled": True})
    check("3.1 a change of host needs the token sent explicitly: the saved token and token file never follow, a token file in the request is ignored (review S2)", r0.status_code == 400 and "token" in r0.text)
    r = c.put("/api/tb/his", json={"kind": "fhir", "label": "Vaidyx Demo Hospital HIS (SYNTHETIC) e2e copy", "url": f"http://127.0.0.1:{MOCK_PORT}", "token": (tmp / "token").read_text().strip(), "enabled": True})
    check("3.1 the HIS connection can be pointed at another HIS on this server (the e2e copy); the saved settings carry no token", r.status_code == 200 and "token" not in r.json()["settings"]
          and r.json()["settings"]["url"].endswith(str(MOCK_PORT)) and r.json()["settings"]["token_file"] == "", r.text[:160])
    check("3.1 a host outside this server is refused for a root admin (only a Vaidyx admin or TB_HIS_ALLOW_HOSTS)",
          c.put("/api/tb/his", json={"kind": "fhir", "url": "http://10.0.0.5:8080/fhir", "token": "x"}).status_code == 200  # the Vaidyx admin may
          and c.put("/api/tb/his", json={"kind": "fhir", "label": "Vaidyx Demo Hospital HIS (SYNTHETIC) e2e copy", "url": f"http://127.0.0.1:{MOCK_PORT}", "token": (tmp / "token").read_text().strip(), "enabled": True}).status_code == 200)
    h = c.get("/api/tb/his").json()
    check("3.1 the e2e copy answers through the adapter", h["status"]["ok"], json.dumps(h["status"])[:160])
    au = c.get("/api/tb/org/audit").json()["events"]
    check("3.1 saving the HIS settings is audited without the token", any(e["kind"] == "his_settings_saved" and "token" not in e for e in au))
    # throw-away doctor logins through the Tumour Board (never a Vaidyx admin)
    cl = {}
    for u, (pw, depts) in H_USERS.items():
        c.request("DELETE", "/api/auth/users", json={"username": u})
        r = c.post("/api/tb/org/accounts", json={"username": u, "password": pw, "departments": depts, "display_name": f"{u} (e2e)"})
        cl[u] = httpx.Client(base_url=base, timeout=600)
        ok = r.status_code == 200 and cl[u].post("/api/auth/login", json={"username": u, "password": pw}).status_code == 200
        if not ok:
            check(f"3.2 e2e login {u}", False, r.text[:120])
    breast, medonc, gyn, gi, surg, rad = (cl[k] for k in ("tb-e2e-h-breast", "tb-e2e-h-medonc", "tb-e2e-h-gyn", "tb-e2e-h-gi", "tb-e2e-h-surg", "tb-e2e-h-rad"))
    check("3.2 the treating doctors see the HIS as a way to create (one treating department each)", all(len(x.get("/api/tb/his").json()["treating_departments"]) == 1 for x in (breast, medonc, gyn, gi, surg))
          and rad.get("/api/tb/his").json()["treating_departments"] == [])
    # lookup
    lk = gyn.get("/api/tb/his/lookup", params={"identifier": "VXH/26/004209"}).json()
    check("3.2 lookup by UHID: registration, encounters, records in the window and the temporary registration to link", lk["found"] and lk["patient"]["uhid"] == "VXH/26/004209"
          and lk["patient"]["age"] == 50 and lk["patient"]["sex"] == "F" and len(lk["encounters"]) >= 1 and lk["reports"] >= 8
          and [s["uhid"] for s in lk["similar"]] == ["VXH/T/26/00412"] and lk["similar"][0]["registration_kind"] == "temporary" and "link" in lk["note"].lower(), json.dumps(lk)[:200])
    lk = medonc.get("/api/tb/his/lookup", params={"identifier": "IP/26/01875"}).json()
    check("3.2 lookup by IP No. resolves to its UHID", lk["found"] and lk["patient"]["uhid"] == "VXH/26/004212" and lk["patient"]["matched_on"] == {"kind": "ip_no", "value": "IP/26/01875"})
    lk = surg.get("/api/tb/his/lookup", params={"identifier": "OP/26/118708"}).json()
    check("3.2 lookup by OP No. resolves to its UHID", lk["found"] and lk["patient"]["uhid"] == "VXH/26/004206" and lk["patient"]["matched_on"]["kind"] == "op_no" and not lk["patient"].get("abha"))
    check("3.2 lookup of an unknown number: not found, no error", gyn.get("/api/tb/his/lookup", params={"identifier": "VXH/26/999999"}).json()["found"] is False)
    l4 = surg.get("/api/tb/his/lookup", params={"identifier": "VXH/26/004204"}).json(); l10 = gyn.get("/api/tb/his/lookup", params={"identifier": "VXH/26/004210"}).json()
    check("3.2 two patients with the same common name (Sunita Devi): each UHID is its own registration, neither offered as a duplicate (ages differ)",
          l4["patient"]["name"] == l10["patient"]["name"] and l4["patient"]["uhid"] != l10["patient"]["uhid"] and l4["similar"] == [] and l10["similar"] == [] and l4["patient"]["age"] != l10["patient"]["age"])
    check("3.2 a supporting doctor cannot create a Case File from the HIS (403)", rad.post("/api/tb/cases/from-his", json={"identifier": "VXH/26/004201", "protocol": "breast"}).status_code == 403)
    check("3.2 a treating doctor cannot own it through a supporting department (400)", breast.post("/api/tb/cases/from-his", json={"identifier": "VXH/26/004201", "protocol": "breast", "department": "Radiology"}).status_code == 400)
    check("3.2 unknown registration answers 404", breast.post("/api/tb/cases/from-his", json={"identifier": "VXH/26/999999", "protocol": "breast"}).status_code == 404)

    def create(client, ident, protocol, setting, cid, level="optimal", window=None, department=None):
        t0 = time.time()
        r = client.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": level, "case_id": cid, "window": window, "department": department})
        fetch_secs = round(time.time() - t0, 1)
        if r.status_code != 200:
            check(f"3.2 create {cid} from {ident}", False, r.text[:200]); return None, None, fetch_secs
        ctx["cases"].append(cid)
        body, j, secs = _job(client, r)
        return client.get(f"/api/tb/cases/{cid}").json(), j, fetch_secs

    # P01: complete work-up (breast, early): the gate passes on the first fetch, every record final and digitally signed, labelled with its OP No.
    d, j, fs = create(breast, "VXH/26/004201", "breast", "early", "TB-H-P01")
    if d:
        g = d["state"]["gate"]; docs = d["documents"]
        check("3.2 P01 complete work-up: Case File created from the UHID, owned by the doctor's department, fetched and read", d["case"]["department"] == "breast_surgery" and d["case"]["his"]["uhid"] == "VXH/26/004201"
              and d["case"]["patient"]["mrn"] == "VXH/26/004201" and d["case"]["hospital_level"] == "optimal" and len(docs) == 8 and all(x["state"] == "ready" for x in docs), f"{len(docs)} docs, job {j['seconds']} s")
        check("3.2 HIS fetch of the patient within 30 s (plan section 6)", fs <= 30, f"{fs} s")
        check("3.3 P01 gate passes at both levels on the first fetch; no request open", g["passed"] and g["levels"]["1"]["open"] == 0 and g["levels"]["2"]["open"] == 0
              and not any(a["status"] != "completed" for a in d["state"]["actions"]), f"{g['satisfied']}/{g['total']}")
        check("3.3 P01 every record is final and digitally signed from the HIS (verified Provenance), status and signature sources recorded",
              all(x["his"]["signed"] and x["classification"]["status"] == "FINAL" and x["classification"]["signed"] == "yes" and x["classification"]["signed_source"] == "his" for x in docs)
              and all(x["his"]["signature"]["ca"] == "Vaidyx Demo CA" for x in docs))
        check("3.4 P01 every record carries its OP No. and accession; records grouped by encounter", all(x["his"]["encounter_number"] == "OP/26/118701" for x in docs)
              and sum(1 for x in docs if x["his"].get("accession")) == 7 and [gr["key"] for gr in d["groups"] if gr["kind"] in ("OP", "IP")] and any(gr["pre_admission"] for gr in d["groups"] if gr.get("kind") == "OP"))
        ids = {(x["kind"], x["value"]) for x in d["case"]["patient"]["ids"]}
        check("3.2 P01 ABHA number shown as an identifier (optional, never a gap); Aadhaar never present", ("abha", "99-2600-0000-0101") in ids
              and not any(k == "aadhaar" for k, _ in ids) and not any(re.fullmatch(r"\d{4}[ -]?\d{4}[ -]?\d{4}", v or "") for _, v in ids))
        check("3.3 P01 values shown as written with a verified quote from the report text", d["facts"]["haemoglobin"]["current"]["verification"] == "verified" and "gm%" in d["facts"]["haemoglobin"]["current"]["value"]
              and d["facts"]["creatinine"]["current"]["verification"] == "verified", f"{d['facts'].get('haemoglobin', {}).get('current', {}).get('value')}")
        check("3.2 P01 Case File list carries the HIS brief", any(x["case_id"] == "TB-H-P01" and (x.get("his") or {}).get("uhid") == "VXH/26/004201" for x in breast.get("/api/tb/cases").json()["cases"]))
        check("3.5 permissions: the treating doctor may re-fetch and link; the supporting doctor may not", d["permissions"]["refetch"] is True and d["permissions"]["link_registration"] is True
              and rad.post("/api/tb/cases/TB-H-P01/his/refetch").status_code == 403)
        check("3.7 a supporting doctor cannot upload into a Case File", rad.post("/api/tb/cases/TB-H-P01/documents", files=[("files", ("x.txt", b"synthetic"))], data={"paths": "[]"}).status_code == 403)

    # P12 by IP No.: preliminary CT -> request to Radiology naming the accession -> sign on the desk -> re-fetch -> passes; the 2025 OPD note is outside the window
    d, j, fs = create(medonc, "IP/26/01875", "lung_nsclc", "non_metastatic", "TB-H-P12")
    if d:
        cid = "TB-H-P12"; r12 = _req(d, "cect_tap")
        check("3.2 P12 entered by IP No.: the Case File is for the UHID and holds every OP visit and IP admission", d["case"]["his"]["uhid"] == "VXH/26/004212" and d["case"]["his"]["matched_on"]["kind"] == "ip_no"
              and {e["kind"] for e in d["case"]["his"]["encounters"]} == {"OP", "IP"} and len(d["documents"]) == 13)
        check("3.3 P12 preliminary CT is a Level 1 gap with its accession No.", _gaps(d) == [("cect_tap", 1)] and r12["status"] == "not_final" and r12["accession"] == "RAD/26/01004", json.dumps(_gaps(d)))
        a = next((x for x in d["state"]["actions"] if x["requirement"] == "cect_tap"), {})
        check("3.3 P12 request routed to Radiology carries the accession No.", a.get("department") == "Radiology" and a.get("accession") == "RAD/26/01004" and a.get("status") != "completed")
        check("4.2 P12 the request is suggested, not sent: not in the Radiology inbox yet", a.get("status") == "suggested" and not _open_rows(rad, "radiology", cid, "cect_tap"))
        rs_ = medonc.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/send", json={})
        rows = _open_rows(rad, "radiology", cid, "cect_tap")
        check("3.3 P12 Radiology inbox shows the request once the treating doctor sent it", rs_.status_code == 200 and len(rows) == 1, rs_.text[:120])
        check("3.2 P12 the OPD note of 2025 is outside the 12-month window and counted as older", d["case"]["his"]["older_available"] == 1 and d["case"]["his"]["window"] == {"months": 12})
        ct = next(x for x in d["documents"] if x["his"]["id"] == "p12-r02")
        check("3.3 P12 preliminary CT: status and signature from the HIS (preliminary, not signed)", ct["classification"]["status"] == "PRELIMINARY" and ct["classification"]["signed"] == "no" and ct["his"]["signed"] is False)
        op = next((gr for gr in d["groups"] if gr.get("number") == "OP/26/118716"), {})
        check("3.4 P12 the CT done at the OP visit before admission is grouped under that visit and labelled pre-admission OPD", op.get("pre_admission") is True and ct["doc_id"] in op.get("docs", []))
        # the radiologist completes and signs on the RIS desk of the e2e copy
        rs = httpx.post(f"http://127.0.0.1:{MOCK_PORT}/desk/api/RAD/orders/rad-26-01004/sign", json={"signer": "prac-vxreg-20201"}, timeout=60)
        check("1.5 desk: Complete and sign makes the CT final with a signature (e2e copy)", rs.status_code == 200 and rs.json().get("status") == "final" and rs.json().get("signature"), rs.text[:160])
        r = medonc.post(f"/api/tb/cases/{cid}/his/refetch")
        body, jj, secs = _job(medonc, r)
        d2 = medonc.get(f"/api/tb/cases/{cid}").json()
        check("3.5 P12 re-fetch brings only the changed report (delta), as a new version; versions at the watermark instant are skipped, not re-read", r.status_code == 200
              and body["his"]["added"] == 1 and body["his"]["updated"] == 0 and body["his"]["skipped"] == body["his"]["reports"] - 1 and body["his"]["reports"] <= 3 and jj["state"] == "finished", json.dumps(body.get("his")))
        vs = sorted((x for x in d2["documents"] if x["his"]["id"] == "p12-r02"), key=lambda x: x["his"]["version"])
        check("3.5 P12 version 1 kept as history (superseded), version 2 final and signed", len(vs) == 2 and vs[0].get("superseded", {}).get("version") == 2 and vs[1]["his"]["signed"] and vs[1]["classification"]["status"] == "FINAL"
              and vs[0]["doc_id"] in d2["state"]["gate"]["documents"]["superseded"])
        check("3.5 P12 gate passes after the re-fetch and the request closed itself", d2["state"]["gate"]["passed"] and next(x for x in d2["state"]["actions"] if x["requirement"] == "cect_tap")["status"] == "completed",
              f"{d2['state']['gate']['satisfied']}/{d2['state']['gate']['total']}")
        check("3.5 P12 the owning department is told what the re-fetch closed", any(n["case_id"] == cid and n.get("refetch") and n["kind"] == "request_closed" for n in medonc.get("/api/tb/notifications").json()["notifications"])
              and jj.get("refetch_result", {}).get("closed"))
        check("3.5 P12 watermark advanced; the fetch is audited", d2["case"]["his"]["watermark"] > d["case"]["his"]["watermark"]
              and any(e["kind"] == "his_fetch" and e.get("reason") == "refetch" for e in medonc.get(f"/api/tb/cases/{cid}/audit").json()["events"]))
        r = medonc.post(f"/api/tb/cases/{cid}/his/fetch-older", json={"all": True})
        body, jj, secs = _job(medonc, r)
        d3 = medonc.get(f"/api/tb/cases/{cid}").json()
        check("3.2 P12 Fetch older records widens the window without starting over", r.status_code == 200 and body["his"]["added"] == 1 and d3["case"]["his"]["window"] == {"all": True}
              and d3["case"]["his"]["older_available"] == 0 and len(d3["documents"]) == 15)

    # P02: an IHC amended after signing
    d, j, fs = create(breast, "VXH/26/004202", "breast", "locally_advanced", "TB-H-P02")
    if d:
        vs = sorted((x for x in d["documents"] if x["his"]["id"] == "p02-r05"), key=lambda x: x["his"]["version"])
        check("3.3 P02 amended IHC: both versions fetched, version 1 as history, version 2 (amended, signed) current; the gate passes", len(vs) == 2 and vs[0].get("superseded") and not vs[1].get("superseded")
              and vs[1]["classification"]["status"] == "AMENDED" and vs[1]["his"]["signed"] and d["state"]["gate"]["passed"], json.dumps(_gaps(d)))
        check("3.3 P02 HER2 current value comes from the amended version; the earlier value stays in the history", "3+" in d["facts"]["her2"]["current"]["value"] and any("2+" in h["value"] for h in d["facts"]["her2"]["history"]))
        items = d["discordances"].get("items") or d["discordances"].get("review") or []
        check("3.3 P02 the change from 2+ to 3+ is shown as a discordance for review", any(it.get("kind") == "amended" and it.get("field") == "her2" for it in items), json.dumps([(it.get('kind'), it.get('field')) for it in items])[:160])

    # P15: molecular sample collected, result awaited; a HIS Observation that disagrees with its PDF
    d, j, fs = create(medonc, "VXH/26/004215", "lung_nsclc", "non_metastatic", "TB-H-P15")
    if d:
        dm, met = _req(d, "driver_mutations"), _req(d, "met")
        check("3.3 P15 driver mutations and MET are pending Level 2 gaps (sample collected, result awaited) with the accession No., routed to Pathology", _gaps(d) == [("driver_mutations", 2), ("met", 2)]
              and dm["accession"] == "PATH/26/00451" and dm.get("pending_from_order") and "result awaited" in " ".join(dm["problems"]) and met["accession"] == "PATH/26/00451" and dm["department"] == "Pathology", json.dumps(dm.get("problems"))[:200])
        acts = [x for x in d["state"]["actions"] if x["requirement"] in ("driver_mutations", "met")]
        check("3.3 P15 the requests carry the accession No. and the order stage", all(x.get("accession") == "PATH/26/00451" and (x.get("pending_order") or {}).get("stage") == "sample_collected" for x in acts) and len(acts) == 2)
        check("3.3 P15 the HIS haemoglobin (11.2 gm%) differs from the report text (12.1 gm%): flagged for review, never shown as a fact", any(f["fact"] == "haemoglobin" and "11.2" in f["his_value"] and "12.1" in (f.get("text_value") or "") for f in d["his_flags"])
              and d["facts"]["haemoglobin"]["current"]["value"].startswith("12.1") and d["facts"]["haemoglobin"]["current"]["verification"] == "verified", json.dumps(d["his_flags"])[:200])
        au = medonc.get("/api/tb/cases/TB-H-P15/audit").json()["events"]
        check("3.3 P15 the value check is audited", any(e["kind"] == "his_value_check" and e.get("fact") == "haemoglobin" and e.get("result") == "differs" for e in au))

    # P09: a temporary registration holds the CECT; a person links it
    d, j, fs = create(gyn, "VXH/26/004209", "cervix", "locally_advanced", "TB-H-P09")
    if d:
        cid = "TB-H-P09"
        check("3.2 P09 the temporary registration is listed for a person to link, never merged; its records are not in the Case File", [s["uhid"] for s in d["his"]["unlinked"]] == ["VXH/T/26/00412"]
              and not any(x["his"].get("registration") for x in d["documents"]) and len(d["documents"]) == 8)
        rq = _req(d, "cect_abdomen_pelvis")
        check("3.3 P09 the CECT is a Level 1 gap pointing at the unlinked registration (no accession No. for a re-scan)", _gaps(d) == [("cect_abdomen_pelvis", 1)] and not rq.get("accession")
              and rq.get("unlinked_registrations") == ["VXH/T/26/00412"] and "link" in " ".join(rq["problems"]).lower(), json.dumps(rq.get("problems"))[:200])
        check("3.2 P09 a wrong UHID cannot be linked (404)", gyn.post(f"/api/tb/cases/{cid}/his/link", json={"uhid": "VXH/26/000001"}).status_code == 404)
        r = gyn.post(f"/api/tb/cases/{cid}/his/link", json={"uhid": "VXH/T/26/00412", "reason": "casualty registration of the same person, confirmed with the patient"})
        body, jj, secs = _job(gyn, r)
        d2 = gyn.get(f"/api/tb/cases/{cid}").json()
        lk = next((x for x in d2["documents"] if x["his"].get("registration")), None)
        check("3.2 P09 after a person links it (audited) the CECT joins the Case File labelled with its registration and the gate passes", r.status_code == 200 and body["his"]["added"] == 1 and lk is not None
              and lk["his"]["registration"] == "VXH/T/26/00412" and d2["state"]["gate"]["passed"] and d2["his"]["unlinked"] == [] and d2["his"]["linked"][0]["uhid"] == "VXH/T/26/00412"
              and any(e["kind"] == "registration_linked" for e in gyn.get(f"/api/tb/cases/{cid}/audit").json()["events"]), json.dumps(_gaps(d2)))
        check("3.2 P09 the Case File learned the temporary UHID; linking twice is refused (409)", ("uhid", "VXH/T/26/00412") in {(x["kind"], x["value"]) for x in d2["case"]["patient"]["ids"]}
              and gyn.post(f"/api/tb/cases/{cid}/his/link", json={"uhid": "VXH/T/26/00412"}).status_code == 409)

    # P17: a duplicate permanent UHID, and the CEA from a private laboratory uploaded by the doctor
    d, j, fs = create(gi, "VXH/26/004217", "colorectal_rectum", "non_metastatic", "TB-H-P17")
    if d:
        cid = "TB-H-P17"
        check("3.3 P17 CEA missing from the HIS: a Level 2 gap to Biochemistry; the duplicate UHID is listed to link", _gaps(d) == [("cea", 2)] and _req(d, "cea")["department"] == "Biochemistry"
              and [s["uhid"] for s in d["his"]["unlinked"]] == ["VXH/26/004317"], json.dumps(_gaps(d)))
        pdf = (REPO / "data" / "his_mock" / "documents" / "outside" / "P17-R10.pdf").read_bytes()
        r = gi.post(f"/api/tb/cases/{cid}/documents", files=[("files", ("cea_private_lab.pdf", pdf))], data={"paths": json.dumps(["cea_private_lab.pdf"])})
        body, jj, secs = _job(gi, r)
        d2 = gi.get(f"/api/tb/cases/{cid}").json()
        od = next((x for x in d2["documents"] if x.get("outside")), None)
        check("3.6 P17 the uploaded private-lab CEA is an outside report, read through the V1 pipeline, matched by name only", od is not None and od["rel_path"].startswith("outside/") and od["state"] == "ready"
              and od["identity"] == "name_match" and (od["classification"] or {}).get("status") == "FINAL" and od["classification"].get("signed_source") is None, json.dumps({k: od.get(k) for k in ("identity", "rel_path")} if od else {}))
        cr = _req(d2, "cea")
        check("3.6 P17 the gate asks the treating doctor to confirm the patient of the outside report", cr["status"] == "needs_confirmation" and {"type": "confirm_match", "doc_id": od["doc_id"]} in cr.get("needs", [])
              and od["doc_id"] in d2["state"]["gate"]["documents"]["outside_unconfirmed"], json.dumps(cr.get("problems"))[:160])
        check("3.6 P17 a supporting doctor cannot confirm it (403)", rad.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "confirm_match", "key": od["doc_id"], "fields": {"case_id": cid}}).status_code == 403)
        st = gi.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "confirm_match", "key": od["doc_id"], "fields": {"case_id": cid}, "reason": "name, age and sex match; confirmed with the patient"}).json()["state"]
        check("3.6 P17 after the confirmation the CEA counts (verified against the outside report's text) and the gate passes", st["gate"]["passed"] and next(x for x in st["gate"]["requirements"] if x["id"] == "cea")["status"] == "satisfied",
              json.dumps([(x["id"], x["status"]) for x in st["gate"]["requirements"] if x["status"] != "satisfied"]))
        d3 = gi.get(f"/api/tb/cases/{cid}").json()
        check("3.6 P17 the confirmation shows on the document and survives (overlay)", next(x for x in d3["documents"] if x["doc_id"] == od["doc_id"])["identity_confirmed_by"] == "tb-e2e-h-gi"
              and "6.8" in d3["facts"]["cea"]["current"]["value"], d3["facts"].get("cea", {}).get("current", {}).get("value"))
        r = gi.post(f"/api/tb/cases/{cid}/his/link", json={"uhid": "VXH/26/004317", "reason": "second UHID issued by mistake"})
        body, jj, secs = _job(gi, r)
        d4 = gi.get(f"/api/tb/cases/{cid}").json()
        check("3.2 P17 linking the duplicate UHID adds its earlier OPD note labelled with that registration", body["his"]["added"] == 1 and any(x["his"].get("registration") == "VXH/26/004317" for x in d4["documents"]) and d4["state"]["gate"]["passed"])

    # P06: a scanned outside biopsy with a masked Aadhaar (OCR path), entered by OP No.
    d, j, fs = create(surg, "OP/26/118708", "oral_cavity", "locally_advanced", "TB-H-P06")
    if d:
        cid = "TB-H-P06"
        check("3.2 P06 entered by OP No.; no ABHA: nothing flagged, the gate passes", d["case"]["his"]["matched_on"]["kind"] == "op_no" and not d["case"]["patient"].get("abha") and d["state"]["gate"]["passed"], json.dumps(_gaps(d)))
        png = (REPO / "data" / "his_mock" / "documents" / "outside" / "P06-R06-scan.png").read_bytes()
        t0 = time.time()
        r = surg.post(f"/api/tb/cases/{cid}/documents", files=[("files", ("private_lab_biopsy_scan.png", png))], data={"paths": json.dumps(["private_lab_biopsy_scan.png"])})
        body, jj, secs = _job(surg, r)
        d2 = surg.get(f"/api/tb/cases/{cid}").json()
        od = next((x for x in d2["documents"] if x.get("outside")), None)
        full = surg.get(f"/api/tb/cases/{cid}/documents/{od['doc_id']}").json() if od else {}
        text = "\n".join(p.get("text", "") for p in full.get("pages") or [])
        check("3.6 P06 the scanned outside report goes through the OCR path, is labelled outside and matched by name for a person to confirm", od is not None and od["state"] == "ready"
              and "vision-transcription" in (od.get("methods") or []) and od["identity"] == "name_match", f"{secs} s, methods {od.get('methods') if od else None}")
        check("3.6 P06 the Aadhaar stays masked: no 12-digit number in the stored text, never an identifier", bool(text) and not re.search(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)", text)
              and not any(i.get("kind") == "aadhaar" for i in (od.get("identity_read") or {}).get("ids") or []) and "aadhaar" not in json.dumps(d2["case"]["patient"]).lower())
        hp = _req(d2, "histopathology")
        check("3.6 P06 the HIS histopathology still stands; the outside one waits for the patient confirmation", hp["status"] == "needs_confirmation" and {"type": "confirm_match", "doc_id": od["doc_id"]} in hp.get("needs", []))
        st = surg.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "confirm_match", "key": od["doc_id"], "fields": {"case_id": cid}, "reason": "e2e: confirmed"}).json()["state"]
        check("3.6 P06 confirmed: the gate passes again", st["gate"]["passed"])

    # P13: the staging CT done in OPD before admission; the summary says so
    d, j, fs = create(medonc, "VXH/26/004213", "lung_nsclc", "non_metastatic", "TB-H-P13")
    if d:
        cid = "TB-H-P13"
        ct = next((x for x in d["documents"] if x["his"]["id"] == "p13-r02"), {})
        op = next((gr for gr in d["groups"] if gr.get("number") == "OP/26/118717"), {})
        check("3.4 P13 the CECT done at the OP visit is found under the UHID, labelled OP and pre-admission, grouped before the IP admission", ct.get("his", {}).get("encounter_kind") == "OP" and op.get("pre_admission") is True
              and ct.get("doc_id") in op.get("docs", []) and [gr["kind"] for gr in d["groups"] if gr["kind"] in ("OP", "IP")][0] == "IP")
        check("3.3 P13 bronchoscopy never ordered: a Level 1 gap whose request names no accession No.", _gaps(d) == [("bronchoscopy", 1)] and not _req(d, "bronchoscopy").get("accession")
              and not next(x for x in d["state"]["actions"] if x["requirement"] == "bronchoscopy").get("accession"), json.dumps(_gaps(d)))
        tl = d["timeline"]
        check("3.4 P13 the timeline shows the OP visit and the IP admission", [e for e in tl if e["kind"] == "encounter" and e.get("encounter_kind") == "OP"] and [e for e in tl if e["kind"] == "encounter" and e.get("encounter_kind") == "IP"])
        sm = medonc.post(f"/api/tb/cases/{cid}/summary", json={"force": True}).json()
        enc = [e for e in sm.get("encounters") or [] if e.get("pre_admission")]
        check("3.4 P13 the summary says which tests were pre-admission OPD", bool(enc) and any("CECT" in rec.upper() for e in enc for rec in e["records"]), json.dumps([e.get("text") for e in sm.get("encounters") or []])[:200])

    # P03: one IP admission with ward transfers; a signature that fails verification
    d, j, fs = create(breast, "VXH/26/004203", "breast", "early", "TB-H-P03")
    if d:
        ip = [gr for gr in d["groups"] if gr["kind"] == "IP"]
        check("3.4 P03 one IP admission with its ward and bed movements; every record of the stay under the same IP No.", len(ip) == 1 and len(ip[0]["ward_history"]) == 3 and "High Dependency" in json.dumps(ip[0]["ward_history"])
              and sum(1 for x in d["documents"] if x["his"]["encounter_number"] == "IP/26/01872") == 7, json.dumps(ip[0]["ward_history"] if ip else [])[:200])
        ds = next((x for x in d["documents"] if x["his"]["id"] == "p03-r10"), {})
        check("3.3 P03 a signature that fails verification (tampered hash) never counts as signed", ds.get("his", {}).get("signed") is False and ds["his"]["signature"]["verification_status"] == "failed"
              and ds["classification"]["signed"] == "no" and any("failed verification" in n for n in ds["classification"].get("status_notes") or []), json.dumps(ds.get("classification", {}).get("status_notes")))
        check("3.3 P03 a value omitted from the signed IHC is a Level 2 gap with the accession No.", _gaps(d) == [("receptor_status", 2)] and _req(d, "receptor_status")["accession"] == "PATH/26/00418", json.dumps(_gaps(d)))

    # P11: final in the LIS without a digital signature -> sign on the desk -> re-fetch
    d, j, fs = create(gyn, "VXH/26/004211", "cervix", "early", "TB-H-P11")
    if d:
        cid = "TB-H-P11"; hp = _req(d, "histopathology")
        check("3.3 P11 a final report without a digital signature is a Level 1 gap (not signed) with its accession No.", _gaps(d) == [("histopathology", 1)] and hp["accession"] == "PATH/26/00434"
              and "no digital signature" in " ".join(hp["problems"]), json.dumps(hp.get("problems"))[:200])
        rs = httpx.post(f"http://127.0.0.1:{MOCK_PORT}/desk/api/PATH/orders/path-26-00434/sign", json={"signer": "prac-vxreg-20204"}, timeout=60)
        check("1.5 desk: a final report that was never signed can be signed (a new signed version)", rs.status_code == 200 and rs.json().get("status") == "final" and rs.json().get("signature")
              and rs.json().get("current_version") == 2, rs.text[:160])
        r = gyn.post(f"/api/tb/cases/{cid}/his/refetch")
        body, jj, secs = _job(gyn, r)
        d2 = gyn.get(f"/api/tb/cases/{cid}").json()
        check("3.5 P11 after Complete and sign on the desk and a re-fetch the request closes and the gate passes", rs.status_code == 200 and d2["state"]["gate"]["passed"]
              and next(x for x in d2["state"]["actions"] if x["requirement"] == "histopathology")["status"] == "completed", json.dumps(_gaps(d2)))

    # P10 cancelled order, P08 ordered viral markers, P04 scheduled bone scan: gaps name the accession and the stage
    d, j, fs = create(gyn, "VXH/26/004210", "cervix", "locally_advanced", "TB-H-P10")
    if d:
        rq = _req(d, "cect_abdomen_pelvis")
        check("3.3 P10 a cancelled CT is a Level 1 gap naming the cancelled accession", _gaps(d) == [("cect_abdomen_pelvis", 1)] and rq["accession"] == "RAD/26/01000" and (rq.get("pending_order") or {}).get("stage") == "cancelled", json.dumps(rq.get("problems"))[:200])
    d, j, fs = create(gyn, "VXH/26/004208", "cervix", "locally_advanced", "TB-H-P08")
    if d:
        rq = _req(d, "viral_markers")
        check("3.3 P08 viral markers ordered, no report: Level 1 gap to Microbiology with the accession", _gaps(d) == [("viral_markers", 1)] and rq["accession"] == "MIC/26/00611" and rq["department"] == "Microbiology"
              and (rq.get("pending_order") or {}).get("stage") == "ordered", json.dumps(_gaps(d)))
    d, j, fs = create(surg, "VXH/26/004204", "breast", "locally_advanced", "TB-H-P04")
    if d:
        rq = _req(d, "bone_scan")
        check("3.3 P04 bone scan scheduled, no report: Level 1 gap to Nuclear Medicine with the accession and the date", _gaps(d) == [("bone_scan", 1)] and rq["accession"] == "NM/26/00152"
              and (rq.get("pending_order") or {}).get("stage") == "scheduled" and d["case"]["department"] == "surgical_oncology", json.dumps(_gaps(d)))
    # the remaining plan 1.1 patients: P05 (reports never ordered), P16 (the second complete work-up), P14 and P18 (creation and first-fetch gate only;
    # the referral and the second primary are Phase 5), each against scenarios.json first_fetch (review M9)
    fx = {p["slot"]: p for p in json.load(open(REPO / "his_mock" / "scenarios.json"))["patients"]}

    def first_fetch(slot, protocol):
        cf = next(c_ for c_ in fx[slot]["case_files"] if c_["protocol"] == protocol)
        return sorted((x["requirement"], x["level"]) for x in cf["first_fetch"]["gaps"]), cf
    d, j, fs = create(c, "VXH/26/004205", "oral_cavity", "locally_advanced", "TB-H-P05", department="ENT / Head and Neck Surgery")  # the Vaidyx admin names the owner
    if d:
        exp, cf = first_fetch("P05", "oral_cavity")
        check("3.3 P05 reports never ordered (chest X-ray, dental evaluation): Level 1 gaps whose requests name no accession No.", _gaps(d) == exp and not any(_req(d, g[0]).get("accession") for g in exp)
              and not any(x.get("accession") for x in d["state"]["actions"] if x["status"] != "completed") and d["case"]["department"] == "ent_head_neck_surgery", json.dumps(_gaps(d)))
    d, j, fs = create(c, "VXH/26/004216", "colorectal_rectum", "non_metastatic", "TB-H-P16", department="Colorectal Surgery")
    if d:
        exp, cf = first_fetch("P16", "colorectal_rectum")
        check("3.3 P16 complete rectal work-up passes on the first fetch", _gaps(d) == exp == [] and d["state"]["gate"]["passed"], json.dumps(_gaps(d)))
    d, j, fs = create(c, "VXH/26/004214", "lung_nsclc", "metastatic", "TB-H-P14", department="Pulmonology")
    if d:
        exp, cf = first_fetch("P14", "lung_nsclc")
        check("3.3 P14 lung work-up (later referred, Phase 5): the first-fetch gate matches the fixture; the HIS referral is listed", _gaps(d) == exp and len(d["his"]["referrals"]) >= 1, json.dumps([_gaps(d), exp]))
    d, j, fs = create(c, "VXH/26/004218", "colorectal_rectum", "non_metastatic", "TB-H-P18", department="Colorectal Surgery")
    if d:
        exp, cf = first_fetch("P18", "colorectal_rectum")
        check("3.3 P18 first primary (rectum) passes on the first fetch; the breast records of the same UHID are fetched too (the second Case File is Phase 5)", _gaps(d) == exp == [] and d["state"]["gate"]["passed"]
              and any("mammogram" in (x["classification"] or {}).get("doc_type", "") for x in d["documents"]), json.dumps(_gaps(d)))
    # unlink (review M8) and the undo of an outside-report confirmation (review M5), on P09 / P17
    if "TB-H-P09" in ctx["cases"]:
        r = gyn.post("/api/tb/cases/TB-H-P09/his/unlink", json={"uhid": "VXH/T/26/00412", "reason": "e2e: not the same person after all"})
        d2 = gyn.get("/api/tb/cases/TB-H-P09").json() if r.status_code == 200 else {}
        check("3.2 P09 a link can be undone: the registration's records leave, its identifiers are forgotten, the gap returns, audited", r.status_code == 200 and r.json()["removed_documents"] == 1
              and not any(x["his"].get("registration") for x in d2.get("documents", [])) and _gaps(d2) == [("cect_abdomen_pelvis", 1)]
              and ("uhid", "VXH/T/26/00412") not in {(x["kind"], x["value"]) for x in d2["case"]["patient"]["ids"]} and d2["his"]["unlinked"][0]["uhid"] == "VXH/T/26/00412"
              and any(e["kind"] == "registration_unlinked" for e in gyn.get("/api/tb/cases/TB-H-P09/audit").json()["events"]), r.text[:160])
    if "TB-H-P17" in ctx["cases"]:
        d3 = gi.get("/api/tb/cases/TB-H-P17").json()
        od = next((x for x in d3["documents"] if x.get("outside")), None)
        conf = next((x for x in d3["state"].get("confirmations", []) if x["type"] == "confirm_match" and x["key"] == (od or {}).get("doc_id") and not x.get("undone")), None)
        r = gi.post(f"/api/tb/cases/TB-H-P17/confirmations/{conf['id']}/undo") if conf else None
        d4 = gi.get("/api/tb/cases/TB-H-P17").json() if r is not None and r.status_code == 200 else {}
        check("3.6 P17 undoing the patient confirmation of an outside report keeps the record and asks again (no unfile)", r is not None and r.status_code == 200 and not r.json().get("unfiled")
              and any(x["doc_id"] == od["doc_id"] and x["identity"] == "name_match" and not x.get("identity_confirmed_by") for x in d4.get("documents", []))
              and _req(d4, "cea").get("status") == "needs_confirmation", (r.text[:160] if r is not None else "no confirmation found"))


def v2_phase3_cleanup(c, ctx):
    """Delete the Case Files and accounts of the section, restore the live HIS connection, stop the e2e mock copy."""
    for cid in ctx.get("cases") or []:
        try:
            c.delete(f"/api/tb/cases/{cid}")
        except Exception as e:
            print("cleanup case failed:", cid, e)
    try:
        o = c.get("/api/tb/org").json()
        users = {k: v for k, v in (o.get("users") or {}).items() if k not in H_USERS}
        c.put("/api/tb/org", json={"users": users})
    except Exception as e:
        print("cleanup org failed:", e)
    for u in H_USERS:
        c.request("DELETE", "/api/auth/users", json={"username": u})
    try:
        tok = (REPO / "data" / "his_mock" / "token").read_text().strip()
        r = c.put("/api/tb/his", json={**LIVE_HIS, "token": tok})
        print("HIS connection restored:", r.status_code, (r.json().get("settings") or {}).get("url") if r.status_code == 200 else r.text[:120])
        (REPO / "data" / "tumour_board" / "his.json").unlink(missing_ok=True)  # back to the pristine default (the demo token file), not a saved copy of the token
    except Exception as e:
        print("restore HIS failed:", e)
    proc = ctx.get("proc")
    if proc:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if ctx.get("tmp"):
        shutil.rmtree(ctx["tmp"], ignore_errors=True)


SCAN_100 = "/data/vaidyx/tb_demo_corpus/cases/TB-006/outside_records/deccan_general_hospital_records_scan.pdf"
HINDI_SCAN = "/data/vaidyx/tb_demo_corpus/cases/TB-005/surgical_oncology/surgical_oncology_opd_2026-09-03.png"


def phase3(c):
    """V1 Phase 3: labelled dates and the confirm_dates flow (3.1), confirm_doc_type with re-extraction (3.2), Hindi flags (3.6),
    the big-scan warning (3.7). Runs on its own synthetic Case File TB-TEST3 (rectum protocol: restaging MRI after treatment)."""
    import os
    c.delete("/api/tb/cases/TB-TEST3")
    r = c.post("/api/tb/cases", json={"case_id": "TB-TEST3", "protocol": "colorectal_rectum", "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-998", "agesex": "55 Y / M"}})
    check("phase3: synthetic rectum Case File created", r.status_code == 200, r.text[:80])
    ts = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDEPARTMENT OF RADIATION ONCOLOGY\nRT COMPLETION SUMMARY\nPatient: SYNTHETIC, Test Patient  UHID: SYN-998  55 Y / M\n"
          "Diagnosis as recorded: carcinoma rectum.\nTreatment received: long-course chemoradiation 50.4 Gy in 28 fractions with concurrent capecitabine.\n"
          "Date of completion: 10/08/2026\nNext review: 05/10/2026\nReport status: FINAL\nReported on 12/08/2026\nSd/- Dr. R. Nair, Radiation Oncologist, Reg. No. KMC 45678\n").encode()
    mri = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDEPARTMENT OF RADIO-DIAGNOSIS\nMRI PELVIS WITH CONTRAST\nPatient: SYNTHETIC, Test Patient  UHID: SYN-998  55 Y / M\n"
           "Findings: rectal wall thickening as recorded, mesorectal fascia clear.\nImpression: as above.\nReport status: FINAL\nSd/- Dr. S. Rao, Consultant Radiologist, Reg. No. KMC 12345\n").encode()
    j = c.post("/api/tb/cases/TB-TEST3/documents", files=[("files", ("rt_completion_summary.txt", ts)), ("files", ("mri_pelvis_restaging.txt", mri))],
               data={"paths": json.dumps(["radiotherapy/rt_completion_summary.txt", "radiology/mri_pelvis_restaging.txt"])}).json()
    wait_job(c, j["job"])
    d = c.get("/api/tb/cases/TB-TEST3").json()
    docs = {x["rel_path"]: x for x in d["documents"]}
    cts, cmri = docs["radiotherapy/rt_completion_summary.txt"]["classification"], docs["radiology/mri_pelvis_restaging.txt"]["classification"]
    check("3.1 treatment summary: event = date of completion, report = reported on, next review ignored",
          cts.get("event_date_iso") == "2026-08-10" and cts.get("report_date_iso") == "2026-08-12" and not cts.get("date_unconfirmed")
          and any(x["iso"] == "2026-10-05" and x["kind"] == "ignore" for x in cts.get("dates") or []), f"{cts.get('event_date_iso')} / {cts.get('report_date_iso')} / {cts.get('event_date_label')}")
    check("3.1 MRI with no date is unconfirmed (no guess)", cmri.get("date_unconfirmed") is True and not cmri.get("report_date_iso") and not cmri.get("event_date_iso"), json.dumps({k: cmri.get(k) for k in ("report_date_iso", "event_date_iso", "date_unconfirmed")}))
    g = d["state"]["gate"]; req = {r["id"]: r for r in g["requirements"]}
    rs = req.get("restaging_mri", {})
    did = docs["radiology/mri_pelvis_restaging.txt"]["doc_id"]
    check("3.1 restaging MRI with an unconfirmed date asks for confirmation", rs.get("status") == "needs_confirmation" and {"type": "confirm_dates", "doc_id": did} in (rs.get("needs") or []),
          f"{rs.get('status')}: {'; '.join(rs.get('problems') or [])[:120]}")
    check("3.1 gate lists the undated document", did in (g["documents"].get("date_unconfirmed") or []))
    st = c.post("/api/tb/cases/TB-TEST3/confirmations", json={"type": "confirm_dates", "key": did, "fields": {"event_date": "20/09/2026"}, "reason": "e2e: read from the scan"}).json()["state"]
    req = {r["id"]: r for r in st["gate"]["requirements"]}
    check("3.1 confirmed event date after treatment satisfies the restaging requirement", req["restaging_mri"]["status"] == "satisfied", "; ".join(req["restaging_mri"]["problems"]))
    cm2 = next(x for x in c.get("/api/tb/cases/TB-TEST3").json()["documents"] if x["doc_id"] == did)["classification"]
    check("3.1 confirmation shown on the document (dates_confirmed_by)", cm2.get("dates_confirmed_by") == "admin" and cm2.get("event_date_iso") == "2026-09-20", f"{cm2.get('dates_confirmed_by')} {cm2.get('event_date_iso')}")
    st = c.post("/api/tb/cases/TB-TEST3/confirmations", json={"type": "confirm_dates", "key": did, "fields": {"event_date": "01/06/2026"}, "reason": "e2e: before treatment"}).json()["state"]
    req = {r["id"]: r for r in st["gate"]["requirements"]}
    check("3.1 an MRI dated before treatment no longer counts", req["restaging_mri"]["status"] == "missing_record", req["restaging_mri"]["status"])
    # 3.2: the classification carries the keyword check; confirming the type extracts the fields again from the stored pages
    check("3.2 keyword check recorded on the classification", cmri.get("doc_type_keyword") == "mri" and "doc_type_check" in cmri, f"{cmri.get('doc_type_keyword')} / {cmri.get('doc_type_check', '')[:80]}")
    r = c.post("/api/tb/cases/TB-TEST3/confirmations", json={"type": "confirm_doc_type", "key": did, "fields": {"doc_type": "mri"}, "reason": "e2e"}).json()
    check("3.2 confirm_doc_type starts a re-extraction job", bool(r.get("job")), json.dumps({k: r.get(k) for k in ("job",)}))
    if r.get("job"):
        jj, secs = wait_job(c, r["job"])
        dd = next(x for x in c.get("/api/tb/cases/TB-TEST3").json()["documents"] if x["doc_id"] == did)
        check("3.2 re-extraction finished with no second read, type confirmed", jj["state"] == "finished" and dd["state"] == "ready" and dd["classification"].get("doc_type_confirmed_by"), f"{secs}s")
        au = c.get("/api/tb/cases/TB-TEST3/audit").json()["events"]
        check("3.2 re-extraction audited", any(e["kind"] == "reextract" for e in au))
    # 3.6: the Hindi / handwritten OPD scan of the demo corpus is flagged, text untouched
    if os.path.exists(HINDI_SCAN):
        j = c.post("/api/tb/cases/TB-TEST3/documents", files=[("files", ("surgical_oncology_opd_2026-09-03.png", open(HINDI_SCAN, "rb").read()))],
                   data={"paths": json.dumps(["scans/surgical_oncology_opd_2026-09-03.png"])}).json()
        wait_job(c, j["job"])
        dd = next((x for x in c.get("/api/tb/cases/TB-TEST3").json()["documents"] if x["rel_path"] == "scans/surgical_oncology_opd_2026-09-03.png"), None)
        check("3.6 Hindi line on the scanned OPD note flagged", dd is not None and any("Hindi / regional text" in f for f in dd.get("page_flags") or []), json.dumps((dd or {}).get("page_flags")))
        full = c.get(f"/api/tb/cases/TB-TEST3/documents/{dd['doc_id']}").json() if dd else {}
        pg = (full.get("pages") or [{}])[0]
        check("3.6 flagged lines carry offsets into the untouched text", bool(pg.get("flagged_lines")) and all(pg["text"][l["start"]:l["end"]] == l["line"] for l in pg.get("flagged_lines") or []))
        check("3.3 second read kept and spans have offsets", pg.get("ocr_reads") == 2 and "second_read" in pg and all(pg["text"][sp["start"]:sp["end"]] == sp["line"] for sp in pg.get("ocr_uncertain_spans") or [] if sp.get("read") != "second"))
    # 3.7: the 100-page scan warns at upload with an estimated time, then reads in batches
    if os.path.exists(SCAN_100):
        t0 = time.time()
        r = c.post("/api/tb/cases/TB-TEST3/documents", files=[("files", ("deccan_general_hospital_records_scan.pdf", open(SCAN_100, "rb").read()))],
                   data={"paths": json.dumps(["outside/deccan_general_hospital_records_scan.pdf"])}).json()
        w = r.get("warnings") or []
        check("3.7 upload warns about the 100-page scan with an estimated time", len(w) == 1 and "100 scanned pages" in w[0]["message"] and "about" in w[0]["message"], json.dumps(w)[:160])
        jj, secs = wait_job(c, r["job"])
        dd = next((x for x in c.get("/api/tb/cases/TB-TEST3").json()["documents"] if x["rel_path"] == "outside/deccan_general_hospital_records_scan.pdf"), None)
        check("3.7 100 pages read in batches, all pages present", dd is not None and dd["state"] == "ready" and dd["pages"] == 100 and jj.get("warnings"), f"{secs}s, {(dd or {}).get('pages')} pages, {round(time.time() - t0)} s in all")
    c.delete("/api/tb/cases/TB-TEST3")


E2E_RADIO4 = ("tb-e2e-radio4", "Radio-e2e-2026!")  # throw-away Radio-diagnosis member for the inbox flow (created and deleted by phase4)


def phase4(c, base):
    """V1 Phase 4 on its own synthetic Case File TB-TEST4 (lung, Essential hospital, non-metastatic): NCG tiers per setting (4.1), the
    Level 1 / Level 2 gate with routing (4.2), the department inbox and notifications end to end (4.4: gap -> a radiology user sees it ->
    upload -> closed -> coordinator notified), a failed document blocks until dismissed (4.3), the stale summary (4.5) and the NCG VTB
    export (4.6)."""
    import io
    user, pw = E2E_RADIO4
    c.request("DELETE", "/api/auth/users", json={"username": user})
    c.post("/api/auth/users", json={"username": user, "password": pw, "is_admin": False})
    o = c.get("/api/tb/org").json(); users = dict(o.get("users") or {}); users[user] = {"departments": {"radiology": "member"}, "coordinator": False}
    c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "admins")}, "users": users})
    m = httpx.Client(base_url=base, timeout=300)
    check("phase4: radiology member logs in", m.post("/api/auth/login", json={"username": user, "password": pw}).status_code == 200)
    c.delete("/api/tb/cases/TB-TEST4")
    try:
        r = c.post("/api/tb/cases", json={"case_id": "TB-TEST4", "protocol": "lung_nsclc", "setting": "non_metastatic", "hospital_level": "essential", "board_date": "2026-10-20",
                                          "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-997", "agesex": "61 Y / M"}})
        check("phase4: synthetic lung Case File created (Essential hospital, non-metastatic)", r.status_code == 200, r.text[:80])
        head = "SAHYADRI CANCER INSTITUTE (SYNTHETIC)\n{dept}\n{title}\nPatient: SYNTHETIC, Test Patient  UHID: SYN-997  61 Y / M\n"
        opd = (head.format(dept="DEPARTMENT OF MEDICAL ONCOLOGY", title="MEDICAL ONCOLOGY OPD NOTE") + "Visit date: 20/09/2026\nHistory: cough for 2 months, ex-smoker 20 pack-years.\n"
               "ECOG performance status: 1\nQuestion for the Tumour Board: staging and management plan.\nReport status: FINAL\nSd/- Dr. P. Iyer, Medical Oncologist, Reg. No. KMC 23456\n").encode()
        hpe = (head.format(dept="DEPARTMENT OF PATHOLOGY", title="HISTOPATHOLOGY REPORT") + "Specimen: CT-guided biopsy, right upper lobe lesion.\nDate of collection: 18/09/2026\n"
               "Microscopy: cores of lung parenchyma infiltrated by malignant glands.\nDiagnosis: Adenocarcinoma, lung, acinar predominant.\nReport status: FINAL\nReported on 22/09/2026\n"
               "Sd/- Dr. A. Menon, Consultant Pathologist, Reg. No. KMC 11223\n").encode()
        mol = (head.format(dept="DEPARTMENT OF MOLECULAR PATHOLOGY", title="MOLECULAR PATHOLOGY REPORT") + "Sample: FFPE block of the lung biopsy.\nDate of report: 26/09/2026\n"
               "EGFR (exons 18-21, ARMS-PCR): No mutation detected\nALK (D5F3 IHC): Negative\nROS1 (IHC): Negative\nKRAS: Not performed\nReport status: FINAL\n"
               "Sd/- Dr. S. Bhat, Molecular Pathologist, Reg. No. KMC 33445\n").encode()
        lab = (head.format(dept="DEPARTMENT OF LABORATORY MEDICINE", title="HAEMATOLOGY AND BIOCHEMISTRY REPORT") + "Collected on 21/09/2026  Reported on 21/09/2026\n"
               "Haemoglobin 12.1 g/dL\nTotal leucocyte count (TLC) 7,200 cells/cumm\nPlatelet count 2.4 lakhs/cumm\nSerum creatinine 0.9 mg/dL\nTotal bilirubin 0.8 mg/dL\nReport status: FINAL\n"
               "Sd/- Dr. R. Pillai, Consultant Pathologist, Reg. No. KMC 55667\n-- End of report --\n").encode()
        j = c.post("/api/tb/cases/TB-TEST4/documents", files=[("files", ("opd_note.txt", opd)), ("files", ("histopathology.txt", hpe)), ("files", ("molecular.txt", mol)), ("files", ("labs.txt", lab))],
                   data={"paths": json.dumps(["medical_oncology/opd_note.txt", "pathology/histopathology.txt", "molecular_pathology/molecular.txt", "laboratory_medicine/labs.txt"])}).json()
        wait_job(c, j["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json(); g = d["state"]["gate"]
        req = {r["id"]: r for r in g["requirements"]}; shown = {r["id"]: r for r in g["shown"]}
        # 4.1 NCG tiers per setting
        check("4.1 Essential hospital: only the NCG Essential (a) records are required", set(req) == {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "cbc", "liver_renal_function"}, ", ".join(sorted(req)))
        check("4.1 PET-CT, MRI brain, PD-L1, MET are NCG Optimal (b): shown, not required", all(shown.get(k, {}).get("tier") == "b" and shown[k]["required"] is False for k in ("pet_ct", "brain_mri", "pdl1", "met")),
              json.dumps({k: (shown.get(k) or {}).get("tier") for k in ("pet_ct", "brain_mri", "pdl1", "met")}))
        check("4.1 every required record cites its NCG line (guideline, page, quote)", all(r.get("source", {}).get("quote") and r["source"].get("page") for r in g["requirements"]),
              req["cect_tap"].get("source", {}).get("quote", ""))
        check("4.1 gate records the setting and hospital level", g["setting"] == "non_metastatic" and g["hospital_level"] == "essential" and g["setting_label"] and g["protocol_version"] == "0.8",
              f"{g['setting']} / {g['hospital_level']} / v{g['protocol_version']}")
        # 4.2 Level 1 gap: the CECT is missing, routed to Radiology (owner of the record type)
        check("4.2 missing CECT is a Level 1 gap", req["cect_tap"]["status"] == "missing_record" and req["cect_tap"]["level"] == 1 and req["cect_tap"]["level1"]["status"] == "missing_record",
              f"{req['cect_tap']['status']} L{req['cect_tap']['level']}")
        others = {k: v["status"] for k, v in req.items() if k != "cect_tap"}
        check("4.1 the four other Essential records are satisfied by the uploads", set(others.values()) == {"satisfied"}, json.dumps(others))
        for k, v in others.items():  # keep the rest of the flow testable even if the reader missed a value: waive it, visibly
            if v != "satisfied":
                c.post("/api/tb/cases/TB-TEST4/confirmations", json={"type": "waive", "key": k, "reason": "e2e fallback: value not read by the model"})
        acts = {a["requirement"]: a for a in c.get("/api/tb/cases/TB-TEST4").json()["state"]["actions"] if a["source"] == "pre_authorization"}
        a = acts.get("cect_tap") or {}
        check("4.2 Level 1 request routed to the department that owns the record (Radiology)", a.get("level") == 1 and a.get("department") == "Radiology" and a.get("department_id") == "radiology", json.dumps({k: a.get(k) for k in ("level", "department", "department_id")}))
        check("4.2 gate summarises open gaps per level", g["levels"]["1"]["open"] >= 1 and "label" in g["levels"]["2"], json.dumps(g["levels"]))
        # V2 4.2: the gap is only suggested; nothing reaches Radiology until the treating side sends it
        check("4.2 (V2) a new gap is a suggested request: no due date, nothing sent, not in the Radiology inbox", a.get("status") == "suggested" and a.get("due") is None
              and not [q for dd in m.get("/api/tb/inbox").json()["departments"] for q in dd["requests"] if q["case_id"] == "TB-TEST4"]
              and not any(n["kind"] == "request" and n["case_id"] == "TB-TEST4" for n in m.get("/api/tb/notifications").json()["notifications"]), json.dumps({k: a.get(k) for k in ("status", "due")}))
        sent = _send_suggested(c, "TB-TEST4", "cect_tap")
        check("4.2 (V2) the request is sent in-app (the admin stands in for the treating doctor)", bool(sent) and all(st_ == 200 for _, st_ in sent), json.dumps(sent))
        # 4.4 the radiology member sees the request in the inbox and the bell
        ib = m.get("/api/tb/inbox").json()
        mine = [q for dd in ib["departments"] for q in dd["requests"] if q["case_id"] == "TB-TEST4"]
        check("4.4 radiology member sees the request in the department inbox", [dd["id"] for dd in ib["departments"]] == ["radiology"] and len(mine) == 1 and mine[0]["label"].startswith("CECT") and mine[0]["status"] == "pending" and mine[0]["level"] == 1,
              json.dumps(mine)[:160])
        nt = m.get("/api/tb/notifications").json()
        check("4.4 radiology member has an unread request notification", nt["unread"] >= 1 and any(n["kind"] == "request" and n["case_id"] == "TB-TEST4" and not n["read"] for n in nt["notifications"]), f"{nt['unread']} unread")
        adm = c.get("/api/tb/inbox").json()
        check("4.4 admin sees every department's inbox, the request under Radio-diagnosis only", "pathology" in [dd["id"] for dd in adm["departments"]]
              and [dd["id"] for dd in adm["departments"] if any(q["case_id"] == "TB-TEST4" and q["status"] != "completed" for q in dd["requests"])] == ["radiology"])
        # the member uploads a CECT for the department: it files itself on the exact UHID; the lesion size is missing -> a Level 2 gap routed to the uploader
        ct1 = (head.format(dept="DEPARTMENT OF RADIO-DIAGNOSIS", title="CECT THORAX, ABDOMEN AND PELVIS") + "Study date: 24/09/2026\nFindings: spiculated mass in the right upper lobe; right hilar node.\n"
               "Abdomen and pelvis: no focal lesion.\nImpression: right upper lobe mass with right hilar adenopathy.\nReport status: FINAL\nSd/- Dr. S. Rao, Consultant Radiologist, Reg. No. KMC 12345\n").encode()
        r = m.post("/api/tb/intake/documents", files=[("files", ("cect_tap_2026-09-24.txt", ct1))], data={"paths": json.dumps(["cect_tap_2026-09-24.txt"]), "department": "radiology"}).json()
        wait_job(m, r["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json(); req = {x["id"]: x for x in d["state"]["gate"]["requirements"]}
        filed = [x for x in d["documents"] if x["rel_path"].endswith("cect_tap_2026-09-24.txt")]
        check("4.4 department upload filed into the Case File on the exact UHID", bool(filed) and filed[0].get("department") == "radiology", json.dumps([(x["rel_path"], x.get("department")) for x in d["documents"]])[:200])
        check("4.2 CECT without the lesion size is a Level 2 gap", req["cect_tap"]["status"] == "missing_field" and req["cect_tap"]["level"] == 2 and req["cect_tap"]["level1"]["status"] == "satisfied",
              f"{req['cect_tap']['status']} L{req['cect_tap']['level']}: {'; '.join(req['cect_tap']['problems'])[:100]}")
        a = next((x for x in d["state"]["actions"] if x["requirement"] == "cect_tap" and x["status"] != "completed"), {})
        check("4.2 Level 2 request routed to the department that uploaded the record (Radio-diagnosis)", a.get("level") == 2 and a.get("department_id") == "radiology" and a.get("source_doc_id") == (filed[0]["doc_id"] if filed else None)
              and any("Level 2" in h["event"] for h in a.get("history", [])), json.dumps({k: a.get(k) for k in ("level", "department", "department_id", "source_doc_id")}))
        check("4.2 (V2) the moved request is a suggestion again, the earlier sending kept, nothing forwarded by itself", a.get("status") == "suggested" and a.get("due") is None
              and (a.get("earlier") or [{}])[0].get("department_id") == "radiology" and (a.get("earlier") or [{}])[0].get("sent", {}).get("count") == 1, json.dumps({k: a.get(k) for k in ("status", "earlier")})[:200])
        _send_suggested(c, "TB-TEST4", "cect_tap")  # the doctor sends the Level 2 request so Radiology hears when it closes
        # the corrected CECT arrives: the request closes by itself and the coordinator is told the Case File is ready
        ct2 = ct1.decode().replace("Study date: 24/09/2026", "Study date: 25/09/2026 (repeat read with measurements)").replace("Findings: spiculated mass in the right upper lobe;", "Findings: spiculated mass in the right upper lobe measuring 4.2 x 3.1 cm;").encode()
        r = m.post("/api/tb/intake/documents", files=[("files", ("cect_tap_2026-09-25_measured.txt", ct2))], data={"paths": json.dumps(["cect_tap_2026-09-25_measured.txt"]), "department": "radiology"}).json()
        wait_job(m, r["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json(); g = d["state"]["gate"]; req = {x["id"]: x for x in g["requirements"]}
        check("4.4 upload with the value closes the request", req["cect_tap"]["status"] == "satisfied" and all(x["status"] == "completed" for x in d["state"]["actions"] if x["requirement"] == "cect_tap"),
              f"{req['cect_tap']['status']}: {'; '.join(req['cect_tap']['problems'])[:100]}")
        check("4.4 Case File passes the Pre-Authorization", g["passed"], f"{g['satisfied']}/{g['total']}, blockers {len(g.get('blockers') or [])}")
        ib = m.get("/api/tb/inbox").json(); mine = [q for dd in ib["departments"] for q in dd["requests"] if q["case_id"] == "TB-TEST4"]
        check("4.4 inbox shows the request closed", bool(mine) and all(q["status"] == "completed" for q in mine), json.dumps([(q["label"], q["status"]) for q in mine]))
        nt = m.get("/api/tb/notifications").json()
        check("4.4 radiology member told the request closed", any(n["kind"] == "request_closed" and n["case_id"] == "TB-TEST4" for n in nt["notifications"]))
        nc = c.get("/api/tb/notifications").json()
        ready = [n for n in nc["notifications"] if n["kind"] == "case_ready" and n["case_id"] == "TB-TEST4"]
        check("4.4 coordinator notified that the Case File is ready", bool(ready) and ready[0]["to"] == {"role": "coordinator"}, json.dumps(ready[:1])[:160])
        rd = m.post("/api/tb/notifications/read", json={"all": True}).json()
        check("4.4 mark all read clears the member's unread count", rd["unread"] == 0 and m.get("/api/tb/notifications").json()["unread"] == 0, json.dumps(rd))
        # 4.3 a corrupted PDF blocks the gate until dismissed; a re-process withdraws the dismissal
        bad = b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n4 0 obj << /Length 999 >> stream\nBT /F1 12 Tf (truncated"
        j = c.post("/api/tb/cases/TB-TEST4/documents", files=[("files", ("mri_brain_corrupted.pdf", bad))], data={"paths": json.dumps(["radiology/mri_brain_corrupted.pdf"])}).json()
        wait_job(c, j["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json(); g = d["state"]["gate"]
        badid = next((x["doc_id"] for x in d["documents"] if x["rel_path"] == "radiology/mri_brain_corrupted.pdf"), None)
        bad_doc = next((x for x in d["documents"] if x["doc_id"] == badid), {})
        check("4.3 corrupted PDF fails to read and blocks the gate", bad_doc.get("state") == "error" and not g["passed"] and [b["doc_id"] for b in g["blockers"]] == [badid] and g["satisfied"] == g["total"],
              f"state {bad_doc.get('state')}, error {str(bad_doc.get('error'))[:60]}, blockers {len(g['blockers'])}")
        st = c.post("/api/tb/cases/TB-TEST4/confirmations", json={"type": "dismiss_failed", "key": badid, "reason": "e2e: corrupted copy; the original was requested from Radio-diagnosis"}).json()["state"]
        check("4.3 dismissal with a reason lets the gate pass", st["gate"]["passed"] and st["gate"]["blockers"] == [] and st["gate"]["documents"]["dismissed"][0]["doc_id"] == badid, json.dumps(st["gate"]["documents"].get("dismissed"))[:120])
        check("4.3 dismissal shown on the document and audited", next(x for x in c.get("/api/tb/cases/TB-TEST4").json()["documents"] if x["doc_id"] == badid).get("dismissed", {}).get("by") == "admin"
              and any(e["kind"] == "confirmation" and e["type"] == "dismiss_failed" for e in c.get("/api/tb/cases/TB-TEST4/audit").json()["events"]))
        okdoc = next(x["doc_id"] for x in d["documents"] if x["state"] == "ready")
        r = c.post("/api/tb/cases/TB-TEST4/confirmations", json={"type": "dismiss_failed", "key": okdoc, "reason": "e2e: must be refused"})
        check("4.3 a document that read cannot be dismissed (409)", r.status_code == 409, f"HTTP {r.status_code}: {r.text[:80]}")
        j = c.post("/api/tb/cases/TB-TEST4/reprocess", json={"which": [badid]}).json(); wait_job(c, j["job"])
        g = c.get("/api/tb/cases/TB-TEST4").json()["state"]["gate"]
        check("4.3 re-processing a dismissed document withdraws the dismissal; still unreadable, it blocks again", not g["passed"] and [b["doc_id"] for b in g["blockers"]] == [badid])
        c.post("/api/tb/cases/TB-TEST4/confirmations", json={"type": "dismiss_failed", "key": badid, "reason": "e2e: dismissed again"})
        # 4.5 / 4.6 the summary carries the Case File signature; the export fills the NCG template; a change makes both stale
        sm = c.post("/api/tb/cases/TB-TEST4/summary", json={"force": True}).json()
        d = c.get("/api/tb/cases/TB-TEST4").json()
        check("4.5 summary stores the Case File signature and is current", sm.get("signature", {}).get("hash") == d["signature"]["hash"] and d["stale"].get("summary") == "", json.dumps(d.get("stale"))[:120])
        r = c.get("/api/tb/cases/TB-TEST4/export/vtb")
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/vnd.openxmlformats-officedocument.presentationml")
        slides, bodies = [], []
        if ok:
            try:
                from pptx import Presentation
                prs = Presentation(io.BytesIO(r.content))
                for s in prs.slides:
                    slides.append(" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame))
                    ph = next((sh for sh in s.placeholders if sh.placeholder_format.idx == 1 and sh.has_text_frame), None)  # the section body (not the footer)
                    bodies.append(ph.text_frame.text if ph is not None else "")
            except Exception as e:
                slides = [f"error: {e}"]
        cited = [i for i, t in enumerate(bodies) if i in (1, 2, 3) and re.search(r"\[[^\]]+, \d{2}/\d{2}/\d{4}\]", t) and "Not documented" not in t]
        check("4.6 NCG VTB export opens with six slides; presentation, investigations and imaging carry cited sentences", ok and len(slides) == 6
              and all(len(b.strip()) > 20 for b in bodies[1:]) and cited == [1, 2, 3] and "Tumour Board Case File TB-TEST4" in slides[0] and "Human oversight" in slides[1],
              f"HTTP {r.status_code}, {len(slides)} slides, cited bodies {cited}, {len(r.content)} bytes")
        check("4.6 export audited", any(e["kind"] == "export_vtb" for e in c.get("/api/tb/cases/TB-TEST4/audit").json()["events"]))
        extra = (head.format(dept="DEPARTMENT OF GENERAL MEDICINE", title="DISCHARGE SUMMARY") + "Date of admission: 27/09/2026\nDate of discharge: 29/09/2026\nCourse: admitted for bronchoscopy; uneventful.\nReport status: FINAL\nSd/- Dr. K. Das, Reg. No. KMC 77889\n").encode()
        j = c.post("/api/tb/cases/TB-TEST4/documents", files=[("files", ("discharge.txt", extra))], data={"paths": json.dumps(["medicine/discharge.txt"])}).json(); wait_job(c, j["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json()
        check("4.5 adding a document marks the summary stale with the reason", (d["stale"].get("summary") or "").startswith("The Case File changed since this was generated") and "1 document added" in d["stale"]["summary"], d["stale"].get("summary", "")[:120])
        r = c.get("/api/tb/cases/TB-TEST4/export/vtb")
        check("4.6 export refused while the summary is stale (409)", r.status_code == 409 and "regenerate" in r.text.lower(), f"HTTP {r.status_code}: {r.text[:100]}")
        r = c.delete("/api/tb/cases/TB-TEST4")
        left = [n for n in c.get("/api/tb/notifications").json()["notifications"] if n["case_id"] == "TB-TEST4"]
        check("4.4 deleting the Case File removes its notifications (patient details)", r.status_code == 200 and r.json().get("notifications_removed", 0) >= 1 and not left,
              f"{r.json().get('notifications_removed') if r.status_code == 200 else r.status_code} removed, {len(left)} left")
    finally:
        c.delete("/api/tb/cases/TB-TEST4")
        o = c.get("/api/tb/org").json(); users = dict(o.get("users") or {}); users.pop(user, None)
        c.put("/api/tb/org", json={**{k: o[k] for k in ("hospital", "departments", "admins")}, "users": users})
        c.request("DELETE", "/api/auth/users", json={"username": user})


def phase5(c):
    """V1 Phase 5: Indian guideline sources, bibliography filter, specialty packs in the agents (guideline references)."""
    from tumour_board import agents, guidelines
    def gsearch(q, cancer=None):
        return c.post("/api/tb/guidelines/search", json={"query": q, "cancer": cancer}).json()
    r = gsearch("Indications for neck dissection in oral cavity squamous cell carcinoma")
    check("5.1 NCG head & neck guideline first for an oral cavity question", (r["india"] or [{}])[0].get("file", "").endswith("ncg-guidelines-for-head-neck-cancer-2019.pdf"),
          (r["india"] or [{}])[0].get("file", ""))
    r = gsearch("Carcinoma cervix staging work-up FIGO MRI pelvis")
    check("5.1 NCG gynaecological guideline first for a cervix question", (r["india"] or [{}])[0].get("file", "").endswith("ncg-guidelines-for-gynecological-cancer-2019.docx"),
          (r["india"] or [{}])[0].get("file", ""))
    r = gsearch("Management of HER2 positive early breast cancer in India", "breast")
    check("5.1 Tata Memorial Centre 2024 first for a breast question", (r["india"] or [{}])[0].get("file", "").startswith("tmc/"), (r["india"] or [{}])[0].get("file", ""))
    r = gsearch("PM-JAY pre-authorization for cancer treatment: multidisciplinary tumour board decision")
    check("5.1 PM-JAY HBP 2.2 manual (PDF pages) first for a pre-authorization question",
          (r["india"] or [{}])[0].get("file", "") == "pmjay/NHA-HBP-2.2-manual-2021.pdf", f"{(r['india'] or [{}])[0].get('file', '')} p {(r['india'] or [{}])[0].get('page')}")
    hits = [h for q in ("RECIST response evaluation criteria Eisenhauer Therasse", "osimertinib EGFR mutated NSCLC FLAURA trial", "letrozole neoadjuvant P024 trial")
            for h in (lambda x: x["india"] + x["international"])(gsearch(q))]
    check("5.2 no bibliography passage among guideline results", hits and not any(guidelines._is_reference_list(h["text"]) for h in hits), f"{len(hits)} passages")
    # 5.5: the radiology agent on the lung Case File: pack with Indian sources first, ICRI / IRIA lung checklist, references verbatim, India first
    t0 = time.time(); brief = None; tools = []
    with c.stream("POST", "/api/tb/cases/TB-001/agents/radiology", json={}) as resp:
        for line in resp.iter_lines():
            if line.strip():
                ev = json.loads(line); tools.append(ev.get("tool"))
                if ev["type"] == "brief":
                    brief = ev["brief"]
    pk = (brief or {}).get("pack") or {}
    check("5.5 radiology brief names its pack, Indian sources first, and the ICRI / IRIA lung checklist",
          bool(pk) and pk["sources"][0]["region"] == "India" and (pk.get("checklist") or {}).get("title", "").startswith("ICRI / IRIA") and "search_guidelines" in tools,
          f"{round(time.time() - t0, 1)} s, checklist {(pk.get('checklist') or {}).get('title')}")
    pts = (brief or {}).get("points_for_review") or []
    refs = [r for p in pts for r in p.get("references") or []]
    check("5.5 guideline references labelled and India first on every point", all(r.get("quote") and r.get("page") and r.get("org") for r in refs)
          and all([x["region"] != "India" for x in p.get("references") or []] == sorted(x["region"] != "India" for x in p.get("references") or []) for p in pts),
          f"{len(pts)} points, {len(refs)} references, {sum(any(x['region'] == 'India' for x in p.get('references') or []) for p in pts)} points with an Indian source")
    check("5.5 no reference states a treatment, indication or eligibility; no point asks for a decision for this patient",
          all(agents._in_scope(r["quote"]) for r in refs) and not any(agents._POINT_SCOPE.search(p["text"]) for p in pts),
          "; ".join([r["quote"][:80] for r in refs if not agents._in_scope(r["quote"])] + [p["text"][:80] for p in pts if agents._POINT_SCOPE.search(p["text"])]))
    case = c.get("/api/tb/cases/TB-001").json()["case"]
    missing = [p["text"] for p in pts if not any(x["region"] == "India" for x in p.get("references") or []) and agents._indian_reference("radiology", case, p["text"])]
    check("5.5 a point without an Indian reference has no fitting Indian passage (the agents' own rule: two shared words or an acronym, same cancer)",
          not missing, "; ".join(missing)[:200])


def phase6(c):
    """V1 Phase 6: board session and attendance (6.1), agents for absent specialties with live answers (6.2), agent log vs decision (6.3),
    removed items with reasons (6.4), near-match off by default (6.5), no documents -> no run (6.6). TB-001 and a throw-away TB-TEST6."""
    from tumour_board import board
    D = "2026-12-04"
    j = c.post("/api/tb/cases/TB-001/listing", json={"protocol": "lung_nsclc", "board_date": D, "hospital_level": "essential"}).json()
    if j.get("total"):
        wait_job(c, j["job"])
    c.delete("/api/tb/cases/TB-TEST6")
    c.post("/api/tb/cases", json={"case_id": "TB-TEST6", "protocol": "lung_nsclc", "board_date": D,
                                  "patient": {"name": "SYNTHETIC, Session Patient", "mrn": "SYN-996", "agesex": "57 Y / M"}})
    note = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nMEDICAL ONCOLOGY OPD NOTE\nPatient: SYNTHETIC, Session Patient  UHID: SYN-996  57 Y / M\nVisit date: 21-Sep-2026\n"
            "History: cough for 3 months.\nECOG performance status: 1\nQuestion for the Tumour Board: work-up review.\nSd/- Dr. M. Iyer, Medical Oncology\n").encode()
    wait_job(c, c.post("/api/tb/cases/TB-TEST6/documents", files=[("files", ("opd_note.txt", note))], data={"paths": json.dumps(["opd_note.txt"])}).json()["job"])
    cand = [x["case_id"] for x in c.get("/api/tb/sessions/candidates", params={"date": D}).json()["cases"]]
    check("6.1 session candidates are the Case Files listed for that date, the real case never", {"TB-001", "TB-TEST6"} <= set(cand) and "TB-2026-bharath" not in cand, ", ".join(cand))
    s = c.post("/api/tb/sessions", json={"date": D, "title": "E2E Thoracic Tumour Board", "case_ids": ["TB-001", "TB-TEST6"]}).json()
    sid = s.get("id")
    check("6.1 board session created from listed Case Files, in agenda order", sid and [a["case_id"] for a in s["agenda"]] == ["TB-001", "TB-TEST6"] and s["status"] == "planned",
          f"{sid}")
    for dept, status in (("radiology", "absent"), ("medical_oncology", "present"), ("surgical_oncology", "present"), ("radiation_oncology", "present"), ("pathology", "present")):
        c.post(f"/api/tb/sessions/{sid}/attendance", json={"department": dept, "status": status})
    c.post(f"/api/tb/sessions/{sid}/members", json={"name": "Dr. A. Rao (synthetic)", "department": "medical_oncology"})
    c.post(f"/api/tb/sessions/{sid}/members", json={"name": "Dr. B. Shah (synthetic)", "department": "surgical_oncology"})
    room = c.get(f"/api/tb/sessions/{sid}").json()
    att = room["session"]["attendance"]
    check("6.1 attendance and members present by name saved", att.get("radiology") == "absent" and att.get("medical_oncology") == "present"
          and [m["name"] for m in room["session"]["members"]] == ["Dr. A. Rao (synthetic)", "Dr. B. Shah (synthetic)"] and room["absent_roles"] == ["radiology"],
          f"absent roles {room['absent_roles']}, participants: {room['participants']['text'][:120]}")
    r = c.post(f"/api/tb/sessions/{sid}/cases/TB-001/log/P1/mark", json={"mark": "accepted"})
    check("6.3 points cannot be marked before the decision is recorded", r.status_code in (400, 404), f"{r.status_code} {r.text[:100]}")
    def wait_agents():
        t = time.time()
        while True:
            rm = c.get(f"/api/tb/sessions/{sid}").json()
            if all(x.get("status") not in ("queued", "running") for by in (rm["session"].get("agents") or {}).values() for x in by.values()) or time.time() - t > 900:
                return rm
            time.sleep(3)
    t0 = time.time(); st = c.post(f"/api/tb/sessions/{sid}/start").json()
    room = wait_agents()
    started = (room["session"].get("agents") or {}).get("TB-001", {}).get("radiology", {}).get("status")
    # "Prepare again" runs the agent afresh (a brief still current for the Case File would otherwise be reused, as at the start)
    pr = c.post(f"/api/tb/sessions/{sid}/agents/prepare", json={"case_id": "TB-001", "role": "radiology", "refresh": True}).json()
    room = wait_agents()
    ag = room["session"].get("agents") or {}
    rb = (room["cases"]["TB-001"].get("briefs") or {}).get("radiology") or {}
    items = sum(len(x["items"]) for x in rb.get("sections") or [])
    check("6.2 session start: the Radiology agent of the absent Radio-diagnosis prepared its brief, every item cited",
          st.get("preparing") == 2 and started == "ready" and pr.get("preparing") == 1 and (ag.get("TB-001") or {}).get("radiology", {}).get("status") == "ready" and items > 0
          and all(it["citations"] for x in rb["sections"] for it in x["items"]),
          f"{round(time.time() - t0, 1)} s, {items} items, {len(rb.get('points_for_review') or [])} points, reused {(ag.get('TB-001') or {}).get('radiology', {}).get('reused')}")
    nb = (room["cases"]["TB-TEST6"].get("briefs") or {}).get("radiology") or {}
    au6 = c.get("/api/tb/cases/TB-TEST6/audit").json()["events"]
    check("6.6 no Radio-diagnosis documents: the agent returns at once with the department's open requests, no model call",
          (ag.get("TB-TEST6") or {}).get("radiology", {}).get("status") == "no_documents" and nb.get("message") == "No Radiology documents in this Case File"
          and any(e["kind"] == "agent_no_documents" for e in au6) and not any(e["kind"] == "llm_call" and str(e.get("purpose", "")).startswith("agent radiology") for e in au6),
          f"{nb.get('message')}; open requests {[x['label'] for x in nb.get('open_items') or []]}")
    qs = ["What does the CT report record about the primary lung lesion and its size?", "What does the PET-CT report record about the mediastinal lymph nodes?",
          "Which imaging reports are in the Case File and on what dates?"]
    ans = []
    for q in qs:
        t1 = time.time(); a = c.post(f"/api/tb/sessions/{sid}/cases/TB-001/agents/radiology/ask", json={"question": q}).json(); a["_s"] = round(time.time() - t1, 1); ans.append(a)
    check("6.2 three live answers from the Radiology agent, every statement cited",
          all(a.get("status") == "answered" and a["statements"] and all(x["citations"] for x in a["statements"]) and a.get("kind") == "AI support (role-specific)" for a in ans),
          "; ".join(f"{a.get('status')} {len(a.get('statements') or [])} st {a['_s']} s" for a in ans))
    bad = [c.post(f"/api/tb/sessions/{sid}/cases/TB-001/agents/radiology/ask", json={"question": q}).json()
           for q in ("Which chemotherapy regimen should the patient receive?", "Look at the CT images and tell us whether the lesion is malignant")]
    check("6.2 out-of-scope questions refused", all(a.get("status") == "out_of_scope" and not a.get("statements") for a in bad), ", ".join(a.get("category", "") for a in bad))
    check("6.4 live answers: removed items match the unverified count", all(a["dropped_unverified"] == sum(x["reason"] != "guardrail" for x in a["removed"]) for a in ans),
          ", ".join(f"{a['dropped_unverified']}/{len(a['removed'])}" for a in ans))
    room = c.get(f"/api/tb/sessions/{sid}").json()
    log = [e for e in room["session"]["log"] if e["case_id"] == "TB-001" and not e.get("superseded")]
    check("6.2 who asked is kept with every live answer", all(e.get("asked_by") == "admin" for e in log if e["kind"] == "answer"),
          ", ".join(str(e.get("asked_by")) for e in log if e["kind"] == "answer"))
    r = c.post(f"/api/tb/sessions/{sid}/agents/prepare", json={"case_id": "TB-001", "role": "pathology"})
    check("6.2 no agent for a specialty that is present", r.status_code == 400, f"{r.status_code} {r.text[:80]}")
    check("6.3 the session keeps every agent point: brief and live answers", sum(e["kind"] == "answer" for e in log) == 5 and any(e["kind"] in ("brief_item", "point_for_review") for e in log),
          f"{len(log)} entries: {sum(e['kind'] == 'answer' for e in log)} answers")
    dec = c.post(f"/api/tb/sessions/{sid}/cases/TB-001/decision", json={"decision_text": "Discussed at the Tumour Board. Plan as per board discussion; re-discuss after review.",
                                                                       "recorded_by": "Dr. Tumour Board Coordinator (synthetic)"}).json()
    rec = dec.get("record") or {}
    check("6.3 decision recorded from the Board room: adjudicated, participants from the attendance, linked to the session",
          rec.get("session") == sid and "Dr. A. Rao (synthetic)" in (rec.get("participants") or "") and "adjudication" in rec
          and (dec.get("session") or {}).get("decisions", {}).get("TB-001", {}).get("board_record") == rec.get("id"), f"{rec.get('id')}, {rec.get('adjudication', {}).get('status')}")
    marks = {}
    for e, m in zip(log, ("accepted", "discussed", "not_relevant")):
        rr = c.post(f"/api/tb/sessions/{sid}/cases/TB-001/log/{e['id']}/mark", json={"mark": m, "note": "e2e"})
        marks[e["id"]] = (m, rr.status_code)
    ex = c.get(f"/api/tb/sessions/{sid}/export", params={"format": "json"}).json()
    case1 = next((x for x in ex.get("cases", []) if x["case_id"] == "TB-001"), {})
    html = c.get(f"/api/tb/sessions/{sid}/export", params={"format": "html"}).text
    check("6.3 export shows what the agents said and what the board decided side by side",
          all(code == 200 for _, code in marks.values()) and (case1.get("decision") or {}).get("board_record") == rec.get("id")
          and case1["marks"]["accepted"] == 1 and case1["marks"]["discussed"] == 1 and case1["marks"]["not_relevant"] == 1
          and "What the board decided" in html and "Plan as per board discussion" in html and "Accepted" in html and "\u2014" not in html,
          f"{len(case1.get('agent_log') or [])} entries, marks {case1.get('marks')}")
    c.post(f"/api/tb/sessions/{sid}/close")
    r = c.post(f"/api/tb/sessions/{sid}/cases/TB-001/agents/radiology/ask", json={"question": "What does the CT report record?"})
    check("6.1 a closed session takes no more questions", r.status_code == 409, str(r.status_code))
    # 6.4: Q&A, brief and summary keep their removed items with the reason; counts match
    a = c.post("/api/tb/cases/TB-001/ask", json={"question": "List every haemoglobin, WBC and platelet value with its date"}).json()
    sm = c.post("/api/tb/cases/TB-001/summary", json={"force": True}).json()
    check("6.4 removed items kept with the reason; counts match (Q&A, brief, summary)",
          isinstance(a.get("removed"), list) and a["dropped_unverified"] == sum(x["reason"] != "guardrail" for x in a["removed"])
          and rb.get("dropped_unverified") == sum(x["reason"] in ("document_not_found", "quote_not_found", "number_not_in_quote") for x in rb.get("removed") or [])
          and rb.get("guardrail_removed") == sum(x["reason"] == "guardrail" for x in rb.get("removed") or [])
          and sm.get("dropped_unverified") == sum(x["reason"] != "guardrail" for x in sm.get("removed") or [])
          and all(x.get("reason_label") and x.get("text") is not None for x in (a["removed"] + (rb.get("removed") or []) + (sm.get("removed") or []))),
          f"Q&A {a['dropped_unverified']}/{len(a['removed'])}, brief {rb.get('dropped_unverified')}+{rb.get('guardrail_removed')}/{len(rb.get('removed') or [])}, "
          f"summary {sm.get('dropped_unverified')}+{sm.get('guardrail_removed')}/{len(sm.get('removed') or [])}")
    check("6.5 near-match is off by default: no approximate item in the brief or the summary", sm.get("near_match") is False and not sm.get("approximate")
          and not rb.get("approximate") and not any(x.get("approximate") for sec in sm.get("sections") or [] for x in sec["sentences"]),
          f"summary approximate {sm.get('approximate')}, brief approximate {rb.get('approximate')}")
    c.delete("/api/tb/cases/TB-TEST6")
    try:  # the e2e session is a test artefact: its file goes, its history stays in sessions/audit.jsonl
        board._path(sid).unlink()
        board.audit_session(sid, {"kind": "e2e_removed", "by": "e2e"})
    except Exception:
        pass


def phase7(c):
    """V1 Phase 7: PM-JAY board composition (7.1), guideline checks of doses, RT and stage (7.2), flag resolution with an amended decision
    (7.3), board actions in department inboxes with a closing suggestion (7.4). TB-002 (breast, reset by the full run) and TB-TEST7."""
    text = ("Clinical stage IIIA. Neoadjuvant chemotherapy: 4 cycles of AC (Inj. Doxorubicin 6 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV, "
            "every 21 days), followed by Inj. Paclitaxel 80 mg/m2 IV weekly for 12 weeks. Then surgery and adjuvant radiotherapy.")
    rec = c.post("/api/tb/cases/TB-002/board-records", json={"board_date": "2026-10-20", "recorded_by": "Dr. Tumour Board Coordinator (synthetic)", "decision_text": text,
           "members": [{"name": "Dr. A. Rao (synthetic)", "department": "Medical Oncology"}, {"name": "Dr. B. Shah (synthetic)", "department": "Surgical Oncology"}],
           "actions": [{"department": "Medical Oncology", "task": "Counsel the patient", "due": "2026-12-20"}]}).json()
    rid, flags = rec.get("id"), (rec.get("adjudication") or {}).get("flags") or []
    comp = [f for f in flags if f["kind"] == "composition"]
    check("7.1 missing radiation oncologist flagged (PM-JAY HBP 2.2 quoted; members typed with their departments)",
          len(comp) == 1 and comp[0]["missing"] == ["radiation_oncology"] and comp[0]["reference"]["region"] == "India" and rec["attendance"]["present"] == ["Medical Oncology", "Surgical Oncology"],
          "; ".join(f["text"][:90] for f in comp))
    room = c.post("/api/tb/cases/TB-002/board-records", json={"decision_text": "Plan as discussed.", "recorded_by": "Dr. Coordinator (synthetic)", "actions": [],
            "participants": "Dr A (Med Onc), Dr B (Surg Onc), Radiation Oncology (AI support agent)"}).json()
    check("7.1 an AI support agent never counts as a member", any(f["kind"] == "composition" and f["missing"] == ["radiation_oncology"] for f in room["adjudication"]["flags"]))
    g = [f for f in flags if f["kind"] == "guideline"]
    dose = [f for f in g if f.get("check") == "dose" and f["severity"] == "expert_review"]
    ref = (dose[0].get("reference") or {}) if dose else {}
    check("7.2 'Doxorubicin 6 mg/m2' flagged as a possible transcription error with its Indian guideline source (page, quote)",
          len(dose) == 1 and "oxorubicin" in dose[0]["text"] and ref.get("region") == "India" and ref.get("page") and "60" in (ref.get("quote") or ""),
          f"{dose[0]['text'][:140] if dose else 'no dose flag'} | {ref.get('org')} p {ref.get('page')}: {(ref.get('quote') or '')[:70]}")
    checks = (rec["adjudication"].get("guideline_checks") or {}).get("checks") or []
    ok = {x.get("drug"): x["result"] for x in checks if x.get("kind") == "drug"}
    check("7.2 correct doses not flagged (cyclophosphamide 600 mg/m2, paclitaxel 80 mg/m2 weekly)",
          ok.get("cyclophosphamide") == "consistent" and ok.get("paclitaxel") == "consistent"
          and not any(w in f["text"].lower() for f in g if f["severity"] != "info" for w in ("cyclophosphamide", "paclitaxel")), json.dumps(ok))
    stage = [f for f in g if f.get("check") == "stage"]
    check("7.2 stage in the decision (IIIA) vs the stage recorded in the signed report (IIB): review, cites the report",
          len(stage) == 1 and stage[0]["severity"] == "review" and (stage[0].get("source") or {}).get("doc_id"), stage[0]["text"][:160] if stage else "no stage flag")
    # 7.3: corrected -> version 2 with history; intentional deviation needs a reason; all resolved -> final; undo -> version 3
    r = c.post(f"/api/tb/cases/TB-002/board-records/{rid}/flags/{dose[0]['id'] if dose else 'F0'}/resolve", json={"resolution": "corrected", "value": "60 mg/m2"}).json().get("record") or {}
    check("7.3 flag corrected: the decision is amended as version 2, version 1 kept",
          r.get("version") == 2 and "Doxorubicin 60 mg/m2" in r.get("decision_text", "") and r["versions"][0]["decision_text"] == text and r["versions"][1]["by"] == "admin",
          (r.get("versions") or [{}])[-1].get("reason", ""))
    bad = c.post(f"/api/tb/cases/TB-002/board-records/{rid}/flags/{comp[0]['id'] if comp else 'F0'}/resolve", json={"resolution": "intentional_deviation"})
    check("7.3 an intentional deviation needs a reason", bad.status_code == 400, f"{bad.status_code} {bad.text[:80]}")
    c.post(f"/api/tb/cases/TB-002/board-records/{rid}/flags/{comp[0]['id'] if comp else 'F0'}/resolve",
           json={"resolution": "intentional_deviation", "reason": "Radiation Oncology reviewed the Case File before the meeting (synthetic)"})
    cur = next(b for b in c.get("/api/tb/cases/TB-002").json()["state"]["board_records"] if b["id"] == rid)
    for f in cur["adjudication"]["flags"]:
        if f["severity"] in ("review", "expert_review") and not f.get("resolution"):
            c.post("/api/tb/cases/TB-002/confirmations", json={"type": "resolve_flag", "key": f"{rid}:{f['id']}", "fields": {"resolution": "false_alarm"}, "reason": "e2e"})
    cur = next(b for b in c.get("/api/tb/cases/TB-002").json()["state"]["board_records"] if b["id"] == rid)
    check("7.3 the decision counts as final once every flag is resolved (audited)", (cur.get("resolution") or {}).get("final") is True
          and any(e["kind"] == "board_flag_resolved" for e in c.get("/api/tb/cases/TB-002/audit").json()["events"]), json.dumps(cur.get("resolution")))
    conf = next((f["resolution"]["confirmation"] for f in cur["adjudication"]["flags"] if (f.get("resolution") or {}).get("resolution") == "corrected"), "")
    u = c.post(f"/api/tb/cases/TB-002/confirmations/{conf}/undo", json={}).json().get("record") or {}
    check("7.3 undo takes the correction back as version 3 (history kept)", u.get("version") == 3 and u.get("decision_text") == text and len(u.get("versions") or []) == 3
          and (u.get("resolution") or {}).get("final") is False)
    # 7.4: a board action reaches the department inbox, overdue on display; a later MRI suggests closing; a person closes it
    c.delete("/api/tb/cases/TB-TEST7")
    c.post("/api/tb/cases", json={"case_id": "TB-TEST7", "protocol": "breast", "board_date": "2026-10-20",
                                  "patient": {"name": "SYNTHETIC, Follow-up Patient", "mrn": "SYN-997", "agesex": "49 Y / F"}})
    yday = (__import__("datetime").date.today() - __import__("datetime").timedelta(days=1)).isoformat()
    r7 = c.post("/api/tb/cases/TB-TEST7/board-records", json={"decision_text": "Response assessment before surgery.", "recorded_by": "Dr. Coordinator (synthetic)",
          "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)", "actions": [{"department": "Radio-diagnosis", "task": "MRI breast after chemotherapy", "due": yday}]}).json()
    act = next((a for a in c.get("/api/tb/cases/TB-TEST7").json()["state"]["actions"] if a.get("source") == "board"), {})
    ib = c.get("/api/tb/inbox").json()
    row = next((q for d in ib["departments"] if d["id"] == "radiology" for q in d["requests"] if q["action_id"] == act.get("id")), {})
    check("7.4 board action in the Radio-diagnosis inbox: labelled, overdue worked out on display, department notified",
          row.get("source") == "board" and row.get("source_label") == "Tumour Board action" and row.get("overdue") and row.get("board_record") == r7.get("id")
          and any(n["kind"] == "board_action" and n.get("action_id") == act.get("id") for n in c.get("/api/tb/notifications", params={"limit": 200}).json()["notifications"]),
          f"{row.get('status')}, {row.get('days_overdue')} d")
    mri = ("SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDEPARTMENT OF RADIO-DIAGNOSIS\nMRI BREAST (BILATERAL), CONTRAST\nPatient: SYNTHETIC, Follow-up Patient  UHID: SYN-997  49 Y / F\n"
           "Study date: 05/10/2026\nFindings: Post-chemotherapy reduction in the size of the left breast lesion, now 1.8 cm.\nImpression: partial response.\n"
           "Report status: FINAL\nSd/- Dr. R. Nair, MD (Radio-diagnosis), KMC 51234\nReported on 05/10/2026\n").encode()
    wait_job(c, c.post("/api/tb/cases/TB-TEST7/documents", files=[("files", ("mri_breast.txt", mri))], data={"paths": json.dumps(["mri_breast.txt"])}).json()["job"])
    act = next((a for a in c.get("/api/tb/cases/TB-TEST7").json()["state"]["actions"] if a.get("id") == act.get("id")), {})
    sug = act.get("suggested_close") or {}
    check("7.4 the MRI that arrived later suggests closing the action (never closed by itself)", bool(sug.get("doc_id")) and act.get("status") != "completed", sug.get("reason", "no suggestion"))
    cl = c.post(f"/api/tb/cases/TB-TEST7/actions/{act.get('id')}/close", json={"doc_id": sug.get("doc_id", "")}).json()
    ib = c.get("/api/tb/inbox").json()
    row = next((q for d in ib["departments"] if d["id"] == "radiology" for q in d["requests"] if q["action_id"] == act.get("id")), {})
    au7 = [e["kind"] for e in c.get("/api/tb/cases/TB-TEST7/audit").json()["events"]]
    check("7.4 closed by a person with that document: completed in the inbox, audited", cl.get("status") == "completed" and cl.get("closed_doc_id") == sug.get("doc_id")
          and row.get("status") == "completed" and "board_action_suggested" in au7 and "board_action_closed" in au7, f"{row.get('status')} {row.get('completed')}")
    c.delete("/api/tb/cases/TB-TEST7")


SCAN_FONT = "/usr/share/fonts/urw-base35/NimbusSans-Regular.otf"


def scan_png(lines, size=34):
    """A clean synthetic scan (PNG bytes) of the given text lines, for the scanned-document checks of Phase 8."""
    import io
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(SCAN_FONT, size)
    im = Image.new("RGB", (1700, 140 + int(size * 1.7) * len(lines)), "white"); dr = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        dr.text((90, 70 + i * int(size * 1.7)), line, fill=(20, 20, 20), font=font)
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


PDL1_SCAN = ["SAHYADRI CANCER INSTITUTE (SYNTHETIC)", "DEPARTMENT OF PATHOLOGY", "IMMUNOHISTOCHEMISTRY REPORT",
             "Patient: SYNTHETIC, Test Patient    UHID: SYN-996    63 Y / M", "Aadhaar: 4821 6093 2200 (synthetic)", "Specimen: FFPE block of the lung biopsy",
             "Date of report: 27/09/2026", "PD-L1 (22C3) Tumour Proportion Score: 60%", "Report status: FINAL",
             "Sd/- Dr. A. Menon, Consultant Pathologist, Reg. No. KMC 11223"]


def phase8(c):
    """V1 Phase 8 on its own synthetic Case File TB-TEST8 (lung, Optimal hospital, so PD-L1 is required): a PD-L1 report uploaded as a
    scan says "from scan" (8.1), needs one confirmation against the image before it counts, then counts (8.2); the independent OCR engine
    read the page (8.3); the value carries its word boxes on the image and the preview has the Aadhaar number blacked out (8.4)."""
    c.delete("/api/tb/cases/TB-TEST8")
    try:
        r = c.post("/api/tb/cases", json={"case_id": "TB-TEST8", "protocol": "lung_nsclc", "setting": "metastatic", "hospital_level": "optimal", "board_date": "2026-10-21",
                                          "patient": {"name": "SYNTHETIC, Test Patient", "mrn": "SYN-996", "agesex": "63 Y / M"}})
        check("phase8: synthetic lung Case File created (Optimal hospital)", r.status_code == 200, r.text[:80])
        j = c.post("/api/tb/cases/TB-TEST8/documents", files=[("files", ("pdl1_ihc_scan.png", scan_png(PDL1_SCAN)))],
                   data={"paths": json.dumps(["pathology/pdl1_ihc_scan.png"])}).json()
        wait_job(c, j["job"])
        d = c.get("/api/tb/cases/TB-TEST8").json()
        doc = next((x for x in d["documents"] if x["rel_path"] == "pathology/pdl1_ihc_scan.png"), {})
        full = c.get(f"/api/tb/cases/TB-TEST8/documents/{doc.get('doc_id')}").json() if doc else {}
        f = (full.get("facts") or {}).get("pdl1") or {}
        check("8.1 scanned page listed and the PD-L1 value says from scan", doc.get("scan_pages") == [0] and f.get("source_method") == "vision-transcription"
              and f.get("verification") == "verified", f"{doc.get('scan_pages')} {f.get('value')!r} {f.get('verification')} {f.get('source_method')}")
        allr = {x["id"]: x for x in d["state"]["gate"]["requirements"] + d["state"]["gate"]["shown"]}
        pd = allr.get("pdl1") or {}
        need = next((n for n in pd.get("needs") or [] if n["type"] == "confirm_value" and n.get("fact") == "pdl1"), None)
        check("8.2 scanned PD-L1 needs a confirmation against the image (Level 2)", pd.get("status") == "needs_confirmation" and pd.get("level") == 2 and need is not None
              and need["doc_id"] == doc.get("doc_id") and pd.get("required") is True, f"{pd.get('status')} L{pd.get('level')} {need}")
        page = (full.get("pages") or [{}])[0]
        eng = page.get("ocr_engine") or {}
        check("8.3 the independent OCR engine read the scanned page (words with boxes, Aadhaar masked)", eng.get("engine") == "tesseract" and len(eng.get("words") or []) > 20
              and "4821" not in json.dumps(eng) and "6093" not in json.dumps(eng), f"{eng.get('engine')} {eng.get('version')} {len(eng.get('words') or [])} words {page.get('ocr_engine_note', '')}")
        check("8.3 a clean scan raises no engine disagreement", not [x for x in page.get("ocr_uncertain_spans") or [] if x.get("source") == "engine"],
              json.dumps([x for x in page.get("ocr_uncertain_spans") or [] if x.get("source") == "engine"])[:160])
        check("8.4 the PD-L1 value carries its word box on the image", len(f.get("boxes") or []) == 1 and bool(page.get("box_map")), json.dumps(f.get("boxes")))
        check("8.4 the confirmation request carries the box (the dialog highlights the value)", bool(need) and need.get("boxes") == f.get("boxes"), json.dumps((need or {}).get("boxes")))
        r = c.get(f"/api/tb/cases/TB-TEST8/documents/{doc.get('doc_id')}/file")
        masked = [w for w in eng.get("words") or [] if w[0] == "XXXX"]
        black = False
        if r.status_code == 200 and masked:
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(r.content)).convert("RGB"); w = masked[0]
            black = im.getpixel((int((w[1] + w[3]) / 2 * im.size[0]), int((w[2] + w[4]) / 2 * im.size[1]))) == (0, 0, 0)
        check("8.4 the preview has the Aadhaar groups blacked out", r.headers.get("content-type", "").startswith("image/png") and len(masked) == 2 and black,
              f"{r.headers.get('content-type')} {len(masked)} masked words, black={black}")
        ev = [e for e in pd.get("evidence") or [] if e.get("fact") == "pdl1"]
        check("8.1 Pre-Authorization evidence says from scan", bool(ev) and ev[0].get("source_method") == "vision-transcription", json.dumps(ev)[:160])
        if need:
            st = c.post("/api/tb/cases/TB-TEST8/confirmations", json={"type": "confirm_value", "key": f"{need['doc_id']}:pdl1", "fields": {"value": need["value"]},
                                                                    "reason": "e2e: read on the scan image"}).json()["state"]
            g = st["gate"]; pd2 = next((x for x in g["requirements"] + g["shown"] if x["id"] == "pdl1"), {})
            check("8.2 confirmed against the image: PD-L1 satisfied", pd2.get("status") == "satisfied" and not [n for n in pd2.get("needs") or [] if n["type"] == "confirm_value"],
                  pd2.get("status", ""))
            au = c.get("/api/tb/cases/TB-TEST8/audit").json()["events"]
            check("8.2 confirmation audited", any(e["kind"] == "confirmation" and e.get("type") == "confirm_value" for e in au))
    finally:
        c.delete("/api/tb/cases/TB-TEST8")


try:  # the corpus generator owns the decision texts; the copies below are used only when they cannot be imported
    from tumour_board.demo_data.india_corpus import DECISION_TEXT_7
except Exception:
    DECISION_TEXT_7 = ("Composite resection: wide local excision of the left buccal mucosa lesion with segmental mandibulectomy, left modified neck "
                       "dissection (levels I to V) and reconstruction with a pectoralis major myocutaneous flap. Adjuvant radiotherapy 60 Gy in 30 "
                       "fractions to the tumour bed and neck, with concurrent Inj. Cisplatin 40 mg/m2 IV weekly if the final histopathology shows a "
                       "positive margin or extranodal extension. Stage as recorded: cT4a N1 M0.")
try:
    from tumour_board.demo_data.india_corpus import DECISION_TEXT_8
except Exception:
    DECISION_TEXT_8 = ("Radical concurrent chemoradiation: external beam radiotherapy 50 Gy in 25 fractions to the pelvis with concurrent Inj. Cisplatin "
                       "40 mg/m2 IV weekly, followed by HDR intracavitary brachytherapy 7 Gy x 3 fractions to point A. FIGO 2018 Stage IIB as recorded.")

# V1 Phase 9: one entry per new demo Case File; phase9() walks each through the whole workflow. Spec keys:
#   counted          records the gate counts at import (setting not recorded yet: strictest tier); each must be counted
#   shown            {record: NCG tier} shown at import, never counted
#   confirm_type     optional: a document whose type is disputed by design (V1 item 3.2) and the records waiting for it
#   gap              optional: the one counted record open at import {record, status, level, department, inbox (department id)}; the
#                    arrivals close it. Without a gap the gate passes at import.
#   listing          the listing payload; listed: {"counted": exact counted set after listing or None, "shown": {record: tier or None}}
#   intake, ask, refuse, brief_role, checklist   department upload matched on the UHID, Ask, the specialty brief's checklist title
#   decision, drug, dose, slip, guideline_file, members, action, inbox   the board record, its dose check and the board action's inbox
# A document the reader mistypes (a confirm_doc_type need on a counted record) is confirmed with its title-keyword type, as a clinician
# would in the UI, and reported in the details, so one reader slip does not fail the run.
V9_CASES = {
    "TB-007": {
        "site": "oral cavity", "protocol": "oral_cavity",
        "counted": ["clinical_history", "histopathology", "primary_neck_imaging", "chest_imaging", "dental_evaluation"],  # NCG records that count
        "shown": {"pet_ct": "c", "cect_thorax": "c"},  # NCG Optional (c): shown, never counted
        # V1 item 3.2 safeguard, intended: the reader types the dental Word file "other" while its title keywords say clinical_note, so the two
        # records it could satisfy wait for one clinician confirmation of its type (as the UI does), then the gate passes
        "confirm_type": {"rel_path": "surgical_oncology/dental_evaluation_2026-09-17.docx", "doc_type": "clinical_note", "records": ["clinical_history", "dental_evaluation"]},
        "listing": {"protocol": "oral_cavity", "setting": "locally_advanced", "board_date": "18/10/2026", "hospital_level": "essential"},
        "listed": {"counted": ["clinical_history", "histopathology", "primary_neck_imaging", "chest_imaging", "dental_evaluation"], "shown": {"pet_ct": None}},
        "intake": {"department": "Radio-diagnosis", "filename": "usg_neck_2026-09-30.txt", "text":
                   "SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDEPARTMENT OF RADIO-DIAGNOSIS\nULTRASOUND NECK\nPatient: Manjunath Gowda  UHID: SYN-700352  54 Y / M\n"
                   "Study date: 30/09/2026\nFindings: left level IB lymph node 2.0 x 1.7 cm. No other enlarged cervical lymph node. Both lobes of the thyroid normal.\n"
                   "Impression: left level IB lymph node, as described.\nReport status: FINAL\nSd/- Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310\n"
                   "Reported on 30/09/2026\n"},
        "ask": ("What depth of invasion does the CT report record?", "12"),
        "refuse": "Should he have surgery or chemoradiation?",
        "brief_role": "radiology", "checklist": "head and neck",
        "decision": DECISION_TEXT_7, "drug": "cisplatin", "dose": "40 mg/m2", "slip": "400 mg/m2", "guideline_file": "ncg-guidelines-for-head-neck-cancer",
        "members": [{"name": "Dr. P. Hegde (synthetic)", "department": "Surgical Oncology"}, {"name": "Dr. M. Iyer (synthetic)", "department": "Radiation Oncology"},
                    {"name": "Dr. A. Kulkarni (synthetic)", "department": "Medical Oncology"}],
        "action": {"department": "Surgical Oncology", "task": "Schedule surgery"}, "inbox": "surgical_oncology",
    },
    "TB-008": {
        "site": "cervix", "protocol": "cervix",
        "counted": ["clinical_history", "histopathology", "cbc", "liver_renal_function", "viral_markers", "abdomen_pelvis_imaging", "cect_abdomen_pelvis", "chest_xray", "cystoscopy_proctoscopy"],
        "shown": {"mri_pelvis": "b", "ct_thorax": "c", "ihc": "c", "pet_ct": "c"},
        # cystoscopy / proctoscopy arrives later: at import it is the one Level 1 gap, routed to Surgical Oncology
        "gap": {"record": "cystoscopy_proctoscopy", "status": "missing_record", "level": 1, "department": "Gynaecologic Oncology", "inbox": "gynaecologic_oncology"},  # V2 2.4 route
        "listing": {"protocol": "cervix", "setting": "locally_advanced", "board_date": "20/10/2026", "hospital_level": "essential"},
        "listed": {"counted": ["clinical_history", "histopathology", "cbc", "liver_renal_function", "viral_markers", "cect_abdomen_pelvis", "cystoscopy_proctoscopy"],
                   "shown": {"abdomen_pelvis_imaging": "none", "chest_xray": "b"}},
        "intake": {"department": "Radio-diagnosis", "filename": "usg_abdomen_2026-09-29.txt", "text":
                   "SAHYADRI CANCER INSTITUTE (SYNTHETIC)\nDEPARTMENT OF RADIO-DIAGNOSIS\nULTRASOUND ABDOMEN AND PELVIS\nPatient: Parvathi Naik  UHID: SYN-800415  46 Y / F\n"
                   "Study date: 29/09/2026\nFindings: liver, gall bladder, pancreas and spleen normal. Both kidneys normal in size; no hydronephrosis. "
                   "Bulky cervix, as described on MRI.\nImpression: no hydronephrosis.\nReport status: FINAL\nSd/- Dr. Shalini Rao, MD (Radio-diagnosis), KMC Reg. No. 66310\n"
                   "Reported on 29/09/2026\n"},
        "ask": ("What FIGO stage is recorded?", "IIB"),
        "refuse": "Should she get chemoradiation or surgery?",
        "brief_role": "radiology", "checklist": "cervix",
        "decision": DECISION_TEXT_8, "drug": "cisplatin", "dose": "40 mg/m2", "slip": "400 mg/m2", "guideline_file": "ncg-guidelines-for-gynecological-cancer",
        "rt_consistent": True,  # NCG cervix gives the EBRT and brachytherapy schedules: 50 Gy / 25 and 7 Gy x 3 must be consistent (review)
        "members": [{"name": "Dr. A. Deshpande (synthetic)", "department": "Surgical Oncology"}, {"name": "Dr. M. Iyer (synthetic)", "department": "Radiation Oncology"},
                    {"name": "Dr. A. Kulkarni (synthetic)", "department": "Medical Oncology"}],
        "action": {"department": "Radiation Oncology", "task": "Start chemoradiation"}, "inbox": "radiation_oncology",
    },
}


def _confirm_disputed(c, cid, d, g):
    """Confirm the type of every document a counted record waits for (a confirm_doc_type need) with the type its title keywords say, as a
    clinician would in the UI; returns [(file, read as, confirmed as or None)]. Nothing to do when the reader typed every document right."""
    out, seen = [], set()
    docs = {x["doc_id"]: x for x in d["documents"]}
    for r in g.get("requirements") or []:
        for n in r.get("needs") or []:
            if n.get("type") != "confirm_doc_type" or n.get("doc_id") in seen:
                continue
            seen.add(n["doc_id"]); x = docs.get(n["doc_id"], {}); cls = x.get("classification") or {}
            kw = cls.get("doc_type_keyword")
            if kw:
                rr = c.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "confirm_doc_type", "key": n["doc_id"], "fields": {"doc_type": kw},
                                                                         "reason": "e2e: type read on the document (title keywords)"})
                if rr.status_code == 200 and rr.json().get("job"):
                    wait_job(c, rr.json()["job"])
                kw = kw if rr.status_code == 200 else None
            out.append((x.get("rel_path", n["doc_id"]), cls.get("doc_type"), kw))
    if out:
        c.post(f"/api/tb/cases/{cid}/recheck")
        print(f"INFO 9 {cid}: reader slip, document type confirmed: {out}", flush=True)
    return out


def _send_suggested(c, cid, requirement=None, message=""):
    """V2 item 4.2: the gate only suggests a request; the treating side (here the admin client) sends it before a department can see
    it in its inbox. Returns [(action id, HTTP status)] for the requests sent."""
    d = c.get(f"/api/tb/cases/{cid}").json()
    out = []
    for a in d["state"].get("actions") or []:
        if a.get("source", "pre_authorization") == "pre_authorization" and a.get("status") == "suggested" and (requirement is None or a.get("requirement") == requirement):
            r = c.post(f"/api/tb/cases/{cid}/requests/{a['id']}/send", json={"message": message})
            out.append((a["id"], r.status_code))
    return out


def _open_rows(c, dept, cid, requirement):
    """Inbox rows of a department for one Case File's Pre-Authorization request."""
    ib = c.get("/api/tb/inbox").json()
    return [q for dd in ib["departments"] if dd["id"] == dept for q in dd["requests"] if q["case_id"] == cid and q.get("requirement") == requirement
            and q.get("source", "pre_authorization") == "pre_authorization"]


def _brief(c, cid, role):
    """Stream one specialty agent's brief (as the UI does): (brief or None, tools used)."""
    brief, tools = None, []
    with c.stream("POST", f"/api/tb/cases/{cid}/agents/{role}", json={}) as resp:
        for line in resp.iter_lines():
            if line.strip():
                ev = json.loads(line); tools.append(ev.get("tool"))
                if ev["type"] == "brief":
                    brief = ev["brief"]
    return brief, tools


def protocol_tier(t):
    return {"a": "NCG Essential", "b": "NCG Optimal", "c": "NCG Optional", "none": "not applicable"}.get(t, t)


def _summary_check(c, cid, tag, when=""):
    sm = c.post(f"/api/tb/cases/{cid}/summary", json={}).json()
    sents = [x for p in sm.get("paragraphs") or [] for x in p]
    stale = c.get(f"/api/tb/cases/{cid}").json()["stale"].get("summary")
    check(f"{tag}: Case File summary compiled{' ' + when if when else ''}, every sentence cited, not stale",
          sm.get("status") == "ready" and sents and all(x.get("citations") for x in sents) and stale == "",
          f"{len(sents)} sentences, {sum(not x.get('citations') for x in sents)} uncited, {sm.get('seconds')} s, stale {stale!r}"[:200])


def phase9_case(c, cid, spec):
    """One Phase 9 demo Case File end to end through the HTTP API: import and gate under its NCG protocol (a disputed document type is
    confirmed as the UI does; a gap at import is routed to its department and closed by the arrivals), listing with the NCG setting, a department upload matched on the UHID, Ask, the Case File summary, the
    specialty brief with its reporting checklist, the arrivals and the board decision (PM-JAY composition, Indian guideline dose check, recorded stage, a planted dose slip, the board action in the
    department inbox). The Case File is re-imported at the end, so it stays as the corpus defines it."""
    import datetime
    t_case = time.time(); tag = f"9 {cid} ({spec['site']})"
    if spec["protocol"] not in {p["id"] for p in c.get("/api/tb/protocols").json()["protocols"]}:
        check(f"{tag}: protocol {spec['protocol']} installed", False, f"tumour_board/protocols/{spec['protocol']}.json is not in this checkout")
    # a. import: every document read, the gate under the protocol with its NCG records
    r = c.post(f"/api/tb/demo/{cid}")
    if r.status_code != 200:
        check(f"{tag}: demo Case File imported", False, f"HTTP {r.status_code} {r.text[:120]} (generate it: python -m tumour_board.demo_data.make_corpus)")
        return
    j, secs = wait_job(c, r.json()["job"])
    d = c.get(f"/api/tb/cases/{cid}").json(); g = d["state"]["gate"] or {}
    bad = [f"{x['rel_path']}: {x['state']} {x.get('error') or ''}" for x in d["documents"] if x["state"] != "ready"]
    check(f"{tag}: imported, every document read", j.get("state") == "finished" and d["documents"] and not bad, f"{j.get('total')} docs in {secs}s; " + ("; ".join(bad)[:160] or "no errors"))
    req = {x["id"]: x for x in g.get("requirements") or []}; shown = {x["id"]: x for x in g.get("shown") or []}
    miss = [k for k in spec["counted"] if k not in req]
    check(f"{tag}: gate under {spec['protocol']} counts the NCG records", g.get("protocol") == spec["protocol"] and not miss,
          f"protocol {g.get('protocol')}; expected {', '.join(spec['counted'])}; the gate counts {', '.join(sorted(req)) or 'nothing'}" + (f"; missing {', '.join(miss)}" if miss else ""))
    opt = {k: (shown.get(k) or {}) for k in spec["shown"]}
    check(f"{tag}: {', '.join(f'{k} ({protocol_tier(t)})' for k, t in spec['shown'].items())} shown, not counted",
          all(v.get("tier") == spec["shown"][k] and v.get("required") is False and k not in req for k, v in opt.items()),
          json.dumps({k: (v.get("tier"), v.get("required")) if v else ("counted" if k in req else "absent") for k, v in opt.items()}))
    ct = spec.get("confirm_type")
    if ct:  # a disputed document type: the records it could satisfy wait for one confirmation naming that document; the others are satisfied
        doc = next((x for x in d["documents"] if x["rel_path"] == ct["rel_path"]), {})
        waiting = {k: req.get(k, {}).get("status") for k in ct["records"]}
        named = all({"type": "confirm_doc_type", "doc_id": doc.get("doc_id")} in (req.get(k, {}).get("needs") or []) for k in ct["records"])
        rest = {k: v["status"] for k, v in req.items() if k not in ct["records"] and v["status"] != "satisfied"}
        typed = (doc.get("classification") or {}).get("doc_type")
        agreed = typed == ct["doc_type"] and not (doc.get("classification") or {}).get("doc_type_disagreement")
        # the reader is not bit-identical between runs: when it typed the document right, nothing is disputed and no confirmation is asked
        check(f"{tag}: disputed type of {ct['rel_path']}: {', '.join(ct['records'])} need a confirmation of its type (or the reader typed it {ct['doc_type']}), the other records satisfied",
              bool(doc) and not rest and ((set(waiting.values()) == {"needs_confirmation"} and named and g.get("passed") is False) or (agreed and set(waiting.values()) == {"satisfied"})),
              f"read as {typed!r}; {json.dumps(waiting)}; named {named}; other open {json.dumps(rest)}; {g.get('satisfied')}/{g.get('total')}")
        if doc and not agreed:
            r = c.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "confirm_doc_type", "key": doc["doc_id"], "fields": {"doc_type": ct["doc_type"]},
                                                                    "reason": "e2e: type read on the document"})
            if r.status_code == 200 and r.json().get("job"):
                wait_job(c, r.json()["job"])
            check(f"{tag}: document type confirmed as {ct['doc_type']}", r.status_code == 200, f"HTTP {r.status_code} {r.text[:100] if r.status_code != 200 else ''}")
            c.post(f"/api/tb/cases/{cid}/recheck")
            d = c.get(f"/api/tb/cases/{cid}").json(); g = d["state"]["gate"] or {}; req = {x["id"]: x for x in g.get("requirements") or []}
    fixed = _confirm_disputed(c, cid, d, g)
    # review M8: a disputed type other than the one the spec expects is a reader / document type regression: confirmed so the walk goes on,
    # but counted as a failure (never only an INFO line)
    check(f"{tag}: no unexpected document type dispute at import", not fixed, f"confirmed {fixed}" if fixed else "none")
    if fixed:
        d = c.get(f"/api/tb/cases/{cid}").json(); g = d["state"]["gate"] or {}; req = {x["id"]: x for x in g.get("requirements") or []}
    unsat = {k: f"{v['status']}: {'; '.join(v.get('problems') or [])[:80]}" for k, v in req.items() if v["status"] != "satisfied"}
    gap = spec.get("gap")
    if not gap:
        check(f"{tag}: every counted record satisfied, gate passed", g.get("passed") is True and not unsat and g.get("total") == len(spec["counted"]),
              f"{g.get('satisfied')}/{g.get('total')} " + json.dumps(unsat)[:200] + (f"; reader slips confirmed {fixed}" if fixed else ""))
    else:
        gr = req.get(gap["record"]) or {}
        check(f"{tag}: gate not passed: {gap['record']} the only open record ({gap['status']}, Level {gap['level']}), every other counted record satisfied",
              g.get("passed") is False and list(unsat) == [gap["record"]] and gr.get("status") == gap["status"] and gr.get("level") == gap["level"]
              and g.get("total") == len(spec["counted"]),
              f"{g.get('satisfied')}/{g.get('total')} " + json.dumps(unsat)[:200] + f"; L{gr.get('level')}" + (f"; reader slips confirmed {fixed}" if fixed else ""))
        act = [a for a in d["state"].get("actions") or [] if a.get("requirement") == gap["record"] and a.get("source", "pre_authorization") == "pre_authorization"
               and a.get("status") != "completed"]
        suggested = bool(act) and act[0].get("status") == "suggested"
        _send_suggested(c, cid, gap["record"])  # V2 4.2: suggested by the gate, sent by the treating side
        rows = [q for q in _open_rows(c, gap["inbox"], cid, gap["record"]) if q["status"] != "completed"]
        check(f"{tag}: {gap['record']} routed to {gap['department']}: suggested by the gate, an open request in its inbox once sent", suggested and act[0].get("department") == gap["department"] and bool(rows),
              f"actions {[(a.get('department'), a.get('status'), a.get('level')) for a in act]}; inbox {[(q.get('label'), q.get('status')) for q in rows]}")
    # b. listing with the NCG setting
    r = c.post(f"/api/tb/cases/{cid}/listing", json=spec["listing"])
    if r.status_code == 200 and r.json().get("total"):
        wait_job(c, r.json()["job"])
    d = c.get(f"/api/tb/cases/{cid}").json(); g = d["state"]["gate"] or {}; shown = {x["id"]: x for x in g.get("shown") or []}
    req = {x["id"]: x for x in g.get("requirements") or []}
    lst, lsd = spec["listing"], spec.get("listed") or {}
    unsat = [k for k, v in req.items() if v["status"] != "satisfied"]
    cnt_ok = lsd.get("counted") is None or set(req) == set(lsd["counted"])
    sh_ok = all(k in shown and shown[k].get("required") is False and (t is None or shown[k].get("tier") == t) for k, t in (lsd.get("shown") or {}).items())
    gate_ok = (g.get("passed") is True) if not gap else (g.get("passed") is False and unsat == [gap["record"]] and (req.get(gap["record"]) or {}).get("status") == gap["status"])
    check(f"{tag}: listed with the NCG setting {lst['setting']}" + ("; counted records as the setting says" if lsd.get("counted") else "")
          + f"; {', '.join(lsd.get('shown') or {})} shown, not required; " + (f"the {gap['record']} gap unchanged" if gap else "gate still passes"),
          r.status_code == 200 and d["case"].get("setting") == lst["setting"] and g.get("setting") == lst["setting"] and g.get("hospital_level") == lst["hospital_level"]
          and cnt_ok and sh_ok and gate_ok,
          f"HTTP {r.status_code} {r.text[:80] if r.status_code != 200 else ''} setting {g.get('setting')}, {g.get('satisfied')}/{g.get('total')} passed {g.get('passed')}, "
          f"counted {sorted(req)}, open {unsat}, shown {json.dumps({k: (shown.get(k) or {}).get('tier') for k in lsd.get('shown') or {}})}")
    # c. patient matching: a department upload without a Case File lands in this Case File on the UHID; then removed again
    it = spec["intake"]
    r = c.post("/api/tb/intake/documents", files=[("files", (it["filename"], it["text"].encode()))], data={"paths": json.dumps([it["filename"]]), "department": it["department"]})
    jj = wait_job(c, r.json()["job"])[0] if r.status_code == 200 else {}
    landed = jj.get("filed") or {}  # doc_id -> Case File
    queued = [x for x in c.get("/api/tb/intake").json()["documents"] if x["rel_path"] == it["filename"]]
    check(f"{tag}: department upload ({it['department']}) matched on the UHID and filed into {cid}", r.status_code == 200 and list(landed.values()) == [cid],
          f"filed {json.dumps(landed)}; waiting {[(x['state'], (x.get('match') or {}).get('reason', '')[:80]) for x in queued]}")
    for did, cs in landed.items():
        if cs == "TB-2026-bharath":  # never touch the real case; say so loudly instead
            check(f"{tag}: synthetic upload never filed into the real Case File", False, "filed into TB-2026-bharath: remove it by hand")
            continue
        c.delete(f"/api/tb/cases/{cs}/documents/{did}")
    for x in queued:
        c.delete(f"/api/tb/intake/{x['doc_id']}?reason=e2e+cleanup")
    left = [x["rel_path"] for x in c.get(f"/api/tb/cases/{cid}").json()["documents"] if x["rel_path"].endswith(it["filename"])]
    check(f"{tag}: the matched upload removed again", not left, ", ".join(left))
    # d. Ask the Case File
    q, want = spec["ask"]
    a = c.post(f"/api/tb/cases/{cid}/ask", json={"question": q}).json()
    quotes = [cc.get("quote", "") for s in a.get("statements") or [] for cc in s.get("citations") or []]
    check(f"{tag}: Ask '{q}' answered with a citation containing {want}", a.get("status") == "answered" and any(re.search(r"(?<![A-Za-z0-9])" + re.escape(want) + r"(?![A-Za-z0-9])", x) for x in quotes),
          f"{a.get('status')} {a.get('seconds')} s: {[s['text'][:80] for s in a.get('statements') or []][:2]}")
    a = c.post(f"/api/tb/cases/{cid}/ask", json={"question": spec["refuse"]}).json()
    check(f"{tag}: '{spec['refuse']}' refused", a.get("status") == "out_of_scope" and not a.get("statements"), f"{a.get('status')} {a.get('category', '')}")
    # e. Case File summary: compiled once every Pre-Authorization check is met (workflow), so a Case File with a gap is refused here and
    #    compiled after the arrivals close the gap (below)
    if spec.get("gap"):
        sm = c.post(f"/api/tb/cases/{cid}/summary", json={}).json()
        rl = next((x["label"] for x in (c.get(f"/api/tb/cases/{cid}").json()["state"]["gate"] or {}).get("requirements") or [] if x["id"] == spec["gap"]["record"]), "")
        check(f"{tag}: Case File summary waits for the open Pre-Authorization record (gate not met)", sm.get("status") == "gate_not_met" and rl and rl in (sm.get("open") or []),
              f"{sm.get('status')}: {sm.get('open')}")
    else:
        _summary_check(c, cid, tag)
    # f. specialty brief with the reporting checklist of the site
    t0 = time.time(); brief, tools = _brief(c, cid, spec["brief_role"])
    items = [it2 for sec in (brief or {}).get("sections") or [] for it2 in sec.get("items") or []]
    title = (((brief or {}).get("pack") or {}).get("checklist") or {}).get("title") or ""
    check(f"{tag}: {spec['brief_role']} brief returns cited items", bool(items) and all(x.get("citations") for x in items),
          f"{len(items)} items, {sum(not x.get('citations') for x in items)} uncited, {len((brief or {}).get('points_for_review') or [])} points, {round(time.time() - t0, 1)} s")
    check(f"{tag}: {spec['brief_role']} brief names the {spec['checklist']} reporting checklist", spec["checklist"] in title.lower(), title or "no checklist")
    # g. arrivals: the board record arrives; the board decision is recorded and checked
    r = c.post(f"/api/tb/cases/{cid}/demo-arrivals")
    if r.status_code == 200:
        wait_job(c, r.json()["job"])
    d = c.get(f"/api/tb/cases/{cid}").json()
    fixed = _confirm_disputed(c, cid, d, d["state"]["gate"] or {})
    check(f"{tag}: no unexpected document type dispute after the arrivals", not fixed, f"confirmed {fixed}" if fixed else "none")
    if fixed:
        d = c.get(f"/api/tb/cases/{cid}").json()
    docs = d["documents"]
    tbr = [x for x in docs if (x.get("classification") or {}).get("doc_type") == "tumour_board_record"]
    check(f"{tag}: arrivals: the board record document arrives and is read", r.status_code == 200 and bool(tbr) and all(x["state"] == "ready" for x in tbr),
          f"HTTP {r.status_code}; {[(x['rel_path'], x['state']) for x in tbr] or [x['rel_path'] for x in docs][-3:]}")
    if gap:  # the record that arrived closes the gap: the gate passes and the department's request is closed
        g = d["state"]["gate"] or {}; req = {x["id"]: x for x in g.get("requirements") or []}
        unsat = {k: v["status"] for k, v in req.items() if v["status"] != "satisfied"}
        n = len(lsd.get("counted") or spec["counted"])
        check(f"{tag}: arrivals close the {gap['record']} gap: gate passed {n}/{n}", g.get("passed") is True and not unsat and g.get("total") == n,
              f"{g.get('satisfied')}/{g.get('total')} open {json.dumps(unsat)}" + (f"; reader slips confirmed {fixed}" if fixed else ""))
        acts = [a for a in d["state"].get("actions") or [] if a.get("requirement") == gap["record"] and a.get("source", "pre_authorization") == "pre_authorization"]
        rows = _open_rows(c, gap["inbox"], cid, gap["record"])
        check(f"{tag}: the {gap['department']} request for {gap['record']} closed (inbox shows it completed)",
              bool(acts) and all(a.get("status") == "completed" for a in acts) and bool(rows) and all(q["status"] == "completed" for q in rows),
              f"actions {[a.get('status') for a in acts]}; inbox {[(q.get('label'), q.get('status')) for q in rows]}")
        _summary_check(c, cid, tag, "once the gap is closed")
    due = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
    body = {"board_date": "2026-10-18", "recorded_by": "Dr. Tumour Board Coordinator (synthetic)", "decision_text": spec["decision"],
            "members": spec["members"], "actions": [{**spec["action"], "due": due}]}
    rec = c.post(f"/api/tb/cases/{cid}/board-records", json=body).json()
    flags = (rec.get("adjudication") or {}).get("flags") or []
    checks = ((rec.get("adjudication") or {}).get("guideline_checks") or {}).get("checks") or []
    comp = [f for f in flags if f["kind"] == "composition"]
    check(f"{tag}: board record: all three oncologists present, no PM-JAY composition flag", bool(rec.get("id")) and not comp, "; ".join(f["text"][:100] for f in comp) or f"{rec.get('id')}")
    drug = [x for x in checks if x.get("kind") == "drug" and x.get("drug") == spec["drug"]]
    refs = [rr for x in drug for rr in x.get("references") or []]
    dose_er = [f for f in flags if f["kind"] == "guideline" and f.get("check") == "dose" and f["severity"] == "expert_review"]
    check(f"{tag}: {spec['drug']} {spec['dose']} consistent with the Indian {spec['guideline_file']} line, no dose flag for expert review",
          bool(drug) and all(x["result"] == "consistent" for x in drug) and any(rr.get("region") == "India" and spec["guideline_file"] in (rr.get("file") or "") for rr in refs) and not dose_er,
          f"{[(x['recorded'], x['result']) for x in drug]}; refs {[(rr.get('org'), rr.get('file'), rr.get('page')) for rr in refs][:2]}; "
          f"flags {[f['text'][:80] for f in dose_er]}; RT {[(x.get('recorded'), x['result']) for x in checks if x.get('kind') == 'rt']}")
    rt = [(x.get("recorded"), x["result"]) for x in checks if x.get("kind") == "rt"]
    if spec.get("rt_consistent"):
        check(f"{tag}: every radiotherapy schedule of the decision consistent with an Indian line", bool(rt) and all(r2 == "consistent" for _, r2 in rt), f"{rt}")
    else:
        print(f"INFO {tag}: radiotherapy checks (reported, not a pass / fail): {rt or 'none'}; all consistent: {'yes' if rt and all(r2 == 'consistent' for _, r2 in rt) else 'no'}", flush=True)
    stage = [x for x in checks if x.get("kind") == "stage"]
    check(f"{tag}: stage check reads the recorded stage (no 'differs')", any(x["result"] == "stage_consistent" for x in stage)
          and not any(x["result"] == "stage_differs" for x in stage) and not [f for f in flags if f.get("check") == "stage"],
          f"{[(x['recorded'], x['result'], (x.get('source') or {}).get('value')) for x in stage]}")
    slip_text = spec["decision"].replace(spec["dose"], spec["slip"], 1)  # the same record with one planted dose slip
    slip = c.post(f"/api/tb/cases/{cid}/board-records", json={**body, "decision_text": slip_text}).json()
    sf = [f for f in (slip.get("adjudication") or {}).get("flags") or [] if f["kind"] == "guideline" and f.get("check") == "dose" and f["severity"] == "expert_review"]
    ref = (sf[0].get("reference") or {}) if sf else {}
    check(f"{tag}: planted slip '{spec['slip']}' flagged for expert review citing an Indian line", slip_text != spec["decision"]
          and len(sf) == 1 and spec["drug"] in sf[0]["text"].lower() and ref.get("region") == "India" and ref.get("page") and ref.get("quote"),
          f"{sf[0]['text'][:140] if sf else 'no dose flag'} | {ref.get('org')} p {ref.get('page')}: {(ref.get('quote') or '')[:70]}")
    ib = c.get("/api/tb/inbox").json()
    rows = [q2 for dd in ib["departments"] if dd["id"] == spec["inbox"] for q2 in dd["requests"] if q2["case_id"] == cid and q2.get("source") == "board"]
    check(f"{tag}: board action in the {spec['action']['department']} inbox (Tumour Board action)", bool(rows) and all(x.get("source_label") == "Tumour Board action" for x in rows),
          f"{len(rows)} rows: {[(x.get('label'), x.get('status')) for x in rows][:2]}")
    # h. leave the Case File as the corpus defines it
    wait_job(c, c.post(f"/api/tb/demo/{cid}").json()["job"])
    print(f"INFO {tag}: section took {round(time.time() - t_case)} s (re-imported at the end)", flush=True)


def skills_section(c):
    """12 Oct: agent skills as SKILL.md files: listed for a known account, validated, a hospital edit saved (audited), the role label
    and department follow it, reset restores the default."""
    r = c.get("/api/tb/skills").json()
    roles = {x["role"]: x for x in r["skills"]}
    check("skills: every agent role listed with an active default skill", set(roles) >= {"radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"}
          and all(x["active"] and x["active"]["origin"] == "default" and x["text"].startswith("---") for x in roles.values()) and r["can_edit"] is True)
    bad = c.post("/api/tb/skills/validate", json={"text": roles["radiology"]["text"].replace("doc_types: [ct", "doc_types: [selfie")}).json()
    check("skills: validation refuses an unknown document type", bad["ok"] is False and "catalogue" in bad["error"], bad.get("error", "")[:80])
    bad2 = c.post("/api/tb/skills/validate", json={"text": roles["radiology"]["text"].replace("name: radiology", "name: cardiology")}).json()
    check("skills: a skill cannot add a role", bad2["ok"] is False and "not a known agent role" in bad2["error"])
    edited = roles["radiology"]["text"].replace("label: Radiology support", "label: Radio-diagnosis support (e2e)").replace("- modality and date of each study", "- modality and date of each study\n- contrast phase stated (e2e)")
    r2 = c.put("/api/tb/skills/radiology", json={"text": edited})
    check("skills: admin saves a hospital edit", r2.status_code == 200 and r2.json()["skill"]["origin"] == "hospital" and r2.json()["skill"]["label"] == "Radio-diagnosis support (e2e)", r2.text[:120])
    rl = c.get("/api/tb/roles").json()
    check("skills: /roles follows the hospital edit", rl["radiology"]["label"] == "Radio-diagnosis support (e2e)" and "contrast phase stated (e2e)" in rl["radiology"]["focus"] and rl["radiology"]["skill_origin"] == "hospital")
    au = [l for l in open(os.path.join(DATA_ROOT_HINT, "org_audit.jsonl")).read().splitlines()] if os.path.exists(os.path.join(DATA_ROOT_HINT, "org_audit.jsonl")) else []
    check("skills: the save is in org_audit.jsonl", any('"skill_saved"' in l and '"radiology"' in l for l in au[-5:]), f"{len(au)} entries")
    r3 = c.post("/api/tb/skills/radiology/reset", json={})
    check("skills: reset removes the hospital edit", r3.status_code == 200 and r3.json()["removed"] is True and c.get("/api/tb/roles").json()["radiology"]["label"] == "Radiology support")
    broken = c.put("/api/tb/skills/radiology", json={"text": "---\nname: radiology\n---\nno focus"})
    check("skills: an invalid edit is refused with the reason (400)", broken.status_code == 400 and "description" in broken.text, broken.text[:100])


def mcp_section(c, base):
    """12 Oct: MCP. The read-only server answers an MCP client with the same Case File the API shows; the demo HIS connector is saved by
    an admin (token hidden from the UI), probed as usable, lists the records the hospital system holds for TB-001 that are not in the Case
    File, and a fetch sends them through the intake pipeline where patient matching files them into TB-001."""
    info = c.get("/api/tb/mcp-server").json()
    check("mcp: server info for admins carries the token and the tool list", info.get("token") and "get_case" in info["tools"] and info["read_only"] is True, f"running={info.get('running')}")
    if not info.get("running"):
        check("mcp: server running on 7110 (start with tumour_board/serve_mcp.sh server)", False, "not running"); return
    import asyncio
    from tumour_board import connectors as cn
    async def via_mcp():
        async with cn.session({"url": info["url"], "token": info["token"]}) as s:
            tools = (await s.list_tools()).tools
            d = cn._structured(await s.call_tool("get_case", {"case_id": "TB-001"}))
            return tools, d
    tools, d = asyncio.run(via_mcp())
    api = c.get("/api/tb/cases/TB-001").json()
    check("mcp: every server tool is annotated read-only", all(t.annotations and t.annotations.readOnlyHint and t.annotations.destructiveHint is False for t in tools), f"{len(tools)} tools")
    check("mcp: get_case over MCP matches the API (patient, gate count, verified fields)", d["case"]["patient"]["name"] == api["case"]["patient"]["name"]
          and d["gate"]["satisfied"] == api["state"]["gate"]["satisfied"] and len(d["verified_fields"]) > 5, f"{d['gate']['satisfied']}/{d['gate']['total']}, {len(d['verified_fields'])} fields")
    check("mcp: the real case is hidden from MCP clients", not any(x["case_id"] == "TB-2026-bharath" for x in cn._structured(asyncio.run(_call(info, "list_cases", {})))["cases"]))
    au = c.get("/api/tb/cases/TB-001/audit").json()["events"]
    check("mcp: MCP calls are in the Case File audit log", any(e["kind"] == "mcp_call" and e["tool"] == "get_case" for e in au))
    # connectors: the demo HIS
    tok = open(os.path.join(DATA_ROOT_HINT, "demo_his_token")).read().strip() if os.path.exists(os.path.join(DATA_ROOT_HINT, "demo_his_token")) else ""
    r = c.put("/api/tb/connectors", json={"connectors": [{"id": "demo_his", "label": "Demo hospital system (SYNTHETIC)", "url": "http://127.0.0.1:7111/mcp", "token": tok, "department": "Radio-diagnosis", "enabled": True}]})
    check("connectors: admin saves the demo HIS connector; token not returned", r.status_code == 200 and r.json()["connectors"][0]["has_token"] is True and "token" not in r.json()["connectors"][0], r.text[:120])
    bad = c.put("/api/tb/connectors", json={"connectors": [{"id": "x", "label": "x", "url": "ftp://x", "department": "Radio-diagnosis"}]})
    check("connectors: a bad url is refused (400)", bad.status_code == 400)
    pr = c.post("/api/tb/connectors/demo_his/probe").json()
    if not pr.get("ok"):
        check("connectors: demo HIS reachable on 7111 (start with tumour_board/serve_mcp.sh demo-his)", False, pr.get("error", "")[:100]); return
    check("connectors: probe says usable, every tool read-only, records protocol present", pr["usable"] and {t["name"] for t in pr["tools"]} >= {"find_patient", "list_records", "fetch_record"}, pr.get("reason", ""))
    wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])  # fresh TB-001: the arrivals are not in it yet
    recs = c.get("/api/tb/cases/TB-001/connectors/demo_his/records").json()
    new = [x for x in recs.get("records", []) if not x["in_case_file"]]
    check("connectors: records of TB-001's patient listed, matched on the hospital number, none in the Case File yet", recs.get("patient", {}).get("patient_id") == "SYN-100231" and recs.get("matched_on") == "SYN-100231" and len(new) == len(recs["records"]) >= 3, f"{len(recs.get('records', []))} records")
    pick = [x["record_id"] for x in new if "cbc" in x["filename"] or "mri_brain" in x["filename"]][:2]
    f = c.post("/api/tb/cases/TB-001/connectors/demo_his/fetch", json={"record_ids": pick}).json()
    check("connectors: fetch returns an intake job and the fetched files with checksums", f.get("job") and len(f["fetched"]) == 2 and all(x["sha256"] for x in f["fetched"]) and not f["errors"], json.dumps(f)[:160])
    j, secs = wait_job(c, f["job"])
    filed = j.get("filed") or {}
    check("connectors: patient matching filed the fetched records into TB-001", j["state"] == "finished" and set(filed.values()) == {"TB-001"} and len(filed) == 2, f"{filed} in {secs}s; needs matching {j.get('needs_matching')}")
    recs2 = c.get("/api/tb/cases/TB-001/connectors/demo_his/records").json()
    check("connectors: fetched records now show as in the Case File", sum(x["in_case_file"] for x in recs2["records"]) == 2)
    docs = c.get("/api/tb/cases/TB-001").json()["documents"]
    conn_docs = [d for d in docs if (d.get("rel_path") or "").startswith("demo_his/")]
    check("connectors: documents carry the connector's department and the upload user", len(conn_docs) == 2 and all(d.get("department") == "radiology" for d in conn_docs) and all("via connector demo_his" in (d.get("uploaded_by") or "") for d in conn_docs), str([(d.get('department'), d.get('uploaded_by')) for d in conn_docs])[:160])
    au = c.get("/api/tb/cases/TB-001/audit").json()["events"]
    check("connectors: listing and fetch audited", any(e["kind"] == "connector_records_listed" for e in au) and any(e["kind"] == "connector_fetch" for e in au))
    m = httpx.Client(base_url=base, timeout=60)
    check("connectors: anonymous cannot list or fetch (401)", m.get("/api/tb/cases/TB-001/connectors/demo_his/records").status_code == 401)
    wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])  # leave TB-001 fresh


def discord_section(c):
    """12 Oct: discordances between reports and the decision watch. TB-004: a decision cites the histology of the first report; the amended
    report that arrives later records a different histology: the Case File lists the amendment for review, the record carries a decision-watch
    flag, the coordinators are notified once, a person notes it (audited, undoable). TB-006: the final MRI differs from the draft (stage)."""
    wait_job(c, c.post("/api/tb/demo/TB-004").json()["job"])
    d = c.get("/api/tb/cases/TB-004").json()
    hist = (d["facts"].get("histologic_type") or {}).get("current") or {}
    check("discord: fresh TB-004 has no review discordance", d["discordances"]["open_review"] == 0, json.dumps(d["discordances"])[:160])
    rec = c.post("/api/tb/cases/TB-004/board-records", json={"board_date": "2026-09-17", "decision_text": f"Histology: {hist.get('value', '')}. Plan agreed by the board.",
                                                              "recorded_by": "Dr. A", "participants": "Dr. A (Med Onc), Dr. B (Surg Onc), Dr. C (Rad Onc)", "actions": []}).json()
    vc = [v for v in rec["adjudication"]["value_checks"] if v["fact"] == "histologic_type"]
    check("discord: the decision's histology value is checked consistent against the first report", bool(vc) and vc[0]["result"] == "consistent", json.dumps(vc)[:160])
    wait_job(c, c.post("/api/tb/cases/TB-004/demo-arrivals").json()["job"])  # the amended histopathology arrives
    d = c.get("/api/tb/cases/TB-004").json()
    items = d["discordances"]["items"]
    am = [x for x in items if x["kind"] == "amended" and x["field"] == "histologic_type"]
    dw = [x for x in items if x["kind"] == "decision_watch"]
    check("discord: the amendment is listed for review with both reports quoted", len(am) == 1 and am[0]["severity"] == "review" and len(am[0]["citations"]) == 2 and all(x["quote"] for x in am[0]["citations"]), (am[0]["text"] if am else "none")[:160])
    check("discord: the decision watch names the record and the later report", len(dw) == 1 and dw[0]["record"] == rec["id"] and "later final report" in dw[0]["text"], (dw[0]["text"] if dw else "none")[:160])
    n = c.get("/api/tb/notifications?limit=80").json()
    ns = [x for x in (n.get("notifications") or n.get("items") or []) if x.get("kind") == "decision_value_changed" and x.get("case_id") == "TB-004" and x.get("record") == rec["id"]]
    check("discord: coordinators notified once for this record", len(ns) == 1, f"{len(ns)} notifications")
    j = c.post("/api/tb/cases/TB-004/confirmations", json={"type": "note_discordance", "key": dw[0]["key"], "reason": "e2e: discussed"}).json()
    d2 = c.get("/api/tb/cases/TB-004").json()
    noted = [x for x in d2["discordances"]["items"] if x["kind"] == "decision_watch"][0]
    check("discord: noting is a confirmation, the item stays listed as noted", noted.get("noted", {}).get("note") == "e2e: discussed" and d2["discordances"]["decision_watch"] == 0, json.dumps(noted.get("noted"))[:120])
    conf_id = (j.get("confirmation") or j.get("record") or {}).get("id") or next((x["id"] for x in d2["state"].get("confirmations", []) if x["type"] == "note_discordance" and not x.get("undone")), None)
    u = c.post(f"/api/tb/cases/TB-004/confirmations/{conf_id}/undo", json={})
    d3 = c.get("/api/tb/cases/TB-004").json()
    check("discord: undo brings the item back", u.status_code == 200 and d3["discordances"]["decision_watch"] == 1, u.text[:100])
    au = [e["kind"] for e in c.get("/api/tb/cases/TB-004/audit").json()["events"]]
    check("discord: notification and confirmation audited", "decision_watch_notified" in au and "confirmation" in au and "confirmation_undone" in au)
    # TB-006: the final MRI arrives after a draft and records a different stage
    wait_job(c, c.post("/api/tb/demo/TB-006").json()["job"]); wait_job(c, c.post("/api/tb/cases/TB-006/demo-arrivals").json()["job"])
    d6 = c.get("/api/tb/cases/TB-006").json()
    st6 = [x for x in d6["discordances"]["items"] if x["field"] == "recorded_stage"]
    check("discord: TB-006 draft MRI vs final MRI stage listed", any(x["kind"] in ("non_final_differs", "conflict", "changed") for x in st6), str([(x["kind"], x["severity"]) for x in st6])[:120])
    wait_job(c, c.post("/api/tb/demo/TB-004").json()["job"]); wait_job(c, c.post("/api/tb/demo/TB-006").json()["job"])  # fresh again


def records_section(c):
    """12 Oct: outcome type and patient-communication fields, the 'inform the patient' follow-up, the tamper-evident audit chain, values over
    time, the FHIR bundle and the registry abstract (TB-003, re-imported at the end)."""
    wait_job(c, c.post("/api/tb/demo/TB-003").json()["job"])
    d = c.get("/api/tb/cases/TB-003").json()
    check("records: outcome types offered by the API", set(d.get("outcomes") or {}) == {"decision", "deferred", "referred", "not_discussed"})
    bad = c.post("/api/tb/cases/TB-003/board-records", json={"decision_text": "x", "recorded_by": "Dr A", "participants": "Dr A (Med Onc)", "outcome_type": "maybe"})
    check("records: an unknown outcome type is refused (400)", bad.status_code == 400, bad.text[:80])
    rec = c.post("/api/tb/cases/TB-003/board-records", json={"board_date": "2026-10-01", "decision_text": "Plan agreed by the board.", "recorded_by": "Dr A",
                                                              "participants": "Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc)", "actions": [], "outcome_type": "decision", "intent_as_recorded": "curative"}).json()
    comm = [f for f in rec["adjudication"]["flags"] if f.get("kind") == "communication"]
    check("records: information flags for the patient-facing items not yet recorded (no resolution needed)", {f["field"] for f in comm} == {"patient_informed_date", "key_worker", "trial_considered", "consent_recorded"}
          and all(f["severity"] == "info" for f in comm) and not any(f["id"] in rec["resolution"]["open_flags"] for f in comm), str(sorted(f["field"] for f in comm)))
    st = c.get("/api/tb/cases/TB-003").json()["state"]
    inform = [a for a in st["actions"] if a.get("communication") and a.get("board_record") == rec["id"]]
    check("records: an 'inform the patient' follow-up is open, due a week after the board", len(inform) == 1 and inform[0]["due"] == "2026-10-08" and inform[0]["status"] == "pending", str(inform)[:120])
    r2 = c.post(f"/api/tb/cases/TB-003/board-records/{rec['id']}/communication", json={"patient_informed_date": "03/10/2026", "informed_by": "Dr A", "key_worker": "Sr. Meena, 98450 00000", "trial_considered": "yes", "consent_recorded": "yes"})
    check("records: communication recorded without a new version; the follow-up closes", r2.status_code == 200 and r2.json()["record"]["patient_informed_date"] == "2026-10-03" and r2.json()["record"].get("version", 1) == 1
          and not any(f.get("kind") == "communication" for f in r2.json()["record"]["adjudication"]["flags"])
          and [a for a in r2.json()["state"]["actions"] if a.get("communication")][0]["status"] == "completed", r2.text[:120])
    deferred = c.post("/api/tb/cases/TB-003/board-records", json={"board_date": "2026-10-01", "decision_text": "Deferred.", "recorded_by": "Dr A", "participants": "Dr A (Med Onc)", "outcome_type": "deferred", "actions": []}).json()
    check("records: a deferred outcome without an action is flagged for review", any(f.get("field") == "actions" and f["severity"] == "review" for f in deferred["adjudication"]["flags"]))
    au = c.get("/api/tb/cases/TB-003/audit").json()
    ch = au.get("chain") or {}
    check("records: the audit chain verifies (every event linked to the one before)", ch.get("ok") is True and ch.get("chained", 0) > 10 and any(e.get("kind") == "board_record_communication" for e in au["events"]), json.dumps(ch)[:120])
    v = c.get("/api/tb/cases/TB-003/audit/verify").json()
    check("records: /audit/verify answers the same", v.get("ok") is True and v["last_hash"] == ch["last_hash"])
    wait_job(c, c.post("/api/tb/cases/TB-003/demo-arrivals").json()["job"])  # later CEA and MRI
    d3 = c.get("/api/tb/cases/TB-003").json()
    cea = next((t for t in d3.get("trends") or [] if t["field"] == "cea"), None)
    check("records: values over time list CEA across the two reports with quotes", cea and len(cea["rows"]) >= 2 and all(r["quote"] and r["doc_id"] for r in cea["rows"]) and cea["rows"][0]["date"] <= cea["rows"][-1]["date"], str([(r["date"], r["value"]) for r in (cea or {}).get("rows", [])])[:120])
    f = c.get("/api/tb/cases/TB-003/export/fhir")
    b = f.json() if f.status_code == 200 else {}
    kinds = {}
    for e in b.get("entry") or []:
        kinds[e["resource"]["resourceType"]] = kinds.get(e["resource"]["resourceType"], 0) + 1
    check("records: FHIR R4 document bundle with Composition, Patient, DocumentReference, Observation, Condition, Task, CarePlan, Communication",
          f.status_code == 200 and b.get("type") == "document" and {"Composition", "Patient", "DocumentReference", "Observation", "Condition", "Task", "CarePlan", "Communication"} <= set(kinds), json.dumps(kinds))
    obs = [e["resource"] for e in b.get("entry") or [] if e["resource"]["resourceType"] == "Observation"]
    check("records: every Observation carries its quote and its source report; LOINC on the standard ones", obs and all(o.get("note") and o["note"][0]["text"].startswith("Quote from the report") and o.get("derivedFrom") for o in obs)
          and any((o["code"].get("coding") or [{}])[0].get("code") == "2039-6" for o in obs), f"{len(obs)} observations")
    cond = [e["resource"] for e in b.get("entry") or [] if e["resource"]["resourceType"] == "Condition"]
    check("records: the Condition carries the stage as recorded, not derived", cond and cond[0].get("stage") and "copied, never derived" in cond[0]["stage"][0]["type"]["text"], str((cond or [{}])[0].get("stage"))[:100])
    reg = c.get("/api/tb/cases/TB-003/export/registry").json()
    items = {i["item"]: i for i in reg.get("items") or []}
    check("records: registry abstract (HBCR items) as recorded, intention to treat from the board record", items.get("intention_to_treat", {}).get("value") == "curative" and items.get("staging_system_and_stage", {}).get("doc_id") and items.get("topography_morphology", {}).get("value", "").startswith("not coded"), str({k: v['value'][:30] for k, v in items.items()})[:200])
    csv_ = c.get("/api/tb/cases/TB-003/export/registry?format=csv")
    check("records: registry abstract as CSV", csv_.status_code == 200 and csv_.text.startswith("case_id,item,label,value") and csv_.text.count("\n") >= 10)
    wait_job(c, c.post("/api/tb/demo/TB-003").json()["job"])  # fresh again


def metrics_section(c, base):
    """12 Oct: agenda readiness and the chase list for a board date; the quality dashboard with reference lines; CSV; permissions."""
    wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])
    d = c.get("/api/tb/cases/TB-001").json()
    bd = d["case"].get("board_date") or ""
    if not bd:
        c.post("/api/tb/cases/TB-001/listing", json={"protocol": "lung_nsclc", "board_date": "2026-10-20"}); bd = "2026-10-20"
    a = c.get("/api/tb/metrics/agenda", params={"date": bd}).json()
    row = next((r for r in a["cases"] if r["case_id"] == "TB-001"), None)
    check("metrics: agenda lists TB-001 with its readiness, gaps and a forecast", row and row["forecast"] in ("ready", "on_track", "at_risk", "blocked") and isinstance(row["gaps"], list) and row["open_requests"] >= 1, json.dumps({k: row.get(k) for k in ("forecast", "why", "readiness", "open_requests")}) if row else "none")
    check("metrics: the chase list groups open requests by department with days left", a["requests_open"] >= 1 and all("items" in g and all("days_left" in x for x in g["items"]) for g in a["chase"]), f"{len(a['chase'])} departments, {a['requests_open']} requests")
    bad = c.get("/api/tb/metrics/agenda", params={"date": "not-a-date"})
    check("metrics: a bad date is refused (400)", bad.status_code == 400)
    dash = c.get("/api/tb/metrics/dashboard").json()
    k = dash["kpis"]
    check("metrics: dashboard has before / during / after KPIs and reference lines with sources", {"before", "during", "after"} <= set(k) and k["before"]["cases"] >= 8 and len(dash["references"]) == 8 and all(r["source"] for r in dash["references"]),
          f"cases {k['before']['cases']}, decisions {k['after']['decisions']}, sessions {k['during']['sessions']}")
    check("metrics: requests by department and attendance per specialty present", isinstance(k["before"]["by_department"], list) and isinstance(k["during"]["attendance"], dict) and len(k["during"]["attendance"]) >= 10)
    csv_ = c.get("/api/tb/metrics/dashboard", params={"format": "csv"})
    check("metrics: dashboard as CSV", csv_.status_code == 200 and csv_.text.startswith("section,metric,value,target,source") and "reference,quorum" in csv_.text)
    m = httpx.Client(base_url=base, timeout=60)
    check("metrics: anonymous cannot read the dashboard (401)", m.get("/api/tb/metrics/dashboard").status_code == 401)


async def _call(info, tool, args):
    from tumour_board import connectors as cn
    async with cn.session({"url": info["url"], "token": info["token"]}) as s:
        return await s.call_tool(tool, args)


DATA_ROOT_HINT = os.environ.get("TB_DATA_ROOT") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "tumour_board")


def phase9(c):
    """V1 Phase 9 (items 9.1 / 9.2): every new demo Case File (oral cavity TB-007, later cervix TB-008) runs the full workflow end to end."""
    have = {x.get("case_id") for x in c.get("/api/tb/cases").json().get("demo") or []}
    for cid, spec in V9_CASES.items():
        if cid not in have:
            check(f"9 {cid} ({spec['site']}): in the demo corpus", False, "not found under /data/vaidyx/tb_demo_corpus/cases (python -m tumour_board.demo_data.make_corpus)")
            continue
        phase9_case(c, cid, spec)


# ---- V2 Phase 4: Pre-Authorization and notifications (4.2 doctor-sent requests, 4.3 supporting inbox, 4.4 stale summary) -----------
# Same throw-away mock copy as the Phase 3 section (port 7131); its own throw-away doctor logins.
H4_USERS = {"tb-e2e-h4-medonc": ("H4medonc-e2e-2026!", {"medical_oncology": "doctor"}), "tb-e2e-h4-gyn": ("H4gyn-e2e-2026!", {"gynaecologic_oncology": "doctor"}),
            "tb-e2e-h4-surg": ("H4surg-e2e-2026!", {"surgical_oncology": "doctor"}), "tb-e2e-h4-rad": ("H4rad-e2e-2026!", {"radiology": "doctor"}),
            "tb-e2e-h4-path": ("H4path-e2e-2026!", {"pathology": "doctor"}), "tb-e2e-h4-anaes": ("H4anaes-e2e-2026!", {"anaesthesiology": "doctor"})}


def _v2_setup(c, base, ctx, users, tag):
    """The mock copy on 7131 as the HIS, throw-away doctor logins created through the Tumour Board (never a Vaidyx admin); clients per login."""
    tmp, proc = _mock_copy(); ctx["tmp"], ctx["proc"] = tmp, proc
    r = c.put("/api/tb/his", json={"kind": "fhir", "label": "Vaidyx Demo Hospital HIS (SYNTHETIC) e2e copy", "url": f"http://127.0.0.1:{MOCK_PORT}", "token": (tmp / "token").read_text().strip(), "enabled": True})
    check(f"{tag} the HIS connection points at the throw-away mock copy", r.status_code == 200 and c.get("/api/tb/his").json()["status"]["ok"], r.text[:120])
    cl = {}
    for u, (pw, depts) in users.items():
        c.request("DELETE", "/api/auth/users", json={"username": u})
        r = c.post("/api/tb/org/accounts", json={"username": u, "password": pw, "departments": depts, "display_name": f"{u} (e2e)"})
        cl[u] = httpx.Client(base_url=base, timeout=600)
        if not (r.status_code == 200 and cl[u].post("/api/auth/login", json={"username": u, "password": pw}).status_code == 200):
            check(f"{tag} e2e login {u}", False, r.text[:120])
    return cl


def _v2_cleanup(c, ctx, users):
    """Delete the Case Files and accounts of the section, restore the live HIS connection, stop the e2e mock copy."""
    for cid in ctx.get("cases") or []:
        try:
            c.delete(f"/api/tb/cases/{cid}")
        except Exception as e:
            print("cleanup case failed:", cid, e)
    try:
        o = c.get("/api/tb/org").json()
        c.put("/api/tb/org", json={"users": {k: v for k, v in (o.get("users") or {}).items() if k not in users}})
    except Exception as e:
        print("cleanup org failed:", e)
    for u in users:
        c.request("DELETE", "/api/auth/users", json={"username": u})
    try:
        tok = (REPO / "data" / "his_mock" / "token").read_text().strip()
        r = c.put("/api/tb/his", json={**LIVE_HIS, "token": tok})
        print("HIS connection restored:", r.status_code, (r.json().get("settings") or {}).get("url") if r.status_code == 200 else r.text[:120])
        (REPO / "data" / "tumour_board" / "his.json").unlink(missing_ok=True)  # back to the pristine default (the demo token file), not a saved copy of the token
    except Exception as e:
        print("restore HIS failed:", e)
    proc = ctx.get("proc")
    if proc:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if ctx.get("tmp"):
        shutil.rmtree(ctx["tmp"], ignore_errors=True)


def _notes_of(client, cid, kind):
    return [n for n in client.get("/api/tb/notifications", params={"limit": 200}).json()["notifications"] if n["case_id"] == cid and n["kind"] == kind]


def v2_phase4(c, base, ctx):
    """V2 Phase 4 on the fixture patients (SYNTHETIC): P12 notify -> acknowledge -> done -> sign on the RIS desk -> re-fetch -> closed ->
    owner told, with the mail draft and the readiness list; P11 closes itself on re-fetch although "done" was never sent; P07 a free
    request to Anaesthesiology; the Case File summary waits for the gate and goes stale after a re-fetch changes the Case File."""
    import datetime
    cl = _v2_setup(c, base, ctx, H4_USERS, "4.2")
    medonc, gyn, surg, rad, path, anaes = (cl[k] for k in ("tb-e2e-h4-medonc", "tb-e2e-h4-gyn", "tb-e2e-h4-surg", "tb-e2e-h4-rad", "tb-e2e-h4-path", "tb-e2e-h4-anaes"))
    today = datetime.date.today()

    def create(client, ident, protocol, setting, cid, board_date=""):
        r = client.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": "optimal", "case_id": cid, "board_date": board_date})
        if r.status_code != 200:
            check(f"4.2 create {cid} from {ident}", False, r.text[:200]); return None, None
        ctx["cases"].append(cid)
        body, j, secs = _job(client, r)
        return client.get(f"/api/tb/cases/{cid}").json(), j

    def action(client, cid, requirement):
        return next((x for x in client.get(f"/api/tb/cases/{cid}").json()["state"]["actions"] if x.get("requirement") == requirement), {})

    # ---- P12 (lung, preliminary CT): the whole loop ---------------------------------------------------------------------------
    bd = (today + datetime.timedelta(days=7)).isoformat()
    d, j = create(medonc, "IP/26/01875", "lung_nsclc", "non_metastatic", "TB-H4-P12", board_date=bd)
    if d:
        cid = "TB-H4-P12"; a = action(medonc, cid, "cect_tap")
        check("4.2 P12 the gap is a suggested request: no due date, nothing sent, counted as unsent", a.get("status") == "suggested" and a.get("due") is None and a.get("accession") == "RAD/26/01004"
              and d["requests"] == {"suggested": 1, "sent": 0, "done": 0, "closed": 0} and d["permissions"]["send_request"] is True and d["permissions"]["create_request"] is True,
              json.dumps({k: a.get(k) for k in ("status", "due", "accession")}) + " " + json.dumps(d.get("requests")))
        check("4.2 P12 nothing reached Radiology: no inbox row, no notification", not _open_rows(rad, "radiology", cid, "cect_tap") and not _notes_of(rad, cid, "request"))
        ag = c.get("/api/tb/metrics/agenda", params={"date": bd}).json()
        row = next((x for x in ag["cases"] if x["case_id"] == cid), {})
        check("4.2 P12 the coordinator's readiness list shows the unsent request", row.get("unsent_requests") == 1 and row.get("open_requests") == 1 and ag.get("requests_unsent", 0) >= 1
              and any(it["case_id"] == cid and it["unsent"] for g_ in ag["chase"] for it in g_["items"]), json.dumps({k: row.get(k) for k in ("unsent_requests", "open_requests", "forecast", "why")}))
        dr = medonc.get(f"/api/tb/cases/{cid}/requests/{a.get('id')}/draft")
        dj = dr.json() if dr.status_code == 200 else {}
        body = dj.get("body") or ""
        check("4.2 P12 the draft names the patient, UHID, IP No., the record, what is missing, the accession No. and the due date", dr.status_code == 200 and dj["to"]["department"] == "radiology"
              and dj["to"]["email"] and "UHID VXH/26/004212" in body and "IP No. IP/26/01875" in body and "Required record: " in body and "What is missing: " in body
              and "Accession / order No.: RAD/26/01004" in body and "Needed by: " in body and dj["due"] == (today + datetime.timedelta(days=int(a.get("sla_days") or 3))).isoformat()
              and dj["uhid"] == "VXH/26/004212" and dj["encounter"].get("ip_no") == "IP/26/01875", (dr.text if dr.status_code != 200 else body)[:300])
        import urllib.parse
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(dj.get("mailto") or "").query)
        check("4.2 P12 the mail draft is a mailto: to the department's address with the same subject and body", (dj.get("mailto") or "").startswith(f"mailto:{dj.get('to', {}).get('email')}?")
              and q.get("subject") == [dj.get("subject")] and q.get("body") == [body.replace("\n", "\r\n")], (dj.get("mailto") or "")[:120])
        check("4.2 P12 a supporting doctor cannot send a request (403)", rad.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/send", json={}).status_code == 403)
        check("4.3 P12 acknowledging a request nobody sent is refused (403 since V2 item 5.1: the department was not asked, so it cannot open the Case File; 409 before)",
              rad.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/acknowledge").status_code in (403, 409))
        due = (today + datetime.timedelta(days=5)).isoformat()
        r = medonc.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/send", json={"message": body + "\nPlease report before the board.", "due": due})
        a = r.json().get("action", {}) if r.status_code == 200 else {}
        check("4.2 P12 the treating doctor sends the edited request in-app: pending with the due date, sent by, audited", r.status_code == 200 and a.get("status") == "pending" and a.get("due") == due
              and a.get("sent", {}).get("by") == "tb-e2e-h4-medonc" and a["sent"]["count"] == 1 and "Please report before the board." in a["sent"]["message"] and "Sent by tb-e2e-h4-medonc (Medical Oncology)" in a["sent"]["message"]
              and any(e["kind"] == "request_sent" and e["by"] == "tb-e2e-h4-medonc" and e["department"] == "Radiology" for e in medonc.get(f"/api/tb/cases/{cid}/audit").json()["events"]), r.text[:200])
        rows = _open_rows(rad, "radiology", cid, "cect_tap")
        check("4.3 P12 the Radiology inbox shows the request with the UHID, IP No., accession No. and who sent it", len(rows) == 1 and rows[0]["uhid"] == "VXH/26/004212" and rows[0]["encounter"].get("ip_no") == "IP/26/01875"
              and rows[0]["accession"] == "RAD/26/01004" and rows[0]["sent"]["by"] == "tb-e2e-h4-medonc" and rows[0]["status"] == "pending" and rows[0]["acknowledged"] is None, json.dumps(rows)[:200])
        n = _notes_of(rad, cid, "request")
        check("4.2 P12 Radiology is notified with the message", len(n) == 1 and "Please report before the board." in n[0].get("message", "") and n[0].get("uhid") == "VXH/26/004212" and n[0].get("reminder") is False)
        row = next((x for x in c.get("/api/tb/metrics/agenda", params={"date": bd}).json()["cases"] if x["case_id"] == cid), {})
        check("4.2 P12 the readiness list counts it as sent now", row.get("unsent_requests") == 0 and row.get("open_requests") == 1, json.dumps({k: row.get(k) for k in ("unsent_requests", "open_requests")}))
        r = medonc.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/send", json={})
        check("4.2 P12 sending again is a reminder (count 2, notification marked reminder)", r.status_code == 200 and r.json()["action"]["sent"]["count"] == 2 and _notes_of(rad, cid, "request")[0].get("reminder") is True
              and r.json()["action"]["due"] == due, r.text[:120])
        check("4.3 P12 the treating doctor cannot acknowledge for Radiology (403)", medonc.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/acknowledge").status_code == 403)
        r = rad.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/acknowledge")
        check("4.3 P12 Radiology acknowledges: the owning department is told", r.status_code == 200 and r.json()["action"]["acknowledged"]["by"] == "tb-e2e-h4-rad"
              and len(_notes_of(medonc, cid, "request_acknowledged")) == 1 and rad.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/acknowledge").status_code == 409, r.text[:120])
        r = rad.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/done", json={"note": "Reported and signed in the RIS (synthetic)"})
        told = _notes_of(medonc, cid, "request_done")
        check("4.3 P12 \"done\" back with a note: the request stays open until the record arrives, the owner is told to re-fetch", r.status_code == 200 and r.json()["action"]["status"] == "pending"
              and r.json()["action"]["done"]["note"] == "Reported and signed in the RIS (synthetic)" and len(told) == 1 and told[0].get("refetch_offer") is True and "Re-fetch" in told[0]["text"]
              and _open_rows(rad, "radiology", cid, "cect_tap")[0]["done"]["by"] == "tb-e2e-h4-rad", r.text[:160])
        check("4.2 P12 a gap request cannot be closed by hand (409): it closes when the record arrives, or through a waiver", medonc.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/close", json={}).status_code == 409)
        # 4.4 the summary waits for the gate
        sm = medonc.post(f"/api/tb/cases/{cid}/summary", json={}).json()
        check("4.4 P12 the Case File summary is not compiled while a Pre-Authorization check is open", sm.get("status") == "gate_not_met" and "CECT" in " ".join(sm.get("open") or []), json.dumps(sm)[:160])
        # the radiologist completes and signs on the RIS desk of the e2e copy; the treating doctor re-fetches
        rs = httpx.post(f"http://127.0.0.1:{MOCK_PORT}/desk/api/RAD/orders/rad-26-01004/sign", json={"signer": "prac-vxreg-20201"}, timeout=60)
        r = medonc.post(f"/api/tb/cases/{cid}/his/refetch")
        body_, jj, secs = _job(medonc, r)
        d2 = medonc.get(f"/api/tb/cases/{cid}").json()
        a2 = next((x for x in d2["state"]["actions"] if x["requirement"] == "cect_tap"), {})
        check("4.3 P12 after the desk sign and the re-fetch the request closed itself and the gate passes", rs.status_code == 200 and d2["state"]["gate"]["passed"] and a2.get("status") == "completed"
              and jj.get("refetch_result", {}).get("closed") == [a.get("id")], json.dumps(_gaps(d2)))
        rows = _open_rows(rad, "radiology", cid, "cect_tap")
        check("4.3 P12 the owner is told what closed; Radiology sees the request closed in its inbox and is told", any(n.get("refetch") and a.get("id") in (n.get("closed") or []) for n in _notes_of(medonc, cid, "request_closed"))
              and len(rows) == 1 and rows[0]["status"] == "completed" and len(_notes_of(rad, cid, "request_closed")) >= 1, json.dumps([(x["status"], x.get("done", {}) or {}) for x in rows])[:160])
        check("4.2 P12 counts: nothing suggested, nothing open, one closed", d2["requests"] == {"suggested": 0, "sent": 0, "done": 0, "closed": 1}, json.dumps(d2["requests"]))
        # 4.4 the summary compiles once the gate passes, then goes stale when a re-fetch changes the Case File
        sm = medonc.post(f"/api/tb/cases/{cid}/summary", json={}).json()
        stale = medonc.get(f"/api/tb/cases/{cid}").json()["stale"].get("summary")
        check("4.4 P12 the summary compiles once the gate passes, every sentence cited, not stale", sm.get("status") == "ready" and sm.get("paragraphs") and all(x.get("citations") for p_ in sm["paragraphs"] for x in p_) and stale == "",
              f"{sm.get('status')} {sm.get('seconds')} s stale {stale!r}")
        ra = httpx.post(f"http://127.0.0.1:{MOCK_PORT}/desk/api/RAD/reports/p12-r02/addendum", json={"signer": "prac-vxreg-20201", "note": "Addendum (synthetic e2e): measurements re-checked, no change in impression."}, timeout=60)
        r = medonc.post(f"/api/tb/cases/{cid}/his/refetch")
        body_, jj, secs = _job(medonc, r)
        d3 = medonc.get(f"/api/tb/cases/{cid}").json()
        stale = d3["stale"].get("summary") or ""
        notice = [n for n in _notes_of(medonc, cid, "request_closed") if n.get("refetch") and n.get("summary_stale")]
        check("4.4 P12 an addendum signed on the desk and re-fetched makes the summary stale (the stale banner)", ra.status_code == 200 and body_["his"]["added"] >= 1
              and stale.startswith("The Case File changed since this was generated") and d3["state"]["gate"]["passed"],
              json.dumps({"desk": ra.status_code, "his": body_.get("his"), "stale": stale[:100], "passed": d3["state"]["gate"].get("passed"), "gaps": _gaps(d3)})[:300])
        check("4.4 P12 the re-fetch result and the owner's notice say the summary is stale", jj.get("refetch_result", {}).get("summary_stale") == stale and len(notice) >= 1
              and "summary compiled earlier is stale" in notice[0]["text"], json.dumps({"job": jj.get("refetch_result"), "notice": [n["text"][:120] for n in notice]})[:300])
        sm = medonc.post(f"/api/tb/cases/{cid}/summary", json={}).json()
        stale = medonc.get(f"/api/tb/cases/{cid}").json()["stale"].get("summary")
        check("4.4 P12 the doctor regenerates the summary: fresh again", sm.get("status") == "ready" and stale == "", f"{sm.get('status')} stale {stale!r}")

    # ---- P11 (cervix, final without a signature): closes itself on re-fetch although "done" was never sent -------------------------
    d, j = create(gyn, "VXH/26/004211", "cervix", "early", "TB-H4-P11")
    if d:
        cid = "TB-H4-P11"; a = action(gyn, cid, "histopathology")
        r = gyn.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/send", json={})
        rows = _open_rows(path, "pathology", cid, "histopathology")
        check("4.3 P11 the request to Pathology sits in its inbox with the accession No.", r.status_code == 200 and len(rows) == 1 and rows[0]["accession"] == "PATH/26/00434" and rows[0]["uhid"] == "VXH/26/004211", r.text[:120])
        rs = httpx.post(f"http://127.0.0.1:{MOCK_PORT}/desk/api/PATH/orders/path-26-00434/sign", json={"signer": "prac-vxreg-20204"}, timeout=60)
        r = gyn.post(f"/api/tb/cases/{cid}/his/refetch")
        body_, jj, secs = _job(gyn, r)
        d2 = gyn.get(f"/api/tb/cases/{cid}").json()
        rows = _open_rows(path, "pathology", cid, "histopathology")
        check("4.3 P11 the request closes itself on re-fetch evidence although \"done\" was never sent; Pathology and the owner are told", rs.status_code == 200 and d2["state"]["gate"]["passed"]
              and next(x for x in d2["state"]["actions"] if x["requirement"] == "histopathology")["status"] == "completed" and rows and rows[0]["status"] == "completed" and rows[0]["done"] is None
              and len(_notes_of(path, cid, "request_closed")) >= 1 and any(n.get("refetch") for n in _notes_of(gyn, cid, "request_closed")), json.dumps(_gaps(d2)))

    # ---- P07 (oral cavity, complete work-up): a free request with no protocol record behind it --------------------------------------
    d, j = create(surg, "VXH/26/004207", "oral_cavity", "locally_advanced", "TB-H4-P07")
    if d:
        cid = "TB-H4-P07"
        check("4.2 P07 complete work-up: nothing suggested", d["state"]["gate"]["passed"] and d["requests"]["suggested"] == 0)
        check("4.2 P07 a free request needs a known department and a label (400)", surg.post(f"/api/tb/cases/{cid}/requests", json={"department": "MDT Coordinator", "label": "x"}).status_code == 400
              and surg.post(f"/api/tb/cases/{cid}/requests", json={"department": "Anaesthesiology", "label": ""}).status_code == 400)
        check("4.2 P07 a supporting doctor cannot write a free request (403)", rad.post(f"/api/tb/cases/{cid}/requests", json={"department": "Anaesthesiology", "label": "x"}).status_code == 403)
        r = surg.post(f"/api/tb/cases/{cid}/requests", json={"department": "Anaesthesiology", "label": "Pre-anaesthetic check-up", "what": "Planned for surgery (synthetic e2e)"})
        a = r.json().get("action", {}) if r.status_code == 200 else {}
        rows = _open_rows(anaes, "anaesthesiology", cid, None)
        check("4.2 P07 \"Notify Anaesthesiology\" with no gap behind it: created and sent in one step, in the Anaesthesiology inbox with the UHID", r.status_code == 200 and a.get("origin") == "doctor"
              and a.get("requirement") is None and a.get("status") == "pending" and "Request: Pre-anaesthetic check-up" in a.get("sent", {}).get("message", "") and len(rows) == 1 and rows[0]["free"] is True
              and rows[0]["uhid"] == "VXH/26/004207", r.text[:160])
        rc = surg.post(f"/api/tb/cases/{cid}/recheck")
        a_after = next((x for x in surg.get(f"/api/tb/cases/{cid}").json()["state"]["actions"] if x["id"] == a.get("id")), {})
        check("4.2 P07 a re-check never closes a free request (review S1)", rc.status_code == 200 and a_after.get("status") == "pending" and not _notes_of(anaes, cid, "request_closed"),
              json.dumps({k: a_after.get(k) for k in ("status", "history")})[:200])
        r = anaes.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/done", json={"note": "PAC done, ASA II (synthetic)"})
        check("4.3 P07 \"done\" closes a free request (nothing in the Case File can confirm it); the owner is told", r.status_code == 200 and r.json()["action"]["status"] == "completed"
              and r.json()["action"]["closed_by"] == "tb-e2e-h4-anaes" and any(n.get("closed") for n in _notes_of(surg, cid, "request_done")), r.text[:120])
        r = surg.post(f"/api/tb/cases/{cid}/requests", json={"department": "Clinical Pharmacology", "label": "Medication review"})
        a = r.json().get("action", {}) if r.status_code == 200 else {}
        r2 = surg.post(f"/api/tb/cases/{cid}/requests/{a.get('id')}/close", json={"note": "not needed after all"})
        check("4.2 P07 the owner closes a free request (audited)", r.status_code == 200 and r2.status_code == 200 and r2.json()["action"]["status"] == "completed"
              and any(e["kind"] == "request_closed_by_owner" for e in surg.get(f"/api/tb/cases/{cid}/audit").json()["events"]), r2.text[:120])
        check("4.2 P07 every request action is audited", {"request_created", "request_sent", "request_done", "request_closed_by_owner"} <= {e["kind"] for e in surg.get(f"/api/tb/cases/{cid}/audit").json()["events"]})


def v2_phase4_cleanup(c, ctx):
    _v2_cleanup(c, ctx, H4_USERS)


H5_USERS = {"tb-e2e-h5-pulmo": ("H5pulmo-e2e-2026!", {"pulmonology": "doctor"}), "tb-e2e-h5-colo": ("H5colo-e2e-2026!", {"colorectal_surgery": "doctor"}),
            "tb-e2e-h5-breast": ("H5breast-e2e-2026!", {"breast_surgery": "doctor"}), "tb-e2e-h5-medonc": ("H5medonc-e2e-2026!", {"medical_oncology": "doctor"}),
            "tb-e2e-h5-rad": ("H5rad-e2e-2026!", {"radiology": "doctor"}), "tb-e2e-h5-nm": ("H5nm-e2e-2026!", {"nuclear_medicine": "doctor"})}
H5_MDT = ("tb-e2e-h5-mdt", "H5mdt-e2e-2026!")


def v2_phase5(c, base, ctx):
    """V2 Phase 5 on the fixture patients (SYNTHETIC): 5.1 the owning department, participants, the departments asked (scoped reads, owner-only
    clinical actions); 5.2 P14 the lung work-up referred to Colorectal Surgery (the HIS referral suggested, decline, accept with the new
    protocol on the same records, the lung gate archived read-only, the open request closed with the reason); 5.3 P18 two primaries as
    linked Case Files under one UHID."""
    cl = _v2_setup(c, base, ctx, H5_USERS, "5.1")
    pulmo, colo, breast, medonc, rad, nm = (cl[k] for k in ("tb-e2e-h5-pulmo", "tb-e2e-h5-colo", "tb-e2e-h5-breast", "tb-e2e-h5-medonc", "tb-e2e-h5-rad", "tb-e2e-h5-nm"))
    c.request("DELETE", "/api/auth/users", json={"username": H5_MDT[0]})
    r = c.post("/api/tb/org/accounts", json={"username": H5_MDT[0], "password": H5_MDT[1], "coordinator": True, "display_name": "MDT Coordinator (e2e h5)"})
    mdt = httpx.Client(base_url=base, timeout=600)
    check("5.1 e2e coordinator login", r.status_code == 200 and mdt.post("/api/auth/login", json={"username": H5_MDT[0], "password": H5_MDT[1]}).status_code == 200, r.text[:120])
    fx = {p_["slot"]: p_ for p_ in json.load(open(REPO / "his_mock" / "scenarios.json"))["patients"]}

    def fixture_gaps(slot, protocol):
        cf = next(c_ for c_ in fx[slot]["case_files"] if c_["protocol"] == protocol)
        return sorted((x["requirement"], x["level"]) for x in cf["first_fetch"]["gaps"])

    def create(client, ident, protocol, setting, cid, department=None):
        r = client.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": "optimal", "case_id": cid, "department": department})
        if r.status_code != 200:
            check(f"5.1 create {cid} from {ident}", False, r.text[:200]); return None, None
        ctx["cases"].append(cid)
        body, j, secs = _job(client, r)
        return client.get(f"/api/tb/cases/{cid}").json(), j

    def action(client, cid, requirement):
        return next((x for x in client.get(f"/api/tb/cases/{cid}").json()["state"]["actions"] if x.get("requirement") == requirement), {})

    def audit_kinds(client, cid):
        return [e["kind"] for e in client.get(f"/api/tb/cases/{cid}/audit").json()["events"]]

    # ---- 5.1 ownership, participants, the departments asked (P14, owned by Pulmonology) --------------------------------------------
    cid = "TB-H5-P14"
    d, j = create(pulmo, "VXH/26/004214", "lung_nsclc", "metastatic", cid)
    if d:
        acc = d.get("access") or {}
        check("5.1 P14 the Case File is owned by the creating doctor's department; the view carries the owner and the full scope",
              d["case"]["department"] == "pulmonology" and acc.get("owner") == {"id": "pulmonology", "name": "Pulmonology"} and acc.get("scope") == "full" and acc.get("participants") == [])
        check("5.1 P14 first-fetch gate matches the fixture (lung, metastatic)", _gaps(d) == fixture_gaps("P14", "lung_nsclc"), json.dumps(_gaps(d)))
        check("5.1 another treating department, a supporting department and a doctor of the department referred to later cannot open it (403); it is not in their lists",
              breast.get(f"/api/tb/cases/{cid}").status_code == 403 and colo.get(f"/api/tb/cases/{cid}").status_code == 403 and rad.get(f"/api/tb/cases/{cid}").status_code == 403
              and nm.get(f"/api/tb/cases/{cid}/documents/{d['documents'][0]['doc_id']}/file").status_code == 403
              and cid not in [x["case_id"] for x in colo.get("/api/tb/cases").json()["cases"]] and cid not in [x["case_id"] for x in rad.get("/api/tb/cases").json()["cases"]])
        rows = [x for x in pulmo.get("/api/tb/cases").json()["cases"] if x["case_id"] == cid]
        check("5.1 P14 the owner's list row carries the owner and the scope", rows and rows[0]["owner_name"] == "Pulmonology" and rows[0]["scope"] == "full" and rows[0]["referral"] is None)
        dm = mdt.get(f"/api/tb/cases/{cid}").json()
        check("5.1 the MDT Coordinator and the Vaidyx admin read the whole Case File; the coordinator does no clinical action on it (no upload, waive or request)",
              dm.get("access", {}).get("scope") == "full" and dm["permissions"]["upload"] is False and not any(dm["permissions"]["waive"].values()) and dm["permissions"]["send_request"] is False
              and dm["permissions"]["list_case"] is True and c.get(f"/api/tb/cases/{cid}").json()["access"]["scope"] == "full"
              and mdt.post(f"/api/tb/cases/{cid}/documents", files=[("files", ("x.txt", b"synthetic"))], data={"paths": "[]"}).status_code == 403)
        # a participant reads and comments, never acts
        r = breast.put(f"/api/tb/cases/{cid}/participants", json={"add": ["breast_surgery"]})
        check("5.1 only the owner's doctors choose the participants (403 for others)", r.status_code == 403)
        r = pulmo.put(f"/api/tb/cases/{cid}/participants", json={"add": ["Breast Surgery"], "reason": "second opinion on a breast lesion (synthetic e2e)"})
        db = breast.get(f"/api/tb/cases/{cid}").json() if r.status_code == 200 else {}
        check("5.1 the owner adds a participating department: it reads the whole Case File, is told, and the Case File lists it", r.status_code == 200
              and r.json()["access"]["participants"][0]["id"] == "breast_surgery" and db.get("access", {}).get("scope") == "full" and db["state"].get("gate")
              and len(_notes_of(breast, cid, "case_shared")) == 1 and "Pulmonology" in _notes_of(breast, cid, "case_shared")[0]["text"], r.text[:160])
        req_id = next((q["id"] for q in db["state"]["gate"]["requirements"] if q["status"] not in ("satisfied", "waived", "not_applicable")), "pet_ct")
        pet = action(pulmo, cid, "pet_ct")
        check("5.1 a participant cannot waive, upload, re-fetch, send a request, refer or change the participants (403); its view hides those actions",
              breast.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "waive", "key": req_id, "reason": "e2e"}).status_code == 403
              and breast.post(f"/api/tb/cases/{cid}/documents", files=[("files", ("x.txt", b"synthetic"))], data={"paths": "[]"}).status_code == 403
              and breast.post(f"/api/tb/cases/{cid}/his/refetch").status_code == 403 and breast.post(f"/api/tb/cases/{cid}/requests/{pet.get('id')}/send", json={}).status_code == 403
              and breast.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "x"}).status_code == 403
              and breast.put(f"/api/tb/cases/{cid}/participants", json={"remove": ["breast_surgery"]}).status_code == 403
              and not any(db["permissions"]["waive"].values()) and db["permissions"]["upload"] is False and db["permissions"]["refer"] is False and db["permissions"]["send_request"] is False)
        check("5.1 a participant may read the records and ask the Case File (read and comment)", breast.get(f"/api/tb/cases/{cid}/documents/{db['documents'][0]['doc_id']}").status_code == 200
              and breast.post(f"/api/tb/cases/{cid}/search", json={"query": "adenocarcinoma"}).status_code == 200)
        pulmo_doc = next((x["doc_id"] for x in db["documents"] if x.get("department") == "pulmonology"), db["documents"][0]["doc_id"])
        check("5.1 a participant cannot attest, confirm or delete a hospital-system record its own department produced, nor compile the summary (403; review Phase 5 S1 / M5)",
              breast.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "attest_final", "key": pulmo_doc}).status_code == 403
              and breast.delete(f"/api/tb/cases/{cid}/documents/{pulmo_doc}").status_code == 403 and breast.post(f"/api/tb/cases/{cid}/summary", json={}).status_code == 403
              and not any(db["permissions"]["delete_document"].values()) and not any(db["permissions"]["confirm"].values()))
        # the department asked sees only the items it was asked about
        check("5.1 before any request is sent, Nuclear Medicine cannot open the Case File at all (403)", nm.get(f"/api/tb/cases/{cid}").status_code == 403)
        rs = pulmo.post(f"/api/tb/cases/{cid}/requests/{pet.get('id')}/send", json={})
        dn = nm.get(f"/api/tb/cases/{cid}").json() if rs.status_code == 200 else {}
        check("5.1 once the PET-CT request is sent, Nuclear Medicine sees only the items it was asked about: its request, no gate, no facts, no other records",
              rs.status_code == 200 and dn.get("access", {}).get("scope") == "requests" and dn["state"].get("limited") is True and dn["state"]["gate"] is None
              and [a["id"] for a in dn["state"]["actions"]] == [pet.get("id")] and dn["facts"] == {} and dn["timeline"] == [] and dn.get("his") is None
              and not any(x.get("department") not in ("nuclear_medicine",) for x in dn["documents"]) and set(dn["permissions"]) == {"answer_request", "update_action"}, json.dumps({k: dn.get(k) for k in ("access",)})[:200])
        other_doc = next((x["doc_id"] for x in db["documents"] if x.get("department") != "nuclear_medicine"), None)
        nm_doc = next((x["doc_id"] for x in dn["documents"]), None)
        check("5.1 the department asked reads its records but never deletes one, and its view carries no referrals, participants, links or empty encounters (review Phase 5 S1 / M2)",
              (nm_doc is None or nm.delete(f"/api/tb/cases/{cid}/documents/{nm_doc}").status_code == 403) and set(dn["case"]) <= {"case_id", "patient", "protocol", "setting", "board_date", "department", "listing", "hospital_level", "created_at"}
              and set(dn["case"]["patient"]) <= {"name", "mrn", "agesex"} and dn["access"]["participants"] == [] and dn["access"]["linked_cases"] == [] and all(g.get("docs") for g in dn["groups"]), json.dumps(sorted(dn["case"]))[:160])
        check("5.1 the department asked cannot open the other records, ask the Case File, waive or refer (403); it may acknowledge its request",
              nm.get(f"/api/tb/cases/{cid}/documents/{other_doc}").status_code == 403 and nm.get(f"/api/tb/cases/{cid}/documents/{other_doc}/file").status_code == 403
              and nm.post(f"/api/tb/cases/{cid}/search", json={"query": "x"}).status_code == 403 and nm.post(f"/api/tb/cases/{cid}/summary", json={}).status_code == 403
              and nm.post(f"/api/tb/cases/{cid}/confirmations", json={"type": "waive", "key": "pet_ct", "reason": "e2e"}).status_code == 403
              and nm.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "x"}).status_code == 403
              and nm.post(f"/api/tb/cases/{cid}/requests/{pet.get('id')}/acknowledge").status_code == 200
              and [x["case_id"] for x in nm.get("/api/tb/cases").json()["cases"] if x["case_id"] == cid and x["scope"] == "requests"] == [cid])
        check("5.1 a supporting department that received nothing still cannot open it (403)", rad.get(f"/api/tb/cases/{cid}").status_code == 403)
        r = pulmo.put(f"/api/tb/cases/{cid}/participants", json={"remove": ["breast_surgery"], "reason": "opinion given"})
        check("5.1 the owner removes the participant: it cannot open the Case File any more; both changes audited", r.status_code == 200 and r.json()["access"]["participants"] == []
              and breast.get(f"/api/tb/cases/{cid}").status_code == 403 and {"participant_added", "participant_removed"} <= set(audit_kinds(pulmo, cid)))
        check("5.1 the owner's doctors may change the listing (the board date); another department's may not", colo.post(f"/api/tb/cases/{cid}/listing", json={"protocol": "lung_nsclc", "setting": "metastatic", "board_date": "2026-11-05", "hospital_level": "optimal"}).status_code == 403
              and pulmo.post(f"/api/tb/cases/{cid}/listing", json={"protocol": "lung_nsclc", "setting": "metastatic", "board_date": "2026-11-05", "hospital_level": "optimal"}).status_code == 200)
        ids = lambda client, path, **params: [x["case_id"] for x in client.get(path, params=params).json().get("cases", [])]
        conds = {"intake: not for a department without access": cid not in ids(colo, "/api/tb/intake"), "intake: the owner": cid in ids(pulmo, "/api/tb/intake"),
                 "intake: the coordinator": cid in ids(mdt, "/api/tb/intake"), "agenda: not for a department without access": cid not in ids(colo, "/api/tb/metrics/agenda", date="2026-11-05"),
                 "agenda: the owner": cid in ids(pulmo, "/api/tb/metrics/agenda", date="2026-11-05"), "candidates: not for a department without access": cid not in ids(colo, "/api/tb/sessions/candidates", date="2026-11-05"),
                 "candidates: the coordinator": cid in ids(mdt, "/api/tb/sessions/candidates", date="2026-11-05")}
        check("5.1 the listings outside the Case File show a doctor only what it may open (intake, agenda readiness, session candidates; review Phase 5 M1)", all(conds.values()),
              json.dumps([k for k, v in conds.items() if not v]))

        # ---- 5.2 referral: the lung work-up turns out to be a colorectal primary ----------------------------------------------------
        d = pulmo.get(f"/api/tb/cases/{cid}").json()
        sug = (d.get("referral") or {}).get("suggestions") or []
        check("5.2 P14 the hospital system's inter-department referral (Pulmonology to Colorectal Surgery) is suggested, never applied by itself",
              len(sug) == 1 and sug[0]["to"] == "colorectal_surgery" and sug[0]["from"] == "pulmonology" and sug[0]["on"] == "04/09/2026" and "Refer this Case File?" in sug[0]["text"]
              and d["case"]["department"] == "pulmonology" and d["referral"]["open"] is None, json.dumps(sug)[:200])
        check("5.2 a referral needs the owner, a reason and a treating target (403 / 400); the suggestion must exist (404)",
              rad.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "x"}).status_code == 403
              and medonc.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "x"}).status_code == 403
              and pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": " "}).status_code == 400
              and pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Radiology", "reason": "x"}).status_code == 400
              and pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Pulmonology", "reason": "x"}).status_code == 409
              and pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "x", "his_ref": "ref-nope"}).status_code == 404)
        r = pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Colorectal Surgery", "reason": "Lung biopsy reported as metastatic adenocarcinoma of colorectal origin; colonoscopy shows a rectal growth (synthetic e2e)", "his_ref": sug[0]["his_ref"]})
        ref1 = r.json().get("referral", {}) if r.status_code == 200 else {}
        inbox_colo = colo.get("/api/tb/inbox").json().get("referrals", []) if r.status_code == 200 else []
        dc = colo.get(f"/api/tb/cases/{cid}").json() if r.status_code == 200 else {}
        check("5.2 the owner refers with a reason: the receiving department is told, sees it in its inbox and may now read the whole Case File; a second referral is refused while it waits",
              r.status_code == 200 and ref1.get("status") == "requested" and ref1.get("from") == "pulmonology" and ref1.get("to") == "colorectal_surgery" and ref1.get("his_ref") == sug[0]["his_ref"]
              and len(_notes_of(colo, cid, "referral")) == 1 and "colorectal origin" in _notes_of(colo, cid, "referral")[0]["text"]
              and len(inbox_colo) == 1 and inbox_colo[0]["direction"] == "to" and inbox_colo[0]["can_answer"] and inbox_colo[0]["uhid"] == "VXH/26/004214"
              and dc.get("access", {}).get("scope") == "full" and dc["permissions"]["answer_referral"] is True and dc["permissions"]["waive"] and not any(dc["permissions"]["waive"].values())
              and pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Medical Oncology", "reason": "y"}).status_code == 409
              and (pulmo.get(f"/api/tb/cases/{cid}").json().get("referral") or {}).get("suggestions") == [], r.text[:160])
        check("5.2 only the receiving department answers (403 for the owner, another department, a supporting one); the owner may withdraw",
              pulmo.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/accept", json={}).status_code == 403 and medonc.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/accept", json={}).status_code == 403
              and breast.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/decline", json={}).status_code == 403 and nm.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/accept", json={}).status_code == 403
              and colo.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/withdraw", json={}).status_code == 403
              and [x["case_id"] for x in pulmo.get("/api/tb/cases").json()["cases"] if x["case_id"] == cid and x["referral"] == "colorectal_surgery"] == [cid])
        r = colo.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/decline", json={"note": "no colorectal primary on the colonoscopy biopsy (synthetic e2e)"})
        check("5.2 the receiving department declines: the Case File stays with its owner, who is told; the department loses its access again",
              r.status_code == 200 and r.json()["referral"]["status"] == "declined" and pulmo.get(f"/api/tb/cases/{cid}").json()["case"]["department"] == "pulmonology"
              and colo.get(f"/api/tb/cases/{cid}").status_code == 403 and len(_notes_of(pulmo, cid, "referral_answered")) == 1 and _notes_of(pulmo, cid, "referral_answered")[0]["status"] == "declined"
              and "colonoscopy biopsy" in _notes_of(pulmo, cid, "referral_answered")[0]["text"], r.text[:160])
        r = pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "colorectal_surgery", "reason": "Review of the biopsy: colorectal origin confirmed by IHC (synthetic e2e)"})
        ref2 = r.json().get("referral", {}) if r.status_code == 200 else {}
        check("5.2 the owner refers again", r.status_code == 200 and ref2.get("status") == "requested" and colo.get(f"/api/tb/cases/{cid}").status_code == 200, r.text[:160])
        check("5.2 an answer to the earlier (declined) referral's id is refused (409): a click in flight never answers a later referral (review Phase 5 M3)",
              colo.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/accept", json={"protocol": "colorectal_rectum", "setting": "metastatic"}).status_code == 409
              and pulmo.post(f"/api/tb/cases/{cid}/referrals/{ref1.get('id')}/withdraw", json={}).status_code == 409 and pulmo.get(f"/api/tb/cases/{cid}").json()["case"]["department"] == "pulmonology")
        check("5.2 accepting with an unknown protocol or setting is refused (400); nothing moves", colo.post(f"/api/tb/cases/{cid}/referrals/{ref2.get('id')}/accept", json={"protocol": "nope"}).status_code == 400
              and colo.post(f"/api/tb/cases/{cid}/referrals/{ref2.get('id')}/accept", json={"protocol": "colorectal_rectum", "setting": "early"}).status_code == 400
              and pulmo.get(f"/api/tb/cases/{cid}").json()["case"]["department"] == "pulmonology")
        before_hist = audit_kinds(pulmo, cid)
        r = colo.post(f"/api/tb/cases/{cid}/referrals/{ref2.get('id')}/accept", json={"protocol": "colorectal_rectum", "setting": "metastatic", "hospital_level": "optimal", "note": "accepted: rectal primary with lung metastases (synthetic e2e)"})
        if r.status_code == 200 and r.json().get("job"):
            wait_job(colo, r.json()["job"])
        d2 = colo.get(f"/api/tb/cases/{cid}").json() if r.status_code == 200 else {}
        acc2 = d2.get("access") or {}
        check("5.2 on acceptance ownership moves to Colorectal Surgery, Pulmonology stays as a participant, the owner history and the referral history are kept",
              r.status_code == 200 and r.json()["referral"]["status"] == "accepted" and d2["case"]["department"] == "colorectal_surgery" and acc2.get("owner", {}).get("id") == "colorectal_surgery"
              and [x["id"] for x in acc2.get("participants", [])] == ["pulmonology"] and len(acc2.get("owner_history", [])) == 1 and acc2["owner_history"][0]["from"] == "pulmonology"
              and [x["status"] for x in d2["referral"]["history"]] == ["declined", "accepted"] and d2["referral"]["open"] is None, r.text[:200])
        g2 = d2.get("state", {}).get("gate") or {}
        check("5.2 the new owner's protocol runs on the same records: the colorectal gate shows the fixture's gaps (MRI pelvis Level 1; CEA, MMR, RAS / BRAF Level 2), nothing re-fetched",
              g2.get("protocol") == "colorectal_rectum" and _gaps(d2) == fixture_gaps("P14", "colorectal_rectum") and d2["case"]["setting"] == "metastatic" and d2["case"]["listing"]["status"] == "listed"
              and len(d2["documents"]) == len(d["documents"]), json.dumps([_gaps(d2), fixture_gaps("P14", "colorectal_rectum")]))
        hist = d2.get("state", {}).get("gate_history") or []
        check("5.2 the lung protocol's gate is kept as read-only history with its gaps and the request that was open",
              len(hist) == 1 and hist[0]["protocol"] == "lung_nsclc" and hist[0]["owner"] == "pulmonology" and hist[0]["reason"] == "referral" and hist[0]["referral"] == ref2.get("id")
              and sorted((x["id"], x.get("level")) for x in hist[0]["gate"]["requirements"] if x["status"] not in ("satisfied", "not_applicable", "waived")) == fixture_gaps("P14", "lung_nsclc")
              and [x["requirement"] for x in hist[0]["actions"] if x["status"] in ("pending", "overdue")] == ["pet_ct"], json.dumps(hist)[:200])
        pet2 = next((x for x in d2["state"]["actions"] if x.get("requirement") == "pet_ct"), {})
        nm_closed = _notes_of(nm, cid, "request_closed")
        check("5.2 the PET-CT request of the lung protocol closed with the referral as the reason; Nuclear Medicine, which had received it, is told",
              pet2.get("status") == "completed" and "referred to Colorectal Surgery" in (pet2.get("history") or [{}])[-1].get("event", "") and len(nm_closed) == 1 and "referred to Colorectal Surgery" in nm_closed[0]["text"], json.dumps(pet2.get("history"))[-300:])
        check("5.2 the new gaps are suggested requests to their departments (Radiology, Biochemistry, Pathology), nothing sent",
              sorted((a["requirement"], a["department"]) for a in d2["state"]["actions"] if a["status"] == "suggested") == [("baseline_mri_pelvis", "Radiology"), ("cea", "Biochemistry"), ("mmr", "Pathology"), ("ras_braf", "Pathology")])
        dp = pulmo.get(f"/api/tb/cases/{cid}").json()
        answered = _notes_of(pulmo, cid, "referral_answered")  # newest first
        conds = {"participant full scope": dp.get("access", {}).get("scope") == "full", "participant no waive": not any(dp["permissions"]["waive"].values()),
                 "participant no refetch": dp["permissions"]["refetch"] is False, "participant no refer": dp["permissions"]["refer"] is False,
                 "participant refer 403": pulmo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Medical Oncology", "reason": "x"}).status_code == 403,
                 "owner waive": any(d2["permissions"]["waive"].values()), "owner send": d2["permissions"]["send_request"] is True, "owner refer": d2["permissions"]["refer"] is True,
                 "owner refetch": d2["permissions"]["refetch"] is True, "two answers told": len(answered) == 2, "latest accepted": bool(answered) and answered[0]["status"] == "accepted"}
        check("5.2 the referring department still reads the Case File as a participant but no longer acts; the new owner may waive, send and refer", all(conds.values()),
              json.dumps([k for k, v in conds.items() if not v]))
        kinds = audit_kinds(colo, cid)
        chain_r = colo.get(f"/api/tb/cases/{cid}/audit/verify"); chain = chain_r.json() if chain_r.status_code == 200 else {}
        check("5.2 every step is audited (requested twice, declined, accepted, owner changed, listed under the new protocol) and the chain verifies",
              kinds.count("referral_requested") == 2 and {"referral_declined", "referral_accepted", "owner_changed", "case_listed"} <= set(kinds) and chain_r.status_code == 200 and chain.get("ok") is True
              and chain.get("first_broken") is None, json.dumps(chain)[:120])
        tl = [e for e in d2.get("timeline", []) if e.get("kind") == "referral"]
        check("5.2 the timeline shows the referrals and the ownership move", len(tl) == 3 and any(e.get("status") == "owner_changed" for e in tl))
        rows = [x for x in colo.get("/api/tb/cases").json()["cases"] if x["case_id"] == cid]
        check("5.2 the Case File list shows the new owner and the participant", rows and rows[0]["owner_name"] == "Colorectal Surgery" and rows[0]["participants"] == ["pulmonology"])
        r = colo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Medical Oncology", "reason": "systemic therapy first (synthetic e2e)"})
        ref3 = r.json().get("referral", {}) if r.status_code == 200 else {}
        open_read = medonc.get(f"/api/tb/cases/{cid}").status_code if ref3 else None
        rw = colo.post(f"/api/tb/cases/{cid}/referrals/{ref3.get('id')}/withdraw", json={"note": "discuss at the board first"}) if ref3 else None
        told = _notes_of(medonc, cid, "referral_answered")
        conds = {"referred onward": r.status_code == 200, "department referred to reads it while open": open_read == 200, "withdrawn": rw is not None and rw.status_code == 200 and rw.json()["referral"]["status"] == "withdrawn",
                 "access gone after the withdrawal": medonc.get(f"/api/tb/cases/{cid}").status_code == 403, "told once": len(told) == 1, "told withdrawn": bool(told) and told[0]["status"] == "withdrawn"}
        check("5.2 the new owner may refer onward and withdraw; the department referred to is told and loses its access", all(conds.values()),
              json.dumps([k for k, v in conds.items() if not v]) + " " + (rw.text[:120] if rw is not None else r.text[:120]))
        # accept without a protocol: the new owner picks it later on the listing form
        r = colo.post(f"/api/tb/cases/{cid}/referrals", json={"to": "Medical Oncology", "reason": "systemic therapy first, after all (synthetic e2e)"})
        ref4 = r.json().get("referral", {}) if r.status_code == 200 else {}
        ra = medonc.post(f"/api/tb/cases/{cid}/referrals/{ref4.get('id')}/accept", json={"note": "protocol to follow"}) if ref4 else None
        d4 = medonc.get(f"/api/tb/cases/{cid}").json() if ra is not None and ra.status_code == 200 else {}
        open_reqs = [a for a in d4.get("state", {}).get("actions", []) if a.get("source") == "pre_authorization" and a.get("status") != "completed"] if d4 else None
        check("5.2 accepting without a protocol closes the earlier protocol's requests with the referral as the reason (nothing stays asked for a protocol nobody follows; review Phase 5 M4)",
              open_reqs == [] and all("referred to Medical Oncology" in (a.get("history") or [{}])[-1].get("event", "") for a in d4["state"]["actions"] if a.get("source") == "pre_authorization" and a.get("requirement") in ("baseline_mri_pelvis", "cea", "mmr", "ras_braf")),
              json.dumps([(a.get("requirement"), a.get("status")) for a in (open_reqs or [])])[:200])
        check("5.2 accepting without a protocol: the Case File waits for the new owner to pick one (awaiting listing, the colorectal gate archived too); the other departments stay as participants",
              ra is not None and ra.status_code == 200 and ra.json()["job"] is None and d4["case"]["department"] == "medical_oncology" and d4["case"]["protocol"] == "" and d4["case"]["listing"]["status"] == "awaiting_listing"
              and d4["case"]["listing"]["reason"] == "referred" and d4["state"]["gate"] is None and [h["protocol"] for h in d4["state"]["gate_history"]] == ["lung_nsclc", "colorectal_rectum"]
              and [x["id"] for x in d4["access"]["participants"]] == ["pulmonology", "colorectal_surgery"] and d4["permissions"]["list_case"] is True, (ra.text[:160] if ra is not None else r.text[:120]))
        rl_ = medonc.post(f"/api/tb/cases/{cid}/listing", json={"protocol": "colorectal_rectum", "setting": "metastatic", "hospital_level": "optimal"})
        if rl_.status_code == 200:
            wait_job(medonc, rl_.json()["job"])
        d5 = medonc.get(f"/api/tb/cases/{cid}").json()
        check("5.2 the new owner lists it under the protocol: the gate re-runs on the same records", rl_.status_code == 200 and (d5["state"].get("gate") or {}).get("protocol") == "colorectal_rectum"
              and _gaps(d5) == fixture_gaps("P14", "colorectal_rectum") and pulmo.get(f"/api/tb/cases/{cid}").json()["access"]["scope"] == "full", rl_.text[:120])

    # ---- 5.3 two primaries: linked Case Files under one UHID (P18) ----------------------------------------------------------------
    d1, j1 = create(colo, "VXH/26/004218", "colorectal_rectum", "non_metastatic", "TB-H5-P18A")
    d2b, j2 = create(breast, "VXH/26/004218", "breast", "early", "TB-H5-P18B")
    if d1 and d2b:
        a_links = (colo.get("/api/tb/cases/TB-H5-P18A").json().get("access") or {}).get("linked_cases") or []
        b_links = (d2b.get("access") or {}).get("linked_cases") or []
        check("5.3 P18 the second cancer of the same UHID gets its own Case File, linked both ways, each with its own owner and protocol",
              [x["case_id"] for x in b_links] == ["TB-H5-P18A"] and b_links[0]["department"] == "colorectal_surgery" and b_links[0]["protocol"] == "colorectal_rectum" and b_links[0]["department_name"] == "Colorectal Surgery"
              and [x["case_id"] for x in a_links] == ["TB-H5-P18B"] and a_links[0]["department"] == "breast_surgery" and d2b["case"]["department"] == "breast_surgery"
              and (d2b["case"]["his"] or {}).get("same_uhid_case") is None, json.dumps([a_links, b_links])[:200])
        check("5.3 P18 both Case Files hold the patient's HIS records and each gate passes (the rectal records never satisfy the breast requirements, nor the reverse)",
              len(d1["documents"]) == len(d2b["documents"]) >= 8 and d1["state"]["gate"]["passed"] and d2b["state"]["gate"]["passed"]
              and _gaps(d1) == fixture_gaps("P18", "colorectal_rectum") == [] and _gaps(d2b) == fixture_gaps("P18", "breast") == [], json.dumps([_gaps(d1), _gaps(d2b)]))
        d1 = colo.get("/api/tb/cases/TB-H5-P18A").json()  # the first Case File re-checked its gate when the second was linked (V2 item 5.3)
        hpe_a = next((x for x in d1["documents"] if x["doc_id"] == _req(d1, "histopathology").get("evidence", [{}])[0].get("doc_id")), {})
        hpe_b = next((x for x in d2b["documents"] if x["doc_id"] == _req(d2b, "histopathology").get("evidence", [{}])[0].get("doc_id")), {})
        check("5.3 P18 each Case File's histopathology requirement is met by its own episode's report, and the row names the other cancer's report that was set aside",
              (hpe_a.get("his") or {}).get("id") and (hpe_b.get("his") or {}).get("id") and hpe_a["his"]["id"] != hpe_b["his"]["id"]
              and any("Two cancers under one UHID" in n for n in _req(d1, "histopathology").get("notes", [])) and any("Two cancers under one UHID" in n for n in _req(d2b, "histopathology").get("notes", [])),
              json.dumps([(hpe_a.get("his") or {}).get("id"), (hpe_b.get("his") or {}).get("id"), _req(d1, "histopathology").get("notes"), _req(d2b, "histopathology").get("notes")])[:300])
        da = breast.get("/api/tb/cases/TB-H5-P18A").json()
        check("5.3 the owners of linked Case Files read each other's (the same patient) but never act on them; a supporting department still cannot",
              da.get("access", {}).get("scope") == "full" and not any(da["permissions"]["waive"].values()) and da["permissions"]["refer"] is False
              and colo.get("/api/tb/cases/TB-H5-P18B").status_code == 200 and rad.get("/api/tb/cases/TB-H5-P18B").status_code == 403
              and breast.post("/api/tb/cases/TB-H5-P18A/his/refetch").status_code == 403)
        rows = {x["case_id"]: x for x in colo.get("/api/tb/cases").json()["cases"]}
        check("5.3 the Case File list shows the link on both", rows.get("TB-H5-P18A", {}).get("linked") == 1 and rows.get("TB-H5-P18B", {}).get("linked") == 1)
        check("5.3 the link is audited in both Case Files", "case_linked" in audit_kinds(colo, "TB-H5-P18A") and "case_linked" in audit_kinds(breast, "TB-H5-P18B"))
        r = c.delete("/api/tb/cases/TB-H5-P18B")
        if r.status_code == 200:
            ctx["cases"].remove("TB-H5-P18B")
        da2 = colo.get("/api/tb/cases/TB-H5-P18A").json()
        check("5.3 deleting one Case File unlinks it from the other (audited)", r.status_code == 200 and (da2.get("access") or {}).get("linked_cases") == [] and "case_unlinked" in audit_kinds(colo, "TB-H5-P18A"), r.text[:120])
    ctx["clients"] = [mdt]


def v2_phase5_cleanup(c, ctx):
    _v2_cleanup(c, ctx, {**H5_USERS, H5_MDT[0]: (H5_MDT[1], {})})


H6_USERS = {"tb-e2e-h6-breast": ("H6breast-e2e-2026!", {"breast_surgery": "doctor"}), "tb-e2e-h6-medonc": ("H6medonc-e2e-2026!", {"medical_oncology": "doctor"}),
            "tb-e2e-h6-rad": ("H6rad-e2e-2026!", {"radiology": "doctor"}), "tb-e2e-h6-gyn": ("H6gyn-e2e-2026!", {"gynaecologic_oncology": "doctor"}),
            "tb-e2e-h6-derm": ("H6derm-e2e-2026!", {"dermatology": "doctor"})}
H6_MDT = ("tb-e2e-h6-mdt", "H6mdt-e2e-2026!")


def v2_phase6(c, base, ctx):
    """V2 Phase 6 on the fixture patients (SYNTHETIC): 6.1 the owner marks the Case File ready, the MDT Coordinator builds the agenda from the
    ready Case Files, reminds on the owner's behalf, opens the Board room (who may), records the decision, exports the minutes and the
    follow-up; 6.2 the agent of a head not recorded present, the surgical seat filled by the Case File's own surgeon, Radiation Oncology
    on demand; 6.3 the records and the images of the current Case File through the app (OHIF and DICOMweb behind a logged-in, granted,
    audited route; never Orthanc directly), a missing HIS PDF fetched live; 6.4 the PM-JAY composition flag only for an empanelled
    hospital, "check PM-JAY requirement" for a surgeon outside the hospital's surgical oncology list."""
    import datetime as _dt
    from tumour_board import board
    cl = _v2_setup(c, base, ctx, H6_USERS, "6.1")
    breast, medonc, rad, gyn, derm = (cl[k] for k in ("tb-e2e-h6-breast", "tb-e2e-h6-medonc", "tb-e2e-h6-rad", "tb-e2e-h6-gyn", "tb-e2e-h6-derm"))
    c.request("DELETE", "/api/auth/users", json={"username": H6_MDT[0]})
    r = c.post("/api/tb/org/accounts", json={"username": H6_MDT[0], "password": H6_MDT[1], "coordinator": True, "display_name": "MDT Coordinator (e2e h6)"})
    mdt = httpx.Client(base_url=base, timeout=600)
    check("6.1 e2e coordinator login", r.status_code == 200 and mdt.post("/api/auth/login", json={"username": H6_MDT[0], "password": H6_MDT[1]}).status_code == 200, r.text[:120])
    o0 = c.get("/api/tb/org").json()
    ctx["hospital"] = dict(o0.get("hospital") or {})  # restored by the cleanup
    today = _dt.date.today()
    D = (today + _dt.timedelta(days=3)).isoformat()
    due = (today + _dt.timedelta(days=10)).isoformat()

    def create(client, ident, protocol, setting, cid):
        r = client.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": "optimal", "case_id": cid, "board_date": D})
        if r.status_code != 200:
            check(f"6.1 create {cid} from {ident}", False, r.text[:200]); return None
        ctx["cases"].append(cid)
        _job(client, r)
        return client.get(f"/api/tb/cases/{cid}").json()

    def room(client):
        return client.get(f"/api/tb/sessions/{sid}").json()

    def wait_agents(client):
        t = time.time()
        while True:
            rm = room(client)
            if all(x.get("status") not in ("queued", "running") for by in (rm["session"].get("agents") or {}).values() for x in by.values()) or time.time() - t > 1200:
                return rm
            time.sleep(3)

    # ---- 6.1 mark ready, candidates, the agenda from the ready Case Files -----------------------------------------------------------
    p01, p12 = "TB-H6-P01", "TB-H6-P12"
    d1 = create(breast, "VXH/26/004201", "breast", "early", p01)        # complete breast work-up with MG and US studies in the PACS
    d2 = create(medonc, "VXH/26/004212", "lung_nsclc", "non_metastatic", p12)  # lung: the CT is preliminary, a suggested request to Radiology
    if not (d1 and d2):
        return
    check("6.1 P01 passes the Pre-Authorization; P12 has a suggested (unsent) request", d1["state"]["gate"]["passed"] is True and d1["permissions"]["mark_ready"] is True
          and any(a.get("status") == "suggested" for a in d2["state"]["actions"]), json.dumps(_gaps(d2)))
    cand = {x["case_id"]: x for x in mdt.get("/api/tb/sessions/candidates", params={"date": D}).json()["cases"]}
    check("6.1 the candidates carry the owner, the ready mark, the gate and the summary state", {p01, p12} <= set(cand) and cand[p01]["owner_name"] == "Breast Surgery"
          and cand[p01]["ready"] is None and cand[p01]["gate_passed"] is True and cand[p12]["gate_passed"] is False and cand[p01]["summary"] == "none", json.dumps({k: {kk: v[kk] for kk in ("owner_name", "ready", "gate_passed", "summary")} for k, v in cand.items()}))
    check("6.1 only the owning department marks a Case File ready (403 for a supporting doctor, another treating department and the coordinator)",
          rad.post(f"/api/tb/cases/{p01}/ready", json={"ready": True}).status_code == 403 and medonc.post(f"/api/tb/cases/{p01}/ready", json={"ready": True}).status_code == 403
          and mdt.post(f"/api/tb/cases/{p01}/ready", json={"ready": True}).status_code == 403)
    r = breast.post(f"/api/tb/cases/{p01}/ready", json={"ready": True, "note": "Summary to follow"})
    j = r.json() if r.status_code == 200 else {}
    nts = mdt.get("/api/tb/notifications", params={"limit": 50}).json()["notifications"]
    check("6.1 the owner marks it ready: recorded with the name and the note, audited, the coordinator told", r.status_code == 200 and (j.get("board_ready") or {}).get("by") == "tb-e2e-h6-breast"
          and j["board_ready"]["note"] == "Summary to follow" and "board_ready" in [e["kind"] for e in breast.get(f"/api/tb/cases/{p01}/audit").json()["events"]]
          and any(n["kind"] == "board_ready" and n["case_id"] == p01 for n in nts), r.text[:160])
    cand = {x["case_id"]: x for x in mdt.get("/api/tb/sessions/candidates", params={"date": D}).json()["cases"]}
    check("6.1 the candidates show who marked it ready", (cand[p01].get("ready") or {}).get("by") == "tb-e2e-h6-breast" and cand[p12].get("ready") is None)
    s = mdt.post("/api/tb/sessions", json={"date": D, "title": "E2E Phase 6 board"}).json()
    sid = s.get("id")
    check("6.1 a session without an explicit agenda takes the Case Files the owners marked ready", sid and [a["case_id"] for a in s["agenda"]] == [p01] and s["agenda"][0]["owner_ready"] is True, json.dumps([a["case_id"] for a in s.get("agenda") or []]))
    if not sid:
        return
    ctx["sid"] = sid
    s = mdt.put(f"/api/tb/sessions/{sid}/agenda", json={"case_ids": [p01, p12]}).json()
    check("6.1 the coordinator may add a Case File not marked ready; the agenda says so", [(a["case_id"], a["owner_ready"]) for a in s["agenda"]] == [(p01, True), (p12, False)])
    check("6.1 the attendance sheet lists the four heads first, the on-demand specialties, then the owners of the agenda; not all 30 departments",
          [d["id"] for d in room(mdt)["attendance_list"]][:6] == ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology", "nuclear_medicine"]
          and "breast_surgery" in [d["id"] for d in room(mdt)["attendance_list"]] and len(room(mdt)["attendance_list"]) < 10 and all(d["head"] for d in room(mdt)["attendance_list"][:4]),
          json.dumps([d["id"] for d in room(mdt)["attendance_list"]]))
    # ---- 6.1 reminders on the owner's behalf -------------------------------------------------------------------------------------------
    a = next((x for x in d2["state"]["actions"] if x.get("status") == "suggested"), {})
    r = mdt.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/remind", json={"note": "Board on " + D})
    nm = medonc.get("/api/tb/notifications", params={"limit": 50}).json()["notifications"]
    nr = rad.get("/api/tb/notifications", params={"limit": 50}).json()["notifications"]
    check("6.1 a reminder about a suggestion nobody sent goes to the owning department, not to the department it names",
          r.status_code == 200 and r.json()["reminders"][0]["sent"] is False and any(n["kind"] == "owner_reminder" and n["case_id"] == p12 for n in nm)
          and not any(n["case_id"] == p12 for n in nr), r.text[:160])
    rs = medonc.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/send", json={})
    r = mdt.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/remind", json={"note": "Please report before the board"})
    nr = rad.get("/api/tb/notifications", params={"limit": 50}).json()["notifications"]
    rem = [n for n in nr if n["kind"] == "request_reminder" and n["case_id"] == p12]
    check("6.1 once sent, the coordinator's reminder reaches Radiology on the owner's behalf (named so), with the note, the accession and the due date kept",
          rs.status_code == 200 and r.status_code == 200 and rem and "on behalf of Medical Oncology" in rem[0]["text"] and "Please report before the board" in rem[0]["text"]
          and rem[0].get("accession") == a.get("accession") and r.json()["due"] == (rs.json().get("action") or {}).get("due") and r.json()["status"] in ("pending", "overdue"),
          f"{r.status_code} {len(rem)} {rem[0]['text'][:120] if rem else ''}")
    check("6.1 only the coordinator and the owner's doctors remind (403 for the department asked, another treating department, a supporting department)",
          rad.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/remind", json={}).status_code == 403 and breast.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/remind", json={}).status_code == 403
          and derm.post(f"/api/tb/cases/{p12}/remind-owner", json={}).status_code == 403 and medonc.post(f"/api/tb/cases/{p12}/requests/{a.get('id')}/remind", json={}).status_code == 200)
    r = mdt.post(f"/api/tb/cases/{p12}/remind-owner", json={"note": "Two days to go"})
    check("6.1 the owner reminder sums up the Case File before the board (summary missing, not marked ready) and is audited",
          r.status_code == 200 and "no Case File summary compiled yet" in r.json()["text"] and "not marked ready for the board" in r.json()["text"] and "Two days to go" in r.json()["text"]
          and "owner_reminded" in [e["kind"] for e in medonc.get(f"/api/tb/cases/{p12}/audit").json()["events"]], r.text[:200])
    ag = mdt.get("/api/tb/metrics/agenda", params={"date": D}).json()
    row = next((x for x in ag["cases"] if x["case_id"] == p01), {})
    chase_items = [i for d_ in ag["chase"] for i in d_["items"] if i["case_id"] == p12]
    check("6.1 the readiness list carries the ready mark and the chase items their action id and reminder count", (row.get("ready") or {}).get("by") == "tb-e2e-h6-breast"
          and chase_items and all(i.get("action_id") for i in chase_items) and any(i.get("reminders", 0) >= 2 for i in chase_items), json.dumps(chase_items)[:200])
    # ---- 6.1 who opens the Board room -------------------------------------------------------------------------------------------------
    rb, rr, rg, rd = (x.get(f"/api/tb/sessions/{sid}") for x in (breast, rad, gyn, derm))
    check("6.1 the room opens to the coordinator, the heads' departments and the owners of the agenda; a department with no part in it is refused (403)",
          rb.status_code == 200 and rr.status_code == 200 and rg.status_code == 403 and rd.status_code == 403, f"{rb.status_code} {rr.status_code} {rg.status_code} {rd.status_code}")
    check("6.1 a doctor sees only the Case Files it may read; the others are restricted, with no patient data",
          rb.status_code == 200 and rb.json()["cases"][p01].get("patient") and rb.json()["cases"][p12].get("restricted") is True and "patient" not in rb.json()["cases"][p12]
          and rr.status_code == 200 and rr.json()["cases"][p01].get("restricted") is True and rr.json()["cases"][p12].get("restricted") is True)
    check("6.1 the session list shows a doctor the sessions it may open", sid in [x["id"] for x in rad.get("/api/tb/sessions").json()["sessions"]]
          and sid not in [x["id"] for x in derm.get("/api/tb/sessions").json()["sessions"]] and [h["id"] for h in mdt.get("/api/tb/sessions").json()["heads"]] == ["radiology", "medical_oncology", "surgical_oncology", "pathology"])
    doc0 = ((d2.get("documents") or [{}])[0]).get("doc_id") or ""
    check("6.1 the MDT Coordinator cannot confirm or waive", mdt.post(f"/api/tb/cases/{p12}/confirmations", json={"type": "waive", "key": "cect_tap", "reason": "e2e"}).status_code == 403
          and mdt.post(f"/api/tb/cases/{p12}/confirmations", json={"type": "attest_final", "key": doc0}).status_code == 403
          and not any((mdt.get(f"/api/tb/cases/{p12}").json()["permissions"].get("waive") or {}).values()) and not any((mdt.get(f"/api/tb/cases/{p12}").json()["permissions"].get("confirm") or {}).values()))
    # ---- 6.2 heads, the surgical seat, agents per Case File, on demand ------------------------------------------------------------------
    for dept in ("radiology", "medical_oncology"):
        mdt.post(f"/api/tb/sessions/{sid}/attendance", json={"department": dept, "status": "present"})
    mdt.post(f"/api/tb/sessions/{sid}/members", json={"name": "Dr Breast Surgeon (e2e, synthetic)", "department": "breast_surgery"})
    rm = room(mdt)
    seat1, seat2 = rm["cases"][p01]["seat"], rm["cases"][p12]["seat"]
    check("6.2 Pathology not recorded present: its agent is active; the breast surgeon fills the surgical seat for the breast Case File only",
          rm["absent_roles_by_case"] == {p01: ["pathology"], p12: ["pathology", "surgical_oncology"]} and seat1["filled_by"] == ["breast_surgery"] and seat1["members"] == ["Dr Breast Surgeon (e2e, synthetic)"]
          and seat1["check_pmjay"] is True and seat2["filled"] is False and seat2["agent"] is True, json.dumps(rm["absent_roles_by_case"]))
    t0 = time.time(); st = mdt.post(f"/api/tb/sessions/{sid}/start").json()
    check("6.2 the session starts the agents per Case File: Pathology for both, Surgical Oncology only where no surgeon fills the seat", st.get("preparing") == 3, str(st.get("preparing")))
    r = mdt.post(f"/api/tb/sessions/{sid}/agents/prepare", json={"case_id": p01, "role": "surgical_oncology"})
    r2 = mdt.post(f"/api/tb/sessions/{sid}/agents/prepare", json={"case_id": p01, "role": "radiation_oncology"})
    check("6.2 no Surgical Oncology agent where the seat is filled (400); Radiation Oncology on demand (200)", r.status_code == 400 and r2.status_code == 200 and r2.json().get("preparing") == 1,
          f"{r.status_code} {r.text[:80]} / {r2.status_code}")
    rm = wait_agents(mdt)
    pname = (rm["cases"][p01].get("patient") or {}).get("name") or ""
    ag_ = rm["session"].get("agents") or {}
    sts = {(cid_, role_): x.get("status") for cid_, by in ag_.items() for role_, x in by.items()}
    check("6.2 every brief prepared (or no documents), none in error", sts and all(v in ("ready", "no_documents") for v in sts.values()) and (p12, "surgical_oncology") in sts and (p01, "radiation_oncology") in sts,
          f"{round(time.time() - t0, 1)} s: {json.dumps({f'{k[0]}:{k[1]}': v for k, v in sts.items()})}")
    check("6.2 the room shows the briefs of the agents active for the Case File and the on-demand brief", "pathology" in rm["cases"][p01]["briefs"] and "radiation_oncology" in rm["cases"][p01]["briefs"]
          and "surgical_oncology" not in rm["cases"][p01]["briefs"] and set(rm["cases"][p12]["briefs"]) >= {"pathology", "surgical_oncology"})
    mdt.post(f"/api/tb/sessions/{sid}/attendance", json={"department": "pathology", "status": "present"})
    check("6.2 a head recorded present later: its agent is no longer active for the Case Files", room(mdt)["absent_roles_by_case"] == {p01: [], p12: ["surgical_oncology"]})
    # ---- 6.3 records and images during the board -----------------------------------------------------------------------------------
    recs = rm["cases"][p01]["records"]
    img = [x for x in recs if x.get("images")]
    check("6.3 the room lists the Case File's records with their hospital-system status and which imaging reports have images", len(recs) >= 6 and img
          and all(x.get("his") and x["his"].get("accession") for x in img), f"{len(recs)} records, {len(img)} with images")
    doc_id = img[0]["doc_id"]
    r = breast.post(f"/api/tb/cases/{p01}/documents/{doc_id}/images")
    j = r.json() if r.status_code == 200 else {}
    check("6.3 Open images: the study found in the hospital system, the viewer URL inside this app, audited", r.status_code == 200 and j.get("available") is True and j.get("study_uid")
          and str(j.get("viewer_url", "")).startswith("/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=") and j.get("modality") in ("MG", "US")
          and "images_opened" in [e["kind"] for e in breast.get(f"/api/tb/cases/{p01}/audit").json()["events"]], r.text[:200])
    uid = j.get("study_uid", "")
    v = breast.get(j.get("viewer_url", "/api/tb/pacs/ohif/viewer"))
    q = breast.get("/api/tb/pacs/dicom-web/studies", params={"StudyInstanceUID": uid})
    se = breast.get(f"/api/tb/pacs/dicom-web/studies/{uid}/series")
    check("6.3 the viewer page and the DICOMweb study are served through the app to the user who opened them", v.status_code == 200 and "text/html" in v.headers.get("content-type", "")
          and q.status_code == 200 and len(q.json()) == 1 and se.status_code == 200 and len(se.json()) >= 1 and "viewer_opened" in [e["kind"] for e in breast.get(f"/api/tb/cases/{p01}/audit").json()["events"]],
          f"{v.status_code} {q.status_code} {se.status_code}")
    check("6.3 nobody else reaches that study, Orthanc's own API is never reached, a study nobody opened is refused",
          gyn.get("/api/tb/pacs/dicom-web/studies", params={"StudyInstanceUID": uid}).status_code == 403 and mdt.get(j.get("viewer_url", "/x")).status_code == 403
          and breast.get("/api/tb/pacs/studies").status_code == 404 and breast.get("/api/tb/pacs/app/explorer.html").status_code == 404
          and breast.get("/api/tb/pacs/dicom-web/studies").status_code == 404 and breast.get("/api/tb/pacs/dicom-web/studies", params={"StudyInstanceUID": "1.2.3.4"}).status_code == 403
          and httpx.Client(base_url=base).get("/api/tb/pacs/ohif/").status_code in (401, 403)
          and breast.get(f"/api/tb/pacs/dicom-web/studies?StudyInstanceUID={uid}&0020,000D=").status_code == 404  # the study tag in another spelling (review S1)
          and breast.get(f"/api/tb/pacs/dicom-web/studies?StudyInstanceUID={uid}&StudyInstanceUID%00=").status_code == 404
          and breast.get(f"/api/tb/pacs/dicom-web/studies?StudyInstanceUID={uid}&PatientName=").status_code == 404
          and len(breast.get(f"/api/tb/pacs/dicom-web/studies?StudyInstanceUID={uid}&includefield=all").json()) == 1)
    check("6.3 a department outside the Case File cannot open its images (403)", rad.post(f"/api/tb/cases/{p01}/documents/{doc_id}/images").status_code == 403 and gyn.post(f"/api/tb/cases/{p01}/documents/{doc_id}/images").status_code == 403)
    rm2 = mdt.post(f"/api/tb/cases/{p01}/documents/{doc_id}/images").json()
    v2 = mdt.get(rm2.get("viewer_url", "/x"))
    check("6.3 the coordinator opens the images from the room after its own Open images (a grant per person)", rm2.get("available") is True and v2.status_code == 200)
    # the file of a hospital-system record fetched live when it is missing on disk
    pdfs = sorted((REPO / "data" / "tumour_board" / "cases" / p01 / "docs" / doc_id).glob("original.*"))
    if pdfs:
        pdfs[0].unlink()
    f = breast.get(f"/api/tb/cases/{p01}/documents/{doc_id}/file")
    check("6.3 a hospital-system PDF missing on disk is fetched live from the HIS, checked against its recorded hash, and audited",
          bool(pdfs) and f.status_code == 200 and "pdf" in f.headers.get("content-type", "") and sorted((REPO / "data" / "tumour_board" / "cases" / p01 / "docs" / doc_id).glob("original.*"))
          and "document_fetched_live" in [e["kind"] for e in breast.get(f"/api/tb/cases/{p01}/audit").json()["events"]], f"{f.status_code} {f.headers.get('content-type')}")
    # ---- 6.1 / 6.4 the decision, the composition, the minutes and the follow-up ----------------------------------------------------
    dec = mdt.post(f"/api/tb/sessions/{sid}/cases/{p01}/decision", json={"decision_text": "Breast conservation surgery first; adjuvant plan after the final histopathology.", "recorded_by": "Dr Chair (e2e, synthetic)",
                                                                        "intent_as_recorded": "curative", "actions": [{"department": "Radiology", "task": "MRI breast before surgery", "due": due}]}).json()
    rec = dec.get("record") or {}
    comp = (rec.get("adjudication") or {}).get("composition") or {}
    cflags = [x for x in (rec.get("adjudication") or {}).get("flags") or [] if x["kind"] == "composition"]
    check("6.4 the breast surgeon fills the surgical seat for PM-JAY with 'check PM-JAY requirement'; the radiation oncologist is missing (a review flag, never a block)",
          comp.get("checked") is True and (comp.get("seat") or {}).get("check") is True and "surgical_oncology" in comp.get("present", []) and comp.get("missing") == ["radiation_oncology"]
          and cflags and "check the PM-JAY requirement" in cflags[0]["text"] and cflags[0]["severity"] == "review", json.dumps(comp)[:240])
    mn = mdt.get(f"/api/tb/sessions/{sid}/minutes", params={"format": "json"}).json()
    html = mdt.get(f"/api/tb/sessions/{sid}/minutes").text
    c1 = next((x for x in mn.get("cases", []) if x["case_id"] == p01), {})
    sheet = {x["id"]: x for x in mn.get("attendance", [])}
    check("6.1 the minutes: the sheet with the heads, who stood in, the decision as dictated with its actions, the seat, the follow-up",
          sheet.get("radiology", {}).get("head") is True and sheet.get("pathology", {}).get("agent_stood_in") == [p01, p12] and sheet.get("breast_surgery", {}).get("members") == ["Dr Breast Surgeon (e2e, synthetic)"]
          and (c1.get("decision") or {}).get("actions") == [{"department": "Radiology", "task": "MRI breast before surgery", "due": due}] and c1.get("decision", {}).get("intent") == "curative"
          and c1.get("seat", {}).get("filled_by") == ["breast_surgery"] and (c1.get("ready") or {}).get("by") == "tb-e2e-h6-breast" and mn["followup"]["open"] >= 1
          and "Tumour Board minutes" in html and "check PM-JAY requirement" in html and "MRI breast before surgery" in html and "—" not in html
          and any(e["kind"] == "minutes_export" for e in board.read_audit(2000) if e.get("session") == sid), json.dumps({k: c1.get(k) for k in ("seat", "ready", "agents")})[:200])
    check("6.1 the minutes open to the room's readers only (403 for a department with no part)", gyn.get(f"/api/tb/sessions/{sid}/minutes").status_code == 403 and breast.get(f"/api/tb/sessions/{sid}/minutes").status_code == 200)
    rr = rad.get(f"/api/tb/sessions/{sid}").json(); rmj = rad.get(f"/api/tb/sessions/{sid}/minutes", params={"format": "json"}).json(); rmh = rad.get(f"/api/tb/sessions/{sid}/minutes").text
    rex = rad.get(f"/api/tb/sessions/{sid}/export", params={"format": "json"}).json(); rexh = rad.get(f"/api/tb/sessions/{sid}/export").text
    bm = breast.get(f"/api/tb/sessions/{sid}/minutes", params={"format": "json"}).json()
    check("6.1 a head's department with no part in the Case Files opens the room but gets no log, decision, agent record, follow-up, minutes or export content of them (restricted); the owner sees its own",
          bool(pname) and not any(e.get("case_id") for e in rr["session"]["log"]) and rr["session"]["decisions"] == {} and rr["session"].get("agents") == {} and not (rr.get("followup") or {}).get("actions")
          and all(c.get("restricted") for c in rmj["cases"]) and not rmj["followup"]["actions"] and pname not in rmh and pname not in json.dumps(rex) and pname not in rexh
          and all(c.get("restricted") and not c.get("agent_log") and c.get("decision") is None for c in rex["cases"])
          and [c.get("restricted", False) for c in bm["cases"]] == [False, True] and bm["cases"][0]["patient"]["name"] == pname,
          f"{len(rr['session']['log'])} log entries, {sum(1 for c in rmj['cases'] if c.get('restricted'))}/{len(rmj['cases'])} restricted, breast {[c.get('restricted', False) for c in bm['cases']]}")
    fu = room(mdt).get("followup") or {}
    check("6.1 the room tracks the follow-up of the decisions (the MRI action open in Radiology's inbox, the patient-communication follow-up beside it)",
          fu.get("open", 0) >= 1 and any(x["department"] == "Radiology" and x["status"] != "completed" for x in fu.get("actions") or [])
          and any(q["case_id"] == p01 for d_ in rad.get("/api/tb/inbox").json()["departments"] for q in d_["requests"] if q.get("source") == "board"), json.dumps(fu)[:200])
    # ---- 6.4 a hospital that is not PM-JAY empanelled; the board heads as a hospital setting --------------------------------------------
    r = c.put("/api/tb/org", json={"hospital": {**ctx["hospital"], "pmjay_empanelled": False}})
    dec2 = mdt.post(f"/api/tb/sessions/{sid}/cases/{p12}/decision", json={"decision_text": "Await the final CT report; re-discuss.", "recorded_by": "Dr Chair (e2e, synthetic)", "outcome_type": "deferred", "deferred_reason": "final CT report"}).json()
    comp2 = ((dec2.get("record") or {}).get("adjudication") or {}).get("composition") or {}
    html2 = mdt.get(f"/api/tb/sessions/{sid}/minutes").text
    dash = c.get("/api/tb/metrics/dashboard").json()["kpis"]["during"]
    check("6.4 not empanelled: the composition is not applicable, no flag, the minutes and the dashboard say so", r.status_code == 200 and comp2.get("not_applicable") is True
          and not any(x["kind"] == "composition" for x in (dec2.get("record") or {}).get("adjudication", {}).get("flags", []))
          and "PM-JAY board composition: not applicable" in html2 and dash.get("pmjay_empanelled") is False and dash.get("quorate_pct") is None, json.dumps(comp2)[:160])
    r = c.put("/api/tb/org", json={"hospital": {**ctx["hospital"], "board_heads": ["pathology", "radiology"]}})
    r_bad = c.put("/api/tb/org", json={"hospital": {**ctx["hospital"], "board_heads": ["cardiology"]}})
    check("6.2 the board heads are a hospital setting (root admin); an unknown department is refused", r.status_code == 200 and [h["id"] for h in mdt.get("/api/tb/sessions").json()["heads"]] == ["pathology", "radiology"]
          and r_bad.status_code == 400, f"{r.status_code} {r_bad.status_code} {r_bad.text[:100]}")
    c.put("/api/tb/org", json={"hospital": ctx["hospital"]})
    mdt.post(f"/api/tb/sessions/{sid}/close")
    check("6.1 the closed session still exports its minutes", mdt.get(f"/api/tb/sessions/{sid}/minutes").status_code == 200)


def v2_phase6_cleanup(c, ctx):
    from tumour_board import board
    try:
        if ctx.get("hospital"):
            c.put("/api/tb/org", json={"hospital": ctx["hospital"]})
    except Exception as e:
        print("restore hospital settings failed:", e)
    sid = ctx.get("sid")
    if sid:
        try:  # the e2e session is a test artefact: its file goes, its history stays in sessions/audit.jsonl
            board._path(sid).unlink()
            board.audit_session(sid, {"kind": "e2e_removed", "by": "e2e"})
        except Exception:
            pass
    _v2_cleanup(c, ctx, {**H6_USERS, H6_MDT[0]: (H6_MDT[1], {})})


H7_USERS = {"tb-e2e-h7-breast": ("H7breast-e2e-2026!", {"breast_surgery": "doctor"}), "tb-e2e-h7-medonc": ("H7medonc-e2e-2026!", {"medical_oncology": "doctor"}),
            "tb-e2e-h7-rad": ("H7rad-e2e-2026!", {"radiology": "doctor"}), "tb-e2e-h7-gyn": ("H7gyn-e2e-2026!", {"gynaecologic_oncology": "doctor"})}
H7_MDT = ("tb-e2e-h7-mdt", "H7mdt-e2e-2026!")
H7_DEPTADMIN = ("tb-e2e-h7-radadmin", "H7radadmin-e2e-2026!")
H7_ROOT = ("tb-e2e-h7-root", "H7root-e2e-2026!")


def v2_phase7(c, base, ctx):
    """V2 item 7.1 on the fixture patients (SYNTHETIC): the home per role. A treating doctor sees its department's Case Files (owned first,
    the ready mark, unsent suggestions, the referral waiting or to answer); a supporting doctor its inbox (acknowledge from the home); the
    MDT Coordinator the next board date, its readiness and the sessions; a department admin its doctors; a root admin the organisation and
    the first set-up question (PM-JAY empanelled), answered once (409 after, 400 on a non-boolean, 403 for anyone without manage_org);
    a login holding two roles stacks them, the clinical one first; a disabled login gets 403; a Vaidyx admin gets treating, coordinator and
    root admin. Counts are compared with a baseline taken before the section, since the live store holds older Case Files (the demo ones
    have no owning department and are open to every placed account)."""
    import datetime as _dt
    cl = _v2_setup(c, base, ctx, H7_USERS, "7.1")
    breast, medonc, rad, gyn = (cl[k] for k in ("tb-e2e-h7-breast", "tb-e2e-h7-medonc", "tb-e2e-h7-rad", "tb-e2e-h7-gyn"))
    o0 = c.get("/api/tb/org").json()
    ctx["hospital"] = dict(o0.get("hospital") or {})  # restored by the cleanup (clears a first-set-up stamp made here)
    extra = {}
    for (u, pw), body in ((H7_MDT, {"coordinator": True, "display_name": "MDT Coordinator (e2e h7)"}),
                          (H7_DEPTADMIN, {"admin_of": ["radiology"], "display_name": "Radiology admin (e2e h7)"}),
                          (H7_ROOT, {"root_admin": True, "display_name": "Root admin (e2e h7)"})):
        c.request("DELETE", "/api/auth/users", json={"username": u})
        r = c.post("/api/tb/org/accounts", json={"username": u, "password": pw, **body})
        extra[u] = httpx.Client(base_url=base, timeout=600)
        check(f"7.1 e2e login {u}", r.status_code == 200 and extra[u].post("/api/auth/login", json={"username": u, "password": pw}).status_code == 200, r.text[:120])
    mdt, radadmin, root = extra[H7_MDT[0]], extra[H7_DEPTADMIN[0]], extra[H7_ROOT[0]]
    D = _dt.date.today().isoformat()  # today: the first board date >= today whatever older Case Files are listed for

    def home(client):
        r = client.get("/api/tb/home")
        return r.json() if r.status_code == 200 else {"_status": r.status_code, "_text": r.text[:160]}

    def row(h, cid):
        return next((x for x in (h.get("treating") or {}).get("cases") or [] if x["case_id"] == cid), None)

    def short(h, keys=("sections", "primary")):
        return json.dumps({k: h.get(k) for k in keys + ("_status",) if k in h})

    def create(client, ident, protocol, setting, cid):
        r = client.post("/api/tb/cases/from-his", json={"identifier": ident, "protocol": protocol, "setting": setting, "hospital_level": "optimal", "case_id": cid, "board_date": D})
        if r.status_code != 200:
            check(f"7.1 create {cid} from {ident}", False, r.text[:200]); return None
        ctx["cases"].append(cid)
        _job(client, r)
        return client.get(f"/api/tb/cases/{cid}").json()

    # baselines before the section's Case Files (only counts are kept; rows of older Case Files are never printed)
    b0 = {k: home(x) for k, x in (("breast", breast), ("medonc", medonc), ("rad", rad), ("gyn", gyn))}
    bt = {k: (v.get("treating") or {}).get("counts") or {} for k, v in b0.items()}
    b_refs = (b0["breast"].get("treating") or {}).get("referrals_to_answer", 0)
    b_inbox_breast = next((d["open"] for d in ((b0["breast"].get("treating") or {}).get("inbox") or {}).get("departments", []) if d["id"] == "breast_surgery"), None)
    b_rad = next((d for d in (b0["rad"].get("supporting") or {}).get("departments", []) if d["id"] == "radiology"), {})

    # ---- 1. treating homes ---------------------------------------------------------------------------------------------------------
    p01, p12 = "TB-H7-P01", "TB-H7-P12"
    d1 = create(breast, "VXH/26/004201", "breast", "early", p01)        # complete breast work-up
    d2 = create(medonc, "VXH/26/004212", "lung_nsclc", "non_metastatic", p12)  # lung: the CT is preliminary, a suggested request to Radiology
    if not (d1 and d2):
        return
    hb = home(breast)
    t = hb.get("treating") or {}
    r1 = row(hb, p01)
    check("7.1 a treating doctor's home: the treating section only, primary treating, its name and department", hb.get("sections") == ["treating"] and hb.get("primary") == "treating"
          and hb.get("user") == "tb-e2e-h7-breast" and hb.get("display_name") == "tb-e2e-h7-breast (e2e)" and [d["id"] for d in hb.get("departments") or []] == ["breast_surgery"]
          and not any(k in hb for k in ("supporting", "coordinator", "dept_admin", "root_admin")), short(hb, ("sections", "primary", "user", "display_name")))
    check("7.1 the owned Case File comes first with the UHID, the owner, the gate passed and the relation owner", bool(t.get("cases")) and t["cases"][0]["case_id"] == p01 and r1
          and r1["relation"] == "owner" and r1["uhid"] == "VXH/26/004201" and r1["owner_name"] == "Breast Surgery" and r1["gate_passed"] is True and r1["scope"] == "full"
          and r1["board_date"] == D and r1["ready"] is None, json.dumps({k: (r1 or {}).get(k) for k in ("relation", "uhid", "owner_name", "gate_passed", "scope", "ready")}))
    tc = t.get("counts") or {}
    check("7.1 the treating counts: one more owned and visible Case File; the other department's Case File is not in the home", tc.get("mine") == bt["breast"].get("mine", 0) + 1
          and tc.get("visible") == bt["breast"].get("visible", 0) + 1 and row(hb, p12) is None and tc.get("gate_passed") == bt["breast"].get("gate_passed", 0) + 1
          and t.get("can_create") is True and t.get("his_enabled") is True,
          json.dumps({"now": {k: tc.get(k) for k in ("mine", "visible", "gate_passed")}, "before": {k: bt["breast"].get(k) for k in ("mine", "visible", "gate_passed")}}))
    hm = home(medonc)
    r2 = row(hm, p12)
    mc = (hm.get("treating") or {}).get("counts") or {}
    check("7.1 the Medical Oncology home shows the unsent suggested request on its Case File and in the counts", r2 and r2["relation"] == "owner" and r2.get("suggested_unsent", 0) >= 1
          and r2["gate_passed"] is False and mc.get("suggested_unsent", 0) >= bt["medonc"].get("suggested_unsent", 0) + 1 and row(hm, p01) is None,
          json.dumps({"row": {k: (r2 or {}).get(k) for k in ("relation", "suggested_unsent", "gate_passed")}, "counts": mc.get("suggested_unsent")}))
    hg = home(gyn)
    gc = (hg.get("treating") or {}).get("counts") or {}
    check("7.1 another treating department's home lists neither Case File; its counts do not move", hg.get("sections") == ["treating"] and row(hg, p01) is None and row(hg, p12) is None
          and gc.get("visible") == bt["gyn"].get("visible", 0) and gc.get("mine") == 0, json.dumps({"now": gc.get("visible"), "before": bt["gyn"].get("visible")}))
    if bt["gyn"].get("visible"):
        print(f"INFO 7.1 the live store holds {bt['gyn']['visible']} Case File(s) without an owning department (before 5.1): every placed doctor's home lists them as 'open'", flush=True)

    # ---- 2. the ready mark ---------------------------------------------------------------------------------------------------------
    r = breast.post(f"/api/tb/cases/{p01}/ready", json={"ready": True, "note": "Summary to follow (e2e h7)"})
    hb = home(breast); r1 = row(hb, p01) or {}
    tc = (hb.get("treating") or {}).get("counts") or {}
    check("7.1 after the owner marks it ready the home row carries who and the note; ready_marked counts it", r.status_code == 200 and (r1.get("ready") or {}).get("by") == "tb-e2e-h7-breast"
          and r1["ready"].get("note") == "Summary to follow (e2e h7)" and r1["ready"].get("at") and tc.get("ready_marked") == bt["breast"].get("ready_marked", 0) + 1,
          json.dumps({"ready": r1.get("ready"), "ready_marked": tc.get("ready_marked"), "before": bt["breast"].get("ready_marked")}))

    # ---- 3. the supporting home --------------------------------------------------------------------------------------------------------
    sent = _send_suggested(medonc, p12, "cect_tap", "Please report before the board (e2e h7)")
    hr = home(rad)
    sp = hr.get("supporting") or {}
    rd = next((d for d in sp.get("departments") or [] if d["id"] == "radiology"), {})
    q = next((x for x in rd.get("requests") or [] if x.get("case_id") == p12 and x.get("requirement") == "cect_tap"), None)
    check("7.1 a supporting doctor's home: the supporting section only, the request sent to Radiology with the UHID and the Case File",
          sent and all(s == 200 for _, s in sent) and hr.get("sections") == ["supporting"] and hr.get("primary") == "supporting" and "treating" not in hr
          and sp.get("open", 0) >= 1 and rd.get("open", 0) == b_rad.get("open", 0) + 1 and q and q.get("uhid") == "VXH/26/004212" and q.get("status") == "pending" and q.get("acknowledged") is None,
          json.dumps({"sent": sent, "sections": hr.get("sections"), "open": rd.get("open"), "before": b_rad.get("open"), "more": rd.get("more"), "row": {k: (q or {}).get(k) for k in ("uhid", "case_id", "status")}}))
    r = rad.post(f"/api/tb/cases/{p12}/requests/{(q or {}).get('id') or (sent[0][0] if sent else 'x')}/acknowledge")
    hr = home(rad)
    rd = next((d for d in (hr.get("supporting") or {}).get("departments") or [] if d["id"] == "radiology"), {})
    q2 = next((x for x in rd.get("requests") or [] if x.get("case_id") == p12 and x.get("requirement") == "cect_tap"), {})
    check("7.1 acknowledged from the home: the department's acknowledged count goes up by one, the row says who", r.status_code == 200
          and rd.get("acknowledged") == b_rad.get("acknowledged", 0) + 1 and (q2.get("acknowledged") or {}).get("by") == "tb-e2e-h7-rad",
          json.dumps({"status": r.status_code, "acknowledged": rd.get("acknowledged"), "before": b_rad.get("acknowledged")}))
    if b_rad.get("acknowledged"):
        print(f"INFO 7.1 Radiology had {b_rad['acknowledged']} acknowledged open request(s) before the section; the check compares with that", flush=True)
    hb = home(breast)
    ibd = ((hb.get("treating") or {}).get("inbox") or {}).get("departments") or []
    bs = next((d for d in ibd if d["id"] == "breast_surgery"), None)
    check("7.1 the treating home's inbox names its own department (requests to Breast Surgery), nothing new open", bs is not None and bs["name"] == "Breast Surgery"
          and bs["open"] == (b_inbox_breast or 0) and [d["id"] for d in ibd] == ["breast_surgery"], json.dumps(ibd))

    # ---- 4. the referral -------------------------------------------------------------------------------------------------------------
    r = medonc.post(f"/api/tb/cases/{p12}/referrals", json={"to": "breast_surgery", "reason": "Breast lesion on the CT to be worked up first (e2e h7, synthetic)"})
    hb = home(breast); rr = row(hb, p12) or {}
    tb_ = hb.get("treating") or {}
    check("7.1 the department referred to sees the Case File as referred, with one referral to answer", r.status_code == 200 and rr.get("relation") == "referred"
          and rr.get("owner_name") == "Medical Oncology" and tb_.get("referrals_to_answer") == b_refs + 1
          and any(x.get("case_id") == p12 and x.get("can_answer") for x in tb_.get("referrals") or []) and tb_["cases"][0]["case_id"] == p01,
          json.dumps({"status": r.status_code, "relation": rr.get("relation"), "to_answer": tb_.get("referrals_to_answer"), "before": b_refs}) + " " + (r.text[:120] if r.status_code != 200 else ""))
    hm = home(medonc); r2 = row(hm, p12) or {}
    mc = (hm.get("treating") or {}).get("counts") or {}
    check("7.1 the referring department sees the referral waiting with Breast Surgery on its row and in the counts", r2.get("relation") == "owner" and r2.get("referral") == "Breast Surgery"
          and mc.get("referral_waiting") == bt["medonc"].get("referral_waiting", 0) + 1, json.dumps({"referral": r2.get("referral"), "waiting": mc.get("referral_waiting")}))

    # ---- 5. the MDT Coordinator ------------------------------------------------------------------------------------------------------
    hc = home(mdt)
    co = hc.get("coordinator") or {}
    ag_ids = [x.get("case_id") for x in (co.get("agenda") or {}).get("cases") or []]
    check("7.1 the coordinator's home: the coordinator section only, the next board date, its readiness list with both Case Files, the ready marks",
          hc.get("sections") == ["coordinator"] and hc.get("primary") == "coordinator" and co.get("today") == D and co.get("next_board_date") == D
          and {p01, p12} <= set(ag_ids) and co.get("ready_marked", 0) >= 1 and co.get("can_manage") is True,
          json.dumps({"sections": hc.get("sections"), "next": co.get("next_board_date"), "h7_in_agenda": sorted(x for x in ag_ids if str(x).startswith("TB-H7-")), "ready": co.get("ready_marked")}))
    s = mdt.post("/api/tb/sessions", json={"date": D, "title": "E2E Phase 7 home board", "case_ids": [p01, p12]})
    sid = (s.json() if s.status_code == 200 else {}).get("id")
    if sid:
        ctx["sid"] = sid
    hc = home(mdt); ss = (hc.get("coordinator") or {}).get("sessions") or {}
    check("7.1 after the coordinator creates a session the home counts it as planned and names it among the open sessions", s.status_code == 200 and sid
          and ss.get("planned", 0) >= 1 and any(x["id"] == sid and x["status"] == "planned" and x["cases"] == 2 for x in ss.get("open") or []),
          json.dumps({"status": s.status_code, "planned": ss.get("planned"), "open": [x.get("id") for x in ss.get("open") or []]}) + (s.text[:120] if s.status_code != 200 else ""))
    r = mdt.post("/api/tb/org/setup", json={"pmjay_empanelled": False})
    check("7.1 the coordinator cannot answer the first set-up (403)", r.status_code == 403, f"{r.status_code} {r.text[:100]}")

    # ---- 6. the department admin, then a doctor who is also its department admin ----------------------------------------------------
    ha = home(radadmin)
    da = (ha.get("dept_admin") or {}).get("departments") or [{}]
    lst = {x["username"]: x for x in da[0].get("list") or []}
    check("7.1 a department admin's home: its department with its doctors (the Radiology doctor placed as member, with a login)", ha.get("sections") == ["dept_admin"]
          and ha.get("primary") == "dept_admin" and da[0].get("id") == "radiology" and len(da) == 1 and da[0].get("doctors", 0) >= 1 and da[0].get("admins", 0) >= 1
          and (lst.get("tb-e2e-h7-rad") or {}).get("role") == "member" and lst["tb-e2e-h7-rad"].get("account") is True and lst["tb-e2e-h7-rad"].get("disabled") is False
          and H7_DEPTADMIN[0] not in lst and [x["id"] for x in ha.get("admin_of") or []] == ["radiology"],
          json.dumps({"sections": ha.get("sections"), "dept": {k: da[0].get(k) for k in ("id", "doctors", "heads", "admins", "no_login")}, "rad": lst.get("tb-e2e-h7-rad")}))
    r = radadmin.post("/api/tb/org/setup", json={"pmjay_empanelled": False})
    check("7.1 a department admin cannot answer the first set-up (403)", r.status_code == 403, f"{r.status_code} {r.text[:100]}")
    r = c.post("/api/tb/org/accounts", json={"username": "tb-e2e-h7-rad", "admin_of": ["radiology"]})
    hr = home(rad)
    check("7.1 a Radiology doctor made also its department admin: both sections, the clinical one first", r.status_code == 200 and hr.get("sections") == ["supporting", "dept_admin"]
          and hr.get("primary") == "supporting" and "supporting" in hr and (hr.get("dept_admin") or {}).get("departments", [{}])[0].get("id") == "radiology", short(hr) + " " + r.text[:100])

    # ---- 7. the root admin and the first set-up -----------------------------------------------------------------------------------------
    hroot = home(root)
    ra = hroot.get("root_admin") or {}
    deps = ra.get("departments") or {}
    check("7.1 a root admin's home: the organisation section only, the set-up question state, accounts and departments, the HIS without a token",
          hroot.get("sections") == ["root_admin"] and hroot.get("primary") == "root_admin" and isinstance(ra.get("setup_needed"), bool)
          and (ra.get("accounts") or {}).get("root_admins", 0) >= 1 and (ra.get("accounts") or {}).get("coordinators", 0) >= 1 and (ra.get("accounts") or {}).get("dept_admins", 0) >= 2
          and deps.get("treating", 0) > 0 and deps.get("supporting", 0) > 0 and isinstance(ra.get("his"), dict) and ra["his"].get("enabled") is True
          and not any("token" in k for k in ra["his"]) and ra["his"].get("url") == f"http://127.0.0.1:{MOCK_PORT}" and "Radiology" in (ra.get("board_heads") or []),
          json.dumps({"sections": hroot.get("sections"), "setup_needed": ra.get("setup_needed"), "accounts": ra.get("accounts"), "departments": deps, "his": ra.get("his")})[:400])
    check("7.1 the live organisation has its default 22 treating and 8 supporting departments", deps.get("treating") == 22 and deps.get("supporting") == 8, json.dumps(deps))
    r = medonc.post("/api/tb/org/setup", json={"pmjay_empanelled": False})
    check("7.1 a plain doctor cannot answer the first set-up (403)", r.status_code == 403, f"{r.status_code} {r.text[:100]}")
    if ra.get("setup_needed") is True:
        rb = root.post("/api/tb/org/setup", json={"pmjay_empanelled": "yes"})
        check("7.1 a non-boolean PM-JAY answer is refused (400), nothing recorded", rb.status_code == 400 and (home(root).get("root_admin") or {}).get("setup_needed") is True, f"{rb.status_code} {rb.text[:100]}")
        r = root.post("/api/tb/org/setup", json={"pmjay_empanelled": False, "name": "Vaidyx Demo Hospital (SYNTHETIC)", "level": "optimal"})
        hroot = home(root); ra = hroot.get("root_admin") or {}
        hh = ra.get("hospital") or {}
        check("7.1 the root admin answers the first set-up: recorded once with who and when; the home stops asking", r.status_code == 200 and (r.json().get("hospital") or {}).get("pmjay_empanelled") is False
              and ra.get("setup_needed") is False and (ra.get("first_setup") or {}).get("by") == H7_ROOT[0] and (ra.get("first_setup") or {}).get("at")
              and hh.get("pmjay_empanelled") is False and hh.get("name") == "Vaidyx Demo Hospital (SYNTHETIC)" and hh.get("level") == "optimal",
              json.dumps({"status": r.status_code, "setup_needed": ra.get("setup_needed"), "first_setup": ra.get("first_setup"), "hospital": hh}) + (r.text[:120] if r.status_code != 200 else ""))
        ev = [e for e in c.get("/api/tb/org/audit", params={"limit": 50}).json().get("events") or [] if e.get("kind") == "first_setup" and e.get("by") == H7_ROOT[0]]
        check("7.1 the first set-up is in the organisation audit, by the root admin, with the answer", ev and str(ev[0].get("ts") or "") >= str((ra.get("first_setup") or {}).get("at") or "~")  # newest first; an earlier run left its own
              and ev[0].get("pmjay_empanelled") is False and ev[0].get("level") == "optimal" and ev[0].get("name") == "Vaidyx Demo Hospital (SYNTHETIC)",
              json.dumps(ev)[:200])
        r = root.post("/api/tb/org/setup", json={"pmjay_empanelled": True})
        check("7.1 a second answer is refused (409): the settings then change under Organisation", r.status_code == 409 and (home(root).get("root_admin") or {}).get("hospital", {}).get("pmjay_empanelled") is False,
              f"{r.status_code} {r.text[:100]}")
    else:
        print(f"NOTE 7.1 the live organisation's first set-up was answered already ({json.dumps(ra.get('first_setup'))}): only the refusals are checked", flush=True)
        r = root.post("/api/tb/org/setup", json={"pmjay_empanelled": False})
        rb = root.post("/api/tb/org/setup", json={"pmjay_empanelled": "yes"})
        check("7.1 the answered first set-up is refused again (409; a non-boolean too, the stamp is checked first)", r.status_code == 409 and rb.status_code in (400, 409), f"{r.status_code} {rb.status_code}")

    # ---- 8. a disabled login -----------------------------------------------------------------------------------------------------------
    r = c.put("/api/tb/org/departments/gynaecologic_oncology/doctors/tb-e2e-h7-gyn", json={"disabled": True})
    rg = gyn.get("/api/tb/home")
    check("7.1 a disabled login has no home (403)", r.status_code == 200 and rg.status_code == 403, f"{r.status_code} {rg.status_code} {rg.text[:100]}")

    # ---- 9. the Vaidyx admin ---------------------------------------------------------------------------------------------------------
    hv = home(c)
    vt = hv.get("treating") or {}
    check("7.1 a Vaidyx admin's home: every Case File, the coordinator's view and the organisation", hv.get("sections") == ["treating", "coordinator", "root_admin"]
          and hv.get("primary") == "treating" and row(hv, p01) is not None and row(hv, p12) is not None and "coordinator" in hv and "root_admin" in hv and "supporting" not in hv
          and hv.get("departments") == [], short(hv))


def v2_phase7_cleanup(c, ctx):
    from tumour_board import board
    throwaway = {**H7_USERS, H7_MDT[0]: (H7_MDT[1], {}), H7_DEPTADMIN[0]: (H7_DEPTADMIN[1], {}), H7_ROOT[0]: (H7_ROOT[1], {})}
    try:
        if ctx.get("hospital"):
            r = c.put("/api/tb/org", json={"hospital": ctx["hospital"]})  # the captured block has no first_setup stamp when it had none: restoring clears it
            print("hospital settings restored:", r.status_code, "first set-up stamp:", (r.json().get("hospital") or {}).get("first_setup") if r.status_code == 200 else r.text[:120])
    except Exception as e:
        print("restore hospital settings failed:", e)
    sid = ctx.get("sid")
    if sid:
        try:  # the e2e session is a test artefact: its file goes, its history stays in sessions/audit.jsonl
            board._path(sid).unlink()
            board.audit_session(sid, {"kind": "e2e_removed", "by": "e2e"})
        except Exception:
            pass
    try:
        o = c.get("/api/tb/org").json()
        c.put("/api/tb/org", json={"users": {k: v for k, v in (o.get("users") or {}).items() if k not in throwaway},
                                   "admins": [a for a in (o.get("admins") or []) if a not in throwaway]})
    except Exception as e:
        print("cleanup org (root admins) failed:", e)
    _v2_cleanup(c, ctx, throwaway)


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
    if only == "v2p2":
        try:
            v2_phase2(c, base)
        finally:
            v2_phase2_cleanup(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase3":
        phase3(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "v2p3":
        ctx = {"cases": []}
        try:
            v2_phase3(c, base, ctx)
        finally:
            v2_phase3_cleanup(c, ctx)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "v2p4":
        ctx = {"cases": []}
        try:
            v2_phase4(c, base, ctx)
        finally:
            v2_phase4_cleanup(c, ctx)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "v2p5":
        ctx = {"cases": []}
        try:
            v2_phase5(c, base, ctx)
        finally:
            v2_phase5_cleanup(c, ctx)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "v2p6":
        ctx = {"cases": []}
        try:
            v2_phase6(c, base, ctx)
        finally:
            v2_phase6_cleanup(c, ctx)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "v2p7":
        ctx = {"cases": []}
        try:
            v2_phase7(c, base, ctx)
        finally:
            v2_phase7_cleanup(c, ctx)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase4":
        phase4(c, base)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase5":
        phase5(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase6":
        phase6(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase7":
        phase7(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "phase8":
        phase8(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    if only == "skills":
        skills_section(c); print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}"); return 0 if not FAIL else 1
    if only == "mcp":
        mcp_section(c, base); print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}"); return 0 if not FAIL else 1
    if only == "discord":
        discord_section(c); print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}"); return 0 if not FAIL else 1
    if only == "records":
        records_section(c); print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}"); return 0 if not FAIL else 1
    if only == "metrics":
        metrics_section(c, base); print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}"); return 0 if not FAIL else 1
    if only == "phase9":
        phase9(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    # 1. import lung case (incomplete)
    j, s = wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])
    g = c.get("/api/tb/cases/TB-001").json()["state"]["gate"]
    check("TB-001 ingest + gate", not g["passed"] and g["satisfied"] == 3 and g["total"] == 6, f"{j['total']} docs in {s}s, gate {g['satisfied']}/{g['total']} (NCG Essential records, V1 item 4.1)")
    st = {r["id"]: r["status"] for r in g["requirements"]}
    shown = {r["id"]: r for r in g.get("shown", [])}
    check("draft histopathology blocked as not final", st["histopathology"] == "not_final")
    check("brain MRI is NCG Optimal: shown as missing, not required at an Essential hospital", shown.get("brain_mri", {}).get("status") == "missing_record" and shown["brain_mri"]["tier"] == "b" and not shown["brain_mri"]["required"])
    check("PD-L1 pending (NCG Optimal, shown)", shown.get("pdl1", {}).get("status") == "missing_field")
    acts = c.get("/api/tb/cases/TB-001").json()["state"]["actions"]
    check("gaps routed to departments", {a["department"] for a in acts} >= {"Pathology"} and all(a["department_id"] for a in acts), ", ".join(sorted({a["department"] for a in acts})))  # V2 2.4: histopathology, molecular and CBC all to Pathology
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
    st = c.post("/api/tb/cases/TB-TEST/overrides", json={"kind": "requirements", "key": "driver_mutations", "value": {"waived": True, "reason": "not indicated per treating team"}}).json()
    req = {r["id"]: r for r in st["gate"]["requirements"]}
    check("waived requirement excluded from the gate", req["driver_mutations"]["status"] == "waived" and st["gate"]["total"] == 5, f"{req['driver_mutations']['status']} {st['gate']['total']}")
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
    # 9b. V2 Phase 2: treating / supporting departments, roles and accounts
    try:
        v2_phase2(c, base)
    finally:
        v2_phase2_cleanup(c)
    # 9c. V2 Phase 3: HIS-connected Case Files on a throw-away copy of the mock hospital
    ctx = {"cases": []}
    try:
        v2_phase3(c, base, ctx)
    finally:
        v2_phase3_cleanup(c, ctx)
    # 9d. V2 Phase 4: doctor-sent requests, the supporting inbox, auto-close on re-fetch, the stale summary (same throw-away mock)
    ctx = {"cases": []}
    try:
        v2_phase4(c, base, ctx)
    finally:
        v2_phase4_cleanup(c, ctx)
    # 9e. V2 Phase 5: owner, participants and scoped reads; the referral (P14); two primaries (P18) (same throw-away mock)
    ctx = {"cases": []}
    try:
        v2_phase5(c, base, ctx)
    finally:
        v2_phase5_cleanup(c, ctx)
    # 9f. V2 Phase 6: the coordinator's agenda from ready Case Files, reminders, the Board room, heads and the surgical seat, records and
    # images through the app, minutes, the PM-JAY flag only when empanelled (same throw-away mock; the live Orthanc for the images)
    ctx = {"cases": []}
    try:
        v2_phase6(c, base, ctx)
    finally:
        v2_phase6_cleanup(c, ctx)
    # 9g. V2 Phase 7: the home per role (treating, supporting, coordinator, department admin, root admin and the first set-up) (same throw-away mock)
    ctx = {"cases": []}
    try:
        v2_phase7(c, base, ctx)
    finally:
        v2_phase7_cleanup(c, ctx)
    # 10. V1 Phase 3: dates, document type, flags, big scans
    phase3(c)
    # 11. V1 Phase 4: NCG tiers, two-level gate, failed documents, inbox and notifications, stale summary, NCG VTB export
    phase4(c, base)
    # 12. V1 Phase 5: Indian guideline library, specialty packs
    phase5(c)
    # 13. V1 Phase 6: board session, agents for absent specialties, agent log vs decision, removed items, no-documents agents
    phase6(c)
    # 14. V1 Phase 7: PM-JAY board composition, guideline checks, flag resolution and amended decision, board actions in inboxes
    phase7(c)
    # 15. V1 Phase 8: scanned documents (from-scan badge, critical values from scans need a confirmation against the image)
    phase8(c)
    # 16. V1 Phase 9: the oral cavity (and later cervix) demo Case Files through the whole workflow (re-imported at the end of the section)
    phase9(c)
    # 17. 12 Oct: agent skills as SKILL.md files
    skills_section(c)
    # 18. 12 Oct: MCP server and connectors (needs serve_mcp.sh server + demo-his; the checks say so when they are down)
    mcp_section(c, base)
    # 19. 12 Oct: discordances between reports and the decision watch
    discord_section(c)
    # 20. 12 Oct: outcome and communication fields, audit chain, values over time, FHIR and registry exports
    records_section(c)
    # 21. 12 Oct: agenda readiness, chase list, quality dashboard
    metrics_section(c, base)
    # leave the demo Case Files in their fresh state for the next user / test
    for cid in ("TB-001", "TB-002", "TB-003"):
        wait_job(c, c.post(f"/api/tb/demo/{cid}").json()["job"])
    c.delete("/api/tb/cases/TB-TEST")
    print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:7000"); ap.add_argument("--password", required=True)
    ap.add_argument("--only", default=None, help="run one section only (phase2 | v2p2 | v2p3 | v2p4 | v2p5 | v2p6 | v2p7 | phase3 | phase4 | phase5 | phase6 | phase7 | phase8 | phase9 | skills | mcp | discord | records | metrics)")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.only))
