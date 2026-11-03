// One PubMed answer (docs/pubmed-ask/DESIGN.md section 8): the label line on top, always visible; the question; the search words as
// an editable chip with a year filter and Search again; 2 to 5 lines, each with numbered quote chips (a chip opens the exact quote,
// its section, its marks and the paper on PubMed); the paper list (quoted first, then read, then not read with why) with Save in a
// Case File; the counts, the time, the model, and "Source: PubMed, U.S. National Library of Medicine". Refused, no papers, not
// found and unavailable each say what happened in plain words and offer the next step.
import { useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, BookmarkPlus, ChevronDown, ExternalLink, Pencil, Pin, PinOff, RotateCcw, SearchX, ShieldQuestion, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SpeakButton } from "@/components/SpeakButton";
import { LoadingButton, StatusChip, fmtDateTime, indianDates, modelLabel } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { NLM_LINE, PUBMED_HOME, orderPapers, paperUrl, type PubMedCitation, type PubMedPaper, type PubMedSearch, type PubMedThread, type Years } from "./api";
import { LabelLine } from "./PubMedMark";

export interface SaveControl {
  /** Save shows only when the server allows it (or the page knows the login is the owner consultant). */
  allowed: boolean;
  pending: string | null;
  error: string | null;
  saved: Set<string>;
  onSave: (pmid: string) => void;
}

export interface AnswerActions {
  busy: boolean;
  onAgain: (i: { years: Years; words?: string }) => void;
  onEditQuestion?: (question: string) => void;
  onPin?: (pinned: boolean) => void;
  pinBusy?: boolean;
  save?: SaveControl;
}

const YEARS: Array<{ v: Years; word: string }> = [{ v: null, word: "All years" }, { v: 10, word: "Last 10 years" }, { v: 5, word: "Last 5 years" }];
const normYears = (y?: number | null): Years => (y === 5 || y === 10 ? y : null);

/** "Abstract, RESULTS", "Abstract", "Title". */
export function whereWords(where?: string): string {
  const w = (where ?? "").trim();
  if (!w || /^abstract$/i.test(w)) return "Abstract";
  if (/^title$/i.test(w)) return "Title";
  return `Abstract, ${w}`;
}

/** The year filter: three plain choices, All years first (PubMed's Best Match over every year finds landmark trials). */
export function YearFilter({ value, onChange, disabled, idPrefix }: { value: Years; onChange: (y: Years) => void; disabled?: boolean; idPrefix: string }) {
  return (
    <div role="radiogroup" aria-label="Publication years" className="inline-flex rounded-md border border-border bg-muted p-0.5" id={`${idPrefix}-years`}>
      {YEARS.map((y) => {
        const on = value === y.v;
        return (
          <button key={String(y.v)} type="button" role="radio" aria-checked={on} disabled={disabled} onClick={() => onChange(y.v)} data-testid="pubmed-years"
            className={cn("min-h-11 rounded px-2 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
              on ? "bg-card text-foreground shadow-[var(--shadow-outer)]" : "text-muted-foreground hover:text-foreground")}>
            {y.word}
          </button>
        );
      })}
    </div>
  );
}

/** The search words sent to PubMed, as a chip: tap to change them; the year filter; Search again. */
function SearchWords({ search, busy, onAgain, startOpen, idPrefix }: { search?: PubMedSearch; busy: boolean; onAgain: AnswerActions["onAgain"]; startOpen?: boolean; idPrefix: string }) {
  const sent = (search?.used ?? "").trim();
  const [editing, setEditing] = useState(!!startOpen);
  const [words, setWords] = useState(sent);
  const [years, setYears] = useState<Years>(normYears(search?.years));
  const changed = words.trim() !== sent;
  const go = () => { if (!busy && words.trim().length >= 2) onAgain({ years, words: changed ? words.trim() : undefined }); };
  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/50 p-2.5" data-testid="pubmed-search">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Search words sent to PubMed</p>
      {editing ? (
        <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); go(); }}>
          <label htmlFor={`${idPrefix}-words`} className="sr-only">Search words</label>
          <Input id={`${idPrefix}-words`} value={words} onChange={(e) => setWords(e.target.value)} maxLength={300} autoFocus className="h-9 text-sm" data-testid="pubmed-words-input" />
        </form>
      ) : (
        <button type="button" onClick={() => setEditing(true)} title="Change the search words" data-testid="pubmed-words"
          className="group flex w-full items-start gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-left text-sm text-foreground transition hover:border-border-strong active:scale-[0.99]">
          <span className="min-w-0 flex-1 break-words">{sent || "No search words"}</span>
          <Pencil className="mt-0.5 size-3.5 shrink-0 text-muted-foreground group-hover:text-foreground" aria-hidden />
          <span className="sr-only">Change</span>
        </button>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <YearFilter value={years} onChange={setYears} disabled={busy} idPrefix={idPrefix} />
        <Button type="button" size="sm" variant="outline" onClick={go} disabled={busy || words.trim().length < 2} className="min-h-11 sm:min-h-8 active:scale-[0.97]" data-testid="pubmed-search-again">
          <RotateCcw className="size-3.5" aria-hidden />Search again
        </Button>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        {search?.by === "model" ? "Written by the model from the question. " : search?.by === "doctor" ? "Your search words. " : search?.by ? "The question's own words. " : ""}Only these words go to PubMed, never a name or number.
      </p>
    </div>
  );
}

/** A numbered quote chip: opens the exact quote, where it is in the abstract, its marks and the paper on PubMed. */
function QuoteChip({ c, n, paper }: { c: PubMedCitation; n: number; paper?: PubMedPaper }) {
  const where = whereWords(c.where);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label={`Paper ${n}, ${where}: show the quote`} title={`Paper ${n}: show the quote`} data-testid="pubmed-quote-chip"
          className="relative inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-pubmed-line bg-pubmed-soft px-1 align-middle text-[11px] font-semibold tabular-nums text-pubmed transition hover:bg-pubmed hover:text-pubmed-soft active:scale-95 data-[state=open]:bg-pubmed data-[state=open]:text-pubmed-soft after:absolute after:-inset-2.5 after:content-[''] sm:after:-inset-1">
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" collisionPadding={12} className="w-[min(24rem,calc(100vw-2rem))] space-y-2 p-3" data-testid="pubmed-quote">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-pubmed">Paper {n} · {where}</p>
        <blockquote className="border-l-2 border-pubmed pl-2.5 text-sm leading-relaxed text-foreground" data-testid="pubmed-quote-text">“{c.quote}”</blockquote>
        {c.whole_sentence || c.added_for_numbers ? (
          <div className="flex flex-wrap gap-1">
            {c.whole_sentence ? <StatusChip kind="info" title="The model shortened the quote; the paper's whole sentence is shown instead.">Whole sentence from the paper</StatusChip> : null}
            {c.added_for_numbers ? <StatusChip kind="info" title="One more sentence of the same paper, shown because it states a number the line gives.">Added to show the numbers</StatusChip> : null}
          </div>
        ) : null}
        {paper ? (
          <div className="border-t border-border pt-2">
            <p className="text-xs font-medium leading-snug text-foreground">{paper.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{[paper.authors_line, paper.journal_abbr || paper.journal, paper.year].filter(Boolean).join(", ")}</p>
          </div>
        ) : null}
        <a href={paperUrl({ pmid: c.pmid, url: paper?.url })} target="_blank" rel="noopener noreferrer" data-testid="pubmed-open"
          className="inline-flex min-h-9 items-center gap-1 text-sm font-medium text-link underline underline-offset-2 hover:no-underline">
          Open on PubMed<ExternalLink className="size-3.5" aria-hidden /><span className="sr-only">(opens in a new tab)</span>
        </a>
        <span className="ml-2 text-xs tabular-nums text-muted-foreground">PMID {c.pmid}</span>
      </PopoverContent>
    </Popover>
  );
}

const Tricolour = () => <span className="inline-block size-2.5 shrink-0 rounded-full bg-[linear-gradient(#ff9933_0_33%,#ffffff_33%_66%,#138808_66%)] ring-1 ring-border" aria-hidden />;

function PaperCard({ p, n, save }: { p: PubMedPaper; n: number; save?: SaveControl }) {
  const saved = !!save?.saved.has(p.pmid);
  const mayKeep = !!save?.allowed && !p.retracted && !p.retraction_notice;
  return (
    <li className={cn("rounded-md border p-2.5", p.read === false ? "border-dashed border-border bg-muted/40" : "border-border bg-card")} data-testid="pubmed-paper" data-pmid={p.pmid} data-read={p.read ? "true" : "false"}>
      <div className="flex items-start gap-2.5">
        <span className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-md text-[11px] font-semibold tabular-nums", p.cited ? "bg-pubmed text-pubmed-soft" : "bg-muted text-muted-foreground")} aria-label={`Paper ${n}`}>{n}</span>
        <div className="min-w-0 flex-1">
          <a href={paperUrl(p)} target="_blank" rel="noopener noreferrer" className="text-sm font-medium leading-snug text-foreground decoration-pubmed/50 underline-offset-2 hover:underline">{p.title}</a>
          {p.authors_line ? <p className="mt-0.5 text-xs text-muted-foreground">{p.authors_line}</p> : null}
          <p className="text-xs text-muted-foreground">{[p.journal || p.journal_abbr, p.year].filter(Boolean).join(", ")}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {p.study_type ? <span className="inline-flex items-center rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground" data-testid="pubmed-study-type">{p.study_type}</span> : null}
            {p.india ? <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 text-xs font-medium text-foreground" title="An author's affiliation is in India" data-testid="pubmed-india"><Tricolour />India</span> : null}
            {p.retracted ? <StatusChip kind="bad">Retracted</StatusChip> : null}
            {p.retraction_notice ? <StatusChip kind="bad">Retraction notice</StatusChip> : null}
            {p.concern ? <StatusChip kind="warn">Expression of concern</StatusChip> : null}
            {p.preprint ? <StatusChip kind="warn">Preprint, not peer reviewed</StatusChip> : null}
            {p.has_abstract === false ? <StatusChip kind="muted">No abstract</StatusChip> : null}
            <a href={paperUrl(p)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-6 items-center gap-0.5 px-1 text-xs tabular-nums text-link underline underline-offset-2 hover:no-underline" data-testid="pubmed-pmid">
              PMID {p.pmid}<ExternalLink className="size-3" aria-hidden /><span className="sr-only">(opens PubMed in a new tab)</span>
            </a>
            {mayKeep ? (saved
              ? <StatusChip kind="ok" className="ml-auto" title="On this Case File's Published list">Saved</StatusChip>
              : <LoadingButton type="button" size="xs" variant="outline" loading={save!.pending === p.pmid} disabled={!!save!.pending} onClick={() => save!.onSave(p.pmid)} title="Save to this Case File's Published list"
                  className="ml-auto min-h-11 sm:min-h-6" data-testid="pubmed-save"><BookmarkPlus className="size-3" aria-hidden />Save</LoadingButton>) : null}
          </div>
          {p.read === false && p.why_not_read ? <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium text-foreground">Not read:</span> {p.why_not_read}</p> : null}
        </div>
      </div>
    </li>
  );
}

function PaperGroup({ title, papers, numberOf, save }: { title: string; papers: PubMedPaper[]; numberOf: Map<string, number>; save?: SaveControl }) {
  if (!papers.length) return null;
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold text-muted-foreground">{title} ({papers.length})</h4>
      <ul className="space-y-1.5">{papers.map((p) => <PaperCard key={p.pmid} p={p} n={numberOf.get(p.pmid) ?? 0} save={save} />)}</ul>
    </div>
  );
}

function PaperList({ thread, save }: { thread: PubMedThread; save?: SaveControl }) {
  const { papers, numberOf } = useMemo(() => orderPapers(thread), [thread]);
  const [all, setAll] = useState(false);
  if (!papers.length) return null;
  const quoted = new Set((thread.statements ?? []).flatMap((s) => (s.citations ?? []).map((c) => c.pmid)));
  const cited = papers.filter((p) => p.cited || quoted.has(p.pmid));
  const citedSet = new Set(cited.map((p) => p.pmid));
  const read = papers.filter((p) => !citedSet.has(p.pmid) && p.read !== false);
  const unread = papers.filter((p) => !citedSet.has(p.pmid) && p.read === false);
  const rest = read.length + unread.length;
  const showAll = all || cited.length === 0;
  return (
    <section className="space-y-2.5" aria-label="Papers" data-testid="pubmed-papers">
      <PaperGroup title="Quoted in the answer" papers={cited} numberOf={numberOf} save={save} />
      {showAll ? (
        <>
          <PaperGroup title="Read, not quoted" papers={read} numberOf={numberOf} save={save} />
          <PaperGroup title="Not read" papers={unread} numberOf={numberOf} save={save} />
        </>
      ) : null}
      {rest > 0 && cited.length > 0 ? (
        <Button type="button" variant="ghost" size="sm" onClick={() => setAll((a) => !a)} aria-expanded={all} className="min-h-11 w-full justify-center text-muted-foreground sm:min-h-8" data-testid="pubmed-more-papers">
          <ChevronDown className={cn("size-4 transition-transform", all && "rotate-180")} aria-hidden />
          {all ? "Show only the quoted papers" : `Show the other ${rest} papers (${read.length} read, ${unread.length} not read)`}
        </Button>
      ) : null}
      {save?.error ? <p role="alert" className="text-xs text-bad" data-testid="pubmed-save-error">{save.error}</p> : null}
    </section>
  );
}

function StatusNote({ icon: Icon, tone, title, text, action, testId }: { icon: typeof AlertTriangle; tone: "warn" | "muted" | "bad"; title: string; text?: string; action?: ReactNode; testId: string }) {
  return (
    <div className={cn("flex items-start gap-2.5 rounded-md p-3", tone === "warn" ? "status-warn" : tone === "bad" ? "status-bad" : "bg-muted text-muted-foreground")} role="status" data-testid={testId}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {text ? <p className="mt-0.5 text-sm text-foreground/80">{text}</p> : null}
        {action ? <div className="mt-2 flex flex-wrap gap-2">{action}</div> : null}
      </div>
    </div>
  );
}

/** "PubMed could not be reached" or "The model could not be reached", from the server's message. */
export function unavailableTitle(message?: string): string {
  return /model could not/i.test(message ?? "") ? "The model could not be reached" : "PubMed could not be reached";
}

export function AnswerCard({ thread: t, caseId, defaultLabel, actions, idPrefix }: { thread: PubMedThread; caseId?: string; defaultLabel: string; actions: AnswerActions; idPrefix: string }) {
  const lines = t.statements ?? [];
  const { papers, numberOf } = useMemo(() => orderPapers(t), [t]);
  const byPmid = useMemo(() => new Map(papers.map((p) => [p.pmid, p])), [papers]);
  const status = String(t.status);
  const found = t.counts?.found ?? t.search?.count;
  const read = t.counts?.read;
  const at = t.at || t.searched_at;
  const model = modelLabel(t.model);
  const local = t.id.startsWith("local-");
  const again = () => actions.onAgain({ years: normYears(t.search?.years), words: undefined });
  const searchBox = status !== "refused" && (t.search?.used || status === "no_papers")
    ? <SearchWords key={`${t.id}:${t.search?.used}:${t.search?.years}`} search={t.search} busy={actions.busy} onAgain={actions.onAgain} startOpen={status === "no_papers"} idPrefix={`${idPrefix}-${t.id}`} />
    : null;
  return (
    <article className={cn("space-y-3 rounded-lg border bg-card p-3 shadow-[var(--shadow-inner)]", t.pinned ? "border-pubmed/60" : "border-border")} data-testid="pubmed-answer" data-status={status} data-thread={t.id}>
      <LabelLine label={t.label || defaultLabel} />
      <header>
        <div className="flex items-start gap-1.5">
          <h3 className="min-w-0 flex-1 text-[0.9375rem] font-semibold leading-snug text-foreground">{t.question}</h3>
          {status === "answered" && !local ? (
            <SpeakButton source={{ ref: { kind: "pubmed", ...(caseId ? { case_id: caseId } : {}), id: t.id } }} screen="pubmed" size="icon-xs" className="justify-end" label="Read the answer aloud" />
          ) : null}
          {actions.onPin && !local ? (
            <Button type="button" variant="ghost" size="icon-xs" aria-label={t.pinned ? "Unpin" : "Pin"} aria-pressed={!!t.pinned} title={t.pinned ? "Unpin" : "Pin to the top for the team"} onClick={() => actions.onPin!(!t.pinned)} disabled={actions.pinBusy} className="min-h-11 min-w-11 sm:min-h-6 sm:min-w-6" data-testid="pubmed-pin">
              {t.pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
            </Button>
          ) : null}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {[t.by_name ?? t.by, at ? fmtDateTime(at) : "", t.seconds ? `${Math.round(t.seconds)} s` : ""].filter(Boolean).join(", ")}
          {t.pinned ? <span className="ml-1.5 inline-flex items-center gap-0.5 font-medium text-pubmed"><Pin className="size-3" aria-hidden />pinned</span> : null}
        </p>
      </header>

      {status === "refused" ? (
        <StatusNote icon={ShieldQuestion} tone="warn" title="Ask PubMed did not take this question" text={t.message} testId="pubmed-refused"
          action={actions.onEditQuestion ? <Button type="button" size="sm" variant="outline" onClick={() => actions.onEditQuestion!(t.question)} className="min-h-11 bg-card sm:min-h-8"><Pencil className="size-3.5" aria-hidden />Change the question</Button> : null} />
      ) : null}
      {status === "no_papers" ? <StatusNote icon={SearchX} tone="muted" title="PubMed found no papers" text={t.message || "Change the search words below and search again."} testId="pubmed-no-papers" /> : null}
      {status === "not_found" ? <StatusNote icon={SearchX} tone="muted" title="No answer in the abstracts read" text={t.message} testId="pubmed-not-found" /> : null}
      {status === "unavailable" ? (
        <StatusNote icon={WifiOff} tone="bad" title={unavailableTitle(t.message)} text={t.message} testId="pubmed-unavailable"
          action={<LoadingButton type="button" size="sm" onClick={again} loading={actions.busy} loadingText="Asking again" className="min-h-11 sm:min-h-8" data-testid="pubmed-try-again"><RotateCcw className="size-3.5" aria-hidden />Try again</LoadingButton>} />
      ) : null}
      {status !== "answered" && status !== "refused" && status !== "no_papers" && status !== "not_found" && status !== "unavailable" && t.message
        ? <StatusNote icon={AlertTriangle} tone="muted" title="No answer" text={t.message} testId="pubmed-other" /> : null}

      {lines.length ? (
        <ol className="space-y-2.5" data-testid="pubmed-lines">
          {lines.map((s, i) => (
            <li key={i} className="flex gap-2 text-sm leading-relaxed text-foreground" data-testid="pubmed-line">
              <span className="mt-[3px] grid size-4 shrink-0 place-items-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground" aria-hidden>{i + 1}</span>
              <span className="min-w-0">
                {indianDates(s.text)}
                <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
                  {(s.citations ?? []).map((c, j) => <QuoteChip key={j} c={c} n={numberOf.get(c.pmid) ?? 0} paper={byPmid.get(c.pmid)} />)}
                </span>
              </span>
            </li>
          ))}
        </ol>
      ) : null}

      {searchBox}
      <PaperList thread={t} save={actions.save} />

      <footer className="space-y-1 border-t border-border pt-2 text-xs text-muted-foreground" data-testid="pubmed-footer">
        <p>
          {[found !== undefined ? `${found.toLocaleString("en-IN")} papers found` : "", read !== undefined ? `${read} read` : "", at ? `searched ${fmtDateTime(at)}` : ""].filter(Boolean).join(", ")}
          {(found !== undefined || at) ? "." : ""}
          {model && (lines.length || status === "not_found") ? <span data-testid="pubmed-model-line"> Written by {model}.</span> : null}
        </p>
        <p><a href={PUBMED_HOME} target="_blank" rel="noopener noreferrer" className="text-link underline underline-offset-2 hover:no-underline">{NLM_LINE}</a></p>
      </footer>
    </article>
  );
}
