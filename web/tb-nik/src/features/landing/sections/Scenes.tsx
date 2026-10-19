// The three screens of "How it works", built from the product's own shapes with synthetic data: a Case File filling itself,
// the meeting, and what happens after. Each plays its small sequence when it appears.
import { motion, useReducedMotion, type Variants } from "motion/react";
import { Check, Clock3, FileText, Hand, Mic, MonitorUp, PhoneOff, Presentation, Video } from "lucide-react";
import { cn } from "@/lib/utils";

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

export function SceneBefore() {
  const reduce = useReducedMotion();
  const rows = [
    { t: "Histopathology report", s: "3 values, each quoted", k: "ok" },
    { t: "Staging imaging, CT chest and abdomen", s: "as recorded, on the PACS", k: "ok" },
    { t: "IHC panel (ER, PR, HER2)", s: "requested from Pathology", k: "warn", later: { s: "received, 3 values quoted", k: "ok" } },
    { t: "Clinical note with performance status", s: "ECOG 1, quoted", k: "ok" },
    { t: "The question for the board", s: "written by the treating doctor", k: "ok" },
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
                  <motion.span className="l-chip l-chip-warn absolute right-0" initial={{ opacity: 1 }} animate={reduce ? { opacity: 0 } : { opacity: 0 }} transition={{ delay: reduce ? 0 : 2.4, duration: 0.3 }}>Pathology</motion.span>
                  <motion.span className="l-chip l-chip-ok absolute right-0" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: reduce ? 0 : 2.6, duration: 0.35 }}>Received</motion.span>
                </span>
              ) : null}
            </motion.li>
          ))}
        </motion.ul>
      </div>
      <motion.div className="mt-2.5 grid grid-cols-3 gap-2" variants={list} initial="hidden" animate="show">
        {[["Radiology brief", "ready", "ok"], ["Pathology brief", "preparing", "info"], ["Medical Oncology brief", "ready", "ok"]].map(([t, s, k]) => (
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

export function SceneDuring() {
  const reduce = useReducedMotion();
  const people = [["LR", "Dr Lakshmi Rao", true], ["IK", "Dr Iqbal Khan", false], ["PN", "Priya Nair", false], ["TJ", "Dr Thomas Joseph", false]] as const;
  return (
    <Frame title="Meeting · Tuesday board · Case File 4 of 9 · synthetic">
      <div className="grid grid-cols-[1.45fr_1fr] gap-2">
        <div className="l-win-ink relative aspect-[4/3] overflow-hidden">
          <div className="absolute inset-0" style={{ background: "radial-gradient(60% 70% at 50% 55%, #2a3340 0%, #141a21 60%, #0f1720 100%)" }} aria-hidden />
          <motion.div className="absolute left-1/2 top-1/2 size-[62%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/15" style={{ background: "radial-gradient(circle, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.03) 45%, transparent 70%)" }} animate={reduce ? undefined : { scale: [1, 1.03, 1] }} transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }} aria-hidden />
          <span className="absolute left-2.5 top-2.5 rounded-md bg-black/40 px-2 py-1 text-[10.5px] font-medium text-white/80">Room screen · CT chest · from the PACS</span>
          <span className="absolute bottom-2.5 left-2.5 text-[10px] text-white/50">Shown to people. No model reads it.</span>
        </div>
        <motion.div className="grid grid-rows-4 gap-2" variants={list} initial="hidden" animate="show">
          {people.map(([ini, name, speaking], i) => (
            <motion.div key={ini} variants={row} className={cn("l-win-ink relative flex items-center gap-2 px-2.5", speaking && "ring-2 ring-[var(--mint)]")}>
              <span className="grid size-7 place-items-center rounded-full text-[10px] font-semibold text-white" style={{ background: `linear-gradient(135deg, ${["#0b4e74", "#5b3fc4", "#01b4c2", "#1d6a44"][i]}, #0a1630)` }}>{ini}</span>
              <span className="truncate text-[11px] text-white/85">{name}</span>
              {speaking ? <motion.span className="ml-auto size-1.5 rounded-full bg-[var(--mint)]" animate={reduce ? undefined : { scale: [1, 1.6, 1] }} transition={{ duration: 1.1, repeat: Infinity }} aria-hidden /> : null}
              {i === 2 ? <Hand className="ml-auto size-3.5 text-[#f0b45c]" aria-hidden /> : null}
            </motion.div>
          ))}
        </motion.div>
      </div>
      <motion.div className="l-win l-mini mt-2 flex items-center gap-2.5 px-3 py-2.5" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.1, duration: 0.5 }}>
        <span className="l-chip l-chip-ok"><Check className="size-3" strokeWidth={3} aria-hidden />Decision recorded</span>
        <span className="truncate text-[var(--text-2)]">14:32 · 6 present · 1 question answered · minutes updating</span>
      </motion.div>
      <div className="mt-2.5 flex items-center justify-center gap-2">
        {[Mic, Video, MonitorUp, Hand].map((I, i) => <span key={i} className="grid size-8 place-items-center rounded-full bg-white/10 text-white/85"><I className="size-3.5" aria-hidden /></span>)}
        <span className="grid size-8 place-items-center rounded-full bg-[#b2362b] text-white"><PhoneOff className="size-3.5" aria-hidden /></span>
      </div>
    </Frame>
  );
}

export function SceneAfter() {
  const follow = [["Inform the ward and the patient", true], ["Pre-authorization documents ready", true], ["Review at the 6-week clinic", false]] as const;
  const log = [["14:32", "Decision recorded", "Dr L. Rao"], ["14:40", "Minutes exported", "P. Nair"], ["14:41", "Board deck downloaded", "P. Nair"]];
  return (
    <Frame title="After the board · synthetic">
      <div className="grid gap-2 sm:grid-cols-2">
        <motion.div className="l-win l-mini p-3.5" variants={list} initial="hidden" animate="show">
          <motion.p variants={row} className="flex items-center gap-2 text-[13px] font-semibold"><FileText className="size-4 text-[#0a6a86]" aria-hidden />Minutes, Tuesday board</motion.p>
          {["9 Case Files discussed, a decision recorded for each", "Present: 7 members, 1 outside expert", "2 follow-ups opened"].map((t) => <motion.p key={t} variants={row} className="mt-2 text-[var(--text-2)]">{t}</motion.p>)}
          <motion.div variants={row} className="mt-3 flex flex-wrap gap-1.5">
            <span className="l-chip l-chip-info"><Presentation className="size-3" aria-hidden />Board deck, .pptx</span>
            <span className="l-chip l-chip-info"><FileText className="size-3" aria-hidden />NCG VTB template</span>
          </motion.div>
        </motion.div>
        <motion.div className="l-win l-mini p-3.5" variants={list} initial="hidden" animate="show">
          <motion.p variants={row} className="text-[13px] font-semibold">Follow-ups</motion.p>
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
