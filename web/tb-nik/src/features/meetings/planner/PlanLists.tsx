// The case list of the one-page planner (meetings-v2 3.3, owner D8 and D9): For discussion and For noting, filled by themselves in
// urgency order (5 first, then the time sent); the coordinator drags a row (or uses Up and Down, or the arrow keys on the handle) and the
// list keeps that order from then on, new Case Files going at its end marked New; "Put back in urgency order" undoes it. Each row: the
// patient, the cancer, the urgency, the presenter, Move to another meeting, Remove (with a reason), and a menu for the other list and a
// reminder. Not ready is folded below. Members read the same rows without the controls.
import { createContext, useContext, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { ArrowDown, ArrowDownToLine, ArrowUp, ArrowUpToLine, Bell, CalendarSync, ChevronDown, GripVertical, ListOrdered, ListPlus, MoreHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { UrgencyTag } from "@/components/UrgencyTag";
import { StatusChip } from "@/features/casefile/components/common";
import { drName, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ListKey, PlanRow, PlanState } from "./types";

/** The Case File just added (ringed for a few seconds so the add is seen in the page). */
export const JustAddedPlan = createContext<string | null>(null);

const TITLES: Record<ListKey, string> = { discussion: "For discussion", noting: "For noting" };
const OTHER: Record<ListKey, ListKey> = { discussion: "noting", noting: "discussion" };

export interface RowActions {
  onReorder: (list: ListKey, ids: string[], focus?: { cid: string; dir: "up" | "down" }) => void;
  onMove: (r: PlanRow) => void;
  onRemove: (r: PlanRow) => void;
  onOtherList: (r: PlanRow, from: ListKey) => void;
  onRemind?: (r: PlanRow) => void;
}

function RowName({ r }: { r: PlanRow }) {
  return (
    <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 pt-0.5">
      <Link className="min-w-0 break-words font-medium text-foreground hover:underline underline-offset-2" to={`/cases/${r.case_id}`}>{r.patient_line || r.case_id}</Link>
      {r.new ? <StatusChip kind="info" title="Added by itself after you arranged this list by hand">New</StatusChip> : null}
      {r.missing ? <span className="text-xs text-bad">(Case File not found)</span> : null}
    </p>
  );
}

function RowDetails({ r, cancer }: { r: PlanRow; cancer: string }) {
  const left = r.left_before_board;
  const presenter = r.presenter?.name ? drName(r.presenter.name) : r.presenter_name ? drName(r.presenter_name) : "";
  return (
    <>
      <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-body">
        <UrgencyTag level={r.urgency ?? null} size="sm" />
        {cancer ? <span className="font-medium">{cancer}</span> : null}
        <span>{presenter ? `Presenter ${presenter}` : "Presenter not chosen"}</span>
        {r.owner_department_name ? <span className="text-muted-foreground">{r.owner_department_name}</span> : null}
      </p>
      {r.board_question ? <p className="mt-1 line-clamp-2 text-sm text-foreground">{r.board_question}</p> : r.restricted ? null : <p className="mt-1 text-xs text-warn">The question for the board is not written yet</p>}
      <div className="mt-1 flex flex-wrap items-center gap-1 empty:hidden">
        {r.outcome || r.decided ? <StatusChip kind="ok">{r.outcome_label || (r.outcome ? r.outcome.replace(/_/g, " ") : "decided")}</StatusChip>
          : left == null ? null : left > 0 ? <StatusChip kind="warn">{left} still open</StatusChip> : <StatusChip kind="ok">nothing open</StatusChip>}
        {r.ready === false && !r.outcome ? <StatusChip kind="muted">not marked ready</StatusChip> : null}
        {r.added_after_send ? <StatusChip kind="review">added after the agenda was sent</StatusChip> : null}
        {r.new_since_sent ? <StatusChip kind="muted">{plural(r.new_since_sent, "new report")} since sent</StatusChip> : null}
        {r.waiting_on ? <StatusChip kind="warn">waiting on {r.waiting_on.name ? drName(r.waiting_on.name) : "the treating doctor"}</StatusChip> : null}
        {r.reason ? <span className="text-xs text-muted-foreground">{r.reason}</span> : null}
      </div>
    </>
  );
}

function RowCard({ r, index, ids, list, canManage, cancer, actions, handle }: {
  r: PlanRow; index: number; ids: string[]; list: ListKey; canManage: boolean; cancer: string; actions?: RowActions; handle?: ReactNode;
}) {
  const count = ids.length;
  const justAdded = useContext(JustAddedPlan) === r.case_id;
  const name = (r.patient_line || r.case_id).split(",")[0];
  return (
    // Laptop: the actions beside the patient's name, the details under both at full width. Phone: the actions in a row at the bottom.
    <div className={cn("grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 rounded-lg border bg-card px-2.5 py-2.5 text-sm transition-[box-shadow,border-color,background-color] duration-500 sm:grid-cols-[auto_minmax(0,1fr)_auto]",
      justAdded ? "border-ok bg-ok-soft ring-2 ring-ok/40" : r.new ? "border-primary/50" : "border-border")}
      data-testid="agenda-row" data-case-id={r.case_id} data-just-added={justAdded || undefined} data-new={r.new || undefined}>
      <div className="col-start-1 row-span-2 row-start-1 flex items-start gap-1 pt-1">
        {handle}
        <span className="w-5 text-right text-sm font-semibold tabular-nums text-muted-foreground" aria-hidden>{index + 1}</span>
      </div>
      <div className="col-start-2 row-start-1 min-w-0"><RowName r={r} /></div>
      <div className="col-start-2 row-start-2 min-w-0 sm:col-span-2"><RowDetails r={r} cancer={cancer} /></div>
      {canManage && actions ? (
        <div className="col-span-2 row-start-3 mt-2 flex flex-wrap items-center gap-0.5 border-t border-border pt-2 sm:col-span-1 sm:col-start-3 sm:row-start-1 sm:mt-0 sm:-mr-1 sm:-mt-1 sm:flex-nowrap sm:border-0 sm:pt-0" data-testid="row-actions">
          <Button size="icon-sm" variant="ghost" disabled={index === 0} onClick={() => actions.onReorder(list, arrayMove(ids, index, index - 1), { cid: r.case_id, dir: "up" })}
            aria-label={`Move ${name} up`} title="Move up" data-reorder={`${r.case_id}-up`}><ArrowUp className="size-4" /></Button>
          <Button size="icon-sm" variant="ghost" disabled={index === count - 1} onClick={() => actions.onReorder(list, arrayMove(ids, index, index + 1), { cid: r.case_id, dir: "down" })}
            aria-label={`Move ${name} down`} title="Move down" data-reorder={`${r.case_id}-down`}><ArrowDown className="size-4" /></Button>
          <span className="flex-1 sm:hidden" />
          <Button size="sm" variant="ghost" onClick={() => actions.onMove(r)} aria-label={`Move ${name} to another meeting`} data-testid="row-move"><CalendarSync className="size-4" />Move</Button>
          <Button size="sm" variant="ghost" className="text-bad hover:text-bad" onClick={() => actions.onRemove(r)} aria-label={`Remove ${name} from this meeting`} data-testid="row-remove"><X className="size-4" />Remove</Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon-sm" variant="ghost" aria-label={`More for ${name}`} data-testid="row-more"><MoreHorizontal className="size-4" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuItem onSelect={() => actions.onOtherList(r, list)} data-testid="row-other-list">
                {list === "discussion" ? <ArrowDownToLine className="size-4" /> : <ArrowUpToLine className="size-4" />}Put in {TITLES[OTHER[list]]}
              </DropdownMenuItem>
              {actions.onRemind ? <DropdownMenuItem onSelect={() => actions.onRemind?.(r)}><Bell className="size-4" />Remind the treating team</DropdownMenuItem> : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : null}
    </div>
  );
}

function SortableRow(p: { r: PlanRow; index: number; ids: string[]; list: ListKey; canManage: boolean; cancer: string; actions?: RowActions }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: p.r.case_id, disabled: !p.canManage });
  const style: React.CSSProperties = { transform: transform ? `translate3d(${Math.round(transform.x)}px, ${Math.round(transform.y)}px, 0)` : undefined, transition, opacity: isDragging ? 0.65 : 1, position: "relative", zIndex: isDragging ? 5 : undefined };
  const name = (p.r.patient_line || p.r.case_id).split(",")[0];
  return (
    <li ref={setNodeRef} style={style}>
      <RowCard {...p} handle={p.canManage ? (
        <button type="button" className="cursor-grab touch-none rounded p-0.5 text-muted-foreground hover:bg-muted active:cursor-grabbing" aria-label={`Drag ${name} to reorder (or focus here and use the arrow keys)`} data-testid="drag-handle" {...attributes} {...listeners}>
          <GripVertical className="size-4" />
        </button>
      ) : null} />
    </li>
  );
}

function PlanList({ list, rows, order, canManage, cancer, actions, onUrgency, urgencyBusy }: {
  list: ListKey; rows: PlanRow[]; order: "urgency" | "hand"; canManage: boolean; cancer: (p?: string | null) => string; actions?: RowActions;
  onUrgency?: () => void; urgencyBusy?: boolean;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const ids = rows.map((r) => r.case_id);
  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id || !actions) return;
    const from = ids.indexOf(String(active.id)); const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    actions.onReorder(list, arrayMove(ids, from, to));
  };
  return (
    <section className="surface p-3 sm:p-4" aria-labelledby={`list-${list}`} data-testid={`list-${list}`} data-order={order}>
      <div className="mb-2 flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-[15rem] flex-1">
          <h2 id={`list-${list}`} className="text-base">{TITLES[list]} <span className="text-sm font-normal text-muted-foreground">({rows.length})</span></h2>
          <p className="text-xs text-muted-foreground" data-testid={`order-${list}`}>
            {order === "hand" ? "In your order. Case Files sent later go at the end, marked New." : "Most urgent first, then the earliest sent."}
          </p>
        </div>
        {canManage && order === "hand" && onUrgency ? (
          <Button size="sm" variant="outline" onClick={onUrgency} disabled={urgencyBusy} data-testid={`urgency-order-${list}`}><ListOrdered className="size-4" />Put back in urgency order</Button>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
          {list === "discussion" ? "No Case File for discussion yet. Case Files sent to the board come here by themselves." : "Nothing to note."}
        </p>
      ) : null}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <ol className="space-y-2">
            {rows.map((r, i) => <SortableRow key={r.case_id} r={r} index={i} ids={ids} list={list} canManage={canManage} cancer={cancer(r.protocol)} actions={actions} />)}
          </ol>
        </SortableContext>
      </DndContext>
    </section>
  );
}

export function PlanLists({ state, canManage, cancer, actions, onUrgency, urgencyBusy, onAdd, onToDiscussion, onRemind, footer }: {
  state: PlanState; canManage: boolean; cancer: (p?: string | null) => string; actions?: RowActions;
  onUrgency?: (list: ListKey) => void; urgencyBusy?: boolean; onAdd?: () => void;
  /** A Case File of the Not ready list put on For discussion. */
  onToDiscussion?: (cid: string) => void; onRemind?: (r: PlanRow) => void; footer?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const nr = state.agenda.not_ready;
  return (
    <div className="space-y-3" data-testid="agenda-lists">
      {(["discussion", "noting"] as const).map((k) => (
        <PlanList key={k} list={k} rows={state.agenda[k]} order={state.agenda_order?.[k] === "hand" ? "hand" : "urgency"} canManage={canManage} cancer={cancer} actions={actions}
          onUrgency={onUrgency ? () => onUrgency(k) : undefined} urgencyBusy={urgencyBusy} />
      ))}
      {canManage && onAdd ? <Button variant="outline" onClick={onAdd} data-testid="add-case" className="w-full sm:w-auto"><ListPlus className="size-4" />Add a Case File</Button> : null}
      {nr.length ? (
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <button type="button" className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted" aria-expanded={open} data-testid="not-ready-toggle">
              <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />Not ready ({nr.length})
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ol className="mt-1 space-y-2" data-testid="not-ready-list">
              {nr.map((r, i) => (
                <li key={r.case_id} className="space-y-1">
                  <RowCard r={r} index={i} ids={nr.map((x) => x.case_id)} list="discussion" canManage={false} cancer={cancer(r.protocol)} />
                  {canManage ? (
                    <div className="flex flex-wrap justify-end gap-1">
                      {onRemind ? <Button size="sm" variant="ghost" onClick={() => onRemind(r)}><Bell className="size-4" />Remind the treating team</Button> : null}
                      {onToDiscussion ? <Button size="sm" variant="outline" onClick={() => onToDiscussion(r.case_id)}><ArrowUpToLine className="size-4" />Put in For discussion</Button> : null}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
      {footer}
    </div>
  );
}
