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
    o = c.get("/api/tb/org").json(); users = dict(o.get("users") or {}); users[user] = {"departments": {"radio_diagnosis": "member"}, "coordinator": False}
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
        check("4.1 Essential hospital: only the NCG Essential (a) records are required", set(req) == {"clinical_history", "cect_tap", "histopathology", "driver_mutations", "baseline_labs"}, ", ".join(sorted(req)))
        check("4.1 PET-CT, MRI brain, PD-L1, MET are NCG Optimal (b): shown, not required", all(shown.get(k, {}).get("tier") == "b" and shown[k]["required"] is False for k in ("pet_ct", "brain_mri", "pdl1", "met")),
              json.dumps({k: (shown.get(k) or {}).get("tier") for k in ("pet_ct", "brain_mri", "pdl1", "met")}))
        check("4.1 every required record cites its NCG line (guideline, page, quote)", all(r.get("source", {}).get("quote") and r["source"].get("page") for r in g["requirements"]),
              req["cect_tap"].get("source", {}).get("quote", ""))
        check("4.1 gate records the setting and hospital level", g["setting"] == "non_metastatic" and g["hospital_level"] == "essential" and g["setting_label"] and g["protocol_version"] == "0.7",
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
        check("4.2 Level 1 request routed to the department that owns the record (Radiology)", a.get("level") == 1 and a.get("department") == "Radiology" and a.get("department_id") == "radio_diagnosis", json.dumps({k: a.get(k) for k in ("level", "department", "department_id")}))
        check("4.2 gate summarises open gaps per level", g["levels"]["1"]["open"] >= 1 and "label" in g["levels"]["2"], json.dumps(g["levels"]))
        # 4.4 the radiology member sees the request in the inbox and the bell
        ib = m.get("/api/tb/inbox").json()
        mine = [q for dd in ib["departments"] for q in dd["requests"] if q["case_id"] == "TB-TEST4"]
        check("4.4 radiology member sees the request in the department inbox", [dd["id"] for dd in ib["departments"]] == ["radio_diagnosis"] and len(mine) == 1 and mine[0]["label"].startswith("CECT") and mine[0]["status"] == "pending" and mine[0]["level"] == 1,
              json.dumps(mine)[:160])
        nt = m.get("/api/tb/notifications").json()
        check("4.4 radiology member has an unread request notification", nt["unread"] >= 1 and any(n["kind"] == "request" and n["case_id"] == "TB-TEST4" and not n["read"] for n in nt["notifications"]), f"{nt['unread']} unread")
        adm = c.get("/api/tb/inbox").json()
        check("4.4 admin sees every department's inbox, the request under Radio-diagnosis only", "pathology" in [dd["id"] for dd in adm["departments"]]
              and [dd["id"] for dd in adm["departments"] if any(q["case_id"] == "TB-TEST4" and q["status"] != "completed" for q in dd["requests"])] == ["radio_diagnosis"])
        # the member uploads a CECT for the department: it files itself on the exact UHID; the lesion size is missing -> a Level 2 gap routed to the uploader
        ct1 = (head.format(dept="DEPARTMENT OF RADIO-DIAGNOSIS", title="CECT THORAX, ABDOMEN AND PELVIS") + "Study date: 24/09/2026\nFindings: spiculated mass in the right upper lobe; right hilar node.\n"
               "Abdomen and pelvis: no focal lesion.\nImpression: right upper lobe mass with right hilar adenopathy.\nReport status: FINAL\nSd/- Dr. S. Rao, Consultant Radiologist, Reg. No. KMC 12345\n").encode()
        r = m.post("/api/tb/intake/documents", files=[("files", ("cect_tap_2026-09-24.txt", ct1))], data={"paths": json.dumps(["cect_tap_2026-09-24.txt"]), "department": "radio_diagnosis"}).json()
        wait_job(m, r["job"])
        d = c.get("/api/tb/cases/TB-TEST4").json(); req = {x["id"]: x for x in d["state"]["gate"]["requirements"]}
        filed = [x for x in d["documents"] if x["rel_path"].endswith("cect_tap_2026-09-24.txt")]
        check("4.4 department upload filed into the Case File on the exact UHID", bool(filed) and filed[0].get("department") == "radio_diagnosis", json.dumps([(x["rel_path"], x.get("department")) for x in d["documents"]])[:200])
        check("4.2 CECT without the lesion size is a Level 2 gap", req["cect_tap"]["status"] == "missing_field" and req["cect_tap"]["level"] == 2 and req["cect_tap"]["level1"]["status"] == "satisfied",
              f"{req['cect_tap']['status']} L{req['cect_tap']['level']}: {'; '.join(req['cect_tap']['problems'])[:100]}")
        a = next((x for x in d["state"]["actions"] if x["requirement"] == "cect_tap" and x["status"] != "completed"), {})
        check("4.2 Level 2 request routed to the department that uploaded the record (Radio-diagnosis)", a.get("level") == 2 and a.get("department_id") == "radio_diagnosis" and a.get("source_doc_id") == (filed[0]["doc_id"] if filed else None)
              and any("Level 2" in h["event"] for h in a.get("history", [])), json.dumps({k: a.get(k) for k in ("level", "department", "department_id", "source_doc_id")}))
        # the corrected CECT arrives: the request closes by itself and the coordinator is told the Case File is ready
        ct2 = ct1.decode().replace("Study date: 24/09/2026", "Study date: 25/09/2026 (repeat read with measurements)").replace("Findings: spiculated mass in the right upper lobe;", "Findings: spiculated mass in the right upper lobe measuring 4.2 x 3.1 cm;").encode()
        r = m.post("/api/tb/intake/documents", files=[("files", ("cect_tap_2026-09-25_measured.txt", ct2))], data={"paths": json.dumps(["cect_tap_2026-09-25_measured.txt"]), "department": "radio_diagnosis"}).json()
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
    for dept, status in (("radio_diagnosis", "absent"), ("medical_oncology", "present"), ("surgical_oncology", "present"), ("radiation_oncology", "present"), ("pathology", "present")):
        c.post(f"/api/tb/sessions/{sid}/attendance", json={"department": dept, "status": status})
    c.post(f"/api/tb/sessions/{sid}/members", json={"name": "Dr. A. Rao (synthetic)", "department": "medical_oncology"})
    c.post(f"/api/tb/sessions/{sid}/members", json={"name": "Dr. B. Shah (synthetic)", "department": "surgical_oncology"})
    room = c.get(f"/api/tb/sessions/{sid}").json()
    att = room["session"]["attendance"]
    check("6.1 attendance and members present by name saved", att.get("radio_diagnosis") == "absent" and att.get("medical_oncology") == "present"
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
          (ag.get("TB-TEST6") or {}).get("radiology", {}).get("status") == "no_documents" and nb.get("message") == "No Radio-diagnosis documents in this Case File"
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
    row = next((q for d in ib["departments"] if d["id"] == "radio_diagnosis" for q in d["requests"] if q["action_id"] == act.get("id")), {})
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
    row = next((q for d in ib["departments"] if d["id"] == "radio_diagnosis" for q in d["requests"] if q["action_id"] == act.get("id")), {})
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


try:  # the corpus generator owns the decision text; the copy below is used only when it cannot be imported
    from tumour_board.demo_data.india_corpus import DECISION_TEXT_7
except Exception:
    DECISION_TEXT_7 = ("Composite resection: wide local excision of the left buccal mucosa lesion with segmental mandibulectomy, left modified neck "
                       "dissection (levels I to V) and reconstruction with a pectoralis major myocutaneous flap. Adjuvant radiotherapy 60 Gy in 30 "
                       "fractions to the tumour bed and neck, with concurrent Inj. Cisplatin 40 mg/m2 IV weekly if the final histopathology shows a "
                       "positive margin or extranodal extension. Stage as recorded: cT4a N1 M0.")

# V1 Phase 9: one entry per new demo Case File; phase9() walks each through the whole workflow. TB-008 (cervix, item 9.2) is one more entry.
V9_CASES = {
    "TB-007": {
        "site": "oral cavity", "protocol": "oral_cavity",
        "counted": ["clinical_history", "histopathology", "primary_neck_imaging", "chest_imaging", "dental_evaluation"],  # NCG records that count
        "optional": ["pet_ct", "cect_thorax"],  # NCG Optional (c): shown, never counted
        # V1 item 3.2 safeguard, intended: the reader types the dental Word file "other" while its title keywords say clinical_note, so the two
        # records it could satisfy wait for one clinician confirmation of its type (as the UI does), then the gate passes
        "confirm_type": {"rel_path": "surgical_oncology/dental_evaluation_2026-09-17.docx", "doc_type": "clinical_note", "records": ["clinical_history", "dental_evaluation"]},
        "listing": {"protocol": "oral_cavity", "setting": "locally_advanced", "board_date": "18/10/2026", "hospital_level": "essential"},
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
}


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


def phase9_case(c, cid, spec):
    """One Phase 9 demo Case File end to end through the HTTP API: import and gate under its NCG protocol (a disputed document type is
    confirmed as the UI does), listing with the NCG setting, a department upload matched on the UHID, Ask, the Case File summary, the
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
    opt = {k: (shown.get(k) or {}) for k in spec["optional"]}
    check(f"{tag}: {', '.join(spec['optional'])} shown as NCG Optional, not counted", all(v.get("tier") == "c" and v.get("required") is False and k not in req for k, v in opt.items()),
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
    unsat = {k: f"{v['status']}: {'; '.join(v.get('problems') or [])[:80]}" for k, v in req.items() if v["status"] != "satisfied"}
    check(f"{tag}: every counted record satisfied, gate passed", g.get("passed") is True and not unsat and g.get("total") == len(spec["counted"]),
          f"{g.get('satisfied')}/{g.get('total')} " + json.dumps(unsat)[:200])
    # b. listing with the NCG setting
    r = c.post(f"/api/tb/cases/{cid}/listing", json=spec["listing"])
    if r.status_code == 200 and r.json().get("total"):
        wait_job(c, r.json()["job"])
    d = c.get(f"/api/tb/cases/{cid}").json(); g = d["state"]["gate"] or {}; shown = {x["id"]: x for x in g.get("shown") or []}
    lst = spec["listing"]
    check(f"{tag}: listed with the NCG setting {lst['setting']}; gate still passes; PET-CT shown, not required",
          r.status_code == 200 and d["case"].get("setting") == lst["setting"] and g.get("setting") == lst["setting"] and g.get("hospital_level") == lst["hospital_level"]
          and g.get("passed") is True and (shown.get("pet_ct") or {}).get("required") is False,
          f"HTTP {r.status_code} {r.text[:80] if r.status_code != 200 else ''} setting {g.get('setting')}, {g.get('satisfied')}/{g.get('total')} passed {g.get('passed')}, "
          f"PET-CT {(shown.get('pet_ct') or {}).get('tier')}")
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
    check(f"{tag}: Ask '{q}' answered with a citation containing {want}", a.get("status") == "answered" and any(want in x for x in quotes),
          f"{a.get('status')} {a.get('seconds')} s: {[s['text'][:80] for s in a.get('statements') or []][:2]}")
    a = c.post(f"/api/tb/cases/{cid}/ask", json={"question": spec["refuse"]}).json()
    check(f"{tag}: '{spec['refuse']}' refused", a.get("status") == "out_of_scope" and not a.get("statements"), f"{a.get('status')} {a.get('category', '')}")
    # e. Case File summary: every sentence cited, current
    sm = c.post(f"/api/tb/cases/{cid}/summary", json={}).json()
    sents = [x for p in sm.get("paragraphs") or [] for x in p]
    stale = c.get(f"/api/tb/cases/{cid}").json()["stale"].get("summary")
    check(f"{tag}: Case File summary compiled, every sentence cited, not stale", sm.get("status") == "ready" and sents and all(x.get("citations") for x in sents) and stale == "",
          f"{len(sents)} sentences, {sum(not x.get('citations') for x in sents)} uncited, {sm.get('seconds')} s, stale {stale!r}"[:200])
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
    docs = c.get(f"/api/tb/cases/{cid}").json()["documents"]
    tbr = [x for x in docs if (x.get("classification") or {}).get("doc_type") == "tumour_board_record"]
    check(f"{tag}: arrivals: the board record document arrives and is read", r.status_code == 200 and bool(tbr) and all(x["state"] == "ready" for x in tbr),
          f"HTTP {r.status_code}; {[(x['rel_path'], x['state']) for x in tbr] or [x['rel_path'] for x in docs][-3:]}")
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


def phase9(c):
    """V1 Phase 9 (items 9.1 / 9.2): every new demo Case File (oral cavity TB-007, later cervix TB-008) runs the full workflow end to end."""
    have = {x.get("case_id") for x in c.get("/api/tb/cases").json().get("demo") or []}
    for cid, spec in V9_CASES.items():
        if cid not in have:
            check(f"9 {cid} ({spec['site']}): in the demo corpus", False, "not found under /data/vaidyx/tb_demo_corpus/cases (python -m tumour_board.demo_data.make_corpus)")
            continue
        phase9_case(c, cid, spec)


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
    if only == "phase3":
        phase3(c)
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
    if only == "phase9":
        phase9(c)
        print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
        return 0 if not FAIL else 1
    # 1. import lung case (incomplete)
    j, s = wait_job(c, c.post("/api/tb/demo/TB-001").json()["job"])
    g = c.get("/api/tb/cases/TB-001").json()["state"]["gate"]
    check("TB-001 ingest + gate", not g["passed"] and g["satisfied"] == 2 and g["total"] == 5, f"{j['total']} docs in {s}s, gate {g['satisfied']}/{g['total']} (NCG Essential records, V1 item 4.1)")
    st = {r["id"]: r["status"] for r in g["requirements"]}
    shown = {r["id"]: r for r in g.get("shown", [])}
    check("draft histopathology blocked as not final", st["histopathology"] == "not_final")
    check("brain MRI is NCG Optimal: shown as missing, not required at an Essential hospital", shown.get("brain_mri", {}).get("status") == "missing_record" and shown["brain_mri"]["tier"] == "b" and not shown["brain_mri"]["required"])
    check("PD-L1 pending (NCG Optimal, shown)", shown.get("pdl1", {}).get("status") == "missing_field")
    acts = c.get("/api/tb/cases/TB-001").json()["state"]["actions"]
    check("gaps routed to departments", {a["department"] for a in acts} >= {"Pathology", "Molecular Pathology", "Laboratory Medicine"}, ", ".join(sorted({a["department"] for a in acts})))
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
    check("waived requirement excluded from the gate", req["driver_mutations"]["status"] == "waived" and st["gate"]["total"] == 4, f"{req['driver_mutations']['status']} {st['gate']['total']}")
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
    # leave the demo Case Files in their fresh state for the next user / test
    for cid in ("TB-001", "TB-002", "TB-003"):
        wait_job(c, c.post(f"/api/tb/demo/{cid}").json()["job"])
    c.delete("/api/tb/cases/TB-TEST")
    print(f"\n{len(OK)} passed, {len(FAIL)} failed: {FAIL}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:7000"); ap.add_argument("--password", required=True)
    ap.add_argument("--only", default=None, help="run one section only (phase2 | phase3 | phase4 | phase5 | phase6 | phase7 | phase8 | phase9)")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.only))
