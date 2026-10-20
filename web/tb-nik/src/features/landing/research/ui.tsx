// Building blocks of the Research page, written like a paper: numbered sections, static tables with a caption and a note,
// the origin and type tags, data cards. Nothing here is interactive; the tables scroll sideways on a phone.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Reveal } from "../components/Reveal";
import { RESEARCH } from "../content";

export const f1 = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(1));
export const signed = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}`);
export const int = (v: number) => v.toLocaleString("en-IN");

/** The country of the developer, as a tag: every table carries it, as the product does. */
export function Origin({ v }: { v: string }) {
  return <span className={cn("l-chip", v === "China" ? "l-chip-warn" : "l-chip-info")}>{v}</span>;
}
/** Medical fine-tune or a general model that is not medically validated. */
export function Kind({ v }: { v: string }) {
  return <span className={cn("l-chip", v === "Medical" ? "l-chip-ok" : "l-chip-review")}>{v}</span>;
}

export type Cell = ReactNode;
export type Row = Cell[] | { cells: Cell[]; sep?: boolean; dim?: boolean; strong?: boolean };

/** A static result table: numbered caption above, the head (a "\n" in a label breaks it over two lines), right-aligned
 * numeric columns, bold for the best value in the columns listed in `boldMax`, an optional note underneath. */
export function Tbl({ n, caption, head, rows, numeric = [], boldMax = [], wrap = [], note, testId, size = "md", maxW }: {
  n: number; caption: string; head: string[]; rows: Row[]; numeric?: number[]; boldMax?: number[]; wrap?: number[]; note?: string; testId?: string; size?: "sm" | "md";
  /** a narrower card for tables with few columns, e.g. "44rem" */ maxW?: string;
}) {
  const best = new Map<number, number>();
  for (const c of boldMax) {
    let m = -Infinity;
    for (const r of rows) {
      const cells = Array.isArray(r) ? r : r.cells;
      const v = cells[c];
      if (typeof v === "number" && v > m) m = v;
    }
    best.set(c, m);
  }
  return (
    <Reveal y={16} amount={0.1}>
      <figure className="l-card overflow-hidden" data-testid={testId} style={maxW ? { maxWidth: maxW } : undefined}>
        <figcaption className="r-cap px-5 pb-3 pt-4 sm:px-6"><b>Table {n}.</b> {caption}</figcaption>
        <div className="overflow-x-auto px-2 pb-2 sm:px-3">
          <table className={cn("r-tbl", size === "sm" && "r-tbl-sm")}>
            <thead>
              <tr>
                {head.map((h, i) => (
                  <th key={i} className={cn(numeric.includes(i) && "num")}>
                    {h.split("\n").map((line, j) => <span key={j} className="block">{line}</span>)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const row = Array.isArray(r) ? { cells: r } : r;
                return (
                  <tr key={i} className={cn(row.sep && "sep", row.dim && "dim", row.strong && "strong")}>
                    {row.cells.map((c, j) => {
                      const isNum = numeric.includes(j);
                      const isBest = typeof c === "number" && best.get(j) === c;
                      const text = typeof c === "number" ? f1(c) : c === "--" ? "–" : c;
                      return <td key={j} className={cn(isNum && "num", wrap.includes(j) && "wrap", isBest && "r-best")}>{text}</td>;
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="r-note px-5 pb-3 sm:hidden">{RESEARCH.swipe}</p>
        {note ? <p className="r-note border-t px-5 py-3 sm:px-6" style={{ borderColor: "var(--l-line)" }}>{note}</p> : null}
      </figure>
    </Reveal>
  );
}

export function Sec({ id, n, title, children }: { id: string; n: number; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-28 pt-14 first:pt-0 sm:pt-16" data-testid={`research-${id}`}>
      <Reveal y={14}><h2 className="r-h2"><em>{n}</em> {title}</h2></Reveal>
      <div className="mt-6 space-y-6">{children}</div>
    </section>
  );
}

export function Sub({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <div className="pt-4">
      <Reveal y={10}><h3 className="r-h3"><em>{n}</em> {title}</h3></Reveal>
      <div className="mt-4 space-y-5">{children}</div>
    </div>
  );
}

export function P({ children, className }: { children: ReactNode; className?: string }) {
  return <Reveal y={10} amount={0.15}><p className={cn("r-p max-w-[52rem]", className)}>{children}</p></Reveal>;
}

/** A term and its definition (the protocol) or a bold lead and its sentence (findings, caveats). */
export function Items({ items, as = "dl" }: { items: readonly (readonly string[])[]; as?: "dl" | "ul" }) {
  if (as === "ul") {
    return (
      <ul className="max-w-[56rem] space-y-3">
        {items.map(([lead, text]) => (
          <li key={lead} className="r-p flex gap-3"><span className="mt-[0.72em] size-1.5 shrink-0 rounded-full" style={{ background: "var(--l-accent)" }} aria-hidden /><span><strong>{lead}</strong> {text}</span></li>
        ))}
      </ul>
    );
  }
  return (
    <dl className="r-dl grid max-w-[64rem] gap-x-8 gap-y-4 sm:grid-cols-[13rem_1fr]">
      {items.map(([term, def]) => (
        <div key={term} className="contents">
          <dt className="r-p">{term}</dt>
          <dd className="r-p">{def}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A data card for one benchmark. */
export function DataCard({ name, kind, tests, n, fmt, chance, scoring, labels }: {
  name: string; kind: string; tests: string; n: string; fmt: string; chance: string; scoring: string;
  labels: { tests: string; n: string; fmt: string; chance: string; scoring: string; kind: string };
}) {
  return (
    <div className="l-box flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-[1.05rem] font-semibold tracking-[-0.01em]">{name}</h4>
        <span className={cn("l-chip", kind === "image" ? "l-chip-review" : "l-chip-info")}>{labels.kind}</span>
      </div>
      <p className="r-cap mt-2">{tests}</p>
      <dl className="r-mini-dl mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
        <dt>{labels.n}</dt><dd>{n}</dd>
        <dt>{labels.fmt}</dt><dd>{fmt}</dd>
        <dt>{labels.chance}</dt><dd>{chance}</dd>
        <dt>{labels.scoring}</dt><dd>{scoring}</dd>
      </dl>
    </div>
  );
}
