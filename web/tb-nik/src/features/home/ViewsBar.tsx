// The views of the Case File list: the built-in ones (All, Mine, Needs me, Waiting, Ready, On the agenda, Decided) with their
// counts, then the person's saved views. The active view carries a pill that glides; a custom set of filters shows as "Custom".
import { motion } from "motion/react";
import { Bookmark, X } from "lucide-react";
import type { SavedFilter } from "@/lib/types";
import { VIEWS, sameQuery, type FilterQuery } from "@/lib/filters";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

function strip(q: FilterQuery): FilterQuery {
  const { q: _q, ...rest } = q; // eslint-disable-line @typescript-eslint/no-unused-vars
  return rest;
}

export function ViewsBar({ query, onChange, counts, saved, onRemoveSaved }: {
  query: FilterQuery;
  onChange: (q: FilterQuery) => void;
  counts: Record<string, number>;
  saved: SavedFilter[];
  onRemoveSaved?: (name: string) => void;
}) {
  const cur = strip(query);
  const items = [
    ...VIEWS.map((v) => ({ id: v.id, label: v.label, hint: v.hint, query: v.query, count: counts[v.id], saved: false })),
    ...saved.map((s) => ({ id: `saved:${s.name}`, label: s.name, hint: "A view of your own", query: s.query as FilterQuery, count: counts[`saved:${s.name}`], saved: true })),
  ];
  const activeId = items.find((it) => sameQuery(it.query, cur))?.id ?? (Object.keys(cur).length ? "custom" : "all");
  return (
    <div className="scroll-thin -mx-1 flex items-center gap-0.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Views">
      {items.map((it) => {
        const active = it.id === activeId;
        return (
          <span key={it.id} className="group relative shrink-0">
            <button
              type="button"
              role="tab"
              aria-selected={active}
              title={it.hint}
              onClick={() => onChange({ ...it.query, q: query.q })}
              className={cn("relative inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", active ? "text-foreground" : "text-muted-foreground hover:text-foreground", it.saved && onRemoveSaved && "pr-7")}
            >
              {active ? <motion.span layoutId="views-pill" className="absolute inset-0 rounded-full bg-secondary" transition={spring} aria-hidden /> : null}
              {it.saved ? <Bookmark className="relative size-3.5" aria-hidden /> : null}
              <span className="relative">{it.label}</span>
              {typeof it.count === "number" ? <span className={cn("relative rounded-full px-1.5 text-[11px] tabular-nums leading-4", active ? "bg-card text-foreground" : "bg-muted text-muted-foreground")}>{it.count}</span> : null}
            </button>
            {it.saved && onRemoveSaved ? (
              <button type="button" onClick={() => onRemoveSaved(it.label)} className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-primary/20 hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100" aria-label={`Remove the view ${it.label}`}>
                <X className="size-3" aria-hidden />
              </button>
            ) : null}
          </span>
        );
      })}
      {activeId === "custom" ? (
        <span className="relative inline-flex h-8 shrink-0 items-center rounded-full px-3 text-[13px] font-medium text-foreground">
          <motion.span layoutId="views-pill" className="absolute inset-0 rounded-full bg-secondary" transition={spring} aria-hidden />
          <span className="relative">Custom</span>
        </span>
      ) : null}
    </div>
  );
}
