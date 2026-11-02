// /cases/new: the New Case File flow (SPEC 3.4) as a 3-step stepper: Patient (hospital system lookup), Cancer (top 10
// per group, checklist, NCG setting as recorded), Logistics (pre-filled). Create runs POST /cases/from-his, then the
// urgency (PUT /cases/{id}/urgency), the board question (the typed value of the clinical_question line), the consent and
// the join code; the first fetch shows its live steps (FetchProgress) and then the Case File opens.
// ?identifier=<UHID> (from the gift box or the search bar) looks the patient up at once.
// One Case File per patient and cancer (night-v3 item 1.1): when the chosen cancer already has a live Case File of this patient
// (GET /patient-case-files, or the server's 409 duplicate_case_file), the Cancer and Logistics steps say whose it is and Create stays off.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowLeft, FolderPlus, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { Stepper, Step, StepTitle } from "@/components/Stepper";
import { notify } from "@/components/Toasts";
import { useInvalidate, useProtocols, keys } from "@/hooks/useQueries";
import { errorMessage } from "@/hooks/useAsyncAction";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useSession } from "@/lib/session";
import { ageSex } from "@/lib/format";
import type { CreateFromHisResponse, DuplicateCaseFileBody, PatientCaseFile } from "@/lib/types";
import { isGeneric } from "@/lib/cancers";
import { DEFAULT_FORM, createBody, type NewCaseForm } from "@/features/newcase/form";
import { StepPatient } from "@/features/newcase/StepPatient";
import { NOT_RECORDED, StepCancer, cancerStepDone } from "@/features/newcase/StepCancer";
import { StepLogistics, logisticsDone, useOwnerChoices } from "@/features/newcase/StepLogistics";
import { FetchProgress, type FollowUp } from "@/features/newcase/FetchProgress";
import { DuplicateNotice, duplicateFor, patientKey, sameCancer, usePatientCaseFiles } from "@/features/newcase/PatientCaseFiles";

interface Created {
  caseId: string;
  jobId: string | null;
  total: number;
  patientLine: string;
}

function createError(e: unknown, form: NewCaseForm): string {
  if (e instanceof ApiError) {
    if (e.status === 400 && /unknown protocol/i.test(e.message) && (!form.protocol || isGeneric(form.protocol))) {
      return `This server cannot start a Case File for a cancer with no checklist yet (${form.cancerName || "this cancer"}). Ask the root admin to update Vaidyx, or pick the closest built checklist.`;
    }
    if (e.status === 400 && /cancer's name/i.test(e.message)) return `${e.message}. Go back to the Cancer step to correct it.`;
    if (e.status === 409 && /hospital information system/i.test(e.message)) return "No hospital system is connected yet. The root admin connects it in Admin, Hospital system.";
    if (e.status === 502) return "The hospital system did not answer. Nothing was created; try again in a minute.";
    if (e.status === 403) return e.message || "You may not start a Case File for this department.";
  }
  return errorMessage(e, "The Case File could not be created.");
}

export default function NewCaseFile() {
  const { me } = useSession();
  const [params] = useSearchParams();
  const initialId = params.get("identifier") || "";
  const [form, setForm] = useState<NewCaseForm>({ ...DEFAULT_FORM, identifier: initialId });
  const [step, setStep] = useState(1);
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [joinCode, setJoinCode] = useState<string | null>(null);
  const [serverDup, setServerDup] = useState<{ key: string; file: PatientCaseFile } | null>(null);
  const protocols = useProtocols();
  const owners = useOwnerChoices();
  const invalidate = useInvalidate();
  const onChange = (patch: Partial<NewCaseForm>) => setForm((f) => ({ ...f, ...patch }));

  // the built checklist only: a cancer with no checklist yet is named by its own name, not the generic rule's label
  const protocol = useMemo(() => (isGeneric(form.protocol) ? undefined : (protocols.data?.protocols ?? []).find((p) => p.id === form.protocol)), [protocols.data, form.protocol]);
  const settingLabel = protocol?.settings.find((s) => s.id === form.setting)?.label;
  const canCreate = Boolean(me && ((me.roles.treating || []).length || me.roles.coordinator));
  const pkey = patientKey(form);
  const files = usePatientCaseFiles(pkey);
  // the live Case File of this patient and the chosen cancer: listed by the server, or named by its 409 on Create
  const duplicate = duplicateFor(files.data?.cases, form) ?? (serverDup && serverDup.key === pkey && sameCancer(serverDup.file, form) ? serverDup.file : null);
  const stepOk = step === 1 ? Boolean(form.lookup?.found && form.lookup.patient) : step === 2 ? cancerStepDone(form) && !duplicate : logisticsDone(form, owners.length > 1) && !duplicate;

  const setFollow = (id: string, patch: Partial<FollowUp>) => setFollowUps((list) => list.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const create = async () => {
    if (!stepOk || creating) return;
    setCreating(true);
    setCreateErr(null);
    try {
      const r = await api.post<CreateFromHisResponse>(EP.fromHis, createBody(form, NOT_RECORDED));
      const caseId = r.case.case_id;
      const p = form.lookup?.patient;
      const line = [p?.name, ageSex(p?.age, p?.sex), p?.uhid ? `UHID ${p.uhid}` : ""].filter(Boolean).join(", ");
      const steps: FollowUp[] = [{ id: "urgency", label: `Urgency tag ${form.urgency} set`, state: "pending" }];
      if (form.boardQuestion.trim()) steps.push({ id: "question", label: "Board question saved", state: "pending" });
      if (form.outsideConsent) steps.push({ id: "consent", label: "Consent for outside experts recorded", state: "pending" });
      if (form.joinCode) steps.push({ id: "code", label: "Join code made for residents", state: "pending" });
      setFollowUps(steps);
      setCreated({ caseId, jobId: r.job || null, total: r.total ?? 0, patientLine: line || caseId });
      notify.success("Case File created", "Fetching the records now.");
      void invalidate(keys.caseLists);
      // The follow-ups run one after another; a failure is shown on its line and never undoes the Case File.
      const run = async (id: string, fn: () => Promise<unknown>) => {
        try { await fn(); setFollow(id, { state: "done" }); } catch (e) { setFollow(id, { state: "failed", detail: `${errorMessage(e)} Set it on the Case File.` }); }
      };
      await run("urgency", () => api.put(EP.urgency(caseId), { level: form.urgency }));
      if (form.boardQuestion.trim()) await run("question", () => api.post(`${EP.case(caseId)}/slots/${encodeURIComponent("fact:clinical_question")}/value`, { value: form.boardQuestion.trim() }));
      if (form.outsideConsent) await run("consent", () => api.put(`${EP.case(caseId)}/consent`, { outside_discussion: true }));
      if (form.joinCode) await run("code", async () => { const c = await api.post<{ code?: string; value?: string }>(EP.teamCode(caseId)); setJoinCode(c.code || c.value || null); });
    } catch (e) {
      const body = e instanceof ApiError && e.status === 409 && e.code === "duplicate_case_file" ? (e.detail as DuplicateCaseFileBody | null) : null;
      if (body?.existing) {  // created meanwhile by someone else: the same card as the list gives, and Create stays off
        setServerDup({ key: pkey, file: body.existing });
        void files.refetch();
      } else {
        setCreateErr(createError(e, form));
      }
    } finally {
      setCreating(false);
    }
  };

  if (!me) return null;
  if (!canCreate) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="New Case File" back={{ to: "/cases", label: "Case Files" }} />
        <div className="surface">
          <EmptyState kind="lock" title="Only treating doctors start a Case File" text="A Case File is owned by a treating department. Ask a consultant of the department, or the MDT Coordinator, to start it." action={<Button type="button" variant="outline" asChild><Link to="/home"><ArrowLeft className="size-4" aria-hidden /> Back to Case Files</Link></Button>} />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="New Case File"
        subtitle={created ? "Created. The records come in from the hospital system now." : "Three short steps. Nothing is created until you press Create."}
        back={{ to: "/cases", label: "Case Files" }}
      />
      {created ? (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="surface p-5 sm:p-6">
          <FetchProgress caseId={created.caseId} jobId={created.jobId} total={created.total} patientLine={created.patientLine} followUps={followUps} joinCode={joinCode} />
        </motion.div>
      ) : (
        <>
          <Stepper
            step={step}
            onStepChange={(n) => { if (n < step || stepOk) setStep(n); }}
            onFinalStepCompleted={() => void create()}
            linear
            nextDisabled={!stepOk}
            nextLoading={creating}
            nextButtonText="Continue"
            completeButtonText={creating ? "Creating" : "Create and fetch records"}
          >
            <Step title="Patient">
              <StepTitle title="Find the patient" text="The hospital system is asked; you see the registration before anything is made." />
              <StepPatient form={form} onChange={onChange} autoLookup={Boolean(initialId)} />
            </Step>
            <Step title="Cancer">
              <StepTitle title="Which cancer" text="The checklist decides which records the board needs." />
              <StepCancer form={form} onChange={onChange} />
              {duplicate ? <div className="mt-4"><DuplicateNotice file={duplicate} /></div> : null}
            </Step>
            <Step title="Logistics">
              <StepTitle title="Logistics" text="Filled in with the usual choices; change what does not fit." />
              <StepLogistics form={form} onChange={onChange} settingLabel={settingLabel} protocolLabel={protocol?.label} />
              {duplicate ? <div className="mt-4"><DuplicateNotice file={duplicate} /></div> : null}
              {createErr ? (
                <div role="alert" className="mt-4 flex items-start gap-2 rounded-md status-bad px-3 py-2 text-sm">
                  <Lock className="mt-0.5 size-4 shrink-0" aria-hidden /> <span>{createErr}</span>
                </div>
              ) : null}
            </Step>
          </Stepper>
          {!stepOk && step === 3 && !duplicate ? <p className="mt-2 text-center text-xs text-muted-foreground"><FolderPlus className="mr-1 inline size-3.5" aria-hidden />Pick an urgency tag{owners.length > 1 ? " and the Responsible Department" : ""} to create.</p> : null}
        </>
      )}
    </div>
  );
}
