// Shared pieces of the Board view (meetings-v2 item 2.3): the Case File reads it needs (the guided steps view, the Case File itself for
// the documents' pages and final marks, the staging view), all through the existing Case File routes that the meeting window opens
// read-only to every admitted member; and the plain card frame the tabs use.
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { getCase } from "@/features/casefile/api";
import type { CaseFile } from "@/features/casefile/types";
import { useSteps } from "@/features/casefile/steps/api";
import { useStaging } from "@/features/casefile/staging/api";

/** The three reads of one Case File. The Case File shares its cache with the Case File page (["case", id]). */
export function useBoardData(caseId: string) {
  const on = !!caseId;
  const steps = useSteps(caseId, on);
  const cf = useQuery<CaseFile>({
    queryKey: ["case", caseId],
    queryFn: ({ signal }) => getCase(caseId, signal),
    enabled: on,
    staleTime: 15_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: (n, e) => !(e instanceof ApiError && (e.status === 403 || e.status === 404)) && n < 1,
  });
  const staging = useStaging(caseId, on);
  return { steps, cf, staging };
}

/** A titled card of the Board view. */
export function Panel({ title, icon, aside, children, testId, className, labelId }: {
  title: ReactNode; icon?: ReactNode; aside?: ReactNode; children: ReactNode; testId?: string; className?: string; labelId: string;
}) {
  return (
    <section className={cn("surface overflow-hidden", className)} aria-labelledby={labelId} data-testid={testId}>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border px-4 py-3 @2xl:px-5">
        {icon}
        <h2 id={labelId} className="text-lg font-semibold text-foreground">{title}</h2>
        {aside ? <div className="flex flex-wrap items-center gap-2">{aside}</div> : null}
      </header>
      <div className="px-4 py-3 @2xl:px-5 @2xl:py-4">{children}</div>
    </section>
  );
}
