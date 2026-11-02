// The Board view's "Stage and values" tab (meetings-v2 item 2.3, D3): the staging card read-only (no work out, confirm, mark wrong, fill
// in or sign-off: the stage as written in the reports, and the Vaidyx draft stage labelled for the board to confirm when the switch is
// on), then the patient at a glance: every key value with its source chip, a "Please check" left as the mark it is, a key value a doctor
// checked marked with the name. A chip opens its report inside the Board view; the staging book opens on this screen only.
import { useMemo, useState } from "react";
import { CheckCheck } from "lucide-react";
import type { SourceTarget } from "@/features/casefile/components/SourceViewer";
import type { Steps } from "@/features/casefile/steps/types";
import { ValueCell } from "@/features/casefile/steps/Value";
import { BookViewer } from "@/features/casefile/staging/BookViewer";
import { StagingCard } from "@/features/casefile/staging/StagingCard";
import type { BookTarget, StagingView } from "@/features/casefile/staging/api";

function Glance({ steps, open }: { steps: Steps; open: (t: SourceTarget) => void }) {
  const checked = useMemo(() => new Map((steps.check?.keys ?? []).filter((k) => k.confirmed).map((k) => [k.slot_id, k.confirmed_by || ""])), [steps.check]);
  return (
    <section aria-labelledby="bv-glance" data-testid="board-glance">
      <h2 id="bv-glance" className="mb-2 text-lg font-semibold text-foreground">The patient at a glance</h2>
      {steps.glance.length ? (
        <div className="grid gap-4 @4xl:grid-cols-2">
          {steps.glance.map((g) => (
            <div key={g.id} className="surface px-4 py-2" data-testid={`board-glance-${g.id}`}>
              <h3 className="py-1.5 text-base font-semibold text-foreground">{g.label}</h3>
              <dl className="divide-y divide-border">
                {g.rows.map((r) => (
                  <div key={r.slot_id} className="grid gap-x-4 gap-y-0.5 py-2 @lg:grid-cols-[minmax(8rem,13rem)_1fr]">
                    <dt className="text-sm text-muted-foreground">{r.label}</dt>
                    <dd className="min-w-0 text-sm">
                      <ValueCell row={r} onOpen={open} />
                      {checked.has(r.slot_id) ? <span className="mt-0.5 flex items-center gap-1 text-xs text-ok"><CheckCheck className="size-3.5" aria-hidden />checked{checked.get(r.slot_id) ? ` by ${checked.get(r.slot_id)}` : ""}</span> : null}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      ) : <p className="text-base text-muted-foreground">No cancer is chosen yet, so nothing is looked for.</p>}
    </section>
  );
}

export function BoardStage({ caseId, steps, staging, stagingLoading, open }: {
  caseId: string; steps: Steps; staging: StagingView | null | undefined; stagingLoading: boolean; open: (t: SourceTarget) => void;
}) {
  const [book, setBook] = useState<BookTarget | null>(null);
  return (
    <div className="space-y-5" data-testid="board-stage">
      <StagingCard caseId={caseId} view={staging} loading={stagingLoading} canRun={false} canConfirm={false} canPropose={false} onOpen={open} onBook={setBook} onChanged={() => undefined} />
      <Glance steps={steps} open={open} />
      <BookViewer target={book} onClose={() => setBook(null)} />
    </div>
  );
}
