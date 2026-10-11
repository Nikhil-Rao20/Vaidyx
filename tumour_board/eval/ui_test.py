"""Browser test of the Vaidyx-TB UI (headless Chromium via Playwright). Fails on any JS error raised while a Tumour Board
page (path /tb) is open; the main app's login and index pages are outside this module and are not counted. Saves screenshots.
Usage: LD_LIBRARY_PATH=... python -m tumour_board.eval.ui_test --password <pw> [--out dir] [--viewports desktop,tablet,phone]
Viewports: desktop 1600x1000, tablet 1024x768, phone 390x844 (screenshots suffixed with the viewport name)."""
import argparse, os, sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


VIEWPORTS = {"desktop": (1600, 1000), "tablet": (1024, 768), "phone": (390, 844)}


def run_flow(b, base, pw, out, size, sfx, errors):
    """The whole UI flow in one fresh page at one viewport size; JS errors go into `errors`, screenshot names end in `sfx`."""
    pg = b.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
    tb_page = lambda: urlparse(pg.url).path.rstrip("/") == "/tb"  # only errors raised while a Tumour Board page is open count
    pg.on("pageerror", lambda e: tb_page() and errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and tb_page() and errors.append(f"console: {m.text} ({(m.location or {}).get('url', '')})"))
    shot = lambda name, **kw: pg.screenshot(path=f"{out}/{name}{sfx}.png", **kw)

    def pick(cid):  # narrow screens keep the Case File list in a slide-over panel (body.side-open) behind the menu button
        if pg.locator("#btn-side").is_visible() and not pg.evaluate("document.body.classList.contains('side-open')"):
            pg.click("#btn-side"); pg.wait_for_timeout(350)  # the closed panel is only translated off screen, so is_visible() cannot tell
        pg.click(f".citem[data-case='{cid}']")

    pg.goto(base + "/login")
    pg.fill("input[type=text], input[name=username], #username", "admin")
    pg.fill("input[type=password]", pw)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2500)
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
    pg.locator("tr[data-doc]").nth(3).click(); pg.wait_for_selector("#doctext", timeout=15000); pg.wait_for_timeout(1200)
    shot("TB-001_doc_drawer"); pg.keyboard.press("Escape")
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
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)  # narrow screens: the side panel must be closed before the top bar is clickable
    if pg.locator("#btn-org").is_visible():
        pg.click("#btn-org"); pg.wait_for_selector("#o-depts tr", timeout=20000); pg.wait_for_timeout(500); shot("org_admin"); pg.keyboard.press("Escape")
    # board sessions and the Board room (V1 6.1 to 6.3): a planned session on TB-001 with Radio-diagnosis absent (no model call), removed afterwards
    from tumour_board import board
    sid = None
    try:
        r = pg.request.post(base + "/api/tb/sessions", data={"date": "2026-12-11", "title": "UI test", "case_ids": ["TB-001"]})
        sid = r.json().get("id") if r.ok else None
        if sid:
            pg.request.post(base + f"/api/tb/sessions/{sid}/attendance", data={"department": "radio_diagnosis", "status": "absent"})
            pg.request.post(base + f"/api/tb/sessions/{sid}/members", data={"name": "Dr. UI Test (synthetic)", "department": "medical_oncology"})
        pg.click("#btn-sessions"); pg.wait_for_selector("#sessions .card", timeout=20000); pg.wait_for_timeout(500); shot("board_sessions", full_page=True)
        if sid:
            pg.click(f"#sessions tr[data-sid='{sid}']"); pg.wait_for_selector("#room-agenda .agenda", timeout=20000); pg.wait_for_selector("#room-agents")
            pg.wait_for_timeout(800); shot("board_room", full_page=True)
    finally:
        if sid:
            board._path(sid).unlink(missing_ok=True); board.audit_session(sid, {"kind": "ui_test_removed", "by": "ui_test"})
    pg.close()


def main(base, pw, out, viewports=None):
    """viewports: list of names from VIEWPORTS. None keeps the original single desktop run with unsuffixed screenshot names."""
    os.makedirs(out, exist_ok=True)
    names = viewports or ["desktop"]
    per = {n: [] for n in names}
    with sync_playwright() as p:
        b = p.chromium.launch(env={**os.environ})
        for n in names:
            try:
                run_flow(b, base, pw, out, VIEWPORTS[n], f"_{n}" if viewports else "", per[n])
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
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.out, a.viewports))
