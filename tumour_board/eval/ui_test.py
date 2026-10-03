"""Browser test of the Vaidyx-TB UI (headless Chromium via Playwright). Fails on any JS error; saves screenshots.
Usage: LD_LIBRARY_PATH=... python -m tumour_board.eval.ui_test --password <pw> [--out dir]"""
import argparse, os, sys

from playwright.sync_api import sync_playwright


def main(base, pw, out):
    os.makedirs(out, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(env={**os.environ})
        pg = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))
        pg.goto(base + "/login")
        pg.fill("input[type=text], input[name=username], #username", "admin")
        pg.fill("input[type=password]", pw)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(2500)
        pg.goto(base + "/tb"); pg.wait_for_selector(".citem", timeout=20000)
        pg.screenshot(path=f"{out}/00_home.png")
        shots = []
        for cid in ["TB-001", "TB-002", "TB-003"]:
            pg.click(f".citem[data-case='{cid}']"); pg.wait_for_selector("#tab-ready .req", timeout=20000); pg.wait_for_timeout(500)
            pg.screenshot(path=f"{out}/{cid}_1_preauth.png", full_page=True); shots.append(f"{cid} preauth")
            for t in ["docs", "summary", "board", "audit"]:
                pg.click(f"#tabs button[data-tab='{t}']"); pg.wait_for_timeout(900)
                pg.screenshot(path=f"{out}/{cid}_{t}.png", full_page=True)
        # document drawer with highlights
        pg.click(".citem[data-case='TB-001']"); pg.wait_for_selector("#tab-ready .req")
        pg.click("#tabs button[data-tab='docs']"); pg.wait_for_selector("tr[data-doc]")
        pg.locator("tr[data-doc]").nth(3).click(); pg.wait_for_selector("#doctext", timeout=15000); pg.wait_for_timeout(1200)
        pg.screenshot(path=f"{out}/TB-001_doc_drawer.png"); pg.keyboard.press("Escape")
        # ask + instant search
        pg.click("#tabs button[data-tab='ask']"); pg.fill("#q", "PD-L1"); pg.wait_for_timeout(900)
        pg.fill("#q", "What is the PD-L1 result and is it from a final report?"); pg.click("#ask")
        pg.wait_for_selector("#answers .answer, #answers .refusal", timeout=120000); pg.wait_for_timeout(500)
        pg.screenshot(path=f"{out}/TB-001_ask.png", full_page=True)
        pg.fill("#q", "What treatment should he receive?"); pg.click("#ask")
        for _ in range(240):
            if pg.locator("#answers .qbox").count() >= 2 and pg.locator("#answers .spin").count() == 0:
                break
            pg.wait_for_timeout(500)
        pg.screenshot(path=f"{out}/TB-001_ask_refusal.png", full_page=True)
        # specialty agent
        pg.click("#tabs button[data-tab='roles']"); pg.wait_for_selector("[data-role='radiology']")
        pg.click("[data-role='radiology']"); pg.wait_for_selector("#brief-radiology .reviewbar", timeout=240000); pg.wait_for_timeout(500)
        pg.screenshot(path=f"{out}/TB-001_agent_radiology.png", full_page=True)
        # guideline references
        pg.click("#tabs button[data-tab='summary']"); pg.click("#gl-case"); pg.wait_for_selector("#glout .hit", timeout=180000)
        pg.screenshot(path=f"{out}/TB-001_guidelines.png", full_page=True)
        pg.click("#btn-cards"); pg.wait_for_timeout(1500); pg.screenshot(path=f"{out}/model_cards.png"); pg.keyboard.press("Escape")
        b.close()
    print("screenshots:", out)
    print("JS errors:", errors or "none")
    return 1 if errors else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:7000"); ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="/home/bharath.tangella/vaidyx/Vaidyx/data/tumour_board/ui_shots")
    a = ap.parse_args(); sys.exit(main(a.base, a.password, a.out))
