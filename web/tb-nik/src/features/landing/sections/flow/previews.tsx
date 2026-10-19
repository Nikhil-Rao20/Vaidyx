// Small previews for the journey's steps, built from the product's own shapes with synthetic data.
import { motion, useReducedMotion } from "motion/react";
import { Check, Clock3, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { SlideCase } from "../Scenes";

const CT_SRC = "/static/tb-nik/brand/art/ct-chest.png";

function Win({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <div className={cn("l-card min-w-0 overflow-hidden text-[12px] leading-[1.35]", className)}>
      {title ? <div className="l-faint border-b border-[var(--l-line)] px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em]">{title}</div> : null}
      <div className="p-3">{children}</div>
    </div>
  );
}

export function PreviewCaseFile() {
  const rows = [["Histopathology report", "3 values quoted", "ok"], ["Staging imaging, CT", "on the PACS", "ok"], ["IHC panel (ER, PR, HER2)", "not in the file", "warn"], ["Clinical note, ECOG", "quoted", "ok"]];
  return (
    <Win title="Case File · TB-2026-0031 · synthetic">
      <div className="flex items-center gap-2"><b className="text-[13px]">Lakshmi R.</b><span className="l-faint">58 F · UHID VXH/2026/000123</span><span className="l-chip l-chip-info ml-auto">Breast cancer</span></div>
      <ul className="mt-2 divide-y divide-[var(--l-line)]">
        {rows.map(([t, s, k]) => (
          <li key={t} className="flex items-center gap-2 py-1.5">
            <span className={cn("grid size-4 place-items-center rounded-full", k === "ok" ? "bg-[var(--l-ok-bg)] text-[var(--l-ok)]" : "bg-[var(--l-warn-bg)] text-[var(--l-warn)]")}>{k === "ok" ? <Check className="size-2.5" strokeWidth={3} /> : <Clock3 className="size-2.5" />}</span>
            <span className="flex-1 font-medium">{t}</span><span className="l-faint">{s}</span>
          </li>
        ))}
      </ul>
    </Win>
  );
}

export function PreviewRequest() {
  const r = useReducedMotion();
  return (
    <Win title="Request · Pathology desk · synthetic">
      <p className="font-medium">IHC panel (ER, PR, HER2) for Lakshmi R.</p>
      <p className="l-faint mt-0.5">Asked by Dr L. Rao · Breast Surgery · due 16/10/2026</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="l-chip l-chip-warn">Waiting on Pathology</span>
        <motion.span className="l-chip l-chip-ok !whitespace-normal" initial={r ? false : { opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.4, duration: 0.4 }}><Check className="size-3 shrink-0" strokeWidth={3} />Report received, 3 values quoted</motion.span>
      </div>
    </Win>
  );
}

export function PreviewBrief() {
  const r = useReducedMotion();
  const lines = ["Invasive carcinoma of no special type, Nottingham grade 2.", "ER positive (80 %), PR positive (60 %); HER2 equivocal (2+), FISH advised.", "No distant disease reported on CT chest and abdomen."];
  return (
    <Win title="Pathology brief · synthetic">
      {lines.map((t, i) => (
        <motion.p key={t} className="flex items-start gap-2 py-1" initial={r ? false : { opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.35, duration: 0.4 }}>
          <span className="flex-1">{t}</span><span className="l-chip l-chip-ok shrink-0"><Quote className="size-3" />source</span>
        </motion.p>
      ))}
    </Win>
  );
}

export function PreviewRoom() {
  return (
    <div className="l-win-ink p-2">
      <div className="grid grid-cols-[1.2fr_1fr] gap-1.5">
        <SlideCase />
        <div className="relative overflow-hidden rounded-md bg-black"><img src={CT_SRC} alt="" className="absolute inset-0 h-full w-full object-cover" /><span className="absolute left-1.5 top-1 rounded bg-black/50 px-1 text-[8px] text-white/80">CT chest · PACS</span></div>
      </div>
      <p className="mt-1.5 text-[10px] text-white/50">Room display · the slide and a scan opened beside it, from the Case File</p>
    </div>
  );
}

export function PreviewSlide() {
  return (
    <Win title="Decision record · synthetic">
      <p className="font-medium">Neoadjuvant chemotherapy, then surgery; HER2 FISH to be reported before the first cycle.</p>
      <p className="l-faint mt-1">Recorded 14:32 · 6 members present · 1 question answered</p>
      <div className="mt-2 flex flex-wrap gap-1.5"><span className="l-chip l-chip-ok"><Check className="size-3" strokeWidth={3} />Decision recorded</span><span className="l-chip l-chip-info">Minutes updating</span></div>
    </Win>
  );
}

export function PreviewAfter() {
  const items = [["Minutes", "ready at the close"], ["Board deck, .pptx", "hospital's logo"], ["NCG VTB template", "filled from the record"], ["Pre-authorization", "PM-JAY papers"], ["Audit log", "every action, who and when"]];
  return (
    <Win title="After the Board · synthetic">
      <ul className="grid grid-cols-2 gap-x-3">
        {items.map(([t, s]) => <li key={t} className="flex items-start gap-1.5 py-1"><Check className="mt-0.5 size-3 shrink-0 text-[var(--l-ok)]" strokeWidth={3} /><span><b className="font-medium">{t}</b><span className="l-faint block text-[11px]">{s}</span></span></li>)}
      </ul>
    </Win>
  );
}

export const PREVIEWS = { casefile: PreviewCaseFile, request: PreviewRequest, brief: PreviewBrief, room: PreviewRoom, slide: PreviewSlide, after: PreviewAfter } as const;
