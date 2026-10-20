// Renders the overlay pages of edit.py (edit/ov/*.html, listed in manifest.json) to PNGs with Playwright, transparent where asked.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const OV = "/data/vaidyx/demo_video/edit/ov";
(async () => {
  const items = JSON.parse(fs.readFileSync(path.join(OV, "manifest.json"), "utf8"));
  const only = process.argv.slice(2);
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  let n = 0;
  for (const it of items) {
    if (only.length && !only.some((o) => it.name.startsWith(o))) continue;
    await page.setViewportSize({ width: it.w, height: it.h });
    await page.goto("file://" + path.join(OV, it.name + ".html"));
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(60);
    await page.screenshot({ path: path.join(OV, it.name + ".png"), omitBackground: !!it.transparent });
    n++;
  }
  await b.close();
  console.log(`${n} overlays`);
})().catch((e) => { console.error(e); process.exit(1); });
