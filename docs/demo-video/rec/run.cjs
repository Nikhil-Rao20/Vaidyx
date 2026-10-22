// Runs recording chapters by name: node run.cjs reception opd lab radiology pathology ...
// Each chapter records into raw/<run>/<session>/ and leaves marks in raw/<run>/marks.jsonl; the state (UHID, accessions, case id)
// carries over in raw/<run>/state.json so a later chapter can run on its own.
const L = require("./lib.cjs");
const HIS = require("./his_chapters.cjs");

const CHAPTERS = { ...HIS };
let V = {};
try { V = require("./v_chapters.cjs"); Object.assign(CHAPTERS, V); } catch (e) { if (!/Cannot find module/.test(String(e))) throw e; }

(async () => {
  const names = process.argv.slice(2);
  const his = names.some((n) => ["reception", "opd", "lab", "radiology", "pathology"].includes(n)) ? await L.session("his", { base: L.H }) : null;
  try {
    for (const n of names) {
      if (!CHAPTERS[n]) throw new Error(`no chapter ${n}`);
      const t = Date.now();
      L.mark(`start:${n}`);
      if (["reception", "opd", "lab", "radiology", "pathology"].includes(n)) await CHAPTERS[n](his);
      else await CHAPTERS[n]();
      L.mark(`end:${n}`);
      console.log(`chapter ${n} done in ${Math.round((Date.now() - t) / 1000)} s`);
    }
  } catch (e) {
    L.mark("error", { message: String(e).slice(0, 300) });
    console.error(e);
    if (his) await his.page.screenshot({ path: `${L.RAW}/error-his.png` }).catch(() => {});
    for (const [k, v] of Object.entries((V && V.SESS) || {})) await v.page.screenshot({ path: `${L.RAW}/error-${k}.png` }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await L.closeAll();
  }
})();
