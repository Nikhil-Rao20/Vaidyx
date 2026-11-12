// Customisable for your hospital (12 Nov): six things a hospital sets for itself, as tabs (a column on a laptop, a row that
// scrolls sideways on a phone) beside a panel that looks like the settings. The level switch and the PM-JAY switch work: the
// checklist tab follows the level, as the real rule does (an Optimal record counts only at an Optimal hospital). Nothing is
// saved or sent anywhere. Tabs follow the ARIA pattern: arrow keys, Home and End move and select.
import { useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bot, Building2, CalendarDays, Check, ImageIcon, ListChecks, Lock, Minus, PlugZap, Users, type LucideIcon } from "lucide-react";
import { CUSTOM } from "../content.pillars";
import { SectionHead } from "../components/SectionHead";
import { Reveal } from "../components/Reveal";

type Key = (typeof CUSTOM.tabs)[number]["key"];
type Level = (typeof CUSTOM.hospital.level.options)[number]["key"];
const ICON: Record<Key, LucideIcon> = { hospital: Building2, departments: Users, checklists: ListChecks, agents: Bot, systems: PlugZap, meetings: CalendarDays };
const TIER_CHIP: Record<string, string> = { a: "l-chip-ok", b: "l-chip-info", c: "l-chip-warn" };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="l-set-row"><span className="l-set-label">{label}</span><span className="l-set-value">{children}</span></div>;
}

function LevelSwitch({ level, setLevel, label }: { level: Level; setLevel: (l: Level) => void; label: string }) {
  return (
    <span className="l-seg" role="group" aria-label={label}>
      {CUSTOM.hospital.level.options.map((o) => <button key={o.key} type="button" aria-pressed={level === o.key} onClick={() => setLevel(o.key)} data-testid={`custom-level-${o.key}`}>{o.label}</button>)}
    </span>
  );
}

function Tags({ label, items, on }: { label: string; items: readonly string[]; on?: boolean }) {
  return (
    <div>
      <p className="l-faint text-[11.5px] font-semibold uppercase tracking-[0.1em]">{label}</p>
      <ul className="mt-2 flex flex-wrap gap-1.5">{items.map((t) => <li key={t} className="l-tag" data-on={on ? "true" : undefined}>{t}</li>)}</ul>
    </div>
  );
}

function Panel({ tab, level, setLevel, pmjay, setPmjay }: { tab: Key; level: Level; setLevel: (l: Level) => void; pmjay: boolean; setPmjay: (v: boolean) => void }) {
  if (tab === "hospital") {
    const H = CUSTOM.hospital;
    return (
      <div>
        <Row label={H.name.label}>{H.name.value}</Row>
        <Row label={H.logo.label}><span className="inline-flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg bg-[var(--l-accent-bg)] text-[var(--l-accent)]"><ImageIcon className="size-4" aria-hidden /></span>{H.logo.value}</span></Row>
        <Row label={H.level.label}><LevelSwitch level={level} setLevel={setLevel} label={H.level.label} /></Row>
        <div className="l-set-row">
          <span className="min-w-0"><span className="l-set-label block" id="custom-pmjay-label">{H.pmjay.label}</span><span className="l-faint block text-[12.5px]" data-testid="custom-pmjay-note">{pmjay ? H.pmjay.on : H.pmjay.off}</span></span>
          <button type="button" role="switch" aria-checked={pmjay} aria-labelledby="custom-pmjay-label" className="l-switch" onClick={() => setPmjay(!pmjay)} data-testid="custom-pmjay" />
        </div>
        <Row label={H.window.label}>{H.window.value}</Row>
      </div>
    );
  }
  if (tab === "departments") {
    const P = CUSTOM.departments;
    return (
      <div className="space-y-5">
        <Tags label={P.treating.label} items={P.treating.items} on />
        <Tags label={P.supporting.label} items={P.supporting.items} on />
        <p className="l-faint -mt-2 text-[12.5px]">{P.more}</p>
        <div className="border-t border-[var(--l-line)] pt-4">
          <Tags label={P.rolesLabel} items={P.roles} />
          <ul className="mt-4">
            {P.people.map((x) => (
              <li key={x.name} className="l-set-row !py-2.5"><span className="text-[14.5px] font-semibold">{x.name}</span><span className="l-set-label text-right">{x.role}</span></li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
  if (tab === "checklists") {
    const L = CUSTOM.checklists;
    const needed = (t: string) => t === "a" || (t === "b" && level === "optimal");
    return (
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--l-line)] pb-3.5">
          <p className="text-[1.05rem] font-semibold tracking-[-0.01em]">{L.cancer} <span className="l-faint ml-1.5 text-[12.5px] font-medium">{L.count}</span></p>
          <span className="inline-flex items-center gap-2.5"><span className="l-set-label">{L.levelLabel}</span><LevelSwitch level={level} setLevel={setLevel} label={L.levelLabel} /></span>
        </div>
        <ul>
          {L.rows.map((r) => {
            const ok = needed(r.tier);
            return (
              <li key={r.label} className="l-check-row" data-needed={ok ? "true" : "false"} data-testid="custom-check-row">
                <span className="l-check-dot" aria-hidden>{ok ? <Check className="size-3.5" strokeWidth={2.6} /> : <Minus className="size-3.5" />}</span>
                <span className="min-w-0"><span className="l-check-label block text-[14.5px] font-medium">{r.label}</span><span className="l-faint block text-[12.5px]">{r.dept} · {ok ? L.needed : L.notNeeded}</span></span>
                <span className={`l-chip ${TIER_CHIP[r.tier]}`}>{L.tiers[r.tier as keyof typeof L.tiers]}</span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }
  if (tab === "agents") {
    const A = CUSTOM.agents;
    return (
      <div className="space-y-5">
        <ul className="flex flex-wrap gap-1.5">{A.roles.map((r, i) => <li key={r} className="l-tag" data-on={i === 0 ? "true" : undefined}><Bot className="size-3.5" aria-hidden />{r}</li>)}</ul>
        <div className="l-box px-4 py-3.5">
          <p className="text-[13.5px] font-semibold">{A.skillOf}</p>
          <ul className="l-muted mt-2 space-y-1 text-[14px]">{A.focus.map((f) => <li key={f} className="flex gap-2.5"><span className="mt-[0.6em] size-1 shrink-0 rounded-full bg-[var(--l-accent)]" aria-hidden />{f}</li>)}</ul>
        </div>
        <div>
          <p className="l-faint flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.1em]"><Lock className="size-3" aria-hidden />{A.fixedLabel}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">{A.fixed.map((f) => <li key={f} className="l-chip l-chip-review !px-2.5 !py-1 !text-[12px] !whitespace-normal">{f}</li>)}</ul>
        </div>
      </div>
    );
  }
  if (tab === "systems") {
    const S = CUSTOM.systems;
    return (
      <div className="space-y-4">
        {[S.his, S.pacs].map((x) => (
          <div key={x.label} className="l-box px-4 py-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[14.5px] font-semibold">{x.label}</p>
              <span className="flex flex-wrap gap-1.5"><span className="l-chip l-chip-info">{x.standard}</span><span className="l-chip l-chip-review">{x.mode}</span></span>
            </div>
            <p className="l-mono l-muted mt-2.5 rounded-lg border border-[var(--l-line)] bg-[var(--l-surface)] px-3 py-2">{x.address}</p>
            <p className="mt-2 flex items-center gap-2 text-[13px] text-[var(--l-ok)]"><span className="l-check-dot !size-[1.15rem]" aria-hidden><Check className="size-3" strokeWidth={2.6} /></span>{x.test}</p>
          </div>
        ))}
        <Tags label={S.ids.label} items={S.ids.items} />
      </div>
    );
  }
  const M = CUSTOM.meetings;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--l-line)] pb-4">
        <span className="l-chip l-chip-info !px-2.5 !py-1 !text-[12.5px]"><CalendarDays className="size-3.5" aria-hidden />{M.series}</span>
        <span className="flex items-center gap-1.5" aria-hidden>
          {M.days.map((d, i) => <span key={i} className="grid size-7 place-items-center rounded-full text-[11px] font-semibold" style={i === M.dayIndex ? { background: "var(--l-accent)", color: "var(--l-surface)" } : { background: "var(--l-surface-2)", color: "var(--l-fg-3)" }}>{d}</span>)}
        </span>
      </div>
      {M.rows.map((r) => <Row key={r.label} label={r.label}>{r.value}</Row>)}
      <Row label={M.coordinator.label}>{M.coordinator.value}</Row>
      <div className="border-t border-[var(--l-line)] pt-4"><Tags label={M.headsLabel} items={M.heads} /></div>
    </div>
  );
}

export function Customise() {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  const [level, setLevel] = useState<Level>("essential");
  const [pmjay, setPmjay] = useState(true);
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const tabs = CUSTOM.tabs;
  const tab = tabs[i];
  const body = CUSTOM[tab.key];
  const go = (k: number) => { const j = (k + tabs.length) % tabs.length; setI(j); refs.current[j]?.focus(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); go(i + 1); }
    else if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); go(i - 1); }
    else if (e.key === "Home") { e.preventDefault(); go(0); }
    else if (e.key === "End") { e.preventDefault(); go(tabs.length - 1); }
  };
  return (
    <section id="customise" className="l-section-2 relative overflow-hidden py-24 sm:py-32" data-testid="customise">
      <span className="l-orb l-orb-violet" style={{ width: 560, height: 560, right: "-10%", bottom: "-6%", opacity: 0.28 }} aria-hidden />
      <div className="relative mx-auto max-w-[1280px] px-5 sm:px-8">
        <SectionHead eyebrow={CUSTOM.eyebrow} title={[CUSTOM.title[0], CUSTOM.title[1]]} lead={CUSTOM.lead} />
        <Reveal y={20} className="mt-12 grid grid-cols-[minmax(0,1fr)] items-start gap-5 lg:mt-14 lg:grid-cols-[minmax(0,0.4fr)_minmax(0,0.6fr)] lg:gap-8">
          <div className="min-w-0">
            <div className="l-tabs" role="tablist" aria-label={CUSTOM.tabsLabel} onKeyDown={onKey}>
              {tabs.map((t, k) => {
                const I = ICON[t.key];
                return (
                  <button key={t.key} ref={(el) => { refs.current[k] = el; }} type="button" role="tab" id={`custom-tab-${t.key}`} aria-selected={k === i} aria-controls="custom-panel" tabIndex={k === i ? 0 : -1} className="l-tab" onClick={() => setI(k)} data-testid={`custom-tab-${t.key}`}>
                    <span className="l-tab-icon"><I className="size-[18px]" aria-hidden /></span>
                    <span className="min-w-0"><span className="block whitespace-nowrap text-[14.5px] font-semibold tracking-[-0.01em]">{t.label}</span><span className="l-tab-sub">{t.sub}</span></span>
                  </button>
                );
              })}
            </div>
            <p className="l-faint mt-4 hidden px-3 text-[12.5px] lg:block">{CUSTOM.hint}</p>
          </div>
          <div className="l-card min-w-0 overflow-hidden" role="tabpanel" id="custom-panel" aria-labelledby={`custom-tab-${tab.key}`} tabIndex={0} data-testid="custom-panel" data-tab={tab.key}>
            <div className="l-tile-tint flex items-center gap-3 border-b border-[var(--l-line)] px-5 py-4 sm:px-7">
              <span className="l-icon !h-10 !w-10 shrink-0">{(() => { const I = ICON[tab.key]; return <I className="size-5" aria-hidden />; })()}</span>
              <h3 className="l-title text-[1.3rem]">{body.title}</h3>
            </div>
            <div className="px-5 py-5 sm:px-7 sm:py-6 lg:min-h-[27.5rem]">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={tab.key} initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: -6, transition: { duration: 0.14 } }} transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}>
                  <p className="l-muted text-[15px]">{body.text}</p>
                  <div className="mt-5"><Panel tab={tab.key} level={level} setLevel={setLevel} pmjay={pmjay} setPmjay={setPmjay} /></div>
                </motion.div>
              </AnimatePresence>
            </div>
            <p className="l-faint border-t border-[var(--l-line)] px-5 py-3 text-[12px] sm:px-7">{CUSTOM.mock}</p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
