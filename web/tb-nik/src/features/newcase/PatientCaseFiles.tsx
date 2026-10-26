// One Case File per patient and cancer (night-v3 item 1.1). The patient's live Case Files come from GET /patient-case-files
// (the same UHID or a registration linked to one; archived ones are never listed). The Patient step lists them; the Cancer and
// Logistics steps show the strong line "A Case File for this patient and this cancer exists (Breast Surgery, Dr X)" when the
// chosen cancer is one of them (the server's rule: the same checklist, and for a cancer with no checklist yet the same typed
// name), and Create stays off. Each file offers "Open it" when this person may open it, else "Ask to join".
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FolderOpen, Lock, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/StatusPill";
import { AskToJoinDialog, type AskTarget } from "@/components/AskToJoinDialog";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { drName, formatDate } from "@/lib/format";
import { cleanCancerName, isGeneric } from "@/lib/cancers";
import type { PatientCaseFile, PatientCaseFilesResponse } from "@/lib/types";
import type { NewCaseForm } from "@/features/newcase/form";

export const ANOTHER_CANCER = "Another cancer gets its own Case File, linked to these.";

/** The patient's live Case Files, by the UHID found (or the number typed). */
export function usePatientCaseFiles(identifier?: string | null) {
  return useQuery<PatientCaseFilesResponse, Error>({
    queryKey: ["patient-case-files", identifier ?? ""],
    queryFn: () => api.get<PatientCaseFilesResponse>(`${EP.patientCaseFiles}?identifier=${encodeURIComponent(identifier as string)}`),
    enabled: Boolean(identifier),
    staleTime: 30_000,
    retry: 1,
  });
}

/** The identifier the New Case File page asks with: the UHID the lookup found, else the number typed. */
export function patientKey(form: NewCaseForm): string {
  return form.lookup?.found ? form.lookup.patient?.uhid || form.identifier : "";
}

/** "Breast Surgery, Dr Rao" (the department alone when no consultant is placed yet). */
export function ownerWords(f: PatientCaseFile): string {
  return f.owner_words || [f.department_name, drName(f.owner_name)].filter(Boolean).join(", ") || "owner not set";
}

/** The server's rule (his_case._same_cancer): the same checklist; under the generic rule the same typed name (any case or spacing). */
export function sameCancer(f: PatientCaseFile, form: NewCaseForm): boolean {
  if (!form.protocol || f.protocol !== form.protocol) return false;
  if (!isGeneric(form.protocol)) return true;
  return cleanCancerName(f.cancer_name || "").toLowerCase() === cleanCancerName(form.cancerName).toLowerCase();
}

/** The live Case File of this patient and the chosen cancer, if any. */
export function duplicateFor(files: PatientCaseFile[] | undefined, form: NewCaseForm): PatientCaseFile | null {
  return (files ?? []).find((f) => sameCancer(f, form)) ?? null;
}

export function duplicateLine(f: PatientCaseFile): string {
  return `A Case File for this patient and this cancer exists (${ownerWords(f)})`;
}

/** "Open it" when this person may open the Case File, else "Ask to join" (a dialog with an optional note). */
function FileActions({ file, asked, onAsk }: { file: PatientCaseFile; asked: boolean; onAsk: (f: PatientCaseFile) => void }) {
  if (file.can_open) {
    return (
      <Button type="button" size="sm" variant="outline" asChild>
        <Link to={`/cases/${encodeURIComponent(file.case_id)}`}><FolderOpen className="size-4" aria-hidden /> Open it</Link>
      </Button>
    );
  }
  return (
    <Button type="button" size="sm" variant="outline" disabled={asked} onClick={() => onAsk(file)}>
      <UserPlus className="size-4" aria-hidden /> {asked ? "Asked" : "Ask to join"}
    </Button>
  );
}

/** The Case Files asked to join on this page visit, shared by the Patient card and the Cancer and Logistics lines. */
const ASKED = new Set<string>();

function useAsk() {
  const [target, setTarget] = useState<AskTarget | null>(null);
  const [asked, setAsked] = useState<Set<string>>(() => new Set(ASKED));
  const ask = (f: PatientCaseFile) => setTarget({ case_id: f.case_id, label: `${f.cancer_label}, ${ownerWords(f)}` });
  const dialog = (
    <AskToJoinDialog target={target} onOpenChange={(o) => { if (!o) setTarget(null); }} onAsked={(id) => { ASKED.add(id); setAsked(new Set(ASKED)); }} />
  );
  return { ask, asked, dialog };
}

/** The Patient step's card: every live Case File of this patient. */
export function PatientCaseFilesCard({ files }: { files: PatientCaseFile[] }) {
  const { ask, asked, dialog } = useAsk();
  if (!files.length) return null;
  return (
    <section className="rounded-md status-review p-4" aria-label="Case Files of this patient" data-testid="patient-case-files">
      <p className="text-sm font-bold">This patient has {files.length === 1 ? "1 Case File" : `${files.length} Case Files`}</p>
      <ul className="mt-2 grid gap-2">
        {files.map((f) => (
          <li key={f.case_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md bg-card/70 p-2 text-sm text-foreground">
            <span className="min-w-0">
              <span className="block font-medium">{f.cancer_label}</span>
              <span className="block text-xs text-muted-foreground">{ownerWords(f)}{f.created_at ? `, since ${formatDate(f.created_at)}` : ""}</span>
            </span>
            {f.status_label ? <Pill tone="neutral">{f.status_label}</Pill> : null}
            <span className="ml-auto"><FileActions file={f} asked={asked.has(f.case_id)} onAsk={ask} /></span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs">For the same cancer, open or join the Case File above instead of starting a second. {ANOTHER_CANCER}</p>
      {dialog}
    </section>
  );
}

/** The strong line at the Cancer and Logistics steps (and for a 409 from the server): Create stays off for this cancer. */
export function DuplicateNotice({ file }: { file: PatientCaseFile }) {
  const { ask, asked, dialog } = useAsk();
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-md status-bad px-3 py-2 text-sm sm:flex-row sm:items-start sm:gap-3" data-testid="duplicate-case-file">
      <div className="flex min-w-0 flex-1 items-start gap-2">
        <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
        <div className="min-w-0">
          <p className="font-medium">{duplicateLine(file)}</p>
          <p className="text-xs">Only one Case File per patient and cancer, so Create is off. {file.can_open ? "Open it to add to it." : "Ask to join it, or pick another cancer."} {ANOTHER_CANCER}</p>
        </div>
      </div>
      <span className="pl-6 sm:pl-0"><FileActions file={file} asked={asked.has(file.case_id)} onAsk={ask} /></span>
      {dialog}
    </div>
  );
}
