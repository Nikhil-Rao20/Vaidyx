"""Browser test of the demo HIMS screens (DemoHIMS of the Vaidyx Demo Hospital), headless Chromium via Playwright.
SYNTHETIC data only.

    LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib /data/vaidyx/venv/app/bin/python -m his_mock.eval.ui_test \
        [--base http://127.0.0.1:7130] [--data data/his_mock] [--out DIR] [--viewports desktop,wide,laptop,phone]
        [--allow-writes]

It starts nothing: the HIMS must already run on --base (his_mock/serve.sh start) over the data directory --data, whose
logins.tsv (mode 600) gives the demo passwords; they are typed into the login page and never printed. Per viewport it
opens the login page, signs in as the OPD consultant and walks the modules: Registration (search, name search, UHID
search to the patient page, an admission and an OP visit, a temporary registration with its look-alikes), OPD, IPD,
Laboratory, Radiology, Pathology (each work list and one order page), Exchange and the old /desk link; then the Admin
module as the hospital IT admin, and "Open images" (the PACS viewer through the HIMS) as the radiologist when a study is
in the PACS. With --allow-writes, once (first viewport), it submits one harmless form: a ward "transfer" of an open
admission to the ward and bed it is already in (use a throwaway instance, never the live demo data).

Every HIMS page must answer below 400, carry the SYNTHETIC ribbon, hold no em or en dash, show the signed-in user and
never scroll sideways; any page error or console error fails the run (the OHIF viewer's own console is not checked).
Screenshots <page>-<viewport>.png go to --out (default data/his_mock/ui_shots/). Prints "UI OK: <n> pages, 0 errors" or
the errors, and exits 1 on any error.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

from his_mock import auth, paths

VIEWPORTS = {"desktop": (1366, 768), "wide": (1920, 1080), "laptop": (1024, 768), "phone": (390, 844)}
DEFAULT_OUT = paths.DATA_DIR / "ui_shots"
DASHES = ("\u2014", "\u2013")
NAME = "Anitha Reddy"
UHID = "VXH/26/004201"
TEMP_UHID = "VXH/T/26/00412"
TRANSFER_REASON = "UI test (SYNTHETIC): bed check, no move"


def get_json(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def logins(data_dir):
    """{first role: (email, password)} from logins.tsv (never printed)."""
    out = {}
    p = Path(data_dir) / auth.LOGINS_NAME
    for line in p.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            out[parts[1].split(",")[0]] = (parts[0], parts[2])
    return out


def _ignored_console(msg):
    """The browser's own favicon request is not a page error (the HIMS serves none)."""
    url = (msg.location or {}).get("url", "")
    return urlparse(url).path.endswith("/favicon.ico")


def run_viewport(browser, base, out, vp, size, accounts, errors, notes, do_form):
    """Fresh browser contexts at one viewport; returns the number of pages checked."""
    count = 0

    def new_page(role):
        ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"[{vp}] pageerror on {pg.url}: {e}"))
        pg.on("console", lambda m: m.type == "error" and not _ignored_console(m) and "/api/tb/pacs/" not in pg.url
              and errors.append(f"[{vp}] console error on {pg.url}: {m.text}"))
        if role:
            email, password = accounts[role]
            pg.goto(base + "/his/login")
            pg.fill("#f-email", email)
            pg.fill("#f-password", password)
            pg.click("form[action='/his/login'] button[type=submit]")
            pg.wait_for_load_state("load")
            if "/his/login" in pg.url:
                errors.append(f"[{vp}] sign-in as {role} failed ({pg.url})")
        return ctx, pg

    def check(pg, name, expect=(), signed_in=True):
        nonlocal count
        pg.wait_for_load_state("load")
        banner = pg.locator(".synthetic")
        if not banner.count() or "SYNTHETIC" not in banner.first.inner_text():
            errors.append(f"[{vp}] {name}: no SYNTHETIC ribbon ({pg.url})")
        text = pg.inner_text("body")
        if any(d in text or d in pg.title() for d in DASHES):
            errors.append(f"[{vp}] {name}: em or en dash in the page text ({pg.url})")
        if signed_in and "Signed in:" not in text:
            errors.append(f"[{vp}] {name}: the signed-in user is not shown ({pg.url})")
        sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if sw > cw + 1:
            errors.append(f"[{vp}] {name}: the page scrolls sideways ({sw} px wide in a {cw} px viewport, {pg.url})")
        for s in expect:
            if s not in text:
                errors.append(f"[{vp}] {name}: {s!r} not on the page ({pg.url})")
        pg.screenshot(path=os.path.join(out, f"{name}-{vp}.png"), full_page=True)
        count += 1

    def visit(pg, name, path, expect=()):
        resp = pg.goto(base + path)
        if resp is None or resp.status >= 400:
            errors.append(f"[{vp}] {name}: HTTP {resp.status if resp else 'no response'} for {path}")
            return False
        check(pg, name, expect)
        return True

    def first_order(pg, path):
        link = pg.locator("#worklist td a.mono")
        return link.first.get_attribute("href") if link.count() else None

    # the login page, then the OPD consultant
    ctx, pg = new_page(None)
    pg.goto(base + "/his/login")
    check(pg, "his_login", ["Sign in", "Email", "Password"], signed_in=False)
    ctx.close()
    ctx, pg = new_page("opd.doctor")
    visit(pg, "his_search", "/his", ["Registration search", "Recent registrations"])
    pg.fill("#q", NAME)
    pg.click("form[action='/his'] button[type=submit]")
    check(pg, "his_name_search", [UHID, "Anitha Reddy (SYNTHETIC)"])
    pg.fill("#q", UHID)
    pg.click("form[action='/his'] button[type=submit]")
    pg.wait_for_load_state("load")
    if not urlparse(pg.url).path.startswith("/his/patients/"):
        errors.append(f"[{vp}] UHID search did not open the patient page ({pg.url})")
    check(pg, "his_patient", [UHID, "Timeline", "New OP visit", "Admit"])
    patient_url = urlparse(pg.url).path
    for kind, name, words in (("IP", "his_admission", ["Ward history", "Referrals", "Orders and reports"]),
                              ("OP", "his_op_visit", ["Orders and reports", "Order entry", "OPD consultation note"])):
        link = pg.locator(f".panel[data-kind={kind}] h3 a")
        if link.count():
            link.first.click()
            check(pg, name, words)
            pg.goto(base + patient_url)
        else:
            notes.append(f"[{vp}] {UHID} has no {kind} encounter; {name} skipped")
    found = get_json(base, "/his/api/search?q=" + quote(TEMP_UHID))
    if found["patients"]:
        visit(pg, "his_similar", f"/his/patients/{found['patients'][0]['id']}", ["Similar registrations"])
    open_ip = get_json(base, "/his/api/encounters?kind=IP&status=in-progress")["encounters"]
    if open_ip:
        e = open_ip[0]
        if visit(pg, "his_open_admission", f"/his/encounters/{e['id']}", ["Transfer ward", "Discharge"]) and do_form:
            pg.fill("#t-ward", e["ward"])
            pg.fill("#t-bed", e["bed"])
            pg.fill("#t-reason", TRANSFER_REASON)
            pg.click("#transfer button[type=submit]")
            check(pg, "his_transfer", ["transferred to"])
            if not pg.locator(".flash.ok").count():
                errors.append(f"[{vp}] the ward transfer form did not show a success message ({pg.url})")
    else:
        notes.append(f"[{vp}] no open admission; the transfer form was skipped")
    visit(pg, "his_opd", "/his/opd", ["OPD list of", "Recent OP visits"])
    visit(pg, "his_ipd", "/his/ipd", ["Ward census"])
    for name, path, words in (("his_lab", "/his/lab?tab=verified", ["Ordered", "Sample collected", "Results entered", "Verified"]),
                              ("his_radiology", "/his/radiology?tab=signed", ["Ordered", "Scheduled", "Signed"]),
                              ("his_pathology", "/his/pathology?tab=signed", ["Ordered", "Specimen received", "Signed"])):
        if visit(pg, name, path, words):
            href = first_order(pg, path)
            if href:
                visit(pg, name + "_order", href, ["Accession / Lab No."])
            else:
                notes.append(f"[{vp}] {path} has no order; {name}_order skipped")
    visit(pg, "his_exchange", "/his/exchange", ["HL7 v2 messages", "FHIR R4 API", "Events log"])
    visit(pg, "desk", "/desk", ["Reporting desk"])
    ctx.close()
    # the Admin module
    ctx, pg = new_page("admin")
    visit(pg, "his_admin", "/his/admin", ["Departments", "Practitioners", "Accounts", "Audit"])
    ctx.close()
    # the PACS viewer through the HIMS, when a study is in the PACS
    ctx, pg = new_page("radiologist")
    pg.goto(base + "/his/radiology?tab=signed")
    link = pg.locator("a:has-text('Open images')")
    if link.count():
        href = link.first.get_attribute("href")
        resp = pg.goto(base + href)
        if resp is None or resp.status >= 400:
            errors.append(f"[{vp}] the PACS viewer did not open: HTTP {resp.status if resp else 'no response'} for {href}")
        else:
            pg.wait_for_timeout(4000)
            pg.screenshot(path=os.path.join(out, f"pacs_viewer-{vp}.png"))
            count += 1
    else:
        notes.append(f"[{vp}] no signed study with images; the viewer was skipped")
    ctx.close()
    return count


def main(base, data_dir, out, viewports, allow_writes=False):
    from playwright.sync_api import sync_playwright

    base = base.rstrip("/")
    os.makedirs(out, exist_ok=True)
    try:
        health = get_json(base, "/health")
    except Exception as e:  # nothing is started here: run his_mock/serve.sh start first
        print(f"UI FAILED: the HIMS does not answer on {base} ({type(e).__name__}: {e})")
        return 1
    if not health.get("ok"):
        print(f"UI FAILED: {base}/health is not ok: {health}")
        return 1
    try:
        accounts = logins(data_dir)
    except OSError as e:
        print(f"UI FAILED: no login file in {data_dir} ({type(e).__name__})")
        return 1
    missing = [r for r in ("opd.doctor", "admin", "radiologist") if r not in accounts]
    if missing:
        print(f"UI FAILED: no login for {', '.join(missing)} in {data_dir}/{auth.LOGINS_NAME}")
        return 1
    errors, notes, pages = [], [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(env={**os.environ})
        for i, vp in enumerate(viewports):
            try:
                pages += run_viewport(browser, base, out, vp, VIEWPORTS[vp], accounts, errors, notes,
                                      do_form=(allow_writes and i == 0))
            except Exception as e:  # a step that cannot be done at this width fails this viewport, not the whole run
                waiting = [line.strip() for line in str(e).splitlines() if "waiting for" in line][:1]
                errors.append(f"[{vp}] flow failed: {type(e).__name__}: {str(e).splitlines()[0][:200]} "
                              f"{' '.join(waiting)[:160]}".rstrip())
        browser.close()
    for n in notes:
        print("note:", n)
    print("screenshots:", out)
    if errors:
        for e in errors:
            print("error:", e)
        print(f"UI FAILED: {pages} pages, {len(errors)} errors")
        return 1
    print(f"UI OK: {pages} pages, 0 errors")
    return 0


def parse_viewports(v):
    names = [x.strip() for x in v.split(",") if x.strip()]
    bad = [x for x in names if x not in VIEWPORTS]
    if bad or not names:
        raise argparse.ArgumentTypeError(f"unknown viewport(s) {bad}; choose from {','.join(VIEWPORTS)}")
    return names


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Browser test of the demo HIMS screens")
    ap.add_argument("--base", default="http://127.0.0.1:7130")
    ap.add_argument("--data", default=str(paths.DATA_DIR), help="the data directory behind --base (its logins.tsv)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--viewports", type=parse_viewports, default=list(VIEWPORTS),
                    help="comma list of desktop,wide,laptop,phone (default: all four)")
    ap.add_argument("--allow-writes", action="store_true",
                    help="also submit the no-move ward transfer form (adds an ADT A02 event to the store behind --base; "
                         "use it against a throwaway instance, never the live demo data)")
    a = ap.parse_args()
    sys.exit(main(a.base, a.data, a.out, a.viewports, a.allow_writes))
