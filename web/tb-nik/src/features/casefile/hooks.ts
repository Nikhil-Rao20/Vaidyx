// Data hooks for the Case File page. The Case File is polled every 30 s; a change is held back behind the
// "N new since you looked" banner so the page never moves under the doctor's hands; the doctor's own actions adopt the
// fresh state at once.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/lib/session";
import { ApiError } from "@/lib/api";
import { deriveSlots, deriveTeam, getCase, getJob, getProposals, getSlots, getTeam, notBuiltYet, ownerOf } from "./api";
import type { CaseFile, Job, Proposal, SlotsResponse, Team } from "./types";

export const POLL_MS = 30_000;

export function caseSignature(cf: CaseFile | null | undefined): string {
  if (!cf) return "";
  if (cf.signature?.hash) return cf.signature.hash;
  const docs = (cf.documents ?? []).map((d) => `${d.doc_id}:${d.state}`).sort().join("|");
  const acts = (cf.state?.actions ?? []).map((a) => `${a.id}:${a.status}`).sort().join("|");
  return `${docs}#${acts}#${cf.case?.board_ready?.at ?? ""}`;
}

export function useCaseFile(id: string) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["case", id],
    queryFn: ({ signal }) => getCase(id, signal),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    retry: (count, err) => !(err instanceof ApiError && (err.status === 403 || err.status === 404)) && count < 1,
  });
  const [shown, setShown] = useState<CaseFile | null>(null);
  const adoptNext = useRef(true);

  useEffect(() => {
    if (!q.data) return;
    if (adoptNext.current || !shown) { setShown(q.data); adoptNext.current = false; }
  }, [q.data, shown]);

  const latestSig = caseSignature(q.data);
  const shownSig = caseSignature(shown);
  const stale = !!shown && !!q.data && latestSig !== shownSig;
  const newCount = useMemo(() => {
    if (!stale || !q.data || !shown) return 0;
    const before = new Set((shown.documents ?? []).map((d) => d.doc_id));
    const added = (q.data.documents ?? []).filter((d) => !before.has(d.doc_id)).length;
    return Math.max(1, added);
  }, [stale, q.data, shown]);

  const show = useCallback(() => { if (q.data) setShown(q.data); void qc.invalidateQueries({ queryKey: ["slots", id] }); }, [q.data, qc, id]);
  const refresh = useCallback(async () => {
    adoptNext.current = true;
    await qc.invalidateQueries({ queryKey: ["case", id] });
    await qc.invalidateQueries({ queryKey: ["slots", id] });
  }, [qc, id]);

  return { data: shown, latest: q.data, isLoading: q.isLoading && !shown, error: q.error, stale, newCount, show, refresh, refetch: q.refetch };
}

export function useSlots(id: string, cf: CaseFile | null) {
  const q = useQuery({
    queryKey: ["slots", id],
    queryFn: () => getSlots(id),
    retry: false,
    enabled: !!cf,
  });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const data: SlotsResponse | null = useMemo(() => {
    if (q.data) return q.data;
    if (notBuilt && cf) return deriveSlots(cf);
    return null;
  }, [q.data, notBuilt, cf]);
  return { data, derived: notBuilt, isLoading: q.isLoading, error: notBuilt ? null : q.error, refetch: q.refetch };
}

export function useTeam(id: string, cf: CaseFile | null, enabled = true) {
  const q = useQuery({ queryKey: ["team", id], queryFn: () => getTeam(id), retry: false, enabled: enabled && !!cf });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const data: Team | null = q.data ?? (notBuilt && cf ? deriveTeam(cf) : null);
  return { data, derived: notBuilt, isLoading: q.isLoading, error: notBuilt ? null : q.error, refetch: q.refetch };
}

export function useProposals(id: string, enabled = true) {
  const q = useQuery({ queryKey: ["proposals", id], queryFn: () => getProposals(id), retry: false, enabled, refetchInterval: POLL_MS });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const proposals: Proposal[] = q.data?.proposals ?? [];
  return { proposals, notBuilt, isLoading: q.isLoading, error: notBuilt ? null : q.error, refetch: q.refetch };
}

/** Polls a job every 1.5 s until it finishes; onDone fires once. */
export function useJob(jobId: string | null, onDone?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const doneRef = useRef<string | null>(null);
  useEffect(() => {
    if (!jobId) { setJob(null); return; }
    let stop = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const j = await getJob(jobId);
        if (stop) return;
        setJob(j);
        if (j.state === "finished" || j.state === "failed") {
          if (doneRef.current !== jobId) { doneRef.current = jobId; onDone?.(j); }
          return;
        }
      } catch (e) {
        if (stop) return;
        setJob((old) => old ?? { id: jobId, total: 0, done: 0, events: [], state: "running" });
        if (e instanceof ApiError && e.status === 404) { doneRef.current = jobId; return; }
      }
      timer = window.setTimeout(tick, 1500);
    };
    void tick();
    return () => { stop = true; if (timer) window.clearTimeout(timer); };
  }, [jobId, onDone]);
  return job;
}

/** Is the signed-in person a resident on this Case File (proposes instead of signing)? */
export function useMyRole(cf: CaseFile | null) {
  const { me } = useSession();
  return useMemo(() => {
    const owner = ownerOf(cf).id;
    const placement = me?.roles?.departments?.[owner];
    const resident = me?.primary_role === "resident" || placement === "resident";
    const coordinator = !!me?.roles?.coordinator;
    const consultant = !resident && (placement === "member" || placement === "head" || (me?.roles?.treating ?? []).includes(owner));
    return { me, resident, coordinator, consultant, ownerDepartment: owner };
  }, [me, cf]);
}

/** Remember the last opened Case File for the "last Case File" start page. */
export function useRememberCase(id: string) {
  useEffect(() => { try { localStorage.setItem("tbnik.lastCase", id); } catch { /* storage blocked */ } }, [id]);
}
