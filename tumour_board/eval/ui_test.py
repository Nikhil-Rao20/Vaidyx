"""Browser test of the Vaidyx-TB UI (headless Chromium via Playwright). Fails on any JS error raised while a Tumour Board
page (path /tb) is open; the main app's login and index pages are outside this module and are not counted. Saves screenshots.
Usage: LD_LIBRARY_PATH=... python -m tumour_board.eval.ui_test --password <pw> [--out dir] [--viewports desktop,tablet,phone] [--only admin]
Viewports: desktop 1600x1000, tablet 1024x768, phone 390x844 (screenshots suffixed with the viewport name).
--only admin: log in and run only the Organisation and My department screens (V2 item 2.3), no model calls."""
import argparse, os, secrets, sys
from urllib.parse import urlparse

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


def run_flow(b, base, pw, out, size, sfx, errors, only=None):
    """The whole UI flow in one fresh page at one viewport size; JS errors go into `errors`, screenshot names end in `sfx`.
    only="admin": log in and run only admin_screens."""
    pg = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    watch(pg, errors)
    shot = lambda name, page=None, **kw: (page or pg).screenshot(path=f"{out}/{name}{sfx}.png", **kw)

    def pick(cid):  # narrow screens keep the Case File list in a slide-over panel (body.side-open) behind the menu button
        if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
            pg.click("#btn-side"); pg.wait_for_timeout(350)  # the closed panel is only translated off screen, so is_visible() cannot tell
        pg.click(f".citem[data-case='{cid}']")

    login(pg, base, "admin", pw)
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
    ap.add_argument("--only", choices=["admin"], default=None, help="admin: only the Organisation and My department screens (no model calls)")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.out, a.viewports, a.only))
