// The outside expert's view of the Case File on the floor (meetings-v2 2.5, security review #9): the Case File's own read routes are
// closed to an outside expert, so the Board view is never shown to them. They read the identity-stripped summary that the meeting's
// summary route gives (GET /meetings/{mid}/cases/{cid}/slides, built by the server with the patient's identity removed when there is no
// consent for outside discussion), shown simply: the question for the board, the summary's sections with their sources named, and the
// key values. Read-only; nothing here opens a report.
import { useQuery } from "@tanstack/react-query";
import { FileText, ShieldCheck } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ErrorState, NotSigned, SkeletonLines, fmtDate, indianDates, niceTitle } from "@/features/casefile/components/common";
import { getSlides } from "../api";
import type { Slide, SlideCitation, SlideContentMap, SlideSentence } from "../types";
import "./board.css";

function Source({ c }: { c: SlideCitation }) {
  const page = typeof c.page === "number" ? `, p. ${c.page + 1}` : "";
  return <span className="quote-chip ml-1 align-middle" title={c.quote ? `"${c.quote}"` : undefined}><FileText className="size-3" aria-hidden />{niceTitle(c.doc_title) || "Report"}{page}<NotSigned word={c.final_word} /></span>;
}

function Line({ s }: { s: SlideSentence | string }) {
  if (typeof s === "string") return <li className="text-base text-foreground">{indianDates(s)}</li>;
  return <li className="text-base text-foreground">{indianDates(s.text)}{(s.citations ?? []).slice(0, 3).map((c, j) => <Source key={j} c={c} />)}</li>;
}

const content = (x: Slide | undefined): SlideContentMap | null => (x && x.content && typeof x.content === "object" && !Array.isArray(x.content) ? x.content : null);

export function ExpertSummary({ mid, caseId, big = false, className }: { mid: string; caseId: string; big?: boolean; className?: string }) {
  const q = useQuery({
    queryKey: ["expert-summary", mid, caseId],
    queryFn: () => getSlides(mid, caseId),
    staleTime: 60_000,
    retry: (n, e) => !(e instanceof ApiError && (e.status === 403 || e.status === 404)) && n < 1,
  });
  const list = q.data?.slides ?? [];
  const summary = content(list.find((x) => x.kind === "summary"));
  const values = content(list.find((x) => x.kind === "values"))?.values ?? [];
  const sections = (summary?.sections ?? []).filter((s) => s.text || (s.sentences ?? s.items ?? []).length);
  return (
    <div className={cn("board-view scroll-thin h-full min-h-0 overflow-y-auto text-foreground", big && "board-big", className)} data-testid="expert-summary">
      <div className="mx-auto max-w-5xl space-y-4">
        <p className="flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-sm text-foreground"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />You are an outside expert: you read the summary of this Case File. The reports stay with the hospital.</p>
        {q.isLoading ? <div className="surface p-5"><SkeletonLines n={6} /></div> : null}
        {q.isError ? <ErrorState error={q.error} retry={() => void q.refetch()} title="The summary could not be read here" /> : null}
        {q.data ? (
          <>
            {summary?.board_question ? (
              <section className="surface px-5 py-4" aria-labelledby="ex-question">
                <h2 id="ex-question" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Question for the board</h2>
                <p className="mt-1 text-2xl font-semibold leading-snug text-foreground">{summary.board_question}</p>
              </section>
            ) : null}
            <section className="surface px-5 py-4" aria-labelledby="ex-summary">
              <h2 id="ex-summary" className="text-lg font-semibold text-foreground">Summary</h2>
              {summary?.label ? <span className={cn("mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium", summary.reviewed ? "status-ok" : "status-review")}>{summary.label}</span> : null}
              {sections.length ? (
                <div className="mt-2 space-y-3">
                  {sections.map((s, i) => (
                    <section key={s.id ?? i}>
                      {s.title ?? s.heading ? <h3 className="font-semibold text-foreground">{s.title ?? s.heading}</h3> : null}
                      {s.text ? <p className="text-base text-foreground">{indianDates(s.text)}</p> : null}
                      <ul className="space-y-1">{(s.sentences ?? s.items ?? []).map((x, j) => <Line key={j} s={x} />)}</ul>
                    </section>
                  ))}
                </div>
              ) : <p className="mt-2 text-base text-muted-foreground">{summary?.note || "No summary is written for this Case File yet."}</p>}
            </section>
            {values.length ? (
              <section className="surface px-5 py-4" aria-labelledby="ex-values">
                <h2 id="ex-values" className="text-lg font-semibold text-foreground">Key values</h2>
                <dl className="mt-2 divide-y divide-border">
                  {values.map((v) => (
                    <div key={v.id} className="grid gap-x-4 gap-y-0.5 py-2 sm:grid-cols-[minmax(8rem,14rem)_1fr]">
                      <dt className="text-sm text-muted-foreground">{v.label}</dt>
                      <dd className="text-sm text-foreground">{v.value}{v.doc_title ? <Source c={{ doc_id: v.doc_id ?? "", doc_title: v.doc_title, page: v.page, quote: v.quote }} /> : null}{v.date ? <span className="ml-2 text-xs text-muted-foreground">{fmtDate(v.date)}</span> : null}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
            <p className="text-xs text-muted-foreground">From the records, with quotes. Vaidyx checks, routes, summarises and flags; the decision is the board&apos;s.</p>
          </>
        ) : null}
      </div>
    </div>
  );
}
