// The New message finder: a dialog over GET /directory (placed hospital staff and the MDT Coordinator only). Choosing someone
// opens the existing conversation with them when there is one, else the composer against them (/messages/new?...).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Users } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SearchBox } from "@/components/SearchBox";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { RowSkeleton } from "@/components/DataList";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { plural } from "@/lib/format";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { useConversations, useDebounced, useDirectory } from "@/features/messages/hooks";
import { PersonAvatar } from "@/features/messages/parts";
import { usePresence } from "@/features/messages/useMessagesLive";
import type { ConversationRow, DirectoryDepartment, DirectoryPerson } from "@/features/messages/types";

export type Pick = { to: string } | { dept: string } | { coordinator: true };

/** The conversation I already have with this target (direct: the pair; department and coordinator: the one I started). */
export function existingConversation(rows: ConversationRow[] | undefined, me: string, pick: Pick): ConversationRow | undefined {
  if (!rows) return undefined;
  if ("to" in pick) return rows.find((r) => r.kind === "direct" && r.with?.user === pick.to);
  if ("dept" in pick) return rows.find((r) => r.kind === "department" && r.department?.id === pick.dept && r.created_by === me);
  return rows.find((r) => r.kind === "coordinator" && r.created_by === me);
}

/** Where a choice goes: the existing conversation, else /messages/new with the target (and the Case File, when given). */
export function pickPath(rows: ConversationRow[] | undefined, me: string, pick: Pick, caseId?: string): string {
  const found = existingConversation(rows, me, pick);
  const c = caseId ? `case=${encodeURIComponent(caseId)}` : "";
  if (found) return `/messages/${encodeURIComponent(found.id)}${c ? `?${c}` : ""}`;
  const t = "to" in pick ? `to=${encodeURIComponent(pick.to)}` : "dept" in pick ? `dept=${encodeURIComponent(pick.dept)}` : "coordinator=1";
  return `/messages/new?${t}${c ? `&${c}` : ""}`;
}

const rowCls = "surface-inner row-lift flex min-h-12 w-full items-center gap-3 px-3 py-2 text-left outline-none hover:border-tint-line focus-visible:ring-2 focus-visible:ring-ring";

function PersonRow({ p, onPick }: { p: DirectoryPerson; onPick: () => void }) {
  const presence = usePresence(p.user, p.online);
  const depts = p.departments.map((d) => `${d.name}${d.role ? ` (${d.role})` : ""}`).join(", ");
  return (
    <button type="button" onClick={onPick} className={rowCls} data-testid="directory-person" data-user={p.user}>
      <PersonAvatar name={p.display_name} photo={p.photo} presence={presence} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{p.display_name}</span>
        <span className="block truncate text-xs text-muted-foreground">
          {[...new Set([p.title, depts, p.coordinator ? "MDT Coordinator" : ""].filter(Boolean))].join(", ")}
        </span>
      </span>
    </button>
  );
}

function DepartmentRow({ d, onPick }: { d: DirectoryDepartment; onPick: () => void }) {
  return (
    <button type="button" onClick={onPick} className={rowCls} data-testid="directory-department" data-department={d.id}>
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground" aria-hidden><Building2 className="size-4" /></span>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{d.name}, {plural(d.members, "person", "people")}</span>
    </button>
  );
}

export function DirectoryPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { me } = useSession();
  const desktop = useIsDesktop();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const dir = useDirectory(dq, open);
  const list = useConversations("all", "", open);
  const meUser = dir.data?.me ?? me?.user ?? "";
  const people = (dir.data?.people ?? []).filter((p) => p.user !== meUser);
  const departments = dir.data?.departments ?? [];
  const coordinators = (dir.data?.coordinators ?? []).filter((p) => p.user !== meUser);
  const iAmCoordinator = !!me?.roles.coordinator;
  const words = q.trim().toLowerCase();
  const showCoordinator = coordinators.length > 0 && !iAmCoordinator && (!words || ["mdt coordinator", "coordinator"].some((w) => w.startsWith(words)));

  const choose = (pick: Pick) => {
    onOpenChange(false);
    setQ("");
    navigate(pickPath(list.data?.conversations, meUser, pick));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="directory-picker"
        className={cn("flex flex-col gap-3", desktop ? "max-h-[85dvh] sm:max-w-lg" : "h-dvh max-h-dvh w-full max-w-none rounded-none border-0 p-4 pt-5 sm:max-w-none")}>
        <DialogHeader className="text-left">
          <DialogTitle>New message</DialogTitle>
          <DialogDescription>To a colleague, a department or the MDT Coordinator of this hospital.</DialogDescription>
        </DialogHeader>
        <SearchBox value={q} onChange={setQ} label="Find a person or a department" placeholder="Find a person or a department" loading={dir.isFetching && !!q} autoFocus={desktop} />
        <div className="scroll-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 pb-1">
          {dir.isLoading ? <div className="space-y-2"><RowSkeleton /><RowSkeleton /><RowSkeleton /></div>
            : dir.error ? <ErrorState error={dir.error} what="the directory" onRetry={() => dir.refetch()} compact />
            : !people.length && !departments.length && !showCoordinator ? <EmptyState kind="search" compact title="No one found" text="No colleague or department matches these words." />
            : (
              <>
                {showCoordinator ? (
                  <section aria-label="MDT Coordinator" className="space-y-1.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">MDT Coordinator</h3>
                    <button type="button" onClick={() => choose({ coordinator: true })} className={rowCls} data-testid="directory-coordinator">
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground" aria-hidden><Users className="size-4" /></span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-foreground">MDT Coordinator</span>
                        <span className="block truncate text-xs text-muted-foreground">{coordinators.map((c) => c.display_name).join(", ")}</span>
                      </span>
                    </button>
                  </section>
                ) : null}
                {people.length ? (
                  <section aria-label="People" className="space-y-1.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">People</h3>
                    <ul className="space-y-1.5">{people.map((p) => <li key={p.user}><PersonRow p={p} onPick={() => choose({ to: p.user })} /></li>)}</ul>
                  </section>
                ) : null}
                {departments.length ? (
                  <section aria-label="Departments" className="space-y-1.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Departments</h3>
                    <ul className="space-y-1.5">{departments.map((d) => <li key={d.id}><DepartmentRow d={d} onPick={() => choose({ dept: d.id })} /></li>)}</ul>
                  </section>
                ) : null}
              </>
            )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
