// Edit in place (meetings-v2 3.3): a value shown as plain text with a small pencil; a click turns it into its field with Save and Cancel
// (Enter saves, Escape cancels); the server's refusal ("That date has passed") shows under it. Members see the text only.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check, Pencil, X, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorText } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

export function InlineField({ label, icon: Icon, value, shown, canEdit, onSave, editor, validate, className, textClassName, testId, heading }: {
  /** "date", "time", "room", "title": in the button's name ("Change the date") */
  label: string;
  icon?: LucideIcon;
  value: string;
  /** What the page shows for the value ("Friday 07/11/2026"). */
  shown: ReactNode;
  canEdit: boolean;
  onSave: (v: string) => Promise<unknown>;
  editor: (draft: string, setDraft: (v: string) => void, inputId: string) => ReactNode;
  validate?: (v: string) => string | null;
  className?: string;
  textClassName?: string;
  testId?: string;
  /** Shown as the page's h1 (the button sits inside it; the form replaces it while editing). */
  heading?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraftState] = useState(value);
  const draftRef = useRef(value);  // the date and time fields hand their value over on blur: Save reads it after that
  const setDraft = (v: string) => { draftRef.current = v; setDraftState(v); };
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputId = useId();
  useEffect(() => { if (!editing) { draftRef.current = value; setDraftState(value); } }, [value, editing]);
  useEffect(() => { if (editing) window.setTimeout(() => (document.getElementById(inputId) as HTMLInputElement | null)?.focus(), 30); }, [editing, inputId]);

  const save = async () => {
    const v = draftRef.current;
    const bad = validate?.(v) ?? null;
    if (bad) { setErr(bad); return; }
    if (v === value) { setEditing(false); return; }
    setBusy(true); setErr(null);
    try { await onSave(v); setEditing(false); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };

  if (!editing) {
    if (!canEdit) {
      const text = <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)} data-testid={testId}>{Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}<span className={cn("min-w-0 break-words [text-wrap:wrap]", textClassName)}>{shown}</span></span>;
      return heading ? <h1 className="min-w-0">{text}</h1> : text;
    }
    const button = (
      <button type="button" onClick={() => setEditing(true)} data-testid={testId} title={`Change the ${label}`}
        className={cn("group inline-flex min-w-0 max-w-[calc(100%+0.75rem)] items-center gap-1.5 rounded-md px-1.5 py-0.5 -mx-1.5 text-left outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring", className)}>
        {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
        <span className={cn("min-w-0 break-words [text-wrap:wrap]", textClassName)}>{shown}</span>
        <span className="sr-only">, change the {label}</span>
        <Pencil className="size-3.5 shrink-0 text-muted-foreground opacity-60 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />
      </button>
    );
    return heading ? <h1 className="min-w-0">{button}</h1> : button;
  }
  return (
    <form className={cn("flex min-w-0 flex-col gap-1", className)} data-testid={testId ? `${testId}-edit` : undefined}
      onSubmit={(e) => {
        e.preventDefault();
        const el = document.activeElement as HTMLElement | null;
        if (el && e.currentTarget.contains(el) && el.tagName === "INPUT") el.blur();  // the field commits what was typed
        window.setTimeout(() => void save(), 0);
      }}
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setErr(null); setEditing(false); } }}>
      <div className="flex min-w-0 items-center gap-1">
        <label htmlFor={inputId} className="sr-only">{label[0].toUpperCase() + label.slice(1)}</label>
        <div className="min-w-0 flex-1">{editor(draft, (v) => { setDraft(v); setErr(null); }, inputId)}</div>
        <Button type="submit" size="icon-sm" disabled={busy} aria-label={`Save the ${label}`}><Check className="size-4" /></Button>
        <Button type="button" size="icon-sm" variant="ghost" disabled={busy} aria-label="Cancel" onClick={() => { setErr(null); setEditing(false); }}><X className="size-4" /></Button>
      </div>
      {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
    </form>
  );
}
