// The Case File list: the views (All, Mine, Needs me, ...), the search, the filter panel, the sort, the active filter tokens
// and the rows. The whole list comes once from GET /case-list and every match runs here, so the search and the filters react
// as the person types; the query lives in the URL (?status=ready&q=...) so a link or a saved view lands on the same list.
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpDown, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SearchBox } from "@/components/SearchBox";
import { FilterButton, ActiveFilters } from "@/components/FilterPanel";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { notify } from "@/components/Toasts";
import { CaseRow } from "@/features/home/CaseRow";
import { ViewsBar } from "@/features/home/ViewsBar";
import { useCaseList } from "@/hooks/useQueries";
import { useSavedFilters } from "@/hooks/useProfile";
import { useDebounce } from "@/hooks/useDebounce";
import type { Me } from "@/lib/session";
import type { CaseListItem, FilterOption } from "@/lib/types";
import { SORT_CHOICES, VIEWS, activeKeys, applyFilters, isLinkedOnly, linkedLast, ownRows, parseQuery, sortCases, toSearchParams, type FilterQuery, type SortKey } from "@/lib/filters";
import { errorMessage } from "@/hooks/useAsyncAction";

export interface ListCounts { all: number; ready: number; waiting: number }

export function CaseFileList({ me, canCreate, onCount }: { me: Me; canCreate: boolean; onCount?: (n: ListCounts) => void }) {
  const [params, setParams] = useSearchParams();
  const query = useMemo(() => parseQuery(params), [params]);
  const sort = (params.get("sort") as SortKey) || "newest";
  const [text, setText] = useState(query.q ?? "");
  const q = useDebounce(text, 120);
  useEffect(() => { if ((query.q ?? "") !== q) setQuery({ ...query, q: q || undefined }); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if ((query.q ?? "") !== text && !text && query.q) setText(query.q); }, [query.q]); // eslint-disable-line react-hooks/exhaustive-deps

  const setQuery = (next: FilterQuery) => {
    const sp = toSearchParams(next);
    if (sort !== "newest") sp.set("sort", sort);
    setParams(sp, { replace: true });
  };
  const setSort = (s: SortKey) => {
    const sp = toSearchParams(query);
    if (s !== "newest") sp.set("sort", s);
    setParams(sp, { replace: true });
  };

  const list = useCaseList({});
  const allCases = useMemo(() => list.data?.cases ?? [], [list.data]);
  // Another department's Case File linked to one of this department's own (night-v3 item 1.3) is listed last, under its own heading,
  // and left out of every count: the views, the footer, the gift box and the coordinator's card count the person's own files only.
  const ownCases = useMemo(() => ownRows(allCases), [allCases]);
  const shown = useMemo(() => linkedLast(sortCases(applyFilters(allCases, query, me.user), sort)), [allCases, query, me.user, sort]);
  const ownShown = useMemo(() => ownRows(shown).length, [shown]);
  const firstLinked = useMemo(() => shown.find(isLinkedOnly)?.case_id, [shown]);
  const saved = useSavedFilters();
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const v of VIEWS) out[v.id] = applyFilters(ownCases, v.query, me.user).length;
    for (const s of saved.list) out[`saved:${s.name}`] = applyFilters(ownCases, s.query as FilterQuery, me.user).length;
    return out;
  }, [ownCases, saved.list, me.user]);
  // The counts drive the gift box and the coordinator's ready card.
  useEffect(() => {
    if (list.data) onCount?.({ all: ownCases.length, ready: ownCases.filter((c) => c.status?.key === "ready").length, waiting: ownCases.filter((c) => c.status?.key === "waiting_department").length });
  }, [ownCases, onCount, list.data]);

  const organs = useMemo<FilterOption[]>(() => {
    const m = new Map<string, string>();
    for (const c of allCases) if (c.protocol) m.set(c.protocol, c.protocol_label || c.protocol);
    return [...m.entries()].map(([id, label]) => ({ id, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [allCases]);
  const owners = useMemo<FilterOption[]>(() => {
    const m = new Map<string, string>();
    for (const c of allCases) if (c.owner?.doctor) m.set(c.owner.doctor, c.owner.doctor_name || c.owner.doctor);
    return [...m.entries()].map(([id, label]) => ({ id, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [allCases]);

  const filtersOn = activeKeys(query).length > 0;
  const hasAny = allCases.length > 0;
  const treating = (me.roles.treating || []).length > 0;
  const coordinator = Boolean(me.roles.coordinator);

  return (
    <section id="cases" aria-label="Case Files" className="scroll-mt-20">
      <div className="mb-3 flex flex-col gap-2.5">
        <ViewsBar
          query={query}
          onChange={setQuery}
          counts={counts}
          saved={saved.list}
          onRemoveSaved={async (name) => { try { await saved.unpin(name); notify.success("View removed", name); } catch (e) { notify.error("Could not remove the view", errorMessage(e)); } }}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchBox value={text} onChange={setText} placeholder="Search a patient, UHID, OP or IP number, accession, cancer, doctor" wrapperClassName="flex-1" />
          <div className="flex items-center gap-2">
            <FilterButton
              query={query}
              onChange={setQuery}
              filters={list.data?.filters}
              organs={organs}
              owners={owners}
              showDepartment={coordinator || !treating}
              showMine={treating}
              onSave={async (name, qq) => { try { await saved.pin(name, qq); notify.success("View saved", name); } catch (e) { notify.error("Could not save the view", errorMessage(e)); } }}
            />
            <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
              <SelectTrigger className="h-10 w-[11.5rem] gap-1.5" aria-label="Sort"><ArrowUpDown className="size-4 text-muted-foreground" aria-hidden /><SelectValue /></SelectTrigger>
              <SelectContent align="end">
                {SORT_CHOICES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <ActiveFilters query={query} onChange={setQuery} filters={list.data?.filters} />
      </div>
      <p className="sr-only" aria-live="polite">{list.data ? `${shown.length} Case Files shown` : ""}</p>
      <DataList<CaseListItem>
        items={shown}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        retrying={list.isFetching}
        what="the Case File list"
        keyFor={(c) => c.case_id}
        renderRow={(c) => (
          <>
            {c.case_id === firstLinked ? <h2 className="mb-1.5 pt-3 text-sm font-semibold text-muted-foreground">Linked Case Files of other departments</h2> : null}
            <CaseRow c={c} q={query.q || ""} showOwner={!treating || coordinator || !c.mine} />
          </>
        )}
        empty={
          hasAny || filtersOn || query.q ? (
            <EmptyState kind="search" title={query.q ? `Nothing matches "${query.q}"` : "No Case File matches these filters"} text={query.q ? "Try a part of the UHID, the OP or IP number, or the patient's name." : "Take a filter off, or choose another view."} action={<Button type="button" variant="outline" size="sm" onClick={() => { setText(""); setQuery({}); }}>Show all</Button>} />
          ) : (
            <EmptyState kind="empty" title="No Case Files yet" text={canCreate ? "Start with one UHID: Vaidyx fetches the records and shows what is missing for the board." : "When a treating doctor adds you to a Case File, it appears here."} action={canCreate ? <Button asChild><Link to="/cases/new"><Plus className="size-4" aria-hidden /> New Case File</Link></Button> : undefined} />
          )
        }
        footer={shown.length && list.data ? <p className="pt-2 text-center text-xs text-muted-foreground">{ownShown === ownCases.length ? `${ownCases.length} Case Files` : `${ownShown} of ${ownCases.length} Case Files`}{shown.length > ownShown ? `, and ${shown.length - ownShown} linked of other departments` : ""}. Cancer and setting as recorded by the treating doctor.</p> : null}
      />
    </section>
  );
}
