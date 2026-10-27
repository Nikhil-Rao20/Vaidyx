// Step 2: the cancer. The ten commonest per group (NCRP 2020, lib/cancers.ts), the group taken from the record's sex and
// age (one tap shows all), a search, and a typed name for a cancer that is not listed. A cancer with a built checklist
// (GET /protocols) shows it; one without goes under the generic rule (protocol "generic": four core records, owner decision
// R05-Q04) with its name, and has no setting to choose ("as_recorded" is sent). A typed cancer asks solid or blood first (night-v3
// item 2.9: a blood cancer goes under "generic_haem", the marrow or immunophenotype instead of staging imaging). Colorectal and
// Kidney ask one more question (colon or rectum; adult or child) before the setting (item 2.10). A draft checklist (version
// "x-draft", owner decision D6) says so on its card. The NCG setting "as recorded" of a built checklist is chosen by the doctor
// (GET /protocols/{pid}); the hospital level comes from the set-up, read only.
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { BookOpenCheck, Check, CircleHelp, ClipboardList, Hospital, PenLine, TriangleAlert } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SearchBox } from "@/components/SearchBox";
import { ErrorState } from "@/components/ErrorState";
import { useProtocols } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import {
  BUILT_DRAFT_WORDS, BUILT_WORDS, CANCER_NAME_MAX, CANCER_NAME_MIN, DRAFT_CHECKLIST, GENERIC_SETTING, GROUP_LABELS, KIND_CHOICES, fallbackFor, nameFor,
  KIND_QUESTION, SOURCE_NOTE, cancerById, cancersFor, cleanCancerName, defaultVariant, genericRecords, genericRule, groupFor, isDraftChecklist,
  isGeneric, protocolFor, protocolsOf, searchCancers, variantOf, type CancerEntry, type CancerGroup, type CancerVariant,
} from "@/lib/cancers";
import type { ProtocolSetting, ProtocolSummary } from "@/lib/types";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import type { NewCaseForm } from "@/features/newcase/form";

const GROUPS: CancerGroup[] = ["men", "women", "children", "general"];
/** A list entry that is not a cancer's name ("Others" in the children's list): picking it opens the typed name. */
const TYPE_INSTEAD = new Set(["other_child"]);

export const NOT_RECORDED = "__not_recorded__";

interface ProtocolDetail extends ProtocolSummary {
  settings: Array<ProtocolSetting & { definition_source?: string }>;
}

function levelWord(level?: string): string {
  if (!level) return "not set yet";
  return level.charAt(0).toUpperCase() + level.slice(1);
}

export function StepCancer({ form, onChange }: { form: NewCaseForm; onChange: (patch: Partial<NewCaseForm>) => void }) {
  const { me } = useSession();
  const protocols = useProtocols();
  const built = useMemo(() => new Map((protocols.data?.protocols ?? []).map((p) => [p.id, p])), [protocols.data]);
  const p = form.lookup?.patient;
  const suggested = groupFor(p?.sex, p?.age);
  const [group, setGroup] = useState<CancerGroup>(suggested);
  const [search, setSearch] = useState("");
  const [typing, setTyping] = useState(form.cancerId === "custom");
  const picked = form.cancerId && form.cancerId !== "custom" ? cancerById(form.cancerId) : undefined;
  const variant = picked ? variantOf(picked, form.variant) : undefined;
  const generic = isGeneric(form.protocol);
  // a typed cancer not yet marked solid or blood, or a Colorectal / Kidney pick without its answer: nothing to show below yet
  const waiting = Boolean(form.cancerId && !form.protocol);
  const protocolId = form.protocol && !generic && built.has(form.protocol) ? form.protocol : null;
  const checklistLoading = Boolean(form.protocol && !generic && !protocolId && protocols.isLoading);  // never flash the generic rule for a built checklist
  const typedName = cleanCancerName(form.cancerName);
  const nameError = form.cancerId === "custom" && form.cancerName.length > 0 && typedName.length < CANCER_NAME_MIN
    ? `Type at least ${CANCER_NAME_MIN} characters` : null;
  const detail = useQuery<ProtocolDetail, Error>({
    queryKey: ["protocol", protocolId],
    queryFn: () => api.get<ProtocolDetail>(EP.protocol(protocolId as string)),
    enabled: Boolean(protocolId),
    staleTime: 10 * 60_000,
    retry: 1,
  });
  const settings: Array<ProtocolSetting & { definition_source?: string }> = detail.data?.settings ?? (protocolId ? built.get(protocolId)?.settings ?? [] : []);
  const draft = protocolId ? isDraftChecklist(built.get(protocolId)) : false;

  // When the checklist list arrives, a picked cancer whose checklist is not built falls back to the generic rule.
  useEffect(() => {
    // a blood cancer entry (Leukaemia, Lymphoma) falls back to the blood cancer rule, any other to the solid one
    if (form.protocol && !isGeneric(form.protocol) && protocols.data && !built.has(form.protocol)) onChange({ protocol: fallbackFor(picked), setting: GENERIC_SETTING });
  }, [protocols.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const known = protocols.data ? built : null;
  // A typed cancer starts with no checklist: the doctor marks it solid ("generic") or blood ("generic_haem") under the name box.
  const startTyping = (name: string) => {
    setTyping(true);
    onChange({ cancerId: "custom", cancerName: name, protocol: null, variant: "", setting: GENERIC_SETTING });
  };
  const choose = (c: CancerEntry) => {
    if (TYPE_INSTEAD.has(c.id)) { startTyping(search.trim()); return; }
    const v = defaultVariant(c, p?.age);  // Kidney: Wilms tumour for a child under 15, renal cell carcinoma otherwise; Colorectal: none
    const protocol = protocolFor(c, known, v?.id);
    setTyping(false);
    onChange({ cancerId: c.id, cancerName: nameFor(c, v), variant: v?.id ?? "", protocol, setting: protocol && isGeneric(protocol) ? GENERIC_SETTING : "" });
  };
  const chooseVariant = (v: CancerVariant) => {
    if (!picked) return;
    const protocol = protocolFor(picked, known, v.id);
    onChange({ variant: v.id, cancerName: nameFor(picked, v), protocol, setting: protocol && isGeneric(protocol) ? GENERIC_SETTING : "" });
  };
  const list = search.trim() ? searchCancers(search) : cancersFor(group);
  // the checklists an entry leads to that the server lists (all of them before the list arrives)
  const builtOf = (c: CancerEntry) => protocolsOf(c).filter((id) => !isGeneric(id) && (!known || known.has(id)));

  return (
    <div className="grid gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={search.trim() ? "" : group} onValueChange={(v) => { setGroup(v as CancerGroup); setSearch(""); }}>
          <TabsList aria-label="Group">
            {GROUPS.map((g) => (
              <TabsTrigger key={g} value={g} className="gap-1">
                {GROUP_LABELS[g]}
                {g === suggested && g !== "general" ? <span className="sr-only"> (from the record)</span> : null}
                {g === suggested && g !== "general" ? <span className="size-1.5 rounded-full bg-primary" aria-hidden /> : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <SearchBox value={search} onChange={setSearch} placeholder="Search a cancer" label="Search a cancer" wrapperClassName="sm:w-64" />
      </div>
      {suggested !== "general" && !search.trim() ? (
        <p className="-mt-2 text-xs text-muted-foreground">
          {GROUP_LABELS[suggested]} shown first from the record ({[p?.age, p?.sex].filter(Boolean).join(", ")}). One tap on All shows every cancer.
        </p>
      ) : null}

      <div role="radiogroup" aria-label="Cancer" className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c, i) => {
          const on = form.cancerId === c.id;
          const ids = builtOf(c);
          const ok = ids.length > 0;
          const isDraft = ids.some((id) => isDraftChecklist(built.get(id)));
          return (
            <motion.button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => choose(c)}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: Math.min(i, 10) * 0.02 }}
              whileTap={{ scale: 0.98 }}
              className={cn(
                "row-lift flex min-h-12 items-center gap-3 rounded-md border bg-card px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
                on ? "border-primary bg-secondary text-secondary-foreground" : "border-border hover:border-tint-line hover:bg-accent",
              )}
            >
              {!search.trim() && group !== "general" ? <span className="w-5 shrink-0 text-right text-xs font-bold tabular-nums text-muted-foreground">{i + 1}</span> : null}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-foreground">{c.label}</span>
                <span className={cn("flex items-center gap-1 text-xs", ok ? "text-ok" : "text-muted-foreground")}>
                  {ok ? <><ClipboardList className="size-3" aria-hidden /> checklist built</> : <><CircleHelp className="size-3" aria-hidden /> no checklist yet</>}
                  {ok && isDraft ? <span className="ml-1 rounded-sm status-warn px-1 text-[11px] font-semibold leading-4" title={DRAFT_CHECKLIST}><span aria-hidden>draft</span><span className="sr-only">{DRAFT_CHECKLIST}</span></span> : null}
                </span>
              </span>
              {on ? <Check className="size-4 shrink-0 text-primary" aria-hidden /> : null}
            </motion.button>
          );
        })}
        {!list.length ? <p className="text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">No cancer in the list matches "{search}". Type it below.</p> : null}
      </div>

      <div className="flex flex-col gap-2">
        {!typing ? (
          <Button type="button" variant="ghost" size="sm" className="w-fit" onClick={() => startTyping(search.trim())}>
            <PenLine className="size-4" aria-hidden /> The cancer is not listed: type its name
          </Button>
        ) : (
          <>
            <Field id="cancer-name" label="Cancer, as written in the record" className="sm:max-w-md" error={nameError}
              hint={nameError ? undefined : `${CANCER_NAME_MIN} to ${CANCER_NAME_MAX} characters. It is shown on the Case File and in every list.`}>
              <Input value={form.cancerName} onChange={(e) => onChange({ cancerId: "custom", cancerName: e.target.value, setting: GENERIC_SETTING })}
                placeholder="e.g. Urinary bladder" autoFocus maxLength={CANCER_NAME_MAX} autoComplete="off" />
            </Field>
            <fieldset className="grid gap-2 sm:max-w-xl" data-testid="cancer-kind">
              <legend className="mb-1 text-sm font-medium">{KIND_QUESTION} <span className="text-xs font-normal text-bad">required</span></legend>
              <RadioGroup value={isGeneric(form.protocol) ? (form.protocol as string) : ""} onValueChange={(v) => onChange({ cancerId: "custom", protocol: v, setting: GENERIC_SETTING })} className="grid gap-2 sm:grid-cols-2">
                {KIND_CHOICES.map((k) => (
                  <Label key={k.protocol} htmlFor={`kind-${k.protocol}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-secondary/50">
                    <RadioGroupItem id={`kind-${k.protocol}`} value={k.protocol} className="mt-0.5" />
                    <span className="text-sm font-medium text-foreground">{k.label}</span>
                  </Label>
                ))}
              </RadioGroup>
            </fieldset>
          </>
        )}
        <p className="text-xs text-muted-foreground">{SOURCE_NOTE}</p>
      </div>

      {protocols.error && !protocols.data ? <ErrorState compact error={protocols.error} what="the checklists" onRetry={() => void protocols.refetch()} retrying={protocols.isFetching} /> : null}

      {form.cancerId ? (
        <motion.section initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="surface-inner grid gap-4 p-4" aria-label="Checklist and setting">
          {picked?.variants?.length ? (
            <fieldset className="grid gap-2" data-testid="cancer-variant">
              <legend className="mb-1 text-sm font-medium">{picked.question ?? "Which one?"} <span className="text-xs font-normal text-bad">required</span></legend>
              <RadioGroup value={variant?.id ?? ""} onValueChange={(id) => { const v = variantOf(picked, id); if (v) chooseVariant(v); }} className="grid gap-2 sm:grid-cols-2">
                {picked.variants.map((v) => (
                  <Label key={v.id} htmlFor={`variant-${v.id}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-secondary/50">
                    <RadioGroupItem id={`variant-${v.id}`} value={v.id} className="mt-0.5" />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-foreground">{v.label}</span>
                      {isGeneric(v.protocol) ? <span className="block text-xs text-muted-foreground">No checklist yet: the core records only</span>
                        : built.get(v.protocol) ? <span className="block text-xs text-muted-foreground">{built.get(v.protocol)?.label} checklist</span> : null}
                    </span>
                  </Label>
                ))}
              </RadioGroup>
              {picked.childDefault && variant ? <p className="text-xs text-muted-foreground">Chosen from the patient's age on the record; change it if the records say otherwise.</p> : null}
            </fieldset>
          ) : null}

          {waiting ? (
            <p className="text-sm text-muted-foreground" data-testid="cancer-waiting">{form.cancerId === "custom" ? "Answer solid or blood above to see what is checked." : "Pick one above to see its checklist."}</p>
          ) : protocolId ? (
            <div className="flex flex-wrap items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-md status-ok"><BookOpenCheck className="size-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold">{built.get(protocolId)?.label ?? protocolId} checklist</p>
                <p className={cn("flex items-center gap-1 text-xs", draft ? "text-warn" : "text-ok")} data-testid="checklist-status">
                  <ClipboardList className="size-3 shrink-0" aria-hidden />{draft ? BUILT_DRAFT_WORDS : BUILT_WORDS}
                </p>
                {variant?.note ?? picked?.note ? <p className="text-xs text-muted-foreground">{variant?.note ?? picked?.note}</p> : null}
                {draft ? (
                  <>
                    {/* the Pill's look, but wrapping on a phone instead of cutting the owner's wording */}
                    <span className="mt-1.5 inline-flex max-w-full items-start gap-1 rounded-md px-2 py-0.5 text-xs font-medium status-warn">
                      <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden /><span>{DRAFT_CHECKLIST}</span>
                    </span>
                    <p className="mt-1 text-xs text-muted-foreground">Built from the Indian guideline book, every record quoted with its page. Not yet checked by a clinician of this hospital.</p>
                  </>
                ) : null}
              </div>
            </div>
          ) : checklistLoading ? (
            <div className="space-y-2" aria-busy="true" aria-label="Loading the checklist"><div className="skeleton-line h-5 w-48" /><div className="skeleton-line h-4 w-72" /></div>
          ) : (
            <div className="flex flex-wrap items-start gap-3" data-testid="generic-rule">
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><CircleHelp className="size-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold break-words">{typedName || "This cancer"}: no checklist yet</p>
                <p className="text-sm text-foreground">{genericRule(form.protocol)}:</p>
                <ul className="mt-1.5 grid gap-1 text-sm">
                  {genericRecords(form.protocol).map((r) => (
                    <li key={r} className="flex items-start gap-2"><ClipboardList className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />{r}</li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">Nothing cancer-specific is asked for and there is no setting to choose. A checklist can be chosen later when one is built.</p>
              </div>
            </div>
          )}

          {protocolId ? (
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">NCG setting, as recorded <span className="text-xs font-normal text-bad">required</span></legend>
              <p className="-mt-1 mb-1 text-xs text-muted-foreground">Pick what the records say. Vaidyx never works out a stage; it uses your choice to know which records the board needs.</p>
              {detail.isLoading && !settings.length ? (
                <div className="space-y-2" aria-busy="true"><div className="skeleton-line h-10" /><div className="skeleton-line h-10" /></div>
              ) : (
                <RadioGroup value={form.setting} onValueChange={(v) => onChange({ setting: v })} className="grid gap-2">
                  {[...settings, { id: NOT_RECORDED, label: "Not recorded yet", definition: "The records do not say yet; choose later on the Case File." }].map((s) => (
                    <Label key={s.id} htmlFor={`setting-${s.id}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-secondary/50">
                      <RadioGroupItem id={`setting-${s.id}`} value={s.id} className="mt-0.5" />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-foreground">{s.label}</span>
                        {s.definition ? <span className="block text-xs text-muted-foreground">{s.definition}</span> : null}
                        {"definition_source" in s && s.definition_source ? <span className="block text-[11px] text-muted-foreground">Source: {s.definition_source}</span> : null}
                      </span>
                    </Label>
                  ))}
                </RadioGroup>
              )}
            </fieldset>
          ) : null}

          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Hospital className="size-4" aria-hidden /> Hospital level: <span className="font-medium text-foreground">{levelWord(me?.hospital?.level)}</span>
            <span className="text-xs">(from the hospital set-up)</span>
          </p>
        </motion.section>
      ) : null}
    </div>
  );
}

/** Step 2 is complete when a cancer is picked (a typed name of 2 to 80 characters counts, marked solid or blood), the entry's
 * follow-up question is answered (Colorectal, Kidney) and, with a built checklist, a setting is chosen; the generic rule has no
 * setting to choose. */
export function cancerStepDone(form: NewCaseForm): boolean {
  if (!form.cancerId || !form.protocol) return false;
  const entry = form.cancerId !== "custom" ? cancerById(form.cancerId) : undefined;
  if (entry?.variants?.length && !variantOf(entry, form.variant)) return false;
  const n = cleanCancerName(form.cancerName).length;
  if (form.cancerId === "custom" || isGeneric(form.protocol)) return n >= CANCER_NAME_MIN && n <= CANCER_NAME_MAX;
  return Boolean(form.setting);
}
