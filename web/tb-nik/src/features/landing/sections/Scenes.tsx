// The three screens of "How it works", built from the product's own shapes with synthetic data: a Case File filling itself,
// the meeting with the case summary slide on the room display, and what follows. Each plays its small sequence when it appears.
import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "motion/react";
import { Check, Clock3, FileText, Hand, Mic, MonitorUp, MousePointer2, PhoneOff, Presentation, Video } from "lucide-react";
import { ICON_SRC } from "@/components/Wordmark";
import { cn } from "@/lib/utils";

const CT_SRC = "/static/tb-nik/brand/art/ct-chest.png";

const list: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.12, delayChildren: 0.2 } } };
const row: Variants = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } } };

function Frame({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("l-screen", className)} data-testid="scene">
      <div className="l-screen-bar"><i /><i /><i /><span className="ml-2 text-[11px] font-medium text-white/50">{title}</span></div>
      <div className="p-3 sm:p-4">{children}</div>
    </div>
  );
}

/** The case summary slide of the board deck, in miniature (16:9). Synthetic data. */
export function SlideCase({ className }: { className?: string }) {
  return (
    <div className={cn("l-slide", className)} role="img" aria-label="Case summary slide, synthetic data" data-testid="slide-case">
      <div className="s-top"><b>Vaidyx Demo Hospital · Tumour Board</b><span>22 October 2026 · Case File 4 of 9</span></div>
      <div className="s-rule" />
      <div className="s-head">
        <div className="s-title">Lakshmi R., 58 F · Breast cancer, locally advanced</div>
        <div className="s-sub">Staging as recorded · UHID VXH/2026/000123 · Breast Surgery · Dr L. Rao</div>
      </div>
      <div className="s-body">
        <div className="s-left">
          <div className="s-h">Clinical summary</div>
          <div className="s-li">Invasive carcinoma of no special type, Nottingham grade 2.<span className="s-q">source</span></div>
          <div className="s-li">ER positive (80 %), PR positive (60 %); HER2 equivocal (2+), FISH advised.<span className="s-q">source</span></div>
          <div className="s-li">CT chest and abdomen, 14 October 2026: no distant disease reported.<span className="s-q">source</span></div>
          <div className="s-li">ECOG performance status 1.<span className="s-q">source</span></div>
        </div>
        <div className="s-right">
          <div className="s-h">Question for the Board</div>
          <div className="s-box"><p>Confirmation of staging and of the HER2 result before the treatment decision.</p></div>
          <div className="s-stage"><div><b>cT3</b><span>T, recorded</span></div><div><b>cN1</b><span>N, recorded</span></div><div><b>cM0</b><span>M, recorded</span></div></div>
          <span className="s-review"><b>For review</b> HER2 FISH pending</span>
        </div>
      </div>
      <div className="s-foot"><span>Every value verified against its source · Synthetic data</span><span style={{ display: "flex", alignItems: "center", gap: "1.2cqw" }}><img src={ICON_SRC} alt="" />Vaidyx · 4 / 9</span></div>
    </div>
  );
}

export function SceneBefore() {
  const reduce = useReducedMotion();
  const rows = [
    { t: "Histopathology report", s: "3 values verified", k: "ok" },
    { t: "Staging imaging, CT chest and abdomen", s: "as recorded, on the PACS", k: "ok" },
    { t: "IHC panel (ER, PR, HER2)", s: "requested from Pathology", k: "warn", later: { s: "received, 3 values verified", k: "ok" } },
    { t: "Clinical note with performance status", s: "ECOG 1, verified", k: "ok" },
    { t: "Question for the Board", s: "recorded by the treating clinician", k: "ok" },
  ];
  return (
    <Frame title="Case File · TB-2026-0031 · synthetic">
      <div className="l-win l-mini p-3.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-[15px] font-semibold tracking-[-0.01em]">Lakshmi R.</span>
          <span className="text-[var(--text-2)]">58 F</span>
          <span className="id text-[11.5px] text-[var(--text-2)]">UHID VXH/2026/000123</span>
          <span className="l-chip l-chip-info ml-auto">Breast cancer</span>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <div className="l-bar flex-1"><motion.i initial={{ width: "38%" }} animate={{ width: "92%" }} transition={{ duration: reduce ? 0 : 2.2, delay: 0.6, ease: [0.22, 1, 0.36, 1] }} /></div>
          <span className="w-10 text-right text-[11px] font-semibold tabular-nums text-[#0a4d52]">92%</span>
        </div>
        <motion.ul className="mt-3 divide-y divide-[rgba(11,25,48,0.07)]" variants={list} initial="hidden" animate="show">
          {rows.map((r) => (
            <motion.li key={r.t} variants={row} className="flex items-center gap-2.5 py-2">
              <span className={cn("grid size-5 shrink-0 place-items-center rounded-full", r.k === "ok" ? "bg-[#e4f4ea] text-[#1d6a44]" : "bg-[#fdf1d6] text-[#8a5200]")}>
                {r.k === "ok" ? <Check className="size-3" strokeWidth={3} aria-hidden /> : <Clock3 className="size-3" aria-hidden />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{r.t}</span>
                {r.later && !reduce ? (
                  <span className="relative block h-[15px]">
                    <motion.span className="absolute inset-0 text-[11.5px] text-[var(--text-2)]" initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ delay: 2.4, duration: 0.3 }}>{r.s}</motion.span>
                    <motion.span className="absolute inset-0 text-[11.5px] text-[#1d6a44]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.6, duration: 0.3 }}>{r.later.s}</motion.span>
                  </span>
                ) : <span className="block text-[11.5px] text-[var(--text-2)]">{r.later ? r.later.s : r.s}</span>}
              </span>
              {r.later ? (
                <span className="relative h-5 w-24">
                  <motion.span className="l-chip l-chip-warn absolute right-0" initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={{ delay: reduce ? 0 : 2.4, duration: 0.3 }}>Pathology</motion.span>
                  <motion.span className="l-chip l-chip-ok absolute right-0" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: reduce ? 0 : 2.6, duration: 0.35 }}>Received</motion.span>
                </span>
              ) : null}
            </motion.li>
          ))}
        </motion.ul>
      </div>
      <motion.div className="mt-2.5 grid grid-cols-3 gap-2" variants={list} initial="hidden" animate="show">
        {[["Radiology brief", "ready", "ok"], ["Pathology brief", "in preparation", "info"], ["Medical Oncology brief", "ready", "ok"]].map(([t, s, k]) => (
          <motion.div key={t} variants={row} className="rounded-xl border border-white/10 bg-white/[0.05] p-2.5">
            <p className="truncate text-[11.5px] font-medium text-white/85">{t}</p>
            <span className={cn("l-chip mt-1.5", k === "ok" ? "l-chip-ok" : "l-chip-info")}>
              {k === "info" ? <motion.i className="size-1.5 rounded-full bg-current" animate={reduce ? undefined : { opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }} /> : null}{s}
            </span>
          </motion.div>
        ))}
      </motion.div>
    </Frame>
  );
}

/** The room display: the slide, then a pointer clicks "Report + scan" and the report and the CT image take its place side by side. */
function RoomDisplay() {
  const reduce = useReducedMotion();
  const [view, setView] = useState<"slide" | "docs">(reduce ? "docs" : "slide");
  const [pressed, setPressed] = useState(false);
  useEffect(() => {
    if (reduce) return;
    let alive = true;
    const timers: number[] = [];
    const cycle = () => {
      timers.push(window.setTimeout(() => alive && setPressed(true), 2300));
      timers.push(window.setTimeout(() => alive && setView("docs"), 2500));
      timers.push(window.setTimeout(() => alive && setPressed(false), 2700));
      timers.push(window.setTimeout(() => alive && setView("slide"), 8200));
      timers.push(window.setTimeout(() => alive && cycle(), 9200));
    };
    cycle();
    return () => { alive = false; timers.forEach((t) => window.clearTimeout(t)); };
  }, [reduce]);
  const docs = view === "docs";
  return (
    <div className="relative">
      {/* the display's toolbar */}
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className={cn("rounded-full px-2.5 py-1 text-[10.5px] font-semibold transition-colors", !docs ? "bg-white/15 text-white" : "text-white/55")}>Slide</span>
        <span className={cn("relative rounded-full px-2.5 py-1 text-[10.5px] font-semibold transition-colors", docs ? "bg-[var(--cyan)] text-[#03262b]" : "text-white/55", pressed && "scale-95")} data-testid="open-docs">Report + scan</span>
        <span className="ml-auto text-[10px] text-white/45">Room display</span>
      </div>
      <div className="relative" style={{ aspectRatio: "16 / 9" }}>
        <AnimatePresence mode="wait" initial={false}>
          {!docs ? (
            <motion.div key="slide" className="absolute inset-0" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.25 } }} transition={{ duration: 0.4 }}>
              <SlideCase />
            </motion.div>
          ) : (
            <motion.div key="docs" className="absolute inset-0 grid grid-cols-[0.95fr_1.05fr] gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.25 } }}>
              <motion.div className="l-win flex flex-col overflow-hidden" initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
                <div className="flex items-center gap-1.5 border-b border-[rgba(11,25,48,0.08)] px-2.5 py-1.5"><span className="rounded bg-[#b2362b] px-1 text-[8px] font-bold text-white">PDF</span><span className="truncate text-[9.5px] font-semibold">Histopathology report</span><span className="ml-auto text-[8px] text-[#5f6b78]">p. 1 of 2</span></div>
                <div className="flex-1 space-y-[5px] p-2.5">
                  <p className="text-[8px] font-semibold">Specimen: core needle biopsy, left breast.</p>
                  {[88, 72, 94, 0, 80, 66, 90, 58, 76].map((w, i) => i === 3
                    ? <p key={i} className="rounded bg-[rgba(1,203,211,0.2)] px-1 text-[8px] font-semibold">Tumour size on core: 2.8 cm.</p>
                    : <span key={i} className="block h-[5px] rounded-full bg-[#e2e8ef]" style={{ width: `${w}%` }} />)}
                </div>
              </motion.div>
              <motion.div className="l-win-ink relative overflow-hidden" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.45, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}>
                <img src={CT_SRC} alt="" className="absolute inset-0 h-full w-full object-cover" />
                <span className="absolute left-2 top-1.5 rounded bg-black/50 px-1.5 py-0.5 text-[8.5px] font-medium text-white/85">CT chest · axial · PACS</span>
                <span className="absolute bottom-1.5 right-2 rounded bg-black/50 px-1.5 py-0.5 text-[8px] text-white/70">W 1500 · L -600</span>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
        {/* the pointer that opens the report and the scan */}
        {!reduce ? (
          <motion.span className="pointer-events-none absolute z-10 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.6)]" initial={{ left: "62%", top: "70%", opacity: 0 }} animate={{ left: docs ? "22%" : ["62%", "22%"], top: docs ? "-8%" : ["70%", "-8%"], opacity: [0, 1, 1] }} transition={{ duration: 1.2, delay: docs ? 0 : 0.9, ease: [0.22, 1, 0.36, 1] }} aria-hidden>
            <motion.span className="block" animate={{ scale: pressed ? 0.85 : 1 }} transition={{ duration: 0.12 }}><MousePointer2 className="size-4 fill-white" strokeWidth={1.5} /></motion.span>
          </motion.span>
        ) : null}
      </div>
      <span className="mt-1.5 block text-[10px] text-white/45">Room display · the slide, then the report and the scan opened inside the meeting</span>
    </div>
  );
}

export function SceneDuring() {
  const reduce = useReducedMotion();
  const people = [["LR", "Dr Lakshmi Rao", true], ["IK", "Dr Iqbal Khan", false], ["PN", "Priya Nair", false], ["TJ", "Dr Thomas Joseph", false]] as const;
  return (
    <Frame title="Meeting · Tuesday Board · Case File 4 of 9 · synthetic">
      <div className="grid grid-cols-[1.55fr_1fr] gap-2">
        <RoomDisplay />
        <motion.div className="grid grid-rows-4 gap-2 self-start pt-6" variants={list} initial="hidden" animate="show">
          {people.map(([ini, name, speaking], i) => (
            <motion.div key={ini} variants={row} className={cn("l-win-ink relative flex items-center gap-2 px-2.5 py-2", speaking && "ring-2 ring-[var(--mint)]")}>
              <span className="grid size-7 place-items-center rounded-full text-[10px] font-semibold text-white" style={{ background: `linear-gradient(135deg, ${["#0b4e74", "#5b3fc4", "#01b4c2", "#1d6a44"][i]}, #0a1630)` }}>{ini}</span>
              <span className="truncate text-[11px] text-white/85">{name}</span>
              {speaking ? <motion.span className="ml-auto size-1.5 rounded-full bg-[var(--mint)]" animate={reduce ? undefined : { scale: [1, 1.6, 1] }} transition={{ duration: 1.1, repeat: Infinity }} aria-hidden /> : null}
              {i === 2 ? <Hand className="ml-auto size-3.5 text-[#f0b45c]" aria-hidden /> : null}
            </motion.div>
          ))}
        </motion.div>
      </div>
      <motion.div className="l-win l-mini mt-3 flex items-center gap-2.5 px-3 py-2.5" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.1, duration: 0.5 }}>
        <span className="l-chip l-chip-ok"><Check className="size-3" strokeWidth={3} aria-hidden />Decision recorded</span>
        <span className="truncate text-[var(--text-2)]">14:32 · 6 members present · 1 question raised · minutes updating</span>
      </motion.div>
      <div className="mt-2.5 flex items-center justify-center gap-2">
        {[Mic, Video, MonitorUp, Hand].map((I, i) => <span key={i} className="grid size-8 place-items-center rounded-full bg-white/10 text-white/85"><I className="size-3.5" aria-hidden /></span>)}
        <span className="grid size-8 place-items-center rounded-full bg-[#b2362b] text-white"><PhoneOff className="size-3.5" aria-hidden /></span>
      </div>
    </Frame>
  );
}

export function SceneAfter() {
  const follow = [["Ward and patient informed", true], ["Pre-authorization documents prepared", true], ["Review at the six-week clinic", false]] as const;
  const log = [["14:32", "Decision recorded", "Dr L. Rao"], ["14:40", "Minutes exported", "P. Nair"], ["14:41", "Board deck downloaded", "P. Nair"]];
  return (
    <Frame title="After the Board · synthetic">
      <div className="grid gap-2 sm:grid-cols-2">
        <motion.div className="l-win l-mini p-3.5" variants={list} initial="hidden" animate="show">
          <motion.p variants={row} className="flex items-center gap-2 text-[13px] font-semibold"><FileText className="size-4 text-[#0a6a86]" aria-hidden />Minutes, Tuesday Board</motion.p>
          {["9 Case Files discussed; a decision recorded for each", "Present: 7 members and 1 external expert", "2 follow-up actions opened"].map((t) => <motion.p key={t} variants={row} className="mt-2 text-[var(--text-2)]">{t}</motion.p>)}
          <motion.div variants={row} className="mt-3 flex flex-wrap gap-1.5">
            <span className="l-chip l-chip-info"><Presentation className="size-3" aria-hidden />Board deck, .pptx</span>
            <span className="l-chip l-chip-info"><FileText className="size-3" aria-hidden />NCG VTB template</span>
          </motion.div>
        </motion.div>
        <motion.div className="l-win l-mini p-3.5" variants={list} initial="hidden" animate="show">
          <motion.p variants={row} className="text-[13px] font-semibold">Follow-up actions</motion.p>
          {follow.map(([t, done]) => (
            <motion.p key={t} variants={row} className="mt-2 flex items-center gap-2">
              <span className={cn("grid size-4 place-items-center rounded-full", done ? "bg-[#e4f4ea] text-[#1d6a44]" : "border border-[rgba(11,25,48,0.2)]")}>{done ? <Check className="size-2.5" strokeWidth={3} aria-hidden /> : null}</span>
              <span className={cn(done && "text-[var(--text-2)]")}>{t}</span>
            </motion.p>
          ))}
          <motion.p variants={row} className="mt-4 text-[13px] font-semibold">Audit log</motion.p>
          {log.map(([at, what, who]) => <motion.p key={at} variants={row} className="mt-1.5 flex gap-2 text-[11.5px] text-[var(--text-2)]"><span className="tabular-nums">{at}</span><span className="text-[var(--text)]">{what}</span><span className="ml-auto">{who}</span></motion.p>)}
        </motion.div>
      </div>
    </Frame>
  );
}
