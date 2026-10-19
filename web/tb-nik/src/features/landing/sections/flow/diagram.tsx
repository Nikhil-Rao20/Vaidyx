// The workflow map, a swimlane chart: rows are who acts (hospital systems, the treating department, Vaidyx, Pathology and
// Radiology, the coordinator and the Board); time runs left to right through three phases (before the Board, the meeting,
// after). Stations are rounded cards; the main route is drawn with right-angled, rounded lines and arrowheads; three loops are
// dashed: a report returning into the file, a deferral for more information, re-discussion at progression. A step lights its
// stations and segments and sends a dot along them. Fixed coordinates in an 800 x 540 box; the drawing scales as a whole.
import { motion, useReducedMotion } from "motion/react";
import {
  BrainCircuit, CalendarDays, Database, FileCheck2, FilePlus2, FileText, FlaskConical, Gavel, HardDrive, Images, ListChecks,
  MessageSquareQuote, MonitorPlay, Send, ShieldCheck, Stethoscope, type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export const W = 800, H = 540;
const AX = 10, AW = 780;                 // the chart area
const CW = AW / 8, NW = 86, NH = 60;     // eight columns; node width and height
const LY = 30, LH = 92;                  // first lane's top, lane height
const col = (i: number) => AX + i * CW + (CW - NW) / 2;
const laneY = (k: number) => LY + k * LH;
const nodeY = (k: number) => laneY(k) + (LH - NH) / 2;
const px = (c: number) => AX + c * CW;
const gapX = (c: number) => px(c);       // the centre of the gap before column c

export const LANES = ["systems", "dept", "vaidyx", "support", "board"] as const;
export const PHASES = [{ key: "before", from: 0, to: 4 }, { key: "meeting", from: 5, to: 6 }, { key: "after", from: 7, to: 7 }] as const;

export interface Node { id: string; x: number; y: number; w?: number; label: string; sub: string; icon: LucideIcon; lane: (typeof LANES)[number]; items?: { icon: LucideIcon; label: string }[] }
export const NODES: Node[] = [
  { id: "systems", x: col(0), y: nodeY(0), w: NW + CW, label: "Hospital systems", sub: "", icon: Database, lane: "systems", items: [{ icon: Database, label: "HIS" }, { icon: HardDrive, label: "LIS / RIS" }, { icon: Images, label: "PACS" }] },
  { id: "opened", x: col(0), y: nodeY(1), label: "Case File", sub: "opened by UHID", icon: FilePlus2, lane: "dept" },
  { id: "records", x: col(1), y: nodeY(2), label: "Records in", sub: "every value quoted", icon: FileText, lane: "vaidyx" },
  { id: "checklist", x: col(2), y: nodeY(2), label: "Checklist", sub: "against the protocol", icon: ListChecks, lane: "vaidyx" },
  { id: "request", x: col(3), y: nodeY(2), label: "Request", sub: "to a department", icon: Send, lane: "vaidyx" },
  { id: "report", x: col(3), y: nodeY(3), label: "Report filed", sub: "at the HIS desk", icon: FlaskConical, lane: "support" },
  { id: "briefs", x: col(4), y: nodeY(2), label: "Briefs", sub: "six specialties", icon: BrainCircuit, lane: "vaidyx" },
  { id: "question", x: col(4), y: nodeY(1), label: "Question", sub: "marked ready", icon: MessageSquareQuote, lane: "dept" },
  { id: "agenda", x: col(5), y: nodeY(4), label: "Agenda", sub: "the coordinator", icon: CalendarDays, lane: "board" },
  { id: "meeting", x: col(6), y: nodeY(4), label: "Meeting", sub: "slide, report, scan", icon: MonitorPlay, lane: "board" },
  { id: "decision", x: col(7), y: nodeY(4), label: "Decision", sub: "the Board's", icon: Gavel, lane: "board" },
  { id: "outputs", x: col(7), y: nodeY(2), label: "Minutes, forms", sub: "deck, NCG, pre-auth", icon: FileCheck2, lane: "vaidyx" },
  { id: "followup", x: col(7), y: nodeY(1), label: "Follow-up", sub: "in the clinic", icon: Stethoscope, lane: "dept" },
];

const nd = (id: string) => { const x = NODES.find((k) => k.id === id)!; const w = x.w ?? NW; return { l: x.x, r: x.x + w, t: x.y, b: x.y + NH, cx: x.x + w / 2, cy: x.y + NH / 2 }; };
/** A right-angled line through the points with rounded corners. */
function orth(pts: [number, number][], r = 10): string {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    const dx1 = Math.sign(x1 - x0), dy1 = Math.sign(y1 - y0), dx2 = Math.sign(x2 - x1), dy2 = Math.sign(y2 - y1);
    d += ` L${x1 - dx1 * r},${y1 - dy1 * r} Q${x1},${y1} ${x1 + dx2 * r},${y1 + dy2 * r}`;
  }
  const [xl, yl] = pts[pts.length - 1];
  return d + ` L${xl},${yl}`;
}
const TOP = LY + 8;                 // the corridor above the first lane's nodes (empty right of the systems node)
const BOTTOM = laneY(5) + 14;       // the corridor under the last lane
const RIGHT = AX + AW + 4;          // the right margin

export interface Path { id: string; d: string; loop?: boolean; label?: { x: number; y: number; text: string } }
export const PATHS: Path[] = [
  { id: "systems-records", d: orth([[nd("records").cx, nd("systems").b], [nd("records").cx, nd("records").t]]) },
  { id: "opened-records", d: orth([[nd("opened").r, nd("opened").cy], [nd("records").cx - 26, nd("opened").cy], [nd("records").cx - 26, nd("records").t]]) },
  { id: "records-checklist", d: orth([[nd("records").r, nd("records").cy], [nd("checklist").l, nd("checklist").cy]]) },
  { id: "checklist-request", d: orth([[nd("checklist").r, nd("checklist").cy], [nd("request").l, nd("request").cy]]) },
  { id: "request-report", d: orth([[nd("request").cx, nd("request").b], [nd("report").cx, nd("report").t]]) },
  { id: "report-records", loop: true, d: orth([[nd("report").l, nd("report").cy], [nd("records").cx, nd("report").cy], [nd("records").cx, nd("records").b]]), label: { x: (nd("report").l + nd("records").cx) / 2, y: nd("report").cy - 7, text: "report returns into the file" } },
  { id: "request-briefs", d: orth([[nd("request").r, nd("request").cy], [nd("briefs").l, nd("briefs").cy]]) },
  { id: "briefs-question", d: orth([[nd("briefs").cx, nd("briefs").t], [nd("question").cx, nd("question").b]]) },
  { id: "question-agenda", d: orth([[nd("question").r, nd("question").cy], [nd("agenda").cx, nd("question").cy], [nd("agenda").cx, nd("agenda").t]]) },
  { id: "agenda-meeting", d: orth([[nd("agenda").r, nd("agenda").cy], [nd("meeting").l, nd("meeting").cy]]) },
  { id: "meeting-decision", d: orth([[nd("meeting").r, nd("meeting").cy], [nd("decision").l, nd("decision").cy]]) },
  { id: "decision-question", loop: true, d: orth([[nd("decision").l, nd("decision").cy - 16], [gapX(7), nd("decision").cy - 16], [gapX(7), TOP], [nd("question").cx + 22, TOP], [nd("question").cx + 22, nd("question").t]]), label: { x: (gapX(7) + nd("question").cx) / 2, y: TOP - 5, text: "deferred: more information needed" } },
  { id: "decision-outputs", d: orth([[nd("decision").cx, nd("decision").t], [nd("outputs").cx, nd("outputs").b]]) },
  { id: "outputs-followup", d: orth([[nd("outputs").cx, nd("outputs").t], [nd("followup").cx, nd("followup").b]]) },
  { id: "followup-opened", loop: true, d: orth([[nd("followup").r, nd("followup").cy], [RIGHT, nd("followup").cy], [RIGHT, BOTTOM], [nd("opened").cx, BOTTOM], [nd("opened").cx, nd("opened").b]]), label: { x: (RIGHT + nd("opened").cx) / 2, y: BOTTOM - 6, text: "re-discussed at progression" } },
];

function Station({ node, on }: { node: Node; on: boolean }) {
  const w = node.w ?? NW;
  const Icon = node.icon;
  return (
    <g className={cn("jy-node", `jy-node-${node.lane}`, on && "jy-node-on")} data-node={node.id} data-on={on}>
      <rect x={node.x - 3} y={node.y - 3} width={w + 6} height={NH + 6} rx={15} className="jy-node-ring" />
      <rect x={node.x} y={node.y} width={w} height={NH} rx={12} className="jy-node-box" />
      {node.items ? (
        <>
          {node.items.map((it, k) => {
            const cx = node.x + (w / node.items!.length) * (k + 0.5);
            return (<g key={it.label}><it.icon x={cx - 9} y={node.y + 9} width={18} height={18} strokeWidth={1.8} className="jy-node-icon" /><text x={cx} y={node.y + 42} textAnchor="middle" className="jy-node-label">{it.label}</text></g>);
          })}
        </>
      ) : (
        <>
          <Icon x={node.x + w / 2 - 9} y={node.y + 8} width={18} height={18} strokeWidth={1.8} className="jy-node-icon" />
          <text x={node.x + w / 2} y={node.y + 39} textAnchor="middle" className="jy-node-label">{node.label}</text>
          <text x={node.x + w / 2} y={node.y + 51} textAnchor="middle" className="jy-node-sub">{node.sub}</text>
        </>
      )}
    </g>
  );
}

export function Diagram({ activeNodes, activePaths, lanes, phases, frame, className }: { activeNodes: string[]; activePaths: string[]; lanes: Record<string, string>; phases: Record<string, string>; frame: string; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-auto w-full", className)} role="img" aria-label="The Tumour Board workflow, from records to follow-up" data-testid="journey-diagram">
      <defs>
        <marker id="jy-arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M1 1l6 3-6 3z" className="jy-arrowhead" /></marker>
        <marker id="jy-arrow-on" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M1 1l6 3-6 3z" fill="var(--jy-line-on)" /></marker>
        <filter id="jy-ball-glow" x="-120%" y="-120%" width="340%" height="340%"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {/* phases: tinted columns with a header */}
      {PHASES.map((p, i) => (
        <g key={p.key} className={cn("jy-phase", i % 2 === 1 && "jy-phase-alt")}>
          <rect x={px(p.from)} y={0} width={px(p.to + 1) - px(p.from)} height={BOTTOM + 18} />
          <text x={(px(p.from) + px(p.to + 1)) / 2} y={18} textAnchor="middle">{phases[p.key]}</text>
        </g>
      ))}
      {/* lanes: a hairline and a small label at the top left */}
      {LANES.map((l, k) => (
        <g key={l} className="jy-lane">
          <line x1={AX} y1={laneY(k)} x2={AX + AW} y2={laneY(k)} />
          <text x={AX + 8} y={laneY(k) + 12}>{lanes[l]}</text>
        </g>
      ))}
      {/* every line, faint; loops dashed with their label */}
      {PATHS.map((p) => (
        <g key={p.id}>
          <path d={p.d} className={cn("jy-route", p.loop && "jy-loop")} markerEnd="url(#jy-arrow)" />
          {p.label ? <text x={p.label.x} y={p.label.y} textAnchor="middle" className="jy-loop-lbl">{p.label.text}</text> : null}
        </g>
      ))}
      {/* the lit segments and the dots */}
      {PATHS.filter((p) => activePaths.includes(p.id)).map((p) => (
        <g key={p.id}>
          <motion.path d={p.d} className="jy-path-on" markerEnd="url(#jy-arrow-on)" initial={reduce ? false : { pathLength: 0, opacity: 0.4 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 0.75, ease: [0.22, 1, 0.36, 1] }} />
          {!reduce ? (
            <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6, duration: 0.3 }}>
              <circle r={4.5} className="jy-ball" filter="url(#jy-ball-glow)"><animateMotion dur="2.6s" repeatCount="indefinite" path={p.d} /></circle>
            </motion.g>
          ) : null}
        </g>
      ))}
      {NODES.map((n) => <Station key={n.id} node={n} on={activeNodes.includes(n.id)} />)}
      <ShieldCheck x={AX + 6} y={BOTTOM + 2} className="jy-shield" width={16} height={16} strokeWidth={1.8} />
      <text x={AX + 28} y={BOTTOM + 14} className="jy-frame-lbl">{frame}</text>
    </svg>
  );
}
