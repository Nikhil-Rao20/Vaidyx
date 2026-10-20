// SVG figures -> vector PDF (and a PNG preview) for the paper: each SVG on a page of its own size, Inter embedded.
// node docs/research/benchmark-paper/experiments/figures_pdf.cjs   (NODE_PATH=web/tb-nik/node_modules)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const DIR = path.resolve(__dirname, "../figures");
const FONTS = path.resolve(__dirname, "../../../../web/tb-nik/public/fonts");
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ deviceScaleFactor: 2 });
  const files = fs.readdirSync(DIR).filter((f) => f.endsWith(".svg"));
  for (const f of files) {
    const svg = fs.readFileSync(path.join(DIR, f), "utf8");
    const w = +svg.match(/viewBox="0 0 (\d+(?:\.\d+)?) /)[1];
    const h = +svg.match(/viewBox="0 0 \d+(?:\.\d+)? (\d+(?:\.\d+)?)"/)[1];
    const htmlDoc = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:"Inter Variable";src:url(file://${FONTS}/inter-latin-wght-normal.woff2) format("woff2");font-weight:100 900}
@font-face{font-family:"Inter Variable";src:url(file://${FONTS}/inter-latin-ext-wght-normal.woff2) format("woff2");font-weight:100 900;unicode-range:U+0100-024F,U+2020,U+2190-21FF}
@page{size:${w}px ${h + 16}px;margin:0} html,body{margin:0;background:#fff} svg{display:block;margin:8px 0}</style></head><body>${svg}</body></html>`;
    await page.setViewportSize({ width: Math.ceil(w), height: Math.ceil(h + 16) });
    const tmp = path.join(DIR, "_render.html");
    fs.writeFileSync(tmp, htmlDoc);
    await page.goto("file://" + tmp, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    const base = path.join(DIR, f.replace(/\.svg$/, ""));
    await page.pdf({ path: base + ".pdf", width: `${w}px`, height: `${h + 16}px`, printBackground: true, pageRanges: "1" });
    await page.screenshot({ path: base + ".png", fullPage: true });
  }
  fs.rmSync(path.join(DIR, "_render.html"), { force: true });
  await b.close();
  console.log(`${files.length} figures -> PDF + PNG in ${DIR}`);
})().catch((e) => { console.error(e); process.exit(1); });
