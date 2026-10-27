// Similar Case Files (night-v3 item 7.3, owner decision D10; docs/night-v3/research/07_similar_cases.md 4.7, 4.10 and 8): past Case
// Files of this hospital that resemble this one, listed in the order Gemma-4-31B (non-medical) gives them, with lines quoted from the two
// files. Every card carries "Past Case File, not advice for this patient"; no number ranks a result. Opening a result asks the server
// first: a file the person may open opens at once (audited); otherwise the "Open with a reason" dialog opens with the reason written in
// (read only for 24 hours, the owner's consultants told), then the file opens. Mirrors PublishedPanel. ?item=similar (the Overview's
// card) brings this card into view.
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderSearch, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { getSimilar, notBuiltYet, openSimilar, searchSimilar } from "../api";
import type { SimilarResponse, SimilarResult } from "../types";
import { EmptyState, ErrorState, LoadingButton, NotYetState, SkeletonLines, StatusChip, errorText } from "./common";
import { OpenWithReasonButton } from "./OpenWithReason";
import { SIMILAR_LABEL, SimilarResultCard } from "./SimilarResultCard";

const FIRST = 5;
const REFUSED = "You cannot open this Case File.";

export function SimilarPanel({ caseId }: { caseId: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [address, setAddress] = useSearchParams();
  const box = useRef<HTMLDivElement>(null);
  const [words, setWords] = useState("");
  // The last answer is kept in the query cache, so it survives the page turning from the laptop to the phone layout (which mounts
  // the section again) and a visit to another section; it is not fetched again on its own (a search is logged and takes a while).
  const [res, setRes] = useState<SimilarResponse | null>(() => qc.getQueryData<SimilarResponse>(["similar-results", caseId]) ?? null);
  const [err, setErr] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [glass, setGlass] = useState<{ past: string; reason: string; via: string } | null>(null);
  const lastPast = useRef("");
  const q = useQuery({ queryKey: ["similar", caseId], queryFn: () => getSimilar(caseId), retry: false });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const search = useMutation({
    mutationFn: (w: string) => searchSimilar(caseId, w),
    onSuccess: (r) => { qc.setQueryData(["similar-results", caseId], r); setRes(r); setErr(null); setAll(false); setMessages({}); void qc.invalidateQueries({ queryKey: ["similar", caseId] }); },
    onError: (e) => { qc.removeQueries({ queryKey: ["similar-results", caseId] }); setRes(null); setErr(errorText(e)); },
  });

  // The Overview's "Similar Case Files" card opens the Summary with ?item=similar: bring this card into view, then drop the param.
  const asked = address.get("item") === "similar";
  useEffect(() => {
    if (!asked) return;
    const t = window.setTimeout(() => {
      box.current?.scrollIntoView({ block: "start" });
      const next = new URLSearchParams(address);
      next.delete("item");
      setAddress(next, { replace: true });
    }, 80);
    return () => window.clearTimeout(t);
  }, [asked]); // eslint-disable-line react-hooks/exhaustive-deps

  const say = (past: string, text: string) => setMessages((m) => ({ ...m, [past]: text }));
  const goTo = (past: string) => nav(`/cases/${encodeURIComponent(past)}/summary?from=similar&of=${encodeURIComponent(caseId)}`);
  const openFailed = (past: string, e: unknown) => say(past, e instanceof ApiError && e.status === 404 ? "This Case File is no longer in the list. Search again." : errorText(e));
  const openPast = async (past: string) => {
    setOpening(past);
    say(past, "");
    try {
      const o = await openSimilar(caseId, past);
      if (o.how === "normal") goTo(past);
      else if (o.how === "with_reason") {
        lastPast.current = past;
        setGlass({ past, reason: o.reason || `similar to Case File ${caseId}`, via: o.via || `similar:${caseId}` });
      } else say(past, REFUSED);
    } catch (e) {
      openFailed(past, e);
    } finally {
      setOpening(null);
    }
  };
  // The read-only window is open now: the server opens the file normally (and records it), then the page goes there.
  const afterWindow = async (past: string) => {
    try {
      const o = await openSimilar(caseId, past);
      if (o.how === "normal") goTo(past);
      else say(past, REFUSED);
    } catch (e) {
      openFailed(past, e);
    }
  };

  const card = (r: SimilarResult) => <SimilarResultCard key={r.case_id} r={r} opening={opening === r.case_id} message={messages[r.case_id] || null} onOpen={() => void openPast(r.case_id)} />;
  const earlier = Array.from(new Set((q.data?.searches ?? []).map((x) => (x.words ?? "").trim()).filter(Boolean))).slice(-5).reverse();
  const results = res?.results ?? [];
  const weaker = res?.weaker ?? [];
  const shown = all ? results : results.slice(0, FIRST);

  let body;
  if (notBuilt) body = <NotYetState what="Similar Case Files" fallback="Finding past Case Files of this hospital comes with the similar route." />;
  else if (q.isLoading) body = <SkeletonLines n={3} />;
  else if (q.isError) body = <ErrorState error={q.error} retry={() => void q.refetch()} compact />;
  else if (q.data && !q.data.available) body = <p className="text-sm text-muted-foreground" data-testid="similar-unavailable">{q.data.reason || "Similar Case Files is not available for this Case File."}</p>;
  else body = (
    <>
      <p className="text-sm text-muted-foreground flex items-start gap-1.5"><FolderSearch className="size-4 mt-0.5 shrink-0" aria-hidden />
        <span>Past Case Files of this hospital that resemble this one, in order of likeness as judged by Gemma-4-31B (a non-medical model that only orders the list and picks quoted lines). The order is not a score. Every reason line is quoted from the two files; the outcome so far shows the past Case summary with its cited line.</span>
      </p>
      <div><StatusChip kind="muted" className="whitespace-normal">{SIMILAR_LABEL}</StatusChip></div>
      <form className="flex flex-wrap gap-1.5" onSubmit={(e) => { e.preventDefault(); search.mutate(words.trim()); }}>
        <label htmlFor="similar-words" className="sr-only">Words to look for (optional)</label>
        <Input id="similar-words" value={words} onChange={(e) => setWords(e.target.value)} placeholder="Words to look for, for example HER2 positive with brain metastases" className="h-9 min-w-[12rem] flex-1 text-sm" maxLength={200} />
        <LoadingButton type="submit" size="sm" className="h-9" loading={search.isPending} loadingText="Searching, up to half a minute" data-testid="similar-search"><Search className="size-4" />Find similar Case Files</LoadingButton>
      </form>
      <p className="text-xs text-muted-foreground">Only the words you type are sent to the model with the recorded facts of this file. The search is logged.</p>
      {earlier.length ? (
        <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-1">Earlier searches:
          {earlier.map((t) => (
            <button key={t} type="button" className="rounded-md border border-border px-1.5 py-0.5 hover:bg-muted active:scale-95 transition" onClick={() => { setWords(t); search.mutate(t); }} disabled={search.isPending} title="Search again with these words">{t}</button>
          ))}
        </p>
      ) : null}
      {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
      {res ? (
        <section className="space-y-2" data-testid="similar-results">
          <h3 className="text-sm font-semibold text-foreground">Results</h3>
          {res.order_note ? <p className="text-xs text-muted-foreground" data-testid="similar-order-note">{res.order_note}</p> : null}
          {res.note ? <p className="text-sm text-body">{res.note}</p> : null}
          {results.length === 0 && weaker.length === 0 ? <EmptyState kind="search" title="No similar Case Files found" text="Try other words, or none." className="py-4" /> : null}
          {results.length ? <ol className="space-y-2 list-none">{shown.map(card)}</ol> : null}
          {!all && results.length > FIRST ? <Button type="button" size="sm" variant="outline" onClick={() => setAll(true)} data-testid="similar-more">Show {Math.min(FIRST, results.length - FIRST)} more</Button> : null}
          {weaker.length ? (
            <div className="space-y-2 pt-1" data-testid="similar-weaker">
              <h3 className="text-sm font-semibold text-foreground">Weaker matches</h3>
              <ol className="space-y-2 list-none">{weaker.map(card)}</ol>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );

  return (
    <div ref={box} className="scroll-mt-40 space-y-3 lg:scroll-mt-20" data-testid="similar-panel">
      {body}
      <OpenWithReasonButton caseId={glass?.past ?? lastPast.current} via={glass?.via} initialReason={glass?.reason} open={!!glass}
        onOpenChange={(o) => { if (!o) setGlass(null); }}
        onOpened={(w) => void afterWindow(w?.case_id || lastPast.current)} />
    </div>
  );
}
