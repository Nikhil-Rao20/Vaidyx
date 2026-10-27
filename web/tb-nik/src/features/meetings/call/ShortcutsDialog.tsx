// The list of the call's keyboard shortcuts (research/04 section 6.10), opened with "?" or from the More menu. The keys never fire
// while the focus is in a text box, except Esc.
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SHORTCUTS } from "./types";

/** The shortcuts this person has: N and P only for the coordinator; Present waits for item 5.2. */
export function shortcutsFor(coordinator: boolean, present = false) {
  return SHORTCUTS.filter((s) => (coordinator || s.who !== "coordinator") && (present || !s.keys.endsWith("+T")));
}

export function ShortcutsDialog({ open, onOpenChange, coordinator, present }: { open: boolean; onOpenChange: (o: boolean) => void; coordinator: boolean; present?: boolean }) {
  const rows = shortcutsFor(coordinator, present);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby="keys-desc" data-testid="shortcuts-dialog">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription id="keys-desc">They work anywhere in the call except while you type in a box; Esc always closes the panel or the menu.</DialogDescription>
        </DialogHeader>
        <table className="w-full text-sm">
          <caption className="sr-only">Keyboard shortcuts of the call</caption>
          <thead><tr className="text-left text-xs text-muted-foreground"><th scope="col" className="pb-1 font-medium">Keys</th><th scope="col" className="pb-1 font-medium">What it does</th></tr></thead>
          <tbody className="divide-y divide-border">
            {rows.map((s) => (
              <tr key={s.keys}>
                <td className="py-1.5 pr-3 align-top whitespace-nowrap">{s.keys.split(" / ").map((k, i) => <span key={k}>{i ? " / " : ""}{k.split("+").map((p, j) => <span key={p}>{j ? "+" : ""}<kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs">{p}</kbd></span>)}</span>)}</td>
                <td className="py-1.5">{s.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DialogContent>
    </Dialog>
  );
}
