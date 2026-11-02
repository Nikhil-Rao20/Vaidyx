// "Add a Case File": a dialog over GET /messages/links, which lists only the Case Files and meetings the sender may attach.
// A link grants nothing (section 9.4): each reader sees the chip as their own access allows.
import { useState } from "react";
import { CalendarDays, FolderOpen } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SearchBox } from "@/components/SearchBox";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { RowSkeleton } from "@/components/DataList";
import { useDebounced, useLinks } from "@/features/messages/hooks";
import type { LinkOption, PickedLink } from "@/features/messages/types";

export function LinkPicker({ open, onOpenChange, onPick }: { open: boolean; onOpenChange: (open: boolean) => void; onPick: (link: PickedLink) => void }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const links = useLinks(dq, open);
  const cases = links.data?.cases ?? [];
  const meetings = links.data?.meetings ?? [];
  const pick = (type: PickedLink["type"], o: LinkOption) => { onPick({ type, id: o.id, label: o.label }); onOpenChange(false); setQ(""); };

  const group = (title: string, type: PickedLink["type"], items: LinkOption[]) => items.length ? (
    <section aria-label={title} className="space-y-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      <ul className="space-y-1.5">
        {items.map((o) => {
          const Icon = type === "case" ? FolderOpen : CalendarDays;
          return (
            <li key={`${type}:${o.id}`}>
              <button type="button" onClick={() => pick(type, o)} data-testid="link-option"
                className="surface-inner row-lift flex min-h-11 w-full items-center gap-2.5 px-3 py-2 text-left text-sm outline-none hover:border-tint-line focus-visible:ring-2 focus-visible:ring-ring">
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  ) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85dvh] flex-col sm:max-w-md" data-testid="link-picker">
        <DialogHeader>
          <DialogTitle>Add a Case File</DialogTitle>
          <DialogDescription>Only the Case Files and meetings you can open are listed. Each reader sees it as their own access allows.</DialogDescription>
        </DialogHeader>
        <SearchBox value={q} onChange={setQ} label="Find a Case File or a meeting" placeholder="Find a Case File or a meeting" loading={links.isFetching && !!q} autoFocus />
        <div className="scroll-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 pb-1">
          {links.isLoading ? <div className="space-y-2"><RowSkeleton lines={1} /><RowSkeleton lines={1} /></div>
            : links.error ? <ErrorState error={links.error} what="the Case Files" onRetry={() => links.refetch()} compact />
            : !cases.length && !meetings.length ? <EmptyState kind="search" compact title="Nothing to attach" text={q ? "No Case File or meeting you can open matches these words." : "There is no Case File or meeting you can open yet."} />
            : <>{group("Case Files", "case", cases)}{group("Meetings", "meeting", meetings)}</>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
