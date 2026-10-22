// Integration (22 Oct): Vaidyx is standalone software between the hospital's own systems and the Tumour Board. On a laptop a drawing:
// the hospital's systems on the left (HIS / HIMS, LIS, RIS, PACS, outside reports), each joined to Vaidyx by its standard (FHIR R4 read
// only, DICOMweb, upload), Vaidyx in the middle on the hospital's server, the Board on the right; small dots run along the lines while
// the section is in view (none under reduced motion). On a phone the same three columns stack. Then four points and the standards.
import { useRef } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { ArrowDown, Building2, ClipboardList, FileUp, FlaskConical, Images, MonitorPlay, PenLine, ScanLine, Server, ShieldCheck, Unplug, Eye, type LucideIcon } from "lucide-react";
import { INTEGRATION } from "../content";
import { SectionHead } from "../components/SectionHead";
import { Reveal, Stagger } from "../components/Reveal";
import { ICON_BOX, ICON_PATHS } from "@/components/brand-paths";

const D = INTEGRATION.diagram;
const SYS_ICON: Record<string, LucideIcon> = { his: Building2, lis: FlaskConical, ris: ScanLine, pacs: Images, outside: FileUp };
const BOARD_ICON: Record<string, LucideIcon> = { team: PenLine, meeting: MonitorPlay, records: ClipboardList };
const POINT_ICON: Record<string, LucideIcon> = { standalone: Server, agnostic: Unplug, readonly: Eye, images: ShieldCheck };

// The drawing, in a 1000 x 470 box.
const W = 1000, H = 470;
const LX = 10, LW = 250, NH = 64, LY0 = 40, LGAP = 18;          // the systems column
const VX = 395, VW = 230, VY = 92, VH = 290;                      // Vaidyx
const RX = 760, RW = 230, RH = 76, RY0 = 104, RGAP = 30;          // the Board column
const sysY = (i: number) => LY0 + i * (NH + LGAP);
const boardY = (j: number) => RY0 + j * (RH + RGAP);
const inY = (i: number) => VY + 52 + i * 46;                       // where each system's line meets Vaidyx
const outY = (j: number) => VY + 86 + j * 60;
const curve = (x1: number, y1: number, x2: number, y2: number) => { const m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`; };

function Node({ x, y, w, h, icon: Icon, title, sub, tone }: { x: number; y: number; w: number; h: number; icon: LucideIcon; title: string; sub: string; tone: "sys" | "board" }) {
  return (
    <g className={`ig-node ig-${tone}`}>
      <rect x={x} y={y} width={w} height={h} rx={14} className="ig-box" />
      <rect x={x + 12} y={y + (h - 36) / 2} width={36} height={36} rx={10} className="ig-icon-bg" />
      <Icon x={x + 21} y={y + (h - 18) / 2} width={18} height={18} strokeWidth={1.8} className="ig-icon" />
      <text x={x + 60} y={y + h / 2 - 3} className="ig-title">{title}</text>
      <text x={x + 60} y={y + h / 2 + 14} className="ig-sub">{sub}</text>
    </g>
  );
}

function Drawing() {
  const ref = useRef<SVGSVGElement>(null);
  const inView = useInView(ref, { amount: 0.3 });
  const reduce = useReducedMotion();
  const live = inView && !reduce;
  const sysLines = D.systems.map((s, i) => ({ id: s.id, d: curve(LX + LW, sysY(i) + NH / 2, VX, inY(i)), label: (D.links as Record<string, string>)[s.id], y: sysY(i) + NH / 2, rises: inY(i) < sysY(i) + NH / 2 - 4 }));  // a label sits on the side the line leaves
  const boardLines = D.board.map((b, j) => ({ id: b.id, d: curve(VX + VW, outY(j), RX, boardY(j) + RH / 2) }));
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={D.label} data-testid="integration-diagram">
      <defs>
        <linearGradient id="ig-vaidyx" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#00183c" /><stop offset="55%" stopColor="#0b4e74" /><stop offset="100%" stopColor="#01b4c2" />
        </linearGradient>
        <filter id="ig-glow" x="-120%" y="-120%" width="340%" height="340%"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <text x={LX + 4} y={22} className="ig-col">{D.systemsTitle}</text>
      <text x={RX + 4} y={RY0 - 18} className="ig-col">{D.boardTitle}</text>

      {sysLines.map((l) => (
        <g key={l.id}>
          <path d={l.d} className={l.id === "pacs" ? "ig-line ig-line-pacs" : l.id === "outside" ? "ig-line ig-line-dash" : "ig-line"} />
          <text x={LX + LW + 10} y={l.rises ? l.y + 16 : l.y - 7} className="ig-link">{l.label}</text>
        </g>
      ))}
      {boardLines.map((l) => <path key={l.id} d={l.d} className="ig-line ig-line-out" />)}
      {live ? (
        <>
          {sysLines.map((l, i) => <circle key={`in-${l.id}`} r={4} className={l.id === "pacs" ? "ig-dot ig-dot-pacs" : "ig-dot"} filter="url(#ig-glow)"><animateMotion dur="2.8s" begin={`${i * 0.45}s`} repeatCount="indefinite" path={l.d} /></circle>)}
          {boardLines.map((l, j) => <circle key={`out-${l.id}`} r={4} className="ig-dot ig-dot-out" filter="url(#ig-glow)"><animateMotion dur="2.4s" begin={`${1.2 + j * 0.5}s`} repeatCount="indefinite" path={l.d} /></circle>)}
        </>
      ) : null}

      {D.systems.map((s, i) => <Node key={s.id} x={LX} y={sysY(i)} w={LW} h={NH} icon={SYS_ICON[s.id] ?? Building2} title={s.title} sub={s.sub} tone="sys" />)}
      {D.board.map((b, j) => <Node key={b.id} x={RX} y={boardY(j)} w={RW} h={RH} icon={BOARD_ICON[b.id] ?? ClipboardList} title={b.title} sub={b.sub} tone="board" />)}

      {/* Vaidyx, standalone on the hospital's server */}
      <motion.g initial={reduce ? false : { opacity: 0, scale: 0.96 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} style={{ transformOrigin: `${VX + VW / 2}px ${VY + VH / 2}px` }}>
        <rect x={VX - 8} y={VY - 8} width={VW + 16} height={VH + 16} rx={30} className="ig-halo" />
        <rect x={VX} y={VY} width={VW} height={VH} rx={24} fill="url(#ig-vaidyx)" />
        <svg x={VX + VW / 2 - 26} y={VY + 18} width={52} height={38} viewBox={`${ICON_BOX.x} ${ICON_BOX.y} ${ICON_BOX.w} ${ICON_BOX.h}`} aria-hidden>
          {ICON_PATHS.map((p, k) => <path key={k} d={p} fill="#ffffff" opacity={k === 0 ? 1 : 0.85} />)}
        </svg>
        <text x={VX + VW / 2} y={VY + 82} textAnchor="middle" className="ig-v-title">{D.vaidyx.title}</text>
        <text x={VX + VW / 2} y={VY + 102} textAnchor="middle" className="ig-v-sub">{D.vaidyx.sub}</text>
        {D.vaidyx.items.map((it, k) => (
          <g key={it}>
            <rect x={VX + 24} y={VY + 124 + k * 38} width={VW - 48} height={28} rx={14} className="ig-v-chip" />
            <text x={VX + VW / 2} y={VY + 142 + k * 38} textAnchor="middle" className="ig-v-chip-t">{it}</text>
          </g>
        ))}
      </motion.g>
    </svg>
  );
}

/** Phones and narrow windows: the three columns one under the other, joined by arrows. */
function Stacked() {
  const col = (title: string, rows: Array<{ id: string; title: string; sub: string }>, icons: Record<string, LucideIcon>, links?: Record<string, string>) => (
    <div className="space-y-2">
      <p className="l-eyebrow">{title}</p>
      {rows.map((r) => {
        const I = icons[r.id] ?? Building2;
        return (
          <div key={r.id} className="l-card flex items-center gap-3 !rounded-2xl px-4 py-3">
            <span className="l-icon !h-9 !w-9 shrink-0"><I className="size-[18px]" aria-hidden /></span>
            <span className="min-w-0 flex-1"><span className="block text-[15px] font-semibold">{r.title}</span><span className="l-faint block text-[13px]">{r.sub}</span></span>
            {links?.[r.id] ? <span className="l-pill !px-2 !py-0.5 !text-[11px]">{links[r.id]}</span> : null}
          </div>
        );
      })}
    </div>
  );
  return (
    <div className="space-y-4" data-testid="integration-stacked">
      {col(D.systemsTitle, D.systems, SYS_ICON, D.links as Record<string, string>)}
      <ArrowDown className="mx-auto size-5 text-[var(--l-accent)]" aria-hidden />
      <div className="rounded-3xl p-5 text-center text-white" style={{ background: "linear-gradient(135deg, #00183c 0%, #0b4e74 55%, #01b4c2 100%)" }}>
        <p className="text-2xl font-semibold tracking-tight">{D.vaidyx.title}</p>
        <p className="mt-1 text-sm opacity-85">{D.vaidyx.sub}</p>
        <div className="mt-3 flex flex-wrap justify-center gap-1.5">{D.vaidyx.items.map((it) => <span key={it} className="rounded-full bg-white/15 px-3 py-1 text-[13px]">{it}</span>)}</div>
      </div>
      <ArrowDown className="mx-auto size-5 text-[var(--l-accent)]" aria-hidden />
      {col(D.boardTitle, D.board, BOARD_ICON)}
    </div>
  );
}

export function Integration() {
  return (
    <section id="integration" className="l-section l-section-2 relative overflow-hidden py-24 sm:py-32" data-testid="integration">
      <span className="l-orb l-orb-teal" style={{ width: 620, height: 620, right: "-12%", top: "6%", opacity: 0.35 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={INTEGRATION.eyebrow} title={[INTEGRATION.title[0], INTEGRATION.title[1]]} lead={INTEGRATION.lead} />
        <Reveal className="mt-14" y={20}>
          <div className="l-card hidden p-6 lg:block xl:p-8"><Drawing /></div>
          <div className="lg:hidden"><Stacked /></div>
        </Reveal>
        <Stagger className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4" itemClassName="h-full">
          {INTEGRATION.points.map((p) => {
            const I = POINT_ICON[p.key] ?? Server;
            return (
              <article key={p.key} className="l-tile flex h-full flex-col p-6" data-testid="integration-point">
                <span className="l-icon"><I className="size-5" aria-hidden /></span>
                <h3 className="l-title mt-4 text-[1.2rem]">{p.title}</h3>
                <p className="l-muted mt-2 text-[15px]">{p.text}</p>
              </article>
            );
          })}
        </Stagger>
        <Reveal className="mt-8 flex flex-wrap items-center gap-2" y={12}>
          {INTEGRATION.standards.map((s) => <span key={s} className="l-pill">{s}</span>)}
        </Reveal>
        <p className="l-faint mt-4 text-[13px]">{INTEGRATION.note}</p>
      </div>
    </section>
  );
}
