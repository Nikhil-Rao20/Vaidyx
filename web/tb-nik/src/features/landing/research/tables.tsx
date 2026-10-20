// The result tables of the Research page, built from the generated data (research/data.ts) so the page and the paper
// never disagree. Table numbers follow the paper.
import { RESEARCH } from "../content";
import { RESEARCH_DATA as D } from "./data";
import { Kind, Origin, Tbl, f1, int, signed, type Row } from "./ui";

const byKey = Object.fromEntries(D.models.map((m) => [m.key, m])) as Record<string, (typeof D.models)[number]>;
const name = (k: string) => byKey[k].name;
const tags = (k: string) => [<Origin key="o" v={byKey[k].country} />, <Kind key="t" v={byKey[k].type} />];
const TEXT = ["MedQA", "MedMCQA", "PubMedQA", "MMLU-Med", "MedXpertQA"];
const clean = (s: string) => s.replace(/\$\^\{(\w)\}\$/g, " ($1)");

export function ModelsTable() {
  return (
    <Tbl n={1} caption={RESEARCH.models.caption} testId="research-table-models"
      head={["Model", "Params", "Developer", "Origin", "Type", "Reads images", "Earlier report"]}
      rows={D.models.map((m) => [m.name, m.params, m.developer, <Origin key="o" v={m.country} />, <Kind key="t" v={m.type} />, m.images ? "Yes" : "No", m.previous ? "Yes" : "New"])} />
  );
}

export function TextCotTable() {
  return (
    <Tbl n={3} caption={RESEARCH.text.cot.caption} testId="research-text-cot"
      head={["#", "Model", "Origin", "Type", ...TEXT, "Overall", "Min parsed %"]} numeric={[0, 4, 5, 6, 7, 8, 9, 10]} boldMax={[4, 5, 6, 7, 8]}
      rows={D.textCot.map((r, i) => [String(i + 1), name(r.key), ...tags(r.key), ...r.acc, r.overall, r.minParsed])} />
  );
}

export function TextDirectTable() {
  return (
    <Tbl n={4} caption={RESEARCH.text.direct.caption} testId="research-text-direct" size="sm"
      head={["Model", "Origin", "Type", ...TEXT, "Overall", "First-token\noverall", "Parsed %", "CoT gain"]} numeric={[3, 4, 5, 6, 7, 8, 9, 10, 11]}
      rows={D.textDirect.map((r) => [r.rescored ? `${name(r.key)} †` : name(r.key), ...tags(r.key), ...r.acc, r.overall, f1(r.overallFt), f1(r.minParsed), signed(r.cotGain)])} />
  );
}

export function TextPublishedTable() {
  const rows: Row[] = [];
  const L = RESEARCH.text.published.rows;
  for (const r of D.publishedText) {
    const pub = r.published as readonly (number | null)[];
    const diffs = r.ours.map((o, i) => (pub[i] == null ? null : o - (pub[i] as number)));
    const have = diffs.filter((d): d is number => d != null);
    rows.push({ cells: [name(r.key), L[0], ...r.ours.map(f1), ""], sep: true });
    rows.push({ cells: ["", `${L[1]} (${clean(r.src)})`, ...pub.map(f1), ""], dim: true });
    rows.push({ cells: ["", L[2], ...diffs.map(signed), signed(have.reduce((a, b) => a + b, 0) / have.length)], strong: true });
  }
  return <Tbl n={5} caption={RESEARCH.text.published.caption} note={RESEARCH.text.published.note} testId="research-text-published" head={["Model", "Row", ...TEXT, "Mean diff."]} numeric={[2, 3, 4, 5, 6, 7]} rows={rows} />;
}

export function Q4Table() {
  const rows: Row[] = [];
  const L = RESEARCH.text.q4.rows;
  for (const r of D.q4) {
    const qm = r.q4.reduce((a, b) => a + b, 0) / 5;
    const mean = (xs: readonly number[]) => signed(xs.reduce((a, b) => a + b, 0) / 5 - qm);
    rows.push({ cells: [name(r.key), L[0], ...r.q4.map(f1), ""], sep: true, dim: true });
    rows.push({ cells: ["", L[1], ...r.direct.map(f1), mean(r.direct)] });
    rows.push({ cells: ["", L[2], ...r.cot.map(f1), mean(r.cot)], strong: true });
  }
  return <Tbl n={6} caption={RESEARCH.text.q4.caption} testId="research-q4" head={["Model", "Run", ...TEXT, "Mean gain"]} numeric={[2, 3, 4, 5, 6, 7]} rows={rows} />;
}

export function ImageAllTable() {
  return (
    <Tbl n={7} caption={RESEARCH.image.all.caption} testId="research-image-all" size="sm"
      head={["Model", "Origin", "Type", "VQA-RAD", "SLAKE", "PathVQA", "PMC-VQA", "MedXpertQA\nMM", "PMC-VQA\nCoT", "MedXpertQA\nMM, CoT", "OmniMedVQA\nstrict", "OmniMedVQA\nfirst-token"]}
      numeric={[3, 4, 5, 6, 7, 8, 9, 10, 11]}
      rows={D.image.map((r) => {
        const o = r.overall as Record<string, number>; const c = r.cot as Record<string, number>;
        return [name(r.key), ...tags(r.key), o.vqa_rad, o.slake, o.pathvqa, o.pmc_vqa, o.medxpertqa_mm, c.pmc_vqa, c.medxpertqa_mm, o.omnimedvqa, r.omniFt];
      })} />
  );
}

export function ImageSplitTable() {
  return (
    <Tbl n={8} caption={RESEARCH.image.split.caption} testId="research-image-split"
      head={["Model", "Origin", "Type", "VQA-RAD\nyes/no", "VQA-RAD\nopen", "SLAKE\nyes/no", "SLAKE\nopen", "PathVQA\nyes/no", "PathVQA\nopen"]} numeric={[3, 4, 5, 6, 7, 8]}
      rows={D.image.map((r) => [name(r.key), ...tags(r.key), ...r.split.vqa_rad, ...r.split.slake, ...r.split.pathvqa])} />
  );
}

export function OmniTable() {
  return (
    <Tbl n={9} caption={RESEARCH.image.omni.caption} testId="research-omni" size="sm"
      head={["Model", "Origin", "Type", "Strict", "First-token", "Parsed %", "Errors", ...D.omniTypes.map((t) => t.replace(" ", "\n"))]} numeric={[3, 4, 5, 6, 7, 8, 9, 10, 11]}
      rows={D.image.map((r) => [name(r.key), ...tags(r.key), (r.overall as Record<string, number>).omnimedvqa, r.omniFt, r.omniParsed, int(r.omniErrors), ...r.byType])} />
  );
}

export function ImagePublishedTable() {
  return (
    <Tbl n={10} caption={RESEARCH.image.published.caption} testId="research-image-published" size="sm"
      head={["Model", "Benchmark", "This run", "Our protocol", "Published", "Source", "Diff.", "Like for like?"]} numeric={[2, 4, 6]} wrap={[7]}
      rows={D.publishedImage.map((r) => [name(r.key), r.benchmark, r.ours, r.protocol, r.published, r.src, signed(r.ours - r.published), r.like])} />
  );
}

export function ThroughputTable() {
  return (
    <Tbl n={11} caption={RESEARCH.throughput.caption} testId="research-table-throughput" maxW="52rem"
      head={["Model", "Protocol", "Load (s)", "Run (s)", "Mean generated tokens"]} numeric={[2, 3, 4]}
      rows={D.throughput.map((r) => [name(r.key), r.protocol === "cot" ? "step-by-step" : "direct", int(Math.round(r.load ?? 0)), int(Math.round(r.total ?? 0)), int(Math.round(r.genTokens))])} />
  );
}

export function BakeoffTable() {
  return (
    <Tbl n={12} caption={RESEARCH.grounded.bakeoff.caption} testId="research-bakeoff" size="sm"
      head={["Model", "Origin", "Type", "Reader\nword recall", "Invented\nnumbers", "Reader s\n(5 scans)", "Doc. types", "Fields", "Fabricated", "Extractor s\n(31 docs)"]} numeric={[3, 4, 5, 6, 7, 8, 9]}
      rows={D.bakeoff.map((r) => [name(r.key), ...tags(r.key), r.readerRecall, r.invented, r.readerS, r.types, r.fields, r.fabricated, r.extractorS])} />
  );
}

export function AnswerabilityTable() {
  return (
    <Tbl n={13} caption={RESEARCH.grounded.answerability.caption} testId="research-answerability" maxW="52rem"
      head={["Reasoner", "Origin", "Type", "Pass", "Fabrications", "Mean latency (s)"]} numeric={[3, 4, 5]}
      rows={D.answerability.map((r) => [name(r.key), ...tags(r.key), r.pass_, r.fabrications, r.latency])} />
  );
}

export function TcgaTable() {
  const t = D.tcga; const L = RESEARCH.grounded.tcga.labels;
  return (
    <Tbl n={14} caption={RESEARCH.grounded.tcga.caption} testId="research-tcga" maxW="52rem"
      head={[L.reports, L.claims, L.ungrounded, ...t.agreement.map(([k]) => k)]} numeric={[0, 1, 2, 3, 4, 5, 6]}
      rows={[[String(t.reports), String(t.claims), String(t.ungrounded), ...t.agreement.map(([, v]) => v)]]} />
  );
}

export function StatusTable() {
  return (
    <Tbl n={15} caption={RESEARCH.grounded.status.caption} testId="research-status" maxW="34rem" head={["Evidence in the report", "Share of the 9,523 reports"]} numeric={[1]}
      rows={D.status.rows.map(([k, v]) => [k, v])} />
  );
}

export function OcrTables() {
  return (
    <>
      <Tbl n={16} caption={RESEARCH.grounded.ocr.captionEngines} testId="research-ocr" maxW="52rem" head={["Engine", "Number recall %", "Number precision %", "s / page (median)", "Threads per page"]} numeric={[1, 2, 3, 4]}
        rows={D.ocr.map((r) => [r.engine, r.recall, r.precision, r.sPage, r.threads])} />
      <Tbl n={17} caption={RESEARCH.grounded.ocr.captionCheck} testId="research-ocr-check" maxW="60rem" head={["Check", "False alarms", "Substitutions caught %", "Insertions caught %", "Deletions caught %"]} numeric={[1, 2, 3, 4]} wrap={[0]}
        rows={D.ocrCheck.map((r) => [r.check, r.falseAlarms, r.subs, r.ins, r.dels])} />
    </>
  );
}
