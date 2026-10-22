// Ask this Case File: the team's saved chat. Every answer is statements with quote chips that open the page with the
// quote marked. Pin keeps a thread on top; "records changed since" stamps an answer older than the Case File.
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { MessageSquareText, Pin, PinOff, SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { askOld, getChats, notBuiltYet, pinChat, postChat } from "../api";
import type { CaseDocument, ChatThread } from "../types";
import type { SourceTarget } from "./SourceViewer";
import { EmptyState, ErrorState, LoadingButton, SkeletonLines, StatusChip, errorText, fmtDateTime, useAnnounce, niceTitle } from "./common";
import { cn } from "@/lib/utils";

export function AskPanel({ caseId, docs, onOpenSource, compact }: { caseId: string; docs: CaseDocument[]; onOpenSource: (t: SourceTarget) => void; compact?: boolean }) {
  const qc = useQueryClient();
  const reduce = useReducedMotion();
  const [question, setQuestion] = useState("");
  const [local, setLocal] = useState<ChatThread[]>([]);
  const [announce, liveNode] = useAnnounce();
  const listRef = useRef<HTMLDivElement>(null);
  const q = useQuery({ queryKey: ["chats", caseId], queryFn: () => getChats(caseId), retry: false });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const docTitle = (id: string) => niceTitle(docs.find((d) => d.doc_id === id)?.classification?.title ?? docs.find((d) => d.doc_id === id)?.filename ?? "record");

  const ask = useMutation({
    mutationFn: async (text: string): Promise<ChatThread> => {
      if (notBuilt) {
        const r = await askOld(caseId, text);
        return {
          id: `local-${Date.now()}`, by: "me", at: new Date().toISOString(), question: text, status: r.status,
          statements: (r.statements ?? []).map((s) => ({ text: s.text, citations: (s.citations ?? []).map((c) => ({ doc_id: c.doc_id, doc_title: c.doc_title ?? c.title ?? docTitle(c.doc_id), page: c.page ?? 0, quote: c.quote ?? "" })) })),
          message: r.message, seconds: r.seconds, unsaved: true,
        };
      }
      return postChat(caseId, text);
    },
    onSuccess: (t) => {
      if (t.unsaved) setLocal((l) => [t, ...l]);
      else void qc.invalidateQueries({ queryKey: ["chats", caseId] });
      setQuestion("");
      announce(t.status === "answered" ? "Answer ready." : t.message ?? "No answer found in the records.");
    },
  });
  const pin = useMutation({
    mutationFn: ({ tid, pinned }: { tid: string; pinned: boolean }) => pinChat(caseId, tid, pinned),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["chats", caseId] }),
  });

  const threads = useMemo(() => {
    const server = q.data?.threads ?? [];
    const all = [...local, ...server];
    return all.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned) || String(b.at).localeCompare(String(a.at)));
  }, [q.data, local]);

  useEffect(() => { if (ask.isSuccess && listRef.current) listRef.current.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); }, [ask.isSuccess, reduce]);

  const submit = () => {
    const t = question.trim();
    if (t.length < 3 || ask.isPending) return;
    ask.mutate(t);
  };
  const askErr = ask.error ? (ask.error instanceof ApiError && ask.error.status === 429 ? "Too many questions in a short time. Please wait a minute." : errorText(ask.error)) : null;

  return (
    <section className={cn("surface flex flex-col", compact ? "p-3" : "p-4")} aria-labelledby="h-ask" data-testid="ask-panel">
      {liveNode}
      <header className="flex items-center gap-2 mb-2">
        <MessageSquareText className="size-4 text-brand" aria-hidden />
        <h2 id="h-ask" className="text-base">Ask about this patient</h2>
        <span className="text-xs text-muted-foreground ml-auto">shared with the team, saved</span>
      </header>
      <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label htmlFor="ask-input" className="sr-only">Your question about the records</label>
        <Textarea id="ask-input" value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} placeholder="For example: what did the HPE report say about the margins? Is ECOG noted?" className="min-h-14 text-sm resize-y" maxLength={600} disabled={ask.isPending} />
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground flex-1">Answers come only from the reports, each with its line.</span>
          <LoadingButton type="submit" size="sm" loading={ask.isPending} loadingText="Reading the records" disabled={question.trim().length < 3}><SendHorizontal className="size-4" />Ask</LoadingButton>
        </div>
        {askErr ? <p role="alert" className="text-xs text-bad">{askErr}</p> : null}
      </form>
      {notBuilt ? <p className="mt-2 text-xs text-muted-foreground rounded-md bg-muted px-2 py-1">Saved team chats are not on this server yet: answers here are not kept after you leave the page.</p> : null}
      <div ref={listRef} className={cn("mt-3 space-y-3 overflow-y-auto", compact ? "max-h-[50dvh]" : "max-h-[60dvh]")}>
        {q.isLoading ? <SkeletonLines n={3} /> : null}
        {q.isError && !notBuilt ? <ErrorState error={q.error} retry={() => void q.refetch()} compact /> : null}
        {!q.isLoading && threads.length === 0 && !ask.isPending ? <EmptyState kind="search" title="No questions yet" text="Ask the first one; the team sees every answer here." className="py-5" /> : null}
        {ask.isPending ? (
          <div className="rounded-md border border-border p-3" aria-busy="true">
            <p className="text-sm font-medium text-foreground">{question.trim()}</p>
            <p className="text-xs text-muted-foreground mt-1 mb-2">Preview filling in: lines become sentences only after their quote is verified.</p>
            <SkeletonLines n={3} />
          </div>
        ) : null}
        <AnimatePresence initial={false}>
          {threads.map((t) => (
            <motion.article key={t.id} layout initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className={cn("rounded-md border p-3", t.pinned ? "border-primary/60 bg-secondary/40" : "border-border")} data-testid="chat-thread">
              <div className="flex items-start gap-2">
                <p className="text-sm font-medium text-foreground flex-1">{t.question}</p>
                {!t.unsaved ? (
                  <Button variant="ghost" size="icon-xs" aria-label={t.pinned ? "Unpin" : "Pin"} aria-pressed={!!t.pinned} title={t.pinned ? "Unpin" : "Pin to the top"} onClick={() => pin.mutate({ tid: t.id, pinned: !t.pinned })} disabled={pin.isPending}>
                    {t.pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                  </Button>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{t.by_name ?? t.by}{t.at ? `, ${fmtDateTime(t.at)}` : ""}{t.seconds ? `, ${Math.round(t.seconds)} s` : ""}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {t.stale ? <StatusChip kind="warn">records changed since</StatusChip> : null}
                {t.unsaved ? <StatusChip kind="muted">not saved</StatusChip> : null}
                {t.status === "not_documented" ? <StatusChip kind="muted">not found in the records</StatusChip> : null}
                {t.status === "out_of_scope" ? <StatusChip kind="bad">outside what Vaidyx answers</StatusChip> : null}
                {t.status === "pending" ? <StatusChip kind="info">answering</StatusChip> : null}
              </div>
              {t.message && t.status !== "answered" ? <p className="mt-2 text-sm text-muted-foreground">{t.message}</p> : null}
              <ol className="mt-2 space-y-2">
                {(t.statements ?? []).map((s, i) => (
                  <li key={i} className="text-sm text-foreground">
                    <span>{s.text}</span>
                    <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
                      {(s.citations ?? []).map((c, j) => (
                        <button key={j} type="button" className="quote-chip hover:brightness-95 active:scale-95 transition" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: c.doc_title || docTitle(c.doc_id) })} title={`Open ${c.doc_title || docTitle(c.doc_id)}, page ${(c.page ?? 0) + 1}`}>
                          {niceTitle(c.doc_title) || docTitle(c.doc_id)} p. {(c.page ?? 0) + 1}
                        </button>
                      ))}
                    </span>
                  </li>
                ))}
              </ol>
            </motion.article>
          ))}
        </AnimatePresence>
      </div>
    </section>
  );
}
