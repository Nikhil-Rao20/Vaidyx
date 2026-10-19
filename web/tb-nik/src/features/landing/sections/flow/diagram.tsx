// The journey's diagram: four bands that never overlap (hospital systems, the Vaidyx Case File, doctors decide, after the
// Board) inside a dashed frame "inside the hospital", and one continuous route through every station in order, like a metro
// line: left to right, down the right margin, right to left, down the left margin, left to right. Two short branches join the
// hospital systems. A step lights its stations and the segments of the route between them and sends a dot along them.
// Fixed coordinates in a 760 x 500 box; the drawing scales as a whole.
import { motion, useReducedMotion } from "motion/react";
import {
  Archive, BrainCircuit, CalendarDays, ClipboardCheck, Database, FileCheck2, FileText, Gavel, HardDrive, Images, ListChecks,
  MessageSquareQuote, MonitorPlay, Presentation, Quote, Send, ShieldCheck, Stamp, type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export const W = 760, H = 500;
const NW = 128, NH = 56, GAP = 16, X0 = 28;
const col = (i: number) => X0 + i * (NW + GAP);
const BANDS = [
  { key: "systems", y: 36 }, { key: "vaidyx", y: 140 }, { key: "doctors", y: 244 }, { key: "after", y: 348 },
] as const;
const BH = 96;                         // band height; the node sits at band.y + 30
const ny = (b: number) => BANDS[b].y + 30;
const cy = (b: number) => ny(b) + NH / 2;

export interface Node { id: string; x: number; y: number; w?: number; label: string; sub: string; icon: LucideIcon; icons?: LucideIcon[]; zone: (typeof BANDS)[number]["key"] }

export const NODES: Node[] = [
  { id: "systems", x: col(0), y: ny(0), w: NW * 3 + GAP * 2, label: "Hospital systems", sub: "HIS · LIS / RIS · PACS", icon: Database, icons: [Database, HardDrive, Images], zone: "systems" },
  { id: "records", x: col(0), y: ny(1), label: "Records in", sub: "One Case File", icon: FileText, zone: "vaidyx" },
  { id: "quote", x: col(1), y: ny(1), label: "Values quoted", sub: "Source line kept", icon: Quote, zone: "vaidyx" },
  { id: "checklist", x: col(2), y: ny(1), label: "Checklist", sub: "What is missing", icon: ListChecks, zone: "vaidyx" },
  { id: "request", x: col(3), y: ny(1), label: "Request", sub: "To a department", icon: Send, zone: "vaidyx" },
  { id: "briefs", x: col(4), y: ny(1), label: "Specialty briefs", sub: "Six helpers", icon: BrainCircuit, zone: "vaidyx" },
  { id: "question", x: col(4), y: ny(2), label: "Question", sub: "For the Board", icon: MessageSquareQuote, zone: "doctors" },
  { id: "ready", x: col(3), y: ny(2), label: "Ready", sub: "By the doctor", icon: ClipboardCheck, zone: "doctors" },
  { id: "agenda", x: col(2), y: ny(2), label: "Agenda", sub: "The coordinator", icon: CalendarDays, zone: "doctors" },
  { id: "meeting", x: col(1), y: ny(2), label: "Meeting", sub: "Slide, report, scan", icon: MonitorPlay, zone: "doctors" },
  { id: "decision", x: col(0), y: ny(2), label: "Decision", sub: "The Board's", icon: Gavel, zone: "doctors" },
  { id: "minutes", x: col(0), y: ny(3), label: "Minutes", sub: "At the close", icon: FileCheck2, zone: "after" },
  { id: "deck", x: col(1), y: ny(3), label: "Board deck", sub: "Hospital's logo", icon: Presentation, zone: "after" },
  { id: "ncg", x: col(2), y: ny(3), label: "NCG form", sub: "Virtual TB", icon: FileText, zone: "after" },
  { id: "preauth", x: col(3), y: ny(3), label: "Pre-auth", sub: "PM-JAY", icon: Stamp, zone: "after" },
  { id: "audit", x: col(4), y: ny(3), label: "Audit log", sub: "Who and when", icon: Archive, zone: "after" },
];

const n = (id: string) => { const x = NODES.find((k) => k.id === id)!; const w = x.w ?? NW; return { l: x.x, r: x.x + w, t: x.y, b: x.y + NH, cx: x.x + w / 2, cy: x.y + NH / 2 }; };
const R = 14, LM = 16, RM = W - 16;   // corner radius, the margins the returns run in
const h = (a: string, b: string) => `M${n(a).cx},${n(a).cy} L${n(b).cx},${n(b).cy}`;

export interface Path { id: string; d: string; arrow?: boolean }
export const PATHS: Path[] = [
  { id: "systems-records", d: `M${n("records").cx},${n("systems").b} L${n("records").cx},${n("records").t}`, arrow: true },
  { id: "request-systems", d: `M${n("request").cx},${n("request").t} C${n("request").cx},${n("systems").b + 10} ${n("systems").r + 24},${n("systems").cy + 10} ${n("systems").r},${n("systems").cy}`, arrow: true },
  { id: "records-quote", d: h("records", "quote") },
  { id: "quote-checklist", d: h("quote", "checklist") },
  { id: "checklist-request", d: h("checklist", "request") },
  { id: "request-briefs", d: h("request", "briefs") },
  { id: "briefs-question", d: `M${n("briefs").cx},${cy(1)} L${RM - R},${cy(1)} Q${RM},${cy(1)} ${RM},${cy(1) + R} L${RM},${cy(2) - R} Q${RM},${cy(2)} ${RM - R},${cy(2)} L${n("question").cx},${cy(2)}` },
  { id: "question-ready", d: h("question", "ready") },
  { id: "ready-agenda", d: h("ready", "agenda") },
  { id: "agenda-meeting", d: h("agenda", "meeting") },
  { id: "meeting-decision", d: h("meeting", "decision") },
  { id: "decision-minutes", d: `M${n("decision").cx},${cy(2)} L${LM + R},${cy(2)} Q${LM},${cy(2)} ${LM},${cy(2) + R} L${LM},${cy(3) - R} Q${LM},${cy(3)} ${LM + R},${cy(3)} L${n("minutes").cx},${cy(3)}` },
  { id: "minutes-deck", d: h("minutes", "deck") },
  { id: "deck-ncg", d: h("deck", "ncg") },
  { id: "ncg-preauth", d: h("ncg", "preauth") },
  { id: "preauth-audit", d: h("preauth", "audit") },
];

/** The whole route, for the faint line under everything. */
const ROUTE = PATHS.filter((p) => !p.arrow).map((p) => p.d).join(" ");

export function Diagram({ activeNodes, activePaths, zones, frame, className }: { activeNodes: string[]; activePaths: string[]; zones: Record<string, string>; frame: string; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-auto w-full", className)} role="img" aria-label="The journey of one patient through Vaidyx" data-testid="journey-diagram">
      <defs>
        <marker id="jy-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M1 1l6 3-6 3z" fill="var(--jy-line-on)" /></marker>
        <filter id="jy-glow" x="-30%" y="-40%" width="160%" height="180%"><feGaussianBlur stdDeviation="5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <rect x={6} y={6} width={W - 12} height={H - 12} rx={22} className="jy-frame" />
      <text x={26} y={26} className="jy-frame-lbl">{frame}</text>
      {BANDS.map((b, i) => (
        <g key={b.key} className={cn("jy-zone", `jy-zone-${b.key}`)}>
          <rect x={X0 - 10} y={b.y} width={W - 2 * (X0 - 10)} height={BH} rx={16} />
          <text x={X0 + 2} y={b.y + 18}>{zones[b.key]}</text>
          <text x={W - X0 + 2} y={b.y + 18} textAnchor="end" className="jy-zone-n">{`0${i + 1}`}</text>
        </g>
      ))}
      {/* the whole route, faint */}
      <path d={ROUTE} className="jy-route" />
      {PATHS.filter((p) => p.arrow).map((p) => <path key={p.id} d={p.d} className="jy-branch" />)}
      {/* the lit segments and the dots */}
      {PATHS.filter((p) => activePaths.includes(p.id)).map((p) => (
        <g key={p.id}>
          <motion.path d={p.d} className="jy-path-on" markerEnd={p.arrow ? "url(#jy-arrow)" : undefined} initial={reduce ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
          {!reduce ? <circle r={4.5} className="jy-ball"><animateMotion dur="2.4s" repeatCount="indefinite" path={p.d} /></circle> : null}
        </g>
      ))}
      {NODES.map((nd) => {
        const on = activeNodes.includes(nd.id);
        const w = nd.w ?? NW;
        const icons = nd.icons ?? [nd.icon];
        const tx = nd.x + 12 + icons.length * 22 + 2;
        return (
          <g key={nd.id} className={cn("jy-node", `jy-node-${nd.zone}`, on && "jy-node-on")} data-node={nd.id} data-on={on}>
            <rect x={nd.x} y={nd.y} width={w} height={NH} rx={12} filter={on ? "url(#jy-glow)" : undefined} />
            {icons.map((I, k) => <I key={k} x={nd.x + 12 + k * 22} y={nd.y + NH / 2 - 9} width={18} height={18} strokeWidth={1.8} className="jy-node-icon" />)}
            <text x={tx} y={nd.y + 24} className="jy-node-label">{nd.label}</text>
            <text x={tx} y={nd.y + 39} className="jy-node-sub">{nd.sub}</text>
          </g>
        );
      })}
      <ShieldCheck x={W - 48} y={H - 42} className="jy-shield" width={22} height={22} strokeWidth={1.8} />
    </svg>
  );
}
