// Settings: theme, text size (both applied at once and saved to the profile), start page; and the saved filters of the
// home list (open, remove with Undo).
import { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { ExternalLink, Filter, Palette, Pin, Trash2 } from "lucide-react";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TextSizeToggle } from "@/components/TextSizeToggle";
import { EmptyState } from "@/components/EmptyState";
import { notify, undoToast } from "@/components/Toasts";
import { useProfile, useSavedFilters } from "@/hooks/useProfile";
import { errorMessage } from "@/hooks/useAsyncAction";
import { activeKeys, describeValue, FILTER_LABELS, queryString, type FilterQuery } from "@/lib/filters";
import type { SavedFilter } from "@/lib/types";
import { SettingsCard } from "@/features/settings/SettingsCard";

type StartPage = "home" | "last_case" | "meetings";
const STARTS: Array<{ id: StartPage; label: string; hint: string }> = [
  { id: "home", label: "Home", hint: "Your Case File list" },
  { id: "last_case", label: "Last Case File", hint: "Where you left off" },
  { id: "meetings", label: "Meetings", hint: "The board calendar" },
];

export function AppearanceSection() {
  const { me, update } = useProfile();
  const [start, setStart] = useState<StartPage>((me?.profile?.start_page as StartPage) || "home");
  const [saving, setSaving] = useState(false);
  const pickStart = async (v: StartPage) => {
    const before = start;
    setStart(v);
    setSaving(true);
    try {
      await update({ start_page: v });
      notify.success("Start page saved", STARTS.find((s) => s.id === v)?.label);
    } catch (e) {
      setStart(before);
      notify.error("Could not save the start page", errorMessage(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <SettingsCard id="appearance" icon={Palette} title="Appearance" text="Changes apply at once and follow you to any device you sign in from.">
      <div className="grid gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-medium">Theme</p><p className="text-xs text-muted-foreground">Light for the ward, dark for the reporting room.</p></div>
          <ThemeToggle withLabel />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-medium">Text size</p><p className="text-xs text-muted-foreground">The whole page changes as you pick.</p></div>
          <TextSizeToggle />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Start page after sign-in {saving ? <span className="text-xs font-normal text-muted-foreground">saving</span> : null}</p>
          <RadioGroup value={start} onValueChange={(v) => void pickStart(v as StartPage)} className="grid gap-2 sm:grid-cols-3" aria-label="Start page">
            {STARTS.map((s) => (
              <Label key={s.id} htmlFor={`st-${s.id}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-secondary/50">
                <RadioGroupItem id={`st-${s.id}`} value={s.id} className="mt-0.5" disabled={saving} />
                <span><span className="block text-sm font-medium text-foreground">{s.label}</span><span className="block text-xs text-muted-foreground">{s.hint}</span></span>
              </Label>
            ))}
          </RadioGroup>
        </div>
      </div>
    </SettingsCard>
  );
}

function describe(f: SavedFilter): string {
  const q = (typeof f.query === "object" && f.query ? f.query : {}) as FilterQuery;
  const keys = activeKeys(q);
  if (!keys.length) return "Everything";
  return keys.map((k) => (k === "q" ? `"${q.q}"` : `${FILTER_LABELS[k]}: ${describeValue(k, q[k] as string)}`)).join(", ");
}

export function SavedFiltersSection() {
  const saved = useSavedFilters();
  const { update } = useProfile();
  const [busy, setBusy] = useState<string | null>(null);
  const remove = async (f: SavedFilter) => {
    const before = saved.list;
    setBusy(f.name);
    try {
      await saved.unpin(f.name);
      undoToast({ text: `Removed "${f.name}"`, onUndo: () => update({ saved_filters: before }) });
    } catch (e) {
      notify.error("Could not remove", errorMessage(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <SettingsCard id="filters" icon={Filter} title="Saved filters" text="Views pinned on your home list. Pin a new one from the filter chips on Home.">
      {saved.list.length ? (
        <ul className="grid gap-2">
          <AnimatePresence initial={false}>
            {saved.list.map((f) => (
              <motion.li key={f.name} layout initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }} className="surface-inner flex flex-wrap items-center gap-3 p-3">
                <Pin className="size-4 text-primary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{f.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{describe(f)}</p>
                </div>
                <Button type="button" variant="outline" size="sm" asChild>
                  <Link to={`/home${queryString((typeof f.query === "object" && f.query ? f.query : {}) as FilterQuery)}#cases`}><ExternalLink className="size-4" aria-hidden /> Open</Link>
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => void remove(f)} disabled={busy === f.name} aria-busy={busy === f.name} aria-label={`Remove ${f.name}`}>
                  <Trash2 className="size-4" aria-hidden /> {busy === f.name ? "Removing" : "Remove"}
                </Button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      ) : (
        <EmptyState compact kind="search" title="No saved filters yet" text="On Home, pick a few filter chips and press Pin this." action={<Button type="button" variant="outline" size="sm" asChild><Link to="/home#cases">Go to Home</Link></Button>} />
      )}
    </SettingsCard>
  );
}
