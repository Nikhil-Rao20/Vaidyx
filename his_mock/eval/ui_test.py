"""Browser test of the mock hospital's human screens (plan item V2-1.6): the HIS screens at /his and the reporting desk at
/desk (1.5), headless Chromium via Playwright. SYNTHETIC data only.

    LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib /data/vaidyx/venv/app/bin/python -m his_mock.eval.ui_test \
        [--base http://127.0.0.1:7130] [--out DIR] [--viewports desktop,tablet,phone]

It starts nothing: the mock app must already run on --base (his_mock/serve.sh start). Per viewport it opens the registration
search, a name search ("Anitha Reddy"), a UHID search (VXH/26/004201, which lands on the patient page), that patient's IP
admission and OP visit pages, a temporary registration with its similar registrations, an open admission, the reporting desk
and its Radiology page (skipped with a note while /desk does not exist). Once (first viewport) it submits one harmless form: a
ward "transfer" of an open admission to the ward and bed it is already in (skipped when no admission is open). Every page must
answer below 400, carry the SYNTHETIC banner, hold no em dash and never scroll sideways; any pageerror or console error fails
the run. Screenshots <page>-<viewport>.png go to --out (default data/his_mock/ui_shots/). Prints "UI OK: <n> pages, 0 errors"
or the errors, and exits 1 on any error.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from his_mock import paths

VIEWPORTS = {"desktop": (1600, 1000), "tablet": (1024, 768), "phone": (390, 844)}
DEFAULT_OUT = paths.DATA_DIR / "ui_shots"
EM_DASH = "—"
NAME = "Anitha Reddy"
UHID = "VXH/26/004201"
TEMP_UHID = "VXH/T/26/00412"
TRANSFER_REASON = "UI test (SYNTHETIC): bed check, no move"


def http_status(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def get_json(base, path):
    with urllib.request.urlopen(base + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _ignored_console(msg):
    """The browser's own favicon request is not a page error (the mock serves none)."""
    url = (msg.location or {}).get("url", "")
    return urlparse(url).path.endswith("/favicon.ico")


def run_viewport(browser, base, out, vp, size, errors, notes, do_form):
    """One fresh page at one viewport; returns the number of pages checked."""
    pg = browser.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    pg.on("pageerror", lambda e: errors.append(f"[{vp}] pageerror on {pg.url}: {e}"))
    pg.on("console", lambda m: m.type == "error" and not _ignored_console(m)
          and errors.append(f"[{vp}] console error on {pg.url}: {m.text}"))
    count = 0

    def check(name, expect=()):
        nonlocal count
        pg.wait_for_load_state("load")
        banner = pg.locator(".synthetic")
        if not banner.count() or "SYNTHETIC" not in banner.first.inner_text():
            errors.append(f"[{vp}] {name}: no SYNTHETIC banner ({pg.url})")
        text = pg.inner_text("body")
        if EM_DASH in text or EM_DASH in pg.title():
            errors.append(f"[{vp}] {name}: em dash in the page text ({pg.url})")
        sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if sw > cw + 1:
            errors.append(f"[{vp}] {name}: the page scrolls sideways ({sw} px wide in a {cw} px viewport, {pg.url})")
        for s in expect:
            if s not in text:
                errors.append(f"[{vp}] {name}: {s!r} not on the page ({pg.url})")
        pg.screenshot(path=os.path.join(out, f"{name}-{vp}.png"), full_page=True)
        count += 1

    def visit(name, path, expect=()):
        resp = pg.goto(base + path)
        if resp is None or resp.status >= 400:
            errors.append(f"[{vp}] {name}: HTTP {resp.status if resp else 'no response'} for {path}")
            return False
        check(name, expect)
        return True

    # registration search, name search, UHID search (redirects to the patient page)
    visit("his_search", "/his", ["Registration search", "Recent registrations", "New registration"])
    pg.fill("#q", NAME)
    pg.click("form[action='/his'] button[type=submit]")
    check("his_name_search", [UHID, "Anitha Reddy (SYNTHETIC)"])
    pg.fill("#q", UHID)
    pg.click("form[action='/his'] button[type=submit]")
    pg.wait_for_load_state("load")
    if not urlparse(pg.url).path.startswith("/his/patients/"):
        errors.append(f"[{vp}] UHID search did not open the patient page ({pg.url})")
    check("his_patient", [UHID, "Timeline", "New OP visit", "Admit"])
    # the patient's newest admission and OP visit
    patient_url = urlparse(pg.url).path
    for kind, name, words in (("IP", "his_admission", ["Ward history", "Referrals", "Orders and reports"]),
                              ("OP", "his_op_visit", ["Referrals", "Orders and reports", "Refer to department"])):
        link = pg.locator(f".panel[data-kind={kind}] h3 a")
        if link.count():
            link.first.click()
            check(name, words)
            pg.goto(base + patient_url)
        else:
            notes.append(f"[{vp}] {UHID} has no {kind} encounter; {name} skipped")
    # a temporary registration and its permanent look-alike
    found = get_json(base, "/his/api/search?q=" + quote(TEMP_UHID))
    if found["patients"]:
        visit("his_similar", f"/his/patients/{found['patients'][0]['id']}", ["Similar registrations"])
    else:
        notes.append(f"[{vp}] {TEMP_UHID} not found; his_similar skipped")
    # an open admission: its page, and once the harmless transfer form
    open_ip = get_json(base, "/his/api/encounters?kind=IP&status=in-progress")["encounters"]
    if open_ip:
        e = open_ip[0]
        if visit("his_open_admission", f"/his/encounters/{e['id']}", ["Transfer ward", "Discharge"]) and do_form:
            pg.fill("#t-ward", e["ward"])
            pg.fill("#t-bed", e["bed"])
            pg.fill("#t-reason", TRANSFER_REASON)
            pg.click("#transfer button[type=submit]")
            check("his_transfer", ["transferred to"])
            if not pg.locator(".flash.ok").count():
                errors.append(f"[{vp}] the ward transfer form did not show a success message ({pg.url})")
    else:
        notes.append(f"[{vp}] no open admission; the transfer form was skipped")
    # the reporting desk (1.5), when it exists
    for name, path in (("desk", "/desk"), ("desk_rad", "/desk/RAD")):
        status = http_status(base, path)
        if status == 404:
            notes.append(f"[{vp}] {path} not found (reporting desk not mounted yet); {name} skipped")
            continue
        visit(name, path)
    pg.close()
    return count


def main(base, out, viewports, allow_writes=False):
    from playwright.sync_api import sync_playwright

    base = base.rstrip("/")
    os.makedirs(out, exist_ok=True)
    try:
        health = get_json(base, "/health")
    except Exception as e:  # nothing is started here: the orchestrator runs his_mock/serve.sh start first
        print(f"UI FAILED: the mock app does not answer on {base} ({type(e).__name__}: {e})")
        return 1
    if not health.get("ok"):
        print(f"UI FAILED: {base}/health is not ok: {health}")
        return 1
    errors, notes, pages = [], [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(env={**os.environ})
        for i, vp in enumerate(viewports):
            try:
                pages += run_viewport(browser, base, out, vp, VIEWPORTS[vp], errors, notes,
                                      do_form=(allow_writes and i == 0))
            except Exception as e:  # a step that cannot be done at this width fails this viewport, not the whole run
                waiting = [l.strip() for l in str(e).splitlines() if "waiting for" in l][:1]
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
    ap = argparse.ArgumentParser(description="Browser test of the mock hospital's HIS screens and reporting desk")
    ap.add_argument("--base", default="http://127.0.0.1:7130")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--viewports", type=parse_viewports, default=list(VIEWPORTS),
                    help="comma list of desktop,tablet,phone (default: all three)")
    ap.add_argument("--allow-writes", action="store_true",
                    help="also submit the no-move ward transfer form (adds an ADT A02 event to the store behind --base; "
                         "use it against a throwaway instance, never the live demo data)")
    a = ap.parse_args()
    sys.exit(main(a.base, a.out, a.viewports, a.allow_writes))
