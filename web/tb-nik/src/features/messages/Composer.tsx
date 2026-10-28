// The composer: the text box (Enter sends, Shift+Enter a new line), dictation into the box (never sent by itself), one Case File
// or meeting chip, @ mentions of the conversation's readers, the counter from 1800 characters, and the soft warning when the
// text looks like a patient number (a warning, never a block: "Send anyway" sends).
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { AlertTriangle, FolderOpen, FolderPlus, Loader2, SendHorizontal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { cn } from "@/lib/utils";
import { LinkPicker } from "@/features/messages/LinkPicker";
import { COUNTER_FROM, NOTE_UNDER_COMPOSER, PATIENT_NUMBER_WARNING, TEXT_MAX, looksLikePatientNumber } from "@/features/messages/parts";
import { sendTyping } from "@/features/messages/useMessagesLive";
import type { LinkRef, PickedLink } from "@/features/messages/types";

export interface ComposerSend { text: string; link: LinkRef | null; mentions: string[] }

/** The "@words" just before the caret, when the person is choosing a mention. */
function mentionAt(text: string, caret: number): { start: number; query: string } | null {
  const m = /(^|\s)@([^\s@]{0,30})$/.exec(text.slice(0, caret));
  return m ? { start: caret - m[2].length - 1, query: m[2] } : null;
}

export function Composer({ conversationId, readers = [], me, initialLink = null, placeholder = "Write a message", onSend, className, autoFocus }: {
  conversationId?: string;
  readers?: Array<{ user: string; display_name: string }>;
  me: string;
  initialLink?: PickedLink | null;
  placeholder?: string;
  /** Sends; resolves true when the server took it (the box is then cleared). */
  onSend: (m: ComposerSend) => Promise<boolean>;
  className?: string;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const [link, setLink] = useState<PickedLink | null>(initialLink);
  const [picking, setPicking] = useState(false);
  const [warn, setWarn] = useState(false);
  const [sending, setSending] = useState(false);
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const [active, setActive] = useState(0);
  const chosen = useRef(new Map<string, string>());
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { if (initialLink) setLink(initialLink); }, [initialLink?.type, initialLink?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // The warning goes once the text no longer looks like a patient number.
  useEffect(() => { if (warn && !looksLikePatientNumber(text)) setWarn(false); }, [text, warn]);

  const options = useMemo(() => {
    if (!mention) return [];
    const q = mention.query.toLowerCase();
    return readers
      .filter((r) => r.user !== me)
      .filter((r) => !q || r.display_name.toLowerCase().split(/\s+/).some((w) => w.replace(/^dr\.?$/, "").startsWith(q)) || r.display_name.toLowerCase().startsWith(q))
      .slice(0, 6);
  }, [mention, readers, me]);

  const len = text.trim().length;
  const over = text.length > TEXT_MAX;
  const canSend = len > 0 && !over && !sending;

  const onChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const v = e.target.value;
    setText(v);
    if (conversationId && v.trim()) sendTyping(conversationId);
    const m = readers.length ? mentionAt(v, e.target.selectionStart ?? v.length) : null;
    setMention(m);
    setActive(0);
  };

  const choose = (r: { user: string; display_name: string }) => {
    if (!mention) return;
    const el = boxRef.current;
    const caret = el?.selectionStart ?? text.length;
    const insert = `@${r.display_name} `;
    const next = text.slice(0, mention.start) + insert + text.slice(caret);
    chosen.current.set(r.user, r.display_name);
    setText(next);
    setMention(null);
    window.setTimeout(() => { const pos = mention.start + insert.length; el?.focus(); el?.setSelectionRange(pos, pos); }, 0);
  };

  const submit = async (force = false) => {
    const t = text.trim();
    if (!t || over || sending) return;
    if (!force && looksLikePatientNumber(t)) { setWarn(true); return; }
    const mentions = [...chosen.current.entries()].filter(([, name]) => t.includes(`@${name}`)).map(([u]) => u).slice(0, 8);
    setSending(true);
    try {
      const ok = await onSend({ text: t, link: link ? { type: link.type, id: link.id } : null, mentions });
      if (ok) {
        setText("");
        setLink(null);
        setWarn(false);
        chosen.current.clear();
        boxRef.current?.focus();
      }
    } finally {
      setSending(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mention && options.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % options.length); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a - 1 + options.length) % options.length); return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); choose(options[active]); return; }
      if (e.key === "Escape") { e.preventDefault(); setMention(null); return; }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); }
  };

  return (
    <form data-testid="composer" className={cn("flex flex-col gap-2", className)} onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      {warn ? (
        <div role="alert" data-testid="number-warning" className="flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-sm text-foreground">
          <span className="flex min-w-[min(100%,16rem)] flex-1 items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
            <span className="min-w-0">{PATIENT_NUMBER_WARNING}</span>
          </span>
          <span className="ml-auto flex shrink-0 gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setPicking(true)}>Add a Case File</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void submit(true)} data-testid="send-anyway">Send anyway</Button>
          </span>
        </div>
      ) : null}
      {link ? (
        <div className="flex">
          <span data-testid="composer-chip" className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-secondary py-1 pl-2.5 pr-1 text-xs font-medium text-secondary-foreground">
            <FolderOpen className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{link.type === "case" ? "Case File" : "Meeting"}: {link.label}</span>
            <button type="button" onClick={() => setLink(null)} className="grid size-6 shrink-0 place-items-center rounded-full hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={link.type === "case" ? "Remove the Case File" : "Remove the meeting"}>
              <X className="size-3.5" aria-hidden />
            </button>
          </span>
        </div>
      ) : null}
      <div className="relative">
        {mention && options.length ? (
          <ul role="listbox" aria-label="People in this conversation" data-testid="mention-list"
            className="absolute bottom-full left-0 z-20 mb-1 w-64 max-w-full overflow-hidden rounded-md border border-border bg-popover p-1 text-sm shadow-md">
            {options.map((r, i) => (
              <li key={r.user} role="option" aria-selected={i === active}>
                <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(r)}
                  className={cn("w-full truncate rounded px-2 py-1.5 text-left", i === active ? "bg-accent text-accent-foreground" : "hover:bg-accent/60")}>
                  {r.display_name}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <label htmlFor="message-box" className="sr-only">Write a message</label>
        <Textarea ref={boxRef} id="message-box" data-testid="composer-input" value={text} onChange={onChange} onKeyDown={onKey}
          onBlur={() => window.setTimeout(() => setMention(null), 150)}
          placeholder={placeholder} autoFocus={autoFocus} rows={1}
          aria-invalid={over || undefined} aria-describedby="message-note"
          className="max-h-40 min-h-11 resize-none text-base md:text-base" />
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setPicking(true)} className="shrink-0" data-testid="add-case-file" title="Add a Case File">
          <FolderPlus className="size-4" aria-hidden /><span className="max-sm:sr-only">Add a Case File</span>
        </Button>
        <MicButton target={boxRef} screen="messages" context="note" label="Dictate the message" className="max-w-[45%] shrink-0"
          onInsert={(next) => setText(next)} />
        <span className={cn("min-w-0 flex-1 text-right text-xs tabular-nums", over ? "font-medium text-bad" : "text-muted-foreground")} aria-live="polite">
          {text.length >= COUNTER_FROM ? `${text.length} / ${TEXT_MAX}` : ""}
        </span>
        <Button type="submit" size="sm" disabled={!canSend} data-testid="send" title="Send (Enter)">
          {sending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <SendHorizontal className="size-4" aria-hidden />}Send
        </Button>
      </div>
      <p id="message-note" className="text-[11px] leading-snug text-muted-foreground">{NOTE_UNDER_COMPOSER}</p>
      <LinkPicker open={picking} onOpenChange={setPicking} onPick={(l) => { setLink(l); setWarn(false); boxRef.current?.focus(); }} />
    </form>
  );
}
