"""Browser test of the Vaidyx-TB UI (headless Chromium via Playwright). Fails on any JS error raised while a Tumour Board
page (path /tb) is open; the main app's login and index pages are outside this module and are not counted. Saves screenshots.
Usage: LD_LIBRARY_PATH=... python -m tumour_board.eval.ui_test --password <pw> [--out dir] [--viewports desktop,tablet,phone] [--only admin]
Viewports: desktop 1600x1000, tablet 1024x768, phone 390x844 (screenshots suffixed with the viewport name).
--only admin: log in and run only the Organisation and My department screens (V2 item 2.3), no model calls.
--only his: the HIS-connected Case File screens (V2 items 3.2 to 3.7) against the mock hospital (synthetic data, 127.0.0.1:7130):
create from a UHID, the HIS card, the Documents tab grouped by encounter, Re-fetch; the side panel as a treating doctor. Every
Case File it creates is deleted at the end (reader model calls for the fetched records).
--only requests: the requests to departments (V2 items 4.2 / 4.3) against the mock hospital: a treating doctor (tb-medonc-doc) creates
a Case File from IP/26/01875, notifies Radiology (the draft, the "Open in mail" mailto: link, Send in-app), the radiologist (tb-rad-doc)
acknowledges and sends "done" from the department inbox, the doctor writes and closes a free request to Anaesthesiology. Logins from
~/vaidyx/.tb_v2_demo_logins; the Case File is deleted at the end.
--only referral: referral and ownership (V2 items 5.1 to 5.3) against the mock hospital (read-only on it): two throw-away doctor logins
(Pulmonology, Colorectal Surgery) created through the Tumour Board; the Pulmonology doctor creates a Case File from VXH/26/004214 (lung),
refers it to Colorectal Surgery from the hospital system's suggested referral; the Colorectal Surgery doctor accepts it from the inbox
under colorectal_rectum (the gate re-runs on the same records, the lung gate stays as read-only history); the Pulmonology doctor stays as
a participant with no Notify / waive buttons. The Case File and the logins are deleted at the end."""
import argparse, os, secrets, sys, time
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright


VIEWPORTS = {"desktop": (1600, 1000), "tablet": (1024, 768), "phone": (390, 844)}


def watch(pg, errors):
    """Count JS errors and console errors raised while a Tumour Board page (path /tb) is open."""
    tb_page = lambda: urlparse(pg.url).path.rstrip("/") == "/tb"
    pg.on("pageerror", lambda e: tb_page() and errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and tb_page() and errors.append(f"console: {m.text} ({(m.location or {}).get('url', '')})"))


def login(pg, base, username, password):
    pg.goto(base + "/login")
    pg.fill("input[type=text], input[name=username], #username", username)
    pg.fill("input[type=password]", password)
    pg.keyboard.press("Enter")
    try:  # a slow login (bcrypt under load) must not leave the page on /login
        pg.wait_for_url(lambda u: urlparse(u).path.rstrip("/") != "/login", timeout=15000)
    except Exception:
        pass  # the next step names what is missing
    pg.wait_for_timeout(2500)


UI_RADADMIN, UI_RADDOC = "tb-ui-radadmin", "tb-ui-raddoc"  # throwaway synthetic logins, removed after the admin pass


def admin_cleanup(pg, base):
    """As admin: take the throwaway department admin and doctor out of the organisation and delete their Vaidyx logins.
    Errors here are not test failures (the accounts may not exist); the next run starts clean either way."""
    pg.request.delete(base + f"/api/tb/org/departments/radiology/doctors/{UI_RADDOC}")
    o = pg.request.get(base + "/api/tb/org")
    if o.ok:
        o = o.json(); users = {u: v for u, v in (o.get("users") or {}).items() if u not in (UI_RADADMIN, UI_RADDOC)}
        if users != (o.get("users") or {}) or any(u in (o.get("admins") or []) for u in (UI_RADADMIN, UI_RADDOC)):
            pg.request.put(base + "/api/tb/org", data={"hospital": o["hospital"], "departments": o["departments"], "users": users,
                                                        "admins": [a for a in (o.get("admins") or []) if a not in (UI_RADADMIN, UI_RADDOC)], "routes": o.get("routes") or {}})
    for u in (UI_RADADMIN, UI_RADDOC):
        pg.request.delete(base + "/api/auth/users", data={"username": u})


def admin_screens(b, pg, base, pw, shot, errors):
    """V2 item 2.3. Root admin: the Organisation section (hospital settings, departments, accounts, audit). Department admin: a
    throwaway Radiology department admin creates a doctor login through the My department form, then disables and re-enables it.
    `pg` is logged in as admin; the throwaway logins are removed through the API even when a step fails. Passwords are random and
    never printed or shown."""
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)  # narrow screens: the side panel must be closed before the top bar is clickable
    pg.click("#btn-org"); pg.wait_for_selector("#o-depts tr", timeout=20000); pg.wait_for_selector("#o-users tr[data-user]", timeout=20000)
    pg.wait_for_selector("#o-routes .rt-sel", timeout=20000)  # V2 2.4: the routing table (one select per protocol record)
    pg.wait_for_timeout(500); shot("org_admin", full_page=True)
    for sel, what in [("#o-pmjay", "PM-JAY empanelled checkbox"), ("#o-fetch", "HIS fetch window"), ("#o-routes #rt-save", "routing table"), ("#na-create", "New login form")]:
        if not pg.locator(sel).count():
            errors.append(f"Organisation: no {what} ({sel})")
    pg2 = None
    admin_cleanup(pg, base)  # a previous run that stopped half way
    try:
        pw_admin = "Synthetic-" + secrets.token_urlsafe(12)  # random, synthetic, never printed
        r = pg.request.post(base + "/api/tb/org/accounts", data={"username": UI_RADADMIN, "password": pw_admin,
                                                                  "display_name": "Radiology admin (UI test, synthetic)", "admin_of": ["radiology"]})
        if not r.ok:  # never a silent pass: the department admin screen must be visited
            errors.append(f"department admin for the My department check could not be created: HTTP {r.status}"); return
        vp = pg.viewport_size
        pg2 = b.new_page(viewport=vp, device_scale_factor=1); watch(pg2, errors)
        login(pg2, base, UI_RADADMIN, pw_admin)
        pg2.goto(base + "/tb"); pg2.wait_for_selector("#btn-mydept:not(.hidden)", timeout=20000)
        if pg2.locator("#btn-org").is_visible():
            errors.append("a department admin sees the Organisation button")
        pg2.click("#btn-mydept"); pg2.wait_for_selector("#dp-doctors tr[data-user]", timeout=20000)
        pg2.fill("#nd-user", UI_RADDOC); pg2.fill("#nd-pass", "Synthetic-" + secrets.token_urlsafe(12))
        pg2.fill("#nd-name", "Dr. Radiology Doctor (UI test, synthetic)"); pg2.select_option("#nd-role", "doctor"); pg2.click("#nd-create")
        row = f"#dp-doctors tr[data-user='{UI_RADDOC}']"
        pg2.wait_for_selector(row, timeout=20000); pg2.wait_for_timeout(500)
        shot("dept_admin", page=pg2, full_page=True)
        pg2.click(f"{row} [data-dis='1']"); pg2.wait_for_selector(f"{row} [data-dis='0']", timeout=20000)
        if "Disabled" not in pg2.inner_text(row):
            errors.append("My department: the disabled doctor shows no Disabled chip")
        pg2.click(f"{row} [data-dis='0']"); pg2.wait_for_selector(f"{row} [data-dis='1']", timeout=20000)
        if "Disabled" in pg2.inner_text(row):
            errors.append("My department: the re-enabled doctor still shows Disabled")
    finally:
        if pg2:
            pg2.close()
        admin_cleanup(pg, base)


DEMO_LOGINS = os.path.expanduser("~/vaidyx/.tb_v2_demo_logins")  # synthetic V2 role logins (tab-separated); passwords never printed
PROTECTED = {"TB-2026-bharath"}  # real patient data: never touched
DEMO_CASES = {f"TB-00{i}" for i in range(1, 9)}  # the demo Case Files: the requests flow never deletes one


def page_checks(pg, where, errors):
    """No em dash in the visible text and no sideways scroll of the page or the main column."""
    txt = pg.inner_text("body")
    if "\u2014" in txt:
        errors.append(f"{where}: an em dash in the visible text")
    wide = pg.evaluate("""() => { const d = document.documentElement, m = document.getElementById('main');
        return d.scrollWidth > d.clientWidth + 1 || (m && getComputedStyle(m).overflowX !== 'visible' && m.scrollWidth > m.clientWidth + 1); }""")
    if wide:
        errors.append(f"{where}: the page scrolls sideways")


def open_side(pg):
    if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
        pg.click("#btn-side"); pg.wait_for_timeout(350)


def wait_job(pg, base, job, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = pg.request.get(base + f"/api/tb/jobs/{job}")
        if r.ok and r.json().get("state") in ("finished", "failed", "interrupted"):
            return r.json()
        time.sleep(2)
    return None


def demo_login(name):
    """(username, password) of a demo role login, or None when the file or the row is missing."""
    try:
        for line in open(DEMO_LOGINS):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] == name:
                return parts[0], parts[1]
    except OSError:
        return None
    return None


def his_screens(b, pg, base, pw, shot, errors):
    """V2 items 3.2 to 3.7 against the mock hospital (synthetic): look up a UHID with a temporary registration, create a Case File
    from another UHID, the HIS card on the Pre-Authorization tab, the Documents tab grouped by encounter, Re-fetch; then the side
    panel as a treating doctor (no department upload box) and as admin (the box stays). The Case File is deleted in `finally`."""
    cid = None
    try:
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
        open_side(pg); pg.click("#btn-new")
        pg.wait_for_selector("[data-way='his']", timeout=20000); pg.click("[data-way='his']")
        pg.fill("#h-id", "VXH/26/004209"); pg.click("#h-look"); pg.wait_for_selector("#h-res .lookbox", timeout=30000)
        t = pg.inner_text("#h-res")
        if "VXH/T/26/00412" not in t or "temporary registration" not in t or "never merged automatically" not in t:
            errors.append("lookup of VXH/26/004209 does not list the temporary registration VXH/T/26/00412 with the link note")
        page_checks(pg, "lookup", errors); shot("his_1_lookup")
        pg.fill("#h-id", "VXH/26/004201"); pg.click("#h-look"); pg.wait_for_selector("#h-res .lookbox:has-text('VXH/26/004201')", timeout=30000)
        if "IP admission" not in pg.inner_text("#h-res"):
            errors.append("lookup of VXH/26/004201 does not count the IP admission")
        pg.select_option("#h-prot", "breast"); pg.select_option("#h-setting", "early"); pg.select_option("#h-level", "optimal")
        pg.select_option("#h-win", "12"); pg.select_option("#h-dept", "breast_surgery")
        shot("his_2_create_form")
        with pg.expect_response(lambda r: "/api/tb/cases/from-his" in r.url, timeout=60000) as resp:
            pg.click("#h-go")
        if not resp.value.ok:
            errors.append(f"create from the HIS failed: HTTP {resp.value.status} {resp.value.text()[:160]}"); return
        res = resp.value.json(); cid = res["case"]["case_id"]
        if cid in PROTECTED:  # never: the server assigns a fresh id; refuse to go on rather than touch it
            cid = None; errors.append("create from the HIS returned a protected Case File id"); return
        pg.wait_for_selector("#his-card", timeout=30000)
        j = wait_job(pg, base, res["job"])
        if not j or j.get("state") != "finished":
            errors.append(f"first fetch job did not finish: {(j or {}).get('state')} {(j or {}).get('error', '')}"); return
        pg.wait_for_function("() => /finished from/.test(document.getElementById('toast').textContent)", timeout=60000)
        pg.wait_for_timeout(800)
        for sel, what in [("#his-card", "HIS card"), ("#btn-refetch", "Re-fetch button next to Re-check"), ("#his-card [data-refetch]", "Re-fetch in the HIS card"), ("#his-card .mono", "UHID")]:
            if not pg.locator(sel).count():
                errors.append(f"Pre-Authorization tab: no {what} ({sel})")
        if "VXH/26/004201" not in pg.inner_text("#his-card"):
            errors.append("HIS card does not show the UHID")
        if "outside report" not in pg.inner_text("#tab-ready").lower():
            errors.append("the upload box of an HIS Case File does not speak of outside reports")
        page_checks(pg, "Pre-Authorization tab", errors); shot("his_3_ready", full_page=True)
        pg.click("#tabs button[data-tab='docs']"); pg.wait_for_selector("#tab-docs .encgroup", timeout=20000); pg.wait_for_timeout(500)
        d = pg.inner_text("#tab-docs")
        if "Pre-admission OPD" not in d and "OP visit" not in d:
            errors.append("Documents tab: no OP visit group heading or Pre-admission OPD chip")
        if "IP admission IP/26/01871" not in d:
            errors.append("Documents tab: no IP admission group")
        if pg.locator("#tab-docs .chip:has-text('Digitally signed')").count() == 0:
            errors.append("Documents tab: no 'Digitally signed' chip on the signed HIS reports")
        if pg.locator("#tab-docs .chip:has-text('from HIS')").count() == 0:
            errors.append("Documents tab: no 'from HIS' chip")
        page_checks(pg, "Documents tab", errors); shot("his_4_documents", full_page=True)
        pg.click("#tabs button[data-tab='board']"); pg.wait_for_timeout(700)
        if "IP admission IP/26/01871" not in pg.inner_text("#tab-board"):
            errors.append("timeline: no IP admission event")
        page_checks(pg, "Board tab", errors)
        pg.click("#tabs button[data-tab='ready']"); pg.wait_for_selector("#btn-refetch", timeout=20000)
        pg.evaluate("document.getElementById('toast').textContent = ''")
        pg.click("#btn-refetch")
        pg.wait_for_function("() => /Re-fetch finished/.test(document.getElementById('toast').textContent)", timeout=600000)
        if "Requests closed" not in pg.inner_text("#toast"):
            errors.append("Re-fetch toast does not report the requests closed / opened")
        shot("his_5_refetch")
        open_side(pg)
        if pg.locator("#intake-upload").is_hidden() or pg.locator("#side-intake").is_hidden():
            errors.append("side panel: the department upload box is hidden for the Vaidyx admin")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    finally:
        if cid and cid not in PROTECTED:
            r = pg.request.delete(base + f"/api/tb/cases/{cid}")
            if not r.ok:
                errors.append(f"could not delete the test Case File {cid}: HTTP {r.status}")
    cred = demo_login("tb-breast-doc")
    if not cred:
        print(f"note: {DEMO_LOGINS} (tb-breast-doc) missing: the treating-doctor side panel check is skipped")
        return
    pg2 = b.new_page(viewport=pg.viewport_size, device_scale_factor=1); watch(pg2, errors)
    try:
        login(pg2, base, *cred)
        pg2.goto(base + "/tb"); pg2.wait_for_selector("#side-intake", state="attached", timeout=20000); pg2.wait_for_timeout(1500)
        if not pg2.locator("#intake-upload").is_hidden():
            errors.append("side panel: a treating doctor sees the department upload box (plan 3.7)")
        open_side(pg2)
        if pg2.locator("#side-intake").is_visible() and "records" not in pg2.inner_text("#side-intake h4").lower():
            errors.append("side panel: the records block is not titled Records")
        if pg2.locator("#btn-new").is_visible():
            pg2.click("#btn-new"); pg2.wait_for_selector("#nc-his", state="attached", timeout=20000)
            if not pg2.locator("[data-way='his'].on").count():
                errors.append("+ New: a treating doctor does not start on From the hospital system")
            if pg2.locator("#h-dept[readonly]").count() and "Breast Surgery" not in (pg2.input_value("#h-dept") or ""):
                errors.append("+ New: the treating doctor's own department is not shown")
            page_checks(pg2, "doctor + New", errors); shot("his_6_doctor_new", page=pg2)
            pg2.keyboard.press("Escape"); pg2.wait_for_timeout(300)
        else:
            errors.append("tb-breast-doc sees no + New button")
        page_checks(pg2, "doctor home", errors); shot("his_7_doctor_side", page=pg2)
    finally:
        pg2.close()


REQ_IP, REQ_UHID, REQ_ACC = "IP/26/01875", "VXH/26/004212", "RAD/26/01004"  # mock hospital, synthetic: lung, CECT ordered in the RIS


def requests_screens(b, pg, base, pw, shot, errors):
    """V2 items 4.2 / 4.3 against the mock hospital (synthetic). A treating doctor (tb-medonc-doc) creates a Case File from IP/26/01875;
    the CECT gap shows as a suggested request with "Notify Radiology"; the draft names the UHID, the IP No. and the accession No.; the
    "Open in mail" link is a mailto: with the subject and the message; "Send in-app" sends it. The radiologist (tb-rad-doc) sees it in
    the department inbox with the UHID and the accession No., acknowledges it and sends "done" back with a note. The doctor sees both,
    then writes a free request to Anaesthesiology (pre-anaesthetic check-up) and closes it. `pg` is the admin page: it deletes the
    Case File in `finally`. Nothing is signed on the mock desk."""
    doc, rad = demo_login("tb-medonc-doc"), demo_login("tb-rad-doc")
    if not doc or not rad:  # never a silent pass
        errors.append(f"{DEMO_LOGINS} lacks tb-medonc-doc or tb-rad-doc: the requests screens cannot be checked"); return
    cid, pages = None, []

    def page_as(cred):
        p = b.new_page(viewport=pg.viewport_size, device_scale_factor=1); watch(p, errors); pages.append(p)
        login(p, base, *cred); p.goto(base + "/tb"); p.wait_for_selector("#btn-new", state="attached", timeout=20000); p.wait_for_timeout(800)
        return p

    def open_case(p, case_id):
        open_side(p); p.click(f".citem[data-case='{case_id}']"); p.click("#tabs button[data-tab='ready']"); p.wait_for_selector("#req-card", timeout=20000)

    try:
        d = page_as(doc)
        open_side(d); d.click("#btn-new"); d.wait_for_selector("#h-id", timeout=20000)
        if d.locator("[data-way='his']").count() and not d.locator("[data-way='his'].on").count():
            d.click("[data-way='his']")
        d.fill("#h-id", REQ_IP); d.click("#h-look"); d.wait_for_selector("#h-res .lookbox", timeout=30000)
        if REQ_UHID not in d.inner_text("#h-res"):
            errors.append(f"lookup of {REQ_IP} does not show the UHID {REQ_UHID}")
        d.select_option("#h-prot", "lung_nsclc"); d.select_option("#h-setting", "non_metastatic"); d.select_option("#h-level", "optimal"); d.select_option("#h-win", "12")
        with d.expect_response(lambda r: "/api/tb/cases/from-his" in r.url, timeout=60000) as resp:
            d.click("#h-go")
        if not resp.value.ok:
            errors.append(f"create from the HIS as tb-medonc-doc failed: HTTP {resp.value.status} {resp.value.text()[:160]}"); return
        res = resp.value.json(); cid = res["case"]["case_id"]
        if cid in PROTECTED or cid in DEMO_CASES:  # the server assigns a fresh id; refuse to go on rather than touch a protected one
            cid = None; errors.append("create from the HIS returned a protected Case File id"); return
        j = wait_job(d, base, res["job"])
        if not j or j.get("state") != "finished":
            errors.append(f"first fetch job did not finish: {(j or {}).get('state')} {(j or {}).get('error', '')}"); return
        d.wait_for_function("() => /finished from/.test(document.getElementById('toast').textContent)", timeout=60000)
        cect, t0 = None, time.time()
        while not cect and time.time() - t0 < 90:  # the gate's re-check after the job may land a moment later
            st = d.request.get(base + f"/api/tb/cases/{cid}").json()
            acts = [a for a in st["state"].get("actions") or [] if a.get("source") == "pre_authorization"]
            cect = next((a for a in acts if a.get("accession") == REQ_ACC), None) or next((a for a in acts if a.get("requirement") == "cect_tap"), None)
            if not cect:
                time.sleep(3)
        if not cect:
            gate = st["state"].get("gate") or {}
            errors.append(f"no Pre-Authorization request for the CECT ({REQ_ACC}) in {cid}: requests {[(a.get('requirement'), a.get('status')) for a in acts]}, "
                          f"gate {gate.get('satisfied')}/{gate.get('total')} {[(x.get('id'), x.get('status')) for x in gate.get('requirements') or [] if x.get('status') != 'satisfied']}, "
                          f"CT records {[((x.get('classification') or {}).get('status'), (x.get('his') or {}).get('status'), (x.get('his') or {}).get('accession')) for x in st.get('documents') or [] if (x.get('classification') or {}).get('doc_type') == 'ct']}"); return
        if not st.get("permissions", {}).get("send_request"):
            errors.append("tb-medonc-doc (a treating doctor) may not send requests")
        card = f"#tab-ready .reqcard[data-aid='{cect['id']}']"
        open_case(d, cid); d.wait_for_selector(card, timeout=20000); d.wait_for_timeout(500)
        if "Requests to departments" not in d.inner_text("#req-card h3"):
            errors.append("the requests card is not titled Requests to departments")
        if "Suggested" not in d.inner_text(f"{card} .reqst"):
            errors.append(f"the CECT request is not shown as suggested: {d.inner_text(card + ' .reqst')!r}")
        btn = d.locator(f"{card} [data-notify]")
        if not btn.count() or btn.inner_text().strip() != "Notify Radiology":
            errors.append(f"the CECT request has no 'Notify Radiology' button ({btn.inner_text().strip() if btn.count() else 'none'})"); return
        if REQ_ACC not in d.inner_text(card):
            errors.append("the CECT request does not show the accession No. chip")
        page_checks(d, "Requests card (suggested)", errors); shot("req_1_suggested", page=d, full_page=True)
        btn.click(); d.wait_for_selector("#reqtxt", timeout=20000); d.wait_for_timeout(300)
        body, subj = d.input_value("#reqtxt"), d.input_value("#reqsubj")
        for v, what in [(REQ_UHID, "UHID"), (REQ_IP, "IP No."), (REQ_ACC, "accession No.")]:
            if v not in body:
                errors.append(f"the draft message lacks the {what} {v}")
        if not d.input_value("#reqdue"):
            errors.append("the Notify dialog has no proposed due date")
        if not d.locator("a#reqmail").count():
            errors.append("the Notify dialog has no 'Open in mail' link (Radiology has an address)")
        else:
            href = d.get_attribute("a#reqmail", "href") or ""
            plain = unquote(href)
            if not href.startswith("mailto:"):
                errors.append(f"'Open in mail' is not a mailto: link: {href[:60]!r}")
            if REQ_UHID not in plain or subj not in plain or REQ_ACC not in plain:
                errors.append("the mailto: link does not carry the subject and the message (UHID, accession No.)")
            d.fill("#reqsubj", subj + " (urgent)")
            if "(urgent)" not in unquote(d.get_attribute("a#reqmail", "href") or ""):
                errors.append("the mailto: link is not rebuilt from the edited subject")
            d.fill("#reqsubj", subj)
        if "sends no e-mail" not in d.inner_text("#modal-body"):
            errors.append("the Notify dialog does not say that the server sends no e-mail")
        if not d.locator("#reqcopy").count():
            errors.append("the Notify dialog has no 'Copy draft' button")
        page_checks(d, "Notify dialog", errors); shot("req_2_notify", page=d)
        d.click("#reqsend")
        d.wait_for_selector(f"{card} .reqst:has-text('Sent')", timeout=20000); d.wait_for_timeout(400)
        if "Request sent to Radiology" not in d.inner_text("#toast"):
            errors.append(f"no 'Request sent to Radiology' toast: {d.inner_text('#toast')[:100]!r}")
        if not d.locator(f"{card} [data-reqmsg]").count() or "Send again" not in d.inner_text(card):
            errors.append("a sent request offers no 'Request message' / 'Send again'")
        d.click(f"{card} [data-reqmsg]"); d.wait_for_selector("#reqview", timeout=10000)
        if REQ_UHID not in d.input_value("#reqview"):
            errors.append("the Request message view does not show the message as sent")
        d.keyboard.press("Escape"); d.wait_for_timeout(300)
        shot("req_3_sent", page=d, full_page=True)

        r = page_as(rad)
        open_side(r); r.click("#btn-inbox")
        row = f"#inbox tr[data-aid='{cect['id']}']"
        r.wait_for_selector(row, timeout=20000); r.wait_for_timeout(400)
        t = r.inner_text(row)
        if REQ_UHID not in t or REQ_ACC not in t:
            errors.append(f"the Radiology inbox row lacks the UHID {REQ_UHID} or the accession No. {REQ_ACC}")
        if "Sent" not in r.inner_text(f"{row} .reqst"):
            errors.append(f"the inbox row is not shown as Sent: {r.inner_text(row + ' .reqst')!r}")
        page_checks(r, "Radiology inbox", errors); shot("req_4_inbox", page=r, full_page=True)
        if (r.request.get(base + f"/api/tb/cases/{cid}").json().get("access") or {}).get("scope") == "requests":  # V2 item 5.1: a department that was only asked
            r.click(f"{row} td:first-child"); r.wait_for_selector("#limited-note", timeout=20000); r.wait_for_timeout(400)
            if "only the items it was asked about" not in r.inner_text("#limited-note"):
                errors.append("the reduced Case File view does not say the department sees only the items it was asked about")
            if not r.locator(f"#tab-ready .reqcard[data-aid='{cect['id']}'] [data-ack]").count():
                errors.append("the reduced Case File view offers no Acknowledge on the department's request")
            shown = [t for t in ("ask", "roles", "summary", "board", "audit") if r.locator(f"#tabs button[data-tab='{t}']").is_visible()]
            if shown or r.locator("#own-card, #btn-recheck").count():
                errors.append(f"the reduced Case File view shows more than the requests and records: tabs {shown}")
            page_checks(r, "Reduced Case File view (Radiology)", errors); shot("req_4b_limited", page=r, full_page=True)
            open_side(r); r.click("#btn-inbox"); r.wait_for_selector(row, timeout=20000); r.wait_for_timeout(300)
        else:
            print("note: tb-rad-doc reads the whole Case File (placed in more than Radiology?): the reduced view check is skipped")
        r.click(f"{row} [data-ack]"); r.wait_for_selector(f"{row} .reqst:has-text('Acknowledged')", timeout=20000)
        if r.locator(f"{row} [data-ack]").count():
            errors.append("Acknowledge is still offered after acknowledging")
        r.once("dialog", lambda dlg: dlg.accept("CECT reported and signed in the RIS (UI test, synthetic)"))
        r.click(f"{row} [data-done]"); r.wait_for_selector(f"{row} .reqst:has-text('Done')", timeout=20000); r.wait_for_timeout(400)
        if "signed in the RIS" not in r.inner_text(row):
            errors.append("the inbox row does not show the done note")
        page_checks(r, "Radiology inbox (done)", errors); shot("req_5_inbox_done", page=r, full_page=True)

        open_case(d, cid); d.wait_for_selector(card, timeout=20000); d.wait_for_timeout(400)
        t = d.inner_text(card)
        if "Acknowledged by" not in t or "Done, awaiting the record" not in d.inner_text(f"{card} .reqst"):
            errors.append(f"the Case File does not show the request as acknowledged and done: {d.inner_text(card + ' .reqst')!r}")
        if d.locator("#btn-bell").is_visible():
            d.click("#btn-bell"); d.wait_for_selector("#modal-body .ntf", timeout=10000)
            n = d.inner_text("#modal-body")
            if "Done by the department" not in n or "Re-fetch from the HIS to close it" not in n:
                errors.append("the bell does not show the done notification with the re-fetch hint")
            page_checks(d, "Notifications", errors); shot("req_6_bell", page=d)
            d.keyboard.press("Escape"); d.wait_for_timeout(300)
        d.click("#req-card [data-newreq]"); d.wait_for_selector("#fr-dept", timeout=10000)
        d.select_option("#fr-dept", "anaesthesiology"); d.fill("#fr-label", "Pre-anaesthetic check-up")
        d.fill("#fr-what", "Planned for surgery after the board (UI test, synthetic)")
        page_checks(d, "Notify a department dialog", errors); shot("req_7_free", page=d)
        d.click("#fr-send")
        free = "#tab-ready .reqcard:has-text('Pre-anaesthetic check-up')"
        d.wait_for_selector(f"{free} .reqst:has-text('Sent')", timeout=20000); d.wait_for_timeout(300)
        if "Anaesthesiology" not in d.inner_text(free):
            errors.append("the free request does not name Anaesthesiology")
        d.click(f"{free} [data-closereq]"); d.wait_for_selector("#cd-note", timeout=10000)
        d.fill("#cd-note", "Done in the OPD (UI test, synthetic)"); d.click("#cd-ok")
        d.wait_for_selector(f"{free} .reqst:has-text('Closed')", timeout=20000); d.wait_for_timeout(300)
        page_checks(d, "Requests card (after)", errors); shot("req_8_after", page=d, full_page=True)
    finally:
        for p in pages:
            p.close()
        if cid and cid not in PROTECTED and cid not in DEMO_CASES:
            r = pg.request.delete(base + f"/api/tb/cases/{cid}")
            if not r.ok:
                errors.append(f"could not delete the test Case File {cid}: HTTP {r.status}")


REF_UHID = "VXH/26/004214"  # mock hospital, synthetic: a lung work-up the hospital system later refers to Colorectal Surgery (plan 1.1, P14)
UI_PULM, UI_CRS = "tb-ui-pulmdoc", "tb-ui-crsdoc"  # throw-away synthetic doctor logins of the referral flow


def referral_cleanup(pg, base, cid=None):
    """As admin: delete the flow's Case File and its two doctor logins (org roles and Vaidyx accounts). Errors are not test failures
    here (the next run starts clean either way)."""
    if cid and cid not in PROTECTED and cid not in DEMO_CASES:
        pg.request.delete(base + f"/api/tb/cases/{cid}")
    o = pg.request.get(base + "/api/tb/org")
    if o.ok:
        cur = o.json().get("users") or {}
        users = {u: v for u, v in cur.items() if u not in (UI_PULM, UI_CRS)}
        if users != cur:
            pg.request.put(base + "/api/tb/org", data={"users": users})
    for u in (UI_PULM, UI_CRS):
        pg.request.delete(base + "/api/auth/users", data={"username": u})


def referral_screens(b, pg, base, pw, shot, errors):
    """V2 items 5.1 to 5.3 against the mock hospital (synthetic, read-only). A throw-away Pulmonology doctor creates a Case File from
    VXH/26/004214 (lung_nsclc, metastatic, Optimal); the Ownership card shows Pulmonology as the owner and the hospital system's referral
    to Colorectal Surgery as a suggestion; Refer opens the pre-filled dialog; Send shows the waiting referral. A throw-away Colorectal
    Surgery doctor accepts it from the inbox Referrals card under colorectal_rectum / metastatic; the header shows the new owner and
    Pulmonology participating; the Pre-Authorization tab shows the earlier lung gate as read-only history. The Pulmonology doctor still
    opens the Case File (participant) without Notify / waive / Refer. `pg` is the admin page: it deletes the Case File and the logins."""
    cid, pages = None, []
    h = pg.request.get(base + "/api/tb/his")
    if not (h.ok and (h.json().get("status") or {}).get("ok")):
        errors.append(f"the hospital system does not answer for the referral flow: HTTP {h.status}"); return
    referral_cleanup(pg, base)  # a previous run that stopped half way
    creds = {}
    try:
        for u, dept, name in [(UI_PULM, "pulmonology", "Dr. Pulmonology Doctor (UI test, synthetic)"), (UI_CRS, "colorectal_surgery", "Dr. Colorectal Surgeon (UI test, synthetic)")]:
            creds[u] = "Synthetic-" + secrets.token_urlsafe(12)  # random, synthetic, never printed
            r = pg.request.post(base + "/api/tb/org/accounts", data={"username": u, "password": creds[u], "departments": {dept: "doctor"}, "display_name": name})
            if not r.ok:
                errors.append(f"the {dept} doctor login for the referral flow could not be created: HTTP {r.status} {r.text()[:120]}"); return

        def page_as(u):
            p = b.new_page(viewport=pg.viewport_size, device_scale_factor=1); watch(p, errors); pages.append(p)
            login(p, base, u, creds[u]); p.goto(base + "/tb"); p.wait_for_selector("#btn-new", state="attached", timeout=20000); p.wait_for_timeout(800)
            return p

        def open_case(p, case_id):
            open_side(p); p.click(f".citem[data-case='{case_id}']"); p.click("#tabs button[data-tab='ready']"); p.wait_for_selector("#own-card", timeout=30000); p.wait_for_timeout(400)

        d = page_as(UI_PULM)
        open_side(d); d.click("#btn-new"); d.wait_for_selector("#h-id", timeout=20000)
        if d.locator("[data-way='his']").count() and not d.locator("[data-way='his'].on").count():
            d.click("[data-way='his']")
        d.fill("#h-id", REF_UHID); d.click("#h-look"); d.wait_for_selector("#h-res .lookbox", timeout=30000)
        d.select_option("#h-prot", "lung_nsclc"); d.select_option("#h-setting", "metastatic"); d.select_option("#h-level", "optimal"); d.select_option("#h-win", "12")
        if d.locator("#h-dept[readonly]").count() and "Pulmonology" not in (d.input_value("#h-dept") or ""):
            errors.append("+ New: the Pulmonology doctor's own department is not shown as the owner")
        with d.expect_response(lambda r: "/api/tb/cases/from-his" in r.url, timeout=60000) as resp:
            d.click("#h-go")
        if not resp.value.ok:
            errors.append(f"create from the HIS as the Pulmonology doctor failed: HTTP {resp.value.status} {resp.value.text()[:160]}"); return
        res = resp.value.json(); cid = res["case"]["case_id"]
        if cid in PROTECTED or cid in DEMO_CASES:  # the server assigns a fresh id; refuse to go on rather than touch a protected one
            cid = None; errors.append("create from the HIS returned a protected Case File id"); return
        j = wait_job(d, base, res["job"])
        if not j or j.get("state") != "finished":
            errors.append(f"first fetch job did not finish: {(j or {}).get('state')} {(j or {}).get('error', '')}"); return
        d.wait_for_function("() => /finished from/.test(document.getElementById('toast').textContent)", timeout=60000)
        st = d.request.get(base + f"/api/tb/cases/{cid}").json()
        sug = [s for s in (st.get("referral") or {}).get("suggestions") or [] if s.get("to") == "colorectal_surgery"]
        if (st.get("access") or {}).get("owner", {}).get("id") != "pulmonology" or not sug:
            errors.append(f"the Case File is not owned by Pulmonology with the hospital system's referral to Colorectal Surgery suggested: owner {(st.get('access') or {}).get('owner')}, "
                          f"suggestions {[(s.get('from'), s.get('to')) for s in (st.get('referral') or {}).get('suggestions') or []]}, HIS referrals {len((st.get('his') or {}).get('referrals') or [])}"); return
        open_case(d, cid)
        if "Pulmonology" not in d.inner_text("#own-name"):
            errors.append(f"the Ownership card does not show Pulmonology as the owner: {d.inner_text('#own-name')!r}")
        if "Owner: Pulmonology" not in d.inner_text("#c-owner"):
            errors.append(f"the Case File header does not show Owner: Pulmonology: {d.inner_text('#c-owner')!r}")
        card = f"#own-card .refsug[data-hisref='{sug[0]['his_ref']}']"
        if "referral from Pulmonology to Colorectal Surgery" not in d.inner_text(card):
            errors.append(f"the suggestion does not read 'referral from Pulmonology to Colorectal Surgery': {d.inner_text(card)[:160]!r}")
        if not d.locator(f"{card} [data-refsugx]").count():
            errors.append("the suggestion has no Dismiss button")
        page_checks(d, "Ownership card (suggestion)", errors); shot("ref_1_suggestion", page=d, full_page=True)
        d.click(f"{card} [data-refsug]"); d.wait_for_selector("#rf-to", timeout=10000); d.wait_for_timeout(300)
        if d.input_value("#rf-to") != "colorectal_surgery" or not d.input_value("#rf-reason").strip():
            errors.append(f"the referral dialog is not pre-filled from the suggestion: to {d.input_value('#rf-to')!r}, reason {d.input_value('#rf-reason')[:60]!r}")
        if d.locator("#rf-to option[value='pulmonology']").count():
            errors.append("the referral dialog offers the owning department itself")
        page_checks(d, "Refer dialog", errors); shot("ref_2_refer_dialog", page=d)
        d.click("#rf-send")
        d.wait_for_selector("#ref-open", timeout=20000); d.wait_for_timeout(400)
        if "Referral to Colorectal Surgery requested" not in d.inner_text("#ref-open"):
            errors.append(f"no 'Referral to Colorectal Surgery requested' banner: {d.inner_text('#ref-open')[:120]!r}")
        if "Referral to Colorectal Surgery waiting" not in d.inner_text("#c-owner"):
            errors.append("the Case File header shows no 'Referral to Colorectal Surgery waiting' chip")
        if not d.locator("#ref-withdraw").count():
            errors.append("the referring doctor is not offered Withdraw on the open referral")
        if d.locator("#btn-refer").count():
            errors.append("Refer to another department is still offered while a referral waits")
        open_side(d)
        if not d.locator(f".citem[data-case='{cid}'] .chip:has-text('Referral waiting')").count():
            errors.append("the case list shows no 'Referral waiting' chip")
        d.keyboard.press("Escape"); d.wait_for_timeout(300)
        page_checks(d, "Ownership card (requested)", errors); shot("ref_3_requested", page=d, full_page=True)

        c = page_as(UI_CRS)
        open_side(c); c.click("#btn-inbox")
        row = f"#ib-referrals tr[data-case='{cid}']"
        c.wait_for_selector(row, timeout=20000); c.wait_for_timeout(400)
        t = c.inner_text(row)
        if REF_UHID not in t or "Pulmonology to Colorectal Surgery" not in t:
            errors.append(f"the inbox Referrals row lacks the UHID or 'Pulmonology to Colorectal Surgery': {t[:160]!r}")
        if not c.locator(f"{row} [data-racc]").count():
            errors.append("the inbox Referrals row offers no Accept to the Colorectal Surgery doctor"); return
        page_checks(c, "Inbox (referrals)", errors); shot("ref_4_inbox", page=c, full_page=True)
        c.click(f"{row} [data-racc]"); c.wait_for_selector("#ra-prot", timeout=10000)
        c.select_option("#ra-prot", "colorectal_rectum"); c.select_option("#ra-setting", "metastatic"); c.select_option("#ra-level", "optimal")
        if not c.locator("#ra-later").count():
            errors.append("the Accept dialog has no 'Accept, choose the protocol later'")
        page_checks(c, "Accept dialog", errors); shot("ref_5_accept_dialog", page=c)
        with c.expect_response(lambda r: "/accept" in r.url and "/referrals/" in r.url, timeout=60000) as resp:
            c.click("#ra-go")
        if not resp.value.ok:
            errors.append(f"accepting the referral failed: HTTP {resp.value.status} {resp.value.text()[:160]}"); return
        acc = resp.value.json()
        if acc.get("job"):
            j = wait_job(c, base, acc["job"])
            if not j or j.get("state") != "finished":
                errors.append(f"the listing job after the acceptance did not finish: {(j or {}).get('state')} {(j or {}).get('error', '')}")
        else:
            errors.append("accepting under a protocol started no job (the Pre-Authorization should re-run on the same records)")
        c.wait_for_timeout(2500)
        open_case(c, cid)
        own, head = c.inner_text("#own-name"), c.inner_text("#c-owner")
        if "Colorectal Surgery" not in own or "Owner: Colorectal Surgery" not in head or "Participating: Pulmonology" not in head:
            errors.append(f"after the acceptance the header does not show Owner: Colorectal Surgery, Participating: Pulmonology: {head!r}")
        hist = c.locator("#tab-ready details.gatehist[data-protocol='lung_nsclc']")
        if not hist.count():
            errors.append("the Pre-Authorization tab shows no 'Earlier protocol' block for lung_nsclc")
        else:
            if "Earlier protocol (read-only history)" not in hist.first.inner_text():
                errors.append("the earlier gate block is not titled 'Earlier protocol (read-only history)'")
            hist.first.locator("summary").click(); c.wait_for_timeout(300)
            if hist.first.locator("button").count():
                errors.append("the earlier gate block carries buttons (it must be read-only)")
        st = c.request.get(base + f"/api/tb/cases/{cid}").json()
        if ((st.get("state") or {}).get("gate") or {}).get("protocol") != "colorectal_rectum":
            errors.append(f"the gate does not run under colorectal_rectum after the acceptance: {((st.get('state') or {}).get('gate') or {}).get('protocol')!r}")
        if not c.locator("#tab-ready .req").count():
            errors.append("the Pre-Authorization tab shows no requirement rows under the new protocol")
        page_checks(c, "Pre-Authorization after the acceptance", errors); shot("ref_6_accepted", page=c, full_page=True)
        c.click("#tabs button[data-tab='board']"); c.wait_for_timeout(700)
        if "Referred from Pulmonology to Colorectal Surgery" not in c.inner_text("#tab-board"):
            errors.append("the timeline shows no referral event")
        page_checks(c, "Board tab (timeline)", errors)

        open_case(d, cid)
        for sel, what in [("[data-notify]", "Notify"), ("[data-waive]", "Waive"), ("#btn-refer", "Refer to another department"), ("[data-newreq]", "Notify a department")]:
            if d.locator(f"#tab-ready {sel}").count():
                errors.append(f"the participating Pulmonology doctor sees a {what} button")
        if "Participating: Pulmonology" not in d.inner_text("#c-owner"):
            errors.append("the participating Pulmonology doctor's header does not show Participating: Pulmonology")
        page_checks(d, "Participant view", errors); shot("ref_7_participant", page=d, full_page=True)
        if d.locator("#btn-bell").is_visible():
            d.click("#btn-bell"); d.wait_for_selector("#modal-body .ntf", timeout=10000)
            if "Referral answered" not in d.inner_text("#modal-body"):
                errors.append("the bell shows no 'Referral answered' notification to the referring department")
            page_checks(d, "Notifications (referral)", errors); shot("ref_8_bell", page=d)
            d.keyboard.press("Escape"); d.wait_for_timeout(300)
    finally:
        for p in pages:
            p.close()
        referral_cleanup(pg, base, cid)
        if cid and pg.request.get(base + f"/api/tb/cases/{cid}").ok:
            errors.append(f"could not delete the test Case File {cid}")


def run_flow(b, base, pw, out, size, sfx, errors, only=None):
    """The whole UI flow in one fresh page at one viewport size; JS errors go into `errors`, screenshot names end in `sfx`.
    only="admin" / "his" / "requests" / "referral": log in and run only that part."""
    pg = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    watch(pg, errors)
    shot = lambda name, page=None, **kw: (page or pg).screenshot(path=f"{out}/{name}{sfx}.png", **kw)

    def pick(cid):  # narrow screens keep the Case File list in a slide-over panel (body.side-open) behind the menu button
        if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
            pg.click("#btn-side"); pg.wait_for_timeout(350)  # the closed panel is only translated off screen, so is_visible() cannot tell
        pg.click(f".citem[data-case='{cid}']")

    login(pg, base, "admin", pw)
    if only == "his":
        pg.goto(base + "/tb")
        try:
            pg.wait_for_selector("#btn-new:not(.hidden)", state="attached", timeout=20000)
            his_screens(b, pg, base, pw, shot, errors)
        finally:
            pg.close()
        return
    if only in ("requests", "referral"):
        pg.goto(base + "/tb")
        try:
            pg.wait_for_selector("#btn-new:not(.hidden)", state="attached", timeout=20000)
            (requests_screens if only == "requests" else referral_screens)(b, pg, base, pw, shot, errors)
        finally:
            pg.close()
        return
    if only == "admin":
        pg.goto(base + "/tb")
        try:
            pg.wait_for_selector("#btn-org:not(.hidden)", state="attached", timeout=20000)
        except Exception:
            raise RuntimeError(f"the Organisation button did not appear for admin (page {urlparse(pg.url).path}, toast {pg.inner_text('#toast')[:120] if pg.locator('#toast').count() else ''!r})")
        try:
            admin_screens(b, pg, base, pw, shot, errors)
        finally:
            pg.close()
        return
    pg.goto(base + "/tb"); pg.wait_for_selector(".citem", state="attached", timeout=20000)
    shot("00_home")
    for cid in ["TB-001", "TB-002", "TB-003"]:
        pick(cid); pg.click("#tabs button[data-tab='ready']")  # the Pre-Authorization tab, before waiting for its rows
        pg.wait_for_selector("#tab-ready .req", timeout=20000); pg.wait_for_timeout(500)
        shot(f"{cid}_1_preauth", full_page=True)
        for t in ["docs", "summary", "board", "audit"]:
            pg.click(f"#tabs button[data-tab='{t}']"); pg.wait_for_timeout(900)
            shot(f"{cid}_{t}", full_page=True)
    # re-check toast must explain what was checked
    pick("TB-001"); pg.click("#tabs button[data-tab='ready']"); pg.wait_for_selector("#tab-ready .req")
    pg.click("#btn-recheck"); pg.wait_for_timeout(1500)
    t = pg.inner_text("#toast")
    if "Re-checked" not in t or "not re-read" not in t:
        errors.append("re-check toast missing detail: " + t[:120])
    pg.click("#tabs button[data-tab='summary']"); pg.wait_for_timeout(600)
    if pg.locator("#sumout h4").count() and pg.locator("#sumout h4").count() < 6:
        errors.append("summary does not show the 6 NCG sections")
    # document drawer with highlights (select the tab explicitly: re-clicking the same case keeps the current tab by design)
    pick("TB-001"); pg.click("#tabs button[data-tab='ready']"); pg.wait_for_selector("#tab-ready .req")
    pg.click("#tabs button[data-tab='docs']"); pg.wait_for_selector("tr[data-doc]")
    if pg.locator("#tab-docs .scan-tag").count() == 0:  # V1 item 8.1: TB-001's PET-CT and CBC are scans; their values say "from scan (OCR)"
        errors.append("no 'from scan (OCR)' tag on TB-001's values (V1 8.1)")
    pg.locator("tr[data-doc]").nth(3).click(); pg.wait_for_selector("#doctext", timeout=15000); pg.wait_for_timeout(1200)
    shot("TB-001_doc_drawer"); pg.keyboard.press("Escape")
    # V1 item 8.4: a scanned document shows where its fields were read on the image (the independent OCR engine's word boxes)
    pg.locator("tr[data-doc]", has_text="PET").first.click(); pg.wait_for_selector("#doctext", timeout=15000); pg.wait_for_timeout(1500)
    if pg.locator("#ocrboxes .ocrbox").count() == 0:
        errors.append("no word boxes drawn over TB-001's scanned PET-CT (V1 8.4)")
    shot("TB-001_scan_boxes"); pg.keyboard.press("Escape")
    # ask + instant search
    pg.click("#tabs button[data-tab='ask']"); pg.fill("#q", "PD-L1"); pg.wait_for_timeout(900)
    pg.fill("#q", "What is the PD-L1 result and is it from a final report?"); pg.click("#ask")
    pg.wait_for_selector("#answers .answer, #answers .refusal", timeout=120000); pg.wait_for_timeout(500)
    shot("TB-001_ask", full_page=True)
    pg.fill("#q", "What treatment should he receive?"); pg.click("#ask")
    for _ in range(240):
        if pg.locator("#answers .qbox").count() >= 2 and pg.locator("#answers .spin").count() == 0:
            break
        pg.wait_for_timeout(500)
    shot("TB-001_ask_refusal", full_page=True)
    # specialty agent
    pg.click("#tabs button[data-tab='roles']"); pg.wait_for_selector("[data-role='radiology']")
    pg.click("[data-role='radiology']"); pg.wait_for_selector("#brief-radiology .reviewbar", timeout=240000); pg.wait_for_timeout(500)
    shot("TB-001_agent_radiology", full_page=True)
    # guideline references
    pg.click("#tabs button[data-tab='summary']"); pg.click("#gl-case"); pg.wait_for_selector("#glout .hit", timeout=180000)
    shot("TB-001_guidelines", full_page=True)
    pg.click("#btn-cards"); pg.wait_for_timeout(1500); shot("model_cards"); pg.keyboard.press("Escape")
    # department uploads and the Needs matching queue (V1 2.3); the hospital set-up screen (V1 2.1)
    if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
        pg.click("#btn-side"); pg.wait_for_timeout(350)
    if pg.locator("#btn-queue").is_visible():
        pg.click("#btn-queue"); pg.wait_for_selector("#intake .card", timeout=20000); pg.wait_for_timeout(600); shot("intake_queue", full_page=True)
    admin_screens(b, pg, base, pw, shot, errors)  # V2 item 2.3: Organisation (root admin) and My department (department admin)
    # after the board (V1 Phase 7): a decision with a dose slip and no radiation oncologist on TB-002 (adjudicated through the API: one
    # reasoner call); the Board tab renders the composition, the guideline flag with its reference and the resolution buttons; one flag
    # corrected through the dialog (version 2); the department inbox shows the board action. TB-002 is reset by the next e2e run.
    r = pg.request.post(base + "/api/tb/cases/TB-002/board-records", data={
        "board_date": "2026-12-11", "recorded_by": "Dr. UI Test (synthetic)",
        "decision_text": "Neoadjuvant chemotherapy: 4 cycles of AC (Inj. Doxorubicin 6 mg/m2 IV and Inj. Cyclophosphamide 600 mg/m2 IV, every 21 days).",
        "members": [{"name": "Dr. UI Test (synthetic)", "department": "Medical Oncology"}, {"name": "Dr. UI Surgeon (synthetic)", "department": "Surgical Oncology"}],
        "actions": [{"department": "Radio-diagnosis", "task": "MRI breast after chemotherapy", "due": "2026-12-20"}]}, timeout=300000)
    if not r.ok:  # never a silent pass: the Phase 7 Board tab must be rendered with flags
        errors.append(f"board record for the Phase 7 check could not be recorded: HTTP {r.status}")
    else:
        pick("TB-002"); pg.click("#tabs button[data-tab='ready']"); pg.wait_for_selector("#tab-ready .req", timeout=20000)
        pg.click("#tabs button[data-tab='board']"); pg.wait_for_selector("#tab-board [data-resolve]", timeout=20000); pg.wait_for_timeout(500)
        if not pg.locator("#tab-board .gref").count():
            errors.append("Board tab: no guideline reference shown under the flags")
        shot("TB-002_board_flags", full_page=True)
        btn = pg.locator("#tab-board .flag:has-text('Doxorubicin') [data-resolve$='|corrected']").first  # the dose flag, not the composition one
        btn.click(); pg.wait_for_selector("#cd-value", timeout=10000)
        pg.fill("#cd-value", "60 mg/m2"); pg.click("#cd-ok")
        pg.wait_for_selector("#tab-board [data-undores]", timeout=20000); pg.wait_for_timeout(600)
        if "Amended: version 2" not in pg.inner_text("#tab-board") or "Doxorubicin 60 mg/m2" not in pg.inner_text("#tab-board"):
            errors.append("Board tab: the corrected dose did not show as the amended version 2")
        shot("TB-002_board_resolved", full_page=True)
        if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
            pg.click("#btn-side"); pg.wait_for_timeout(350)  # narrow screens: the inbox button sits in the slide-over side panel
        if pg.locator("#btn-inbox").is_visible():
            pg.click("#btn-inbox"); pg.wait_for_selector("#inbox .card", timeout=20000); pg.wait_for_timeout(500); shot("inbox_board_action", full_page=True)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    # board sessions and the Board room (V1 6.1 to 6.3): a planned session on TB-001 with Radio-diagnosis absent (no model call), removed afterwards
    from tumour_board import board
    sid = None
    try:
        r = pg.request.post(base + "/api/tb/sessions", data={"date": "2026-12-11", "title": "UI test", "case_ids": ["TB-001"]})
        sid = r.json().get("id") if r.ok else None
        if not sid:  # never a silent pass: the Board room must be visited
            errors.append(f"board session could not be created for the Board room check: HTTP {r.status}")
        if sid:
            pg.request.post(base + f"/api/tb/sessions/{sid}/attendance", data={"department": "radiology", "status": "absent"})
            pg.request.post(base + f"/api/tb/sessions/{sid}/members", data={"name": "Dr. UI Test (synthetic)", "department": "medical_oncology"})
        pg.click("#btn-sessions"); pg.wait_for_selector("#sessions .card", timeout=20000); pg.wait_for_timeout(500); shot("board_sessions", full_page=True)
        if sid:
            pg.click(f"#sessions tr[data-sid='{sid}']"); pg.wait_for_selector("#room-agenda .agenda", timeout=20000); pg.wait_for_selector("#room-agents")
            pg.wait_for_timeout(800); shot("board_room", full_page=True)
    finally:
        if sid:
            board._path(sid).unlink(missing_ok=True); board.audit_session(sid, {"kind": "ui_test_removed", "by": "ui_test"})
    pg.close()


def main(base, pw, out, viewports=None, only=None):
    """viewports: list of names from VIEWPORTS. None keeps the original single desktop run with unsuffixed screenshot names."""
    os.makedirs(out, exist_ok=True)
    names = viewports or ["desktop"]
    per = {n: [] for n in names}
    with sync_playwright() as p:
        b = p.chromium.launch(env={**os.environ})
        for n in names:
            try:
                run_flow(b, base, pw, out, VIEWPORTS[n], f"_{n}" if viewports else "", per[n], only)
            except Exception as e:  # a step that cannot be done at this width is a failure of this viewport, not of the run
                waiting = [l.strip() for l in str(e).splitlines() if "waiting for" in l][:1]  # names the selector that failed
                per[n].append(f"flow failed: {type(e).__name__}: {str(e).splitlines()[0][:200]} {' '.join(waiting)[:160]}".rstrip())
        b.close()
    print("screenshots:", out)
    if viewports:
        for n in names:
            print(f"JS errors [{n} {VIEWPORTS[n][0]}x{VIEWPORTS[n][1]}]:", per[n] or "none")
    errors = [e for n in names for e in per[n]]
    print("JS errors:", errors or "none")
    return 1 if errors else 0


def parse_viewports(v):
    names = [x.strip() for x in v.split(",") if x.strip()]
    bad = [x for x in names if x not in VIEWPORTS]
    if bad or not names:
        raise argparse.ArgumentTypeError(f"unknown viewport(s) {bad}; choose from {','.join(VIEWPORTS)}")
    return names


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:7000"); ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="/home/bharath.tangella/vaidyx/Vaidyx/data/tumour_board/ui_shots")
    ap.add_argument("--viewports", type=parse_viewports, default=None, help="comma list of desktop,tablet,phone (default: desktop)")
    ap.add_argument("--only", choices=["admin", "his", "requests", "referral"], default=None, help="admin: only the Organisation and My department screens (no model calls); "
                    "his: only the HIS-connected Case File screens against the mock hospital (reader model calls; the Case Files it creates are deleted); "
                    "requests: the requests to departments (V2 items 4.2 / 4.3) as a treating doctor and a radiologist (reader model calls; the Case File is deleted); "
                    "referral: referral and ownership (V2 items 5.1 to 5.3) with two throw-away doctor logins (reader model calls; the Case File and logins are deleted)")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.out, a.viewports, a.only))
