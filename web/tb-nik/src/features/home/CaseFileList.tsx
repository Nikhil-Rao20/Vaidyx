// The Case File list newest first (GET /case-list) with the search box, filter chips, saved filters and rows.
// The filter set lives in the URL (?status=ready) so a pinned view or a link lands on the same list.
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchBox } from "@/components/SearchBox";
import { FilterChips } from "@/components/FilterChips";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { notify } from "@/components/Toasts";
import { CaseRow } from "@/features/home/CaseRow";
import { useCaseList } from "@/hooks/useQueries";
import { useSavedFilters } from "@/hooks/useProfile";
import { useDebounce } from "@/hooks/useDebounce";
import type { Me } from "@/lib/session";
import type { CaseListItem, FilterOption } from "@/lib/types";
import { activeKeys, applyFilters, parseQuery, sortNewest, toSearchParams, type FilterQuery } from "@/lib/filters";
import { errorMessage } from "@/hooks/useAsyncAction";

export interface ListCounts { all: number; ready: number; waiting: number }

export function CaseFileList({ me, canCreate, onCount }: { me: Me; canCreate: boolean; onCount?: (n: ListCounts) => void }) {
  const [params, setParams] = useSearchParams();
  const query = useMemo(() => parseQuery(params), [params]);
  const [text, setText] = useState(query.q ?? "");
  const q = useDebounce(text, 250);
  useEffect(() => { if ((query.q ?? "") !== q) setQuery({ ...query, q: q || undefined }); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if ((query.q ?? "") !== text && !text && query.q) setText(query.q); }, [query.q]); // eslint-disable-line react-hooks/exhaustive-deps

  const setQuery = (next: FilterQuery) => {
    const sp = toSearchParams(next);
    setParams(sp, { replace: true });
  };

  // The server filters when it can; the same matches run here so chips react at once.
  const serverQuery = useMemo(() => ({ ...query, q: undefined }), [query]);
  const list = useCaseList(serverQuery);
  const allCases = useMemo(() => sortNewest(list.data?.cases ?? []), [list.data]);
  const shown = useMemo(() => applyFilters(allCases, query, me.user), [allCases, query, me.user]);
  const serverFiltered = activeKeys(serverQuery).length > 0;
  // The counts drive the gift box and the coordinator's ready card: only an unfiltered list tells the truth about them.
  useEffect(() => {
    if (!serverFiltered && list.data) onCount?.({ all: allCases.length, ready: allCases.filter((c) => c.status?.key === "ready").length, waiting: allCases.filter((c) => c.status?.key === "waiting_department").length });
  }, [allCases, onCount, serverFiltered, list.data]);

  const organs = useMemo<FilterOption[]>(() => {
    const m = new Map<string, string>();
    for (const c of allCases) if (c.protocol) m.set(c.protocol, c.protocol_label || c.protocol);
    return [...m.entries()].map(([id, label]) => ({ id, label }));
  }, [allCases]);
  const owners = useMemo<FilterOption[]>(() => {
    const m = new Map<string, string>();
    for (const c of allCases) if (c.owner?.doctor) m.set(c.owner.doctor, c.owner.doctor_name || c.owner.doctor);
    return [...m.entries()].map(([id, label]) => ({ id, label }));
  }, [allCases]);

  const saved = useSavedFilters();
  const pinnedNow = saved.pinned(query);
  const filtersOn = activeKeys(query).length > 0;
  const hasAny = allCases.length > 0;

  return (
    <section id="cases" aria-label="Case Files" className="scroll-mt-20">
      <div className="mb-3 flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <SearchBox value={text} onChange={setText} loading={list.isFetching && Boolean(text)} placeholder="Patient name, UHID, cancer, doctor" wrapperClassName="flex-1" />
        </div>
        <FilterChips
          query={query}
          onChange={setQuery}
          filters={list.data?.filters}
          organs={organs}
          owners={owners}
          saved={saved.list}
          pinnedName={pinnedNow?.name ?? null}
          onPin={async (name) => { try { await saved.pin(name, query); notify.success("Pinned to your home", name); } catch (e) { notify.error("Could not pin", errorMessage(e)); } }}
          onUnpin={async (name) => { try { await saved.unpin(name); notify.success("Unpinned", name); } catch (e) { notify.error("Could not unpin", errorMessage(e)); } }}
          hideMine={!(me.roles.treating || []).length}
        />
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
        renderRow={(c) => <CaseRow c={c} />}
        empty={
          hasAny || filtersOn || query.q ? (
            <EmptyState kind="search" title="No Case File matches" text="Try fewer filters or another word." action={<Button type="button" variant="outline" size="sm" onClick={() => { setText(""); setQuery({}); }}>Clear filters</Button>} />
          ) : (
            <EmptyState kind="empty" title="No Case Files yet" text={canCreate ? "Start with one UHID: Vaidyx fetches the records and shows what is missing for the board." : "When a treating doctor adds you to a Case File, it appears here."} action={canCreate ? <Button type="button" asChild><Link to="/cases/new"><Plus className="size-4" aria-hidden /> New Case File</Link></Button> : undefined} />
          )
        }
        footer={shown.length && list.data ? <p className="pt-2 text-center text-xs text-muted-foreground">{shown.length === allCases.length ? `${allCases.length} Case Files, newest first` : `${shown.length} of ${allCases.length} Case Files`}</p> : null}
      />
    </section>
  );
}
