// The slide titles as tabs above the stage (research/04 sections 6.2 and 6.3). A member clicks a tab to look on their own (steps
// away); the chip "Stepped away: back to the room's screen" follows the room again. The coordinator's tabs change what the room sees,
// with "Records and images" opening the Case panel and "Back to the slide" while a record or the images are open.
import type { KeyboardEvent } from "react";
import { Footprints, Images, MonitorCheck, MonitorOff } from "lucide-react";
import { useCall } from "./context";
import { cn } from "@/lib/utils";

export function StageTabs({ className }: { className?: string }) {
  const c = useCall();
  if (c.variant === "room") return null;
  const coordinator = c.variant === "coordinator" && c.canManage;
  const openedItem = c.opened && c.opened.kind !== "none" ? c.opened : null;
  const selected = openedItem ? -1 : c.shownSlide;
  const slides = c.slides;
  const pick = (i: number) => {
    if (coordinator) { if (c.cid) void c.actions.go(c.cid, i).catch(() => {}); return; }
    c.showSlide(i);
  };
  const stepAway = () => c.showSlide(Math.min(slides.length - 1, c.sharedSlide + 1 < slides.length ? c.sharedSlide + 1 : Math.max(0, c.sharedSlide - 1)));
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const tabs = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("[role=tab]"));
    const at = tabs.findIndex((t) => t === document.activeElement);
    if (at < 0) return;
    e.preventDefault();
    tabs[(at + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]?.focus();
  };

  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)} data-testid="stage-tabs">
      {slides.length ? (
        <div role="tablist" aria-label={coordinator ? "What the room sees" : "Slides of this case"} className="scroll-thin flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto" onKeyDown={onKey}>
          {slides.map((s, i) => {
            const on = selected === i;
            const shared = c.sharedSlide === i && !openedItem;
            return (
              <button key={s.id} type="button" role="tab" aria-selected={on} tabIndex={on || (selected < 0 && i === 0) ? 0 : -1} onClick={() => pick(i)}
                title={coordinator ? `Show "${s.title}" to the room` : shared ? `${s.title}: on the room's screen` : `Look at "${s.title}" on your own`}
                className={cn("relative shrink-0 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary", on ? "bg-stage-raised text-stage-fg" : "text-stage-muted hover:bg-stage-raised/60 hover:text-stage-fg")}>
                {s.title}
                {!coordinator && shared && !on ? <span className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-primary/70" aria-hidden /> : null}
                {!coordinator && shared ? <span className="sr-only"> (on the room's screen)</span> : null}
              </button>
            );
          })}
        </div>
      ) : <p className="min-w-0 flex-1 truncate text-xs text-stage-muted">{c.cid ? (c.slidesStatus === "loading" ? "Loading the slides" : c.slidesStatus === "error" ? "The slides could not be loaded" : "No slides for this case") : "No case on the screen yet"}</p>}

      {coordinator ? (
        <>
          {openedItem ? <button type="button" onClick={() => void c.actions.open("none").catch(() => {})} className="inline-flex shrink-0 items-center gap-1 rounded-md border border-stage-line px-2 py-1 text-xs text-stage-fg outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary" data-testid="back-to-slide"><MonitorOff className="size-3.5" aria-hidden />Back to the slide</button> : null}
          <button type="button" onClick={() => c.togglePanel("case")} aria-pressed={c.panel === "case"} disabled={!c.cid} className="inline-flex shrink-0 items-center gap-1 rounded-md border border-stage-line px-2 py-1 text-xs text-stage-fg outline-none hover:bg-stage-raised focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40" data-testid="records-and-images"><Images className="size-3.5" aria-hidden />Records and images</button>
        </>
      ) : !c.following ? (
        <button type="button" onClick={() => c.setFollowing(true)} className="inline-flex shrink-0 items-center gap-1 rounded-full bg-warn/20 px-2.5 py-1 text-xs font-medium text-[#ffd48a] outline-none hover:bg-warn/30 focus-visible:ring-2 focus-visible:ring-primary" data-testid="back-to-shared" title="Follow the room's screen again"><MonitorCheck className="size-3.5" aria-hidden />Stepped away: back to the room's screen</button>
      ) : slides.length > 1 ? (
        <button type="button" onClick={stepAway} className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-stage-muted outline-none hover:bg-stage-raised hover:text-stage-fg focus-visible:ring-2 focus-visible:ring-primary" data-testid="step-away" title="Look at the other slides on your own"><Footprints className="size-3.5" aria-hidden />Step away</button>
      ) : null}
    </div>
  );
}
