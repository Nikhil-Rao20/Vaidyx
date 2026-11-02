// Published cases: the doctor approves the search words, picks results, and each saved paper shows authors, journal,
// year, link, peer-reviewed or not, and verbatim quotes labelled "Published case, not advice for this patient".
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ExternalLink, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { consultantTitle } from "@/lib/format";
import { addPublished, getPublished, notBuiltYet, removePublished, searchPublished } from "../api";
import type { PublishedResult } from "../types";
import { EmptyState, ErrorState, LoadingButton, NotYetState, SkeletonLines, StatusChip, errorText, fmtDateTime } from "./common";

const LABEL = "Published case, not advice for this patient";

function Paper({ p, action }: { p: PublishedResult; action?: React.ReactNode }) {
  return (
    <li className="rounded-md border border-border p-3 space-y-1" data-testid="published-item">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{p.title}</p>
          <p className="text-xs text-muted-foreground">{[p.authors, p.journal, p.year].filter(Boolean).join(", ")}</p>
        </div>
        {action}
      </div>
      <div className="flex flex-wrap gap-1">
        <StatusChip kind="muted">{LABEL}</StatusChip>
        {p.peer_reviewed ? <StatusChip kind="ok">peer-reviewed</StatusChip> : <StatusChip kind="warn">not peer-reviewed</StatusChip>}
        {p.kind && p.kind !== "paper" ? <StatusChip kind="info">{p.kind.replace(/_/g, " ")}</StatusChip> : null}
        {p.source ? <StatusChip kind="info">{p.source === "europepmc" ? "Europe PMC" : p.source === "pubmed" ? "PubMed" : "local library"}</StatusChip> : null}
      </div>
      {p.url || p.doi ? <a className="text-xs text-link underline inline-flex items-center gap-1" href={p.url ?? `https://doi.org/${p.doi}`} target="_blank" rel="noopener noreferrer">Open the paper <ExternalLink className="size-3" aria-hidden /></a> : null}
      {(p.quotes ?? []).length ? (
        <ul className="space-y-1 mt-1">
          {p.quotes!.map((q, i) => <li key={i} className="text-sm border-l-2 border-border pl-2"><span className="text-foreground">{q.text}</span> <span className="text-xs text-muted-foreground">({q.where})</span></li>)}
        </ul>
      ) : null}
      {p.added_by || p.at ? <p className="text-xs text-muted-foreground">added by {p.by_name ?? p.added_by_name ?? p.added_by}{p.at ? `, ${fmtDateTime(p.at)}` : ""}</p> : null}
    </li>
  );
}

export function PublishedPanel({ caseId, resident, consultantName, onPropose }: { caseId: string; resident: boolean; consultantName: string; onPropose: (payload: Record<string, unknown>, label: string) => Promise<void> }) {
  const qc = useQueryClient();
  const [terms, setTerms] = useState("");
  const [results, setResults] = useState<PublishedResult[] | null>(null);
  const [searchErr, setSearchErr] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["published", caseId], queryFn: () => getPublished(caseId), retry: false });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const search = useMutation({
    mutationFn: (t: string) => searchPublished(caseId, t),
    onSuccess: (r) => { setResults(r.results ?? []); setSearchErr(r.error ?? null); void qc.invalidateQueries({ queryKey: ["published", caseId] }); },
    onError: (e) => { setResults([]); setSearchErr(errorText(e)); },
  });
  const add = useMutation({
    mutationFn: async (r: PublishedResult) => { if (resident) { await onPropose({ result: r }, `Add published case: ${r.title}`); return; } await addPublished(caseId, r); },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["published", caseId] }),
  });
  const del = useMutation({ mutationFn: (pid: string) => removePublished(caseId, pid), onSuccess: () => void qc.invalidateQueries({ queryKey: ["published", caseId] }) });
  if (notBuilt) return <NotYetState what="Published cases" fallback="Searching the local library and PubMed comes with the published route." />;
  const items = q.data?.items ?? [];
  const have = new Set(items.map((i) => i.doi ?? i.url ?? i.title));
  return (
    <div className="space-y-3" data-testid="published-panel">
      <p className="text-sm text-muted-foreground flex items-start gap-1.5"><BookOpen className="size-4 mt-0.5 shrink-0" aria-hidden />Papers you choose, shown with their own words. Vaidyx never applies them to this patient.</p>
      <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); if (terms.trim().length >= 3) search.mutate(terms.trim()); }}>
        <label htmlFor="pub-terms" className="sr-only">Search words (diagnosis words only)</label>
        <Input id="pub-terms" value={terms} onChange={(e) => setTerms(e.target.value)} placeholder="Search words, for example: rectal adenocarcinoma total neoadjuvant" className="h-9 text-sm" maxLength={200} />
        <LoadingButton type="submit" size="sm" loading={search.isPending} loadingText="Searching" disabled={terms.trim().length < 3}><Search className="size-4" />Search</LoadingButton>
      </form>
      <p className="text-xs text-muted-foreground">Only the words you type are sent (to the local library first, then PubMed or Europe PMC). The search is logged.</p>
      {(q.data?.searches ?? []).length ? (
        <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-1">Earlier searches:
          {Array.from(new Set(q.data!.searches.map((x) => (typeof x === "string" ? x : x.terms)).filter(Boolean))).slice(-5).reverse().map((t) => (
            <button key={t} type="button" className="rounded-md border border-border px-1.5 py-0.5 hover:bg-muted active:scale-95 transition" onClick={() => { setTerms(t); search.mutate(t); }} disabled={search.isPending} title="Search again with these words">{t}</button>
          ))}
        </p>
      ) : null}
      {searchErr ? <p role="alert" className="text-xs text-bad">{searchErr}</p> : null}
      {results ? (
        <section>
          <h3 className="text-sm font-semibold text-foreground">Results</h3>
          {results.length === 0 ? <EmptyState kind="search" title="No papers found" text="Try different words, or fewer of them." className="py-4" /> : null}
          <ul className="mt-1 space-y-2">
            {results.map((r, i) => (
              <Paper key={i} p={r} action={have.has(r.doi ?? r.url ?? r.title) ? <StatusChip kind="ok">added</StatusChip> : <LoadingButton size="xs" loading={add.isPending && add.variables === r} onClick={() => add.mutate(r)}><Plus className="size-3" />{resident ? `Ask ${consultantTitle(consultantName)}` : "Add"}</LoadingButton>} />
            ))}
          </ul>
          {add.isError ? <p role="alert" className="text-xs text-bad mt-1">{errorText(add.error)}</p> : null}
        </section>
      ) : null}
      <section>
        <h3 className="text-sm font-semibold text-foreground">On this Case File</h3>
        {q.isLoading ? <SkeletonLines n={3} /> : null}
        {q.isError ? <ErrorState error={q.error} retry={() => void q.refetch()} compact /> : null}
        {!q.isLoading && items.length === 0 ? <p className="text-xs text-muted-foreground mt-1">No published cases added yet.</p> : null}
        <ul className="mt-1 space-y-2">
          {items.map((p) => <Paper key={p.id ?? p.title} p={p} action={!resident && p.id ? <Button size="icon-xs" variant="ghost" aria-label={`Remove ${p.title}`} onClick={() => del.mutate(p.id!)} disabled={del.isPending}><Trash2 className="size-3" /></Button> : undefined} />)}
        </ul>
      </section>
    </div>
  );
}
