// The meeting stage, the way a video call is laid out: a dark frame over the whole window, a thin top bar, the shared screen
// in the middle, the people beside it, panels that slide in from the right, and a round-button control bar at the bottom.
// The member view, the coordinator's conduct view and the room screen all build on these pieces.
import { useEffect, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Opened } from "@/lib/live";
import type { Slide } from "../types";
import { recordPageUrl, viewerSrc } from "../api";
import { SlideContent } from "./shared";
import { VaidyxIcon } from "@/components/Wordmark";
import { cn } from "@/lib/utils";

/** Marks the body while a stage covers it (the shell's Dock and scrolling stay out of the way). */
export function useStageLayer() {
  useEffect(() => {
    document.body.classList.add("tbnik-fullscreen");
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.classList.remove("tbnik-fullscreen"); document.body.style.overflow = prev; };
  }, []);
}

export function StageFrame({ children, className, testId, attrs }: { children: ReactNode; className?: string; testId?: string; attrs?: Record<string, string | undefined> }) {
  useStageLayer();
  return (
    <div className={cn("fixed inset-0 z-50 flex flex-col overflow-hidden bg-stage text-stage-fg", className)} data-theme="dark" data-testid={testId} {...attrs}>
      {children}
    </div>
  );
}

export function StageTopBar({ left, center, right, className }: { left?: ReactNode; center?: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex min-h-12 items-center gap-3 border-b border-stage-line px-3 py-1.5 lg:px-4", className)}>
      <div className="flex min-w-0 shrink-0 items-center gap-2.5">
        <VaidyxIcon tone="white" className="h-5 opacity-90" />
        {left}
      </div>
      <div className="min-w-0 flex-1">{center}</div>
      <div className="flex shrink-0 items-center gap-1.5">{right}</div>
    </header>
  );
}

/** A round control-bar button with its word under it; `tone` danger is the red Leave / End. */
export function BarButton({ icon: Icon, label, onClick, active, tone = "default", disabled, badge, title, testId, className }: {
  icon: LucideIcon; label: string; onClick?: () => void; active?: boolean; tone?: "default" | "danger" | "primary"; disabled?: boolean; badge?: number | string; title?: string; testId?: string; className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      aria-label={label}
      aria-pressed={active}
      data-testid={testId}
      className={cn("group flex min-w-16 flex-col items-center gap-1 outline-none disabled:opacity-40", className)}
    >
      <span className={cn(
        "relative grid size-11 place-items-center rounded-full transition-[background-color,transform] duration-150 group-active:scale-95 group-focus-visible:ring-2 group-focus-visible:ring-primary",
        tone === "danger" ? "bg-[#d64545] text-white hover:bg-[#c23b3b]" : tone === "primary" ? "bg-primary text-primary-foreground hover:bg-primary-hover" : active ? "bg-stage-fg text-stage" : "bg-stage-raised text-stage-fg hover:bg-[#232d38]",
      )}>
        <Icon className="size-5" aria-hidden />
        {badge ? <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-primary px-1.5 text-center text-[11px] font-bold leading-5 text-primary-foreground">{badge}</span> : null}
      </span>
      <span className="whitespace-nowrap text-[11px] font-medium leading-none text-stage-muted group-hover:text-stage-fg">{label}</span>
    </button>
  );
}

export function ControlBar({ children, className, left, right }: { children: ReactNode; className?: string; left?: ReactNode; right?: ReactNode }) {
  return (
    <footer className={cn("flex min-h-[4.5rem] items-center gap-2 border-t border-stage-line px-3 py-2", className)}>
      <div className="hidden min-w-0 flex-1 items-center gap-2 lg:flex">{left}</div>
      <div className="flex flex-1 items-center justify-center gap-1 sm:gap-2 lg:flex-none">{children}</div>
      <div className="hidden min-w-0 flex-1 items-center justify-end gap-2 lg:flex">{right}</div>
    </footer>
  );
}

/** A panel that slides in at the right of the stage (people, questions, the decision). */
export function StagePanel({ open, title, onClose, children, width = "w-[22rem]", testId, actions }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode; width?: string; testId?: string; actions?: ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.aside
          key="panel"
          initial={{ x: 32, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 32, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className={cn("flex h-full min-h-0 shrink-0 flex-col rounded-xl border border-stage-line bg-stage-panel", width)}
          data-testid={testId}
          aria-label={typeof title === "string" ? title : undefined}
        >
          <header className="flex items-center gap-2 border-b border-stage-line px-3 py-2">
            <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-stage-fg">{title}</h2>
            {actions}
            <button type="button" onClick={onClose} className="rounded-full p-1.5 text-stage-muted hover:bg-stage-raised hover:text-stage-fg" aria-label="Close the panel"><X className="size-4" /></button>
          </header>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}

/** What the room shows: the image viewer, a record page, a slide, or a waiting word. */
export function SharedScreen({ cid, opened, slide, empty, big, children, className, label }: {
  cid: string | null; opened: Opened | null | undefined; slide: Slide | null; empty: string; big?: boolean; children?: ReactNode; className?: string; label?: ReactNode;
}) {
  const viewer = opened?.kind === "images" ? viewerSrc(opened) : null;
  return (
    <section className={cn("relative min-h-0 flex-1 overflow-hidden rounded-xl border border-stage-line bg-stage-panel", className)} aria-label="Shared screen" data-testid="shared-screen" data-opened={opened?.kind ?? "slide"}>
      <AnimatePresence mode="wait" initial={false}>
        {viewer ? (
          <motion.iframe key={`img-${viewer}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} title={`Image viewer${opened?.title ? `: ${opened.title}` : ""}`} src={viewer} className="absolute inset-0 h-full w-full bg-black" allow="fullscreen" />
        ) : opened?.kind === "record" && opened.doc_id && cid ? (
          <motion.div key={`rec-${opened.doc_id}-${opened.page ?? 0}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="scroll-thin absolute inset-0 overflow-auto bg-[#1a1f26] p-3">
            {opened.title ? <p className="sticky top-0 z-10 mb-2 inline-block rounded-md bg-stage-raised/90 px-2 py-1 text-sm font-medium text-stage-fg shadow">{opened.title}</p> : null}
            <img src={recordPageUrl(cid, opened.doc_id, opened.page ?? 0)} alt={`${opened.title ?? "Record"}, page ${(opened.page ?? 0) + 1}`} className="mx-auto h-auto max-w-full rounded-md bg-white" />
          </motion.div>
        ) : slide ? (
          <motion.div key={`slide-${slide.id}`} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22 }} className={cn("scroll-thin absolute inset-0 overflow-y-auto stage-slide", big ? "p-6 lg:p-8" : "p-4 lg:p-5")}>
            <SlideContent slide={slide} big={big} />
          </motion.div>
        ) : (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 grid place-items-center p-6 text-center">
            <p className={cn("text-stage-muted", big ? "text-2xl" : "text-base")}>{empty}</p>
          </motion.div>
        )}
      </AnimatePresence>
      {label ? <div className="pointer-events-none absolute right-3 top-3 z-10 flex items-center gap-2 [&>*]:pointer-events-auto">{label}</div> : null}
      {children}
    </section>
  );
}

/** The dots under the shared screen: which slide is on. */
export function SlideDots({ slides, index, className }: { slides: Slide[]; index: number; className?: string }) {
  if (slides.length < 2) return null;
  return (
    <ol className={cn("flex items-center gap-1", className)} aria-label="Slides">
      {slides.map((x, i) => <li key={x.id} className={cn("h-1.5 rounded-full transition-all", i === index ? "w-6 bg-primary" : "w-2 bg-stage-line")} aria-current={i === index ? "true" : undefined} title={x.title} />)}
    </ol>
  );
}

/** The live decision strip: what the coordinator is typing, then "saved" for a moment. */
export function DecisionStrip({ text, saved, big, className }: { text: string; saved: boolean; big?: boolean; className?: string }) {
  if (!text && !saved) return null;
  return (
    <div className={cn("flex items-start gap-3 rounded-xl border px-4 py-2", saved ? "border-ok/60 bg-ok/10" : "border-warn/50 bg-warn/10", className)} role="status" aria-live="polite" data-testid="decision-strip" data-saved={saved ? "true" : "false"}>
      <span className={cn("mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold", saved ? "bg-ok text-white" : "bg-warn text-white")}>{saved ? "Decision saved" : "Decision, not saved yet"}</span>
      <p className={cn("min-w-0 leading-snug text-stage-fg", big ? "text-xl" : "text-sm")}>{saved ? "The decision was read back and saved." : text}</p>
    </div>
  );
}
