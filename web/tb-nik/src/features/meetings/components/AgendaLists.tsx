// The agenda: For discussion and For noting, in the coordinator's order (drag to reorder, keyboard too), Not ready folded.
import { createContext, useContext, useState } from "react";
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Link } from "react-router-dom";
import { ArrowDownToLine, ArrowUpToLine, Bell, ChevronDown, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { AgendaRow } from "@/lib/live";
import { StatusChip } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { drName } from "@/lib/format";

/** The Case File the coordinator has just added (night-v3 1.11): its row is ringed for a few seconds so the add is seen in the page. */
export const JustAddedContext = createContext<string | null>(null);

export function AgendaRowView({ r, canManage, onRemind, remindBusy, dragHandle, moveLabel, onMove, current, decided }: {
  r: AgendaRow; canManage: boolean; onRemind?: (cid: string) => void; remindBusy?: boolean; dragHandle?: React.ReactNode; moveLabel?: string; onMove?: () => void; current?: boolean; decided?: boolean;
}) {
  const left = r.left_before_board;
  const justAdded = useContext(JustAddedContext) === r.case_id;
  return (
    <div className={cn("flex items-start gap-2 rounded-md border px-2 py-2 text-sm bg-card transition-[box-shadow,border-color,background-color] duration-500", current ? "border-primary ring-2 ring-primary/30" : justAdded ? "border-ok bg-ok-soft ring-2 ring-ok/40" : "border-border")} data-testid="agenda-row" data-case-id={r.case_id} data-just-added={justAdded || undefined}>
      {dragHandle}
      <div className="min-w-0 flex-1">
        <p className="font-medium text-foreground truncate"><Link className="hover:underline underline-offset-2" to={`/cases/${r.case_id}`}>{r.patient_line || r.case_id}</Link>{r.missing ? <span className="ml-1 text-xs text-bad">(Case File not found)</span> : null}</p>
        <p className="text-xs text-muted-foreground truncate">{[r.owner_name ? `owner ${r.owner_name}` : null, r.presenter_name && !r.presenter ? `presenter ${r.presenter_name}` : null].filter(Boolean).join(", ")}</p>
        {r.board_question ? <p className="text-xs text-foreground mt-0.5 line-clamp-2">{r.board_question}</p> : <p className="text-xs text-warn mt-0.5">board question not written</p>}
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {decided || r.decided || r.outcome ? <StatusChip kind="ok">{r.outcome_label ?? (r.outcome ? r.outcome.replace(/_/g, " ") : "decided")}</StatusChip> : left == null ? <StatusChip kind="muted">not checked yet</StatusChip> : left > 0 ? <StatusChip kind="warn">{left} left</StatusChip> : <StatusChip kind="ok">nothing left</StatusChip>}
          {r.ready === false && !r.outcome ? <StatusChip kind="muted">not marked ready</StatusChip> : null}
          {justAdded ? <StatusChip kind="ok">added just now</StatusChip> : null}
          {r.presenter?.name ? <StatusChip kind="muted">Presenter {drName(r.presenter.name)}</StatusChip> : null}
          {r.added_after_send ? <StatusChip kind="review">added after the agenda was sent</StatusChip> : null}
          {typeof r.minutes === "number" ? <span className="text-xs text-muted-foreground">{r.minutes} min</span> : null}
          {r.reason ? <span className="text-xs text-muted-foreground">{r.reason}</span> : null}
        </div>
      </div>
      <div className="flex flex-col gap-1 shrink-0">
        {canManage && onRemind ? <Button size="xs" variant="outline" onClick={() => onRemind(r.case_id)} disabled={remindBusy} aria-label={`Remind the owner of ${r.patient_line}`}><Bell className="size-3" />Remind</Button> : null}
        {canManage && onMove ? <Button size="xs" variant="ghost" onClick={onMove} aria-label={moveLabel}>{moveLabel?.startsWith("To noting") ? <ArrowDownToLine className="size-3" /> : <ArrowUpToLine className="size-3" />}{moveLabel}</Button> : null}
      </div>
    </div>
  );
}

function SortableRow({ r, canManage, onRemind, remindBusy, moveLabel, onMove, current }: { r: AgendaRow; canManage: boolean; onRemind?: (cid: string) => void; remindBusy?: boolean; moveLabel: string; onMove: () => void; current?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: r.case_id, disabled: !canManage });
  const style: React.CSSProperties = { transform: transform ? `translate3d(${Math.round(transform.x)}px, ${Math.round(transform.y)}px, 0)` : undefined, transition, opacity: isDragging ? 0.6 : 1 };
  return (
    <li ref={setNodeRef} style={style}>
      <AgendaRowView r={r} canManage={canManage} onRemind={onRemind} remindBusy={remindBusy} moveLabel={moveLabel} onMove={onMove} current={current}
        dragHandle={canManage ? <button type="button" className="mt-0.5 cursor-grab touch-none rounded p-0.5 text-muted-foreground hover:bg-muted active:cursor-grabbing" aria-label={`Reorder ${r.patient_line}`} {...attributes} {...listeners}><GripVertical className="size-4" /></button> : null} />
    </li>
  );
}

function SortableList({ title, rows, canManage, onReorder, onRemind, remindBusy, moveLabel, onMove, currentId, emptyText }: {
  title: string; rows: AgendaRow[]; canManage: boolean; onReorder: (ids: string[]) => void; onRemind?: (cid: string) => void; remindBusy?: boolean; moveLabel: string; onMove: (cid: string) => void; currentId?: string | null; emptyText: string;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const ids = rows.map((r) => r.case_id);
  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = ids.indexOf(String(active.id)); const to = ids.indexOf(String(over.id));
    if (from < 0 || to < 0) return;
    onReorder(arrayMove(ids, from, to));
  };
  return (
    <section className="surface p-3" aria-label={title}>
      <h2 className="text-base mb-2">{title} <span className="text-sm font-normal text-muted-foreground">({rows.length})</span></h2>
      {rows.length === 0 ? <p className="text-sm text-muted-foreground">{emptyText}</p> : null}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <ol className="space-y-1.5">
            {rows.map((r) => <SortableRow key={r.case_id} r={r} canManage={canManage} onRemind={onRemind} remindBusy={remindBusy} moveLabel={moveLabel} onMove={() => onMove(r.case_id)} current={currentId === r.case_id} />)}
          </ol>
        </SortableContext>
      </DndContext>
      {canManage && rows.length > 1 ? <p className="mt-2 text-xs text-muted-foreground">Drag the handle to reorder, or focus it and use the arrow keys.</p> : null}
    </section>
  );
}

export function AgendaLists({ agenda, canManage, onChange, onRemind, remindBusy, currentId, onAddFromNotReady }: {
  agenda: { discussion: AgendaRow[]; noting: AgendaRow[]; not_ready: AgendaRow[] }; canManage: boolean;
  onChange: (discussion: string[], noting: string[]) => void; onRemind?: (cid: string) => void; remindBusy?: boolean; currentId?: string | null;
  onAddFromNotReady?: (cid: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const d = agenda.discussion.map((r) => r.case_id); const n = agenda.noting.map((r) => r.case_id);
  return (
    <div className="space-y-3" data-testid="agenda-lists">
      <SortableList title="For discussion" rows={agenda.discussion} canManage={canManage} onReorder={(ids) => onChange(ids, n)} onRemind={onRemind} remindBusy={remindBusy} moveLabel="To noting" onMove={(cid) => onChange(d.filter((x) => x !== cid), [...n, cid])} currentId={currentId} emptyText="No Case File for discussion yet. Case Files marked ready appear here." />
      <SortableList title="For noting" rows={agenda.noting} canManage={canManage} onReorder={(ids) => onChange(d, ids)} onRemind={onRemind} remindBusy={remindBusy} moveLabel="To discussion" onMove={(cid) => onChange([...d, cid], n.filter((x) => x !== cid))} currentId={currentId} emptyText="Nothing to note." />
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted" aria-expanded={open}>
            <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />Not ready ({agenda.not_ready.length})
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ol className="mt-1 space-y-1.5 pl-1" data-testid="not-ready-list">
            {agenda.not_ready.length === 0 ? <li className="text-xs text-muted-foreground px-2">Every listed Case File is ready.</li> : null}
            {agenda.not_ready.map((r) => <li key={r.case_id}><AgendaRowView r={r} canManage={canManage} onRemind={onRemind} remindBusy={remindBusy} moveLabel={onAddFromNotReady ? "To discussion" : undefined} onMove={onAddFromNotReady ? () => onAddFromNotReady(r.case_id) : undefined} /></li>)}
          </ol>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
