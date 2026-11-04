// Follow and drive (meetings-v2 item 2.4, owner decisions D2 and D4): the Board view of the Case File on the floor is led by the MDT
// Coordinator, or by the case's presenter while presenting. The driver's clicks post the follow state (POST /meetings/{mid}/view); the
// driver's own view moves at once (optimistic) and the server's answer and the socket's "view" event confirm it. Everyone else follows
// the state as it comes (the room and every remote member render the same tab, report, page and line). A remote member may "Look around"
// (clicks stay on this screen, nothing is posted) and come "Back to the room". Nothing here decides what a person may read: the server's
// meeting window gives the admitted members read-only access to the Case File on the floor.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { errorText } from "@/features/casefile/components/common";
import { drName } from "@/lib/format";
import type { BoardTab, BoardViewState, MeetingState, Opened } from "@/lib/live";
import { setView } from "../api";

export type BoardMode = "drive" | "follow" | "look";

/** Where the Board view stands: a tab, and on Reports or Images a record (with its page and highlighted line on Reports). */
export interface BoardPosition {
  tab: BoardTab;
  doc_id: string | null;
  /** 0-based page of the record. */
  page: number | null;
  quote: string;
  /** What the server opened for this position (the images' viewer url); absent for a local position. */
  opened?: Opened | null;
}

export type BoardNavigate = (tab: BoardTab, docId?: string | null, page?: number | null, quote?: string | null) => void;

/** The server keeps at most 300 characters of the highlighted line: a longer line is cut at a word, so the post is never refused. */
export const QUOTE_MAX = 300;
export function clipQuote(q?: string | null): string {
  const t = String(q ?? "").replace(/\s+/g, " ").trim();
  if (t.length <= QUOTE_MAX) return t;
  const cut = t.slice(0, QUOTE_MAX);
  const sp = cut.lastIndexOf(" ");
  return (sp > QUOTE_MAX * 0.6 ? cut.slice(0, sp) : cut).trim();
}

function position(tab: BoardTab, docId?: string | null, page?: number | null, quote?: string | null): BoardPosition {
  const doc = docId || null;
  return { tab, doc_id: doc, page: doc ? (typeof page === "number" && page >= 0 ? Math.floor(page) : 0) : null, quote: doc ? clipQuote(quote) : "" };
}

const SUMMARY: BoardPosition = { tab: "summary", doc_id: null, page: null, quote: "", opened: null };
const time = (iso?: string) => { const t = Date.parse(iso ?? ""); return Number.isFinite(t) ? t : -Infinity; };

/** The admitted login that may lead the Board view now: the coordinator (manage), or the presenter of the Case File on the floor. The
 *  server checks the same rule on every post (meetings.may_drive). */
export function mayDrive(state: MeetingState | null | undefined): boolean {
  if (!state || state.meeting.status !== "in_session" || !state.current?.case_id) return false;
  if (state.can?.manage) return true;
  const me = state.me?.user;
  const admitted = state.me?.status === "present" || state.me?.status === "remote";
  return !!me && admitted && state.current?.presenter?.user === me;
}

export interface Follow {
  /** The Case File on the floor (null: nothing on the floor, or the meeting is not in session). */
  caseId: string | null;
  tab: BoardTab;
  docId: string | null;
  page: number | null;
  quote: string;
  /** What is shown, ready for <BoardView view={...}>. */
  view: BoardPosition;
  mode: BoardMode;
  /** A click in the Board view: posted when driving, local when looking around; a follower who may look around starts looking. */
  navigate: BoardNavigate;
  lookAround: () => void;
  backToRoom: () => void;
  /** "Dr Lakshmi Rao" for the presenter, the plain name for anyone else; "" when the server named nobody. */
  followingName: string;
  /** This screen may look around (a remote member); false for the room screen, which always follows. */
  canLook: boolean;
  /** A post is on its way. */
  pending: boolean;
  /** The server refused the last post, in its plain words (cleared by the next click, or after 8 s). */
  error: string | null;
}

/** The follow state of one meeting for this screen. `state` is the live meeting state (useMeetingLive); `canDrive` defaults to
 *  mayDrive(state); `canLook` (default true) is false on the room screen. */
export function useFollow({ mid, state, canDrive, canLook = true }: { mid: string; state: MeetingState | null | undefined; canDrive?: boolean; canLook?: boolean }): Follow {
  const server = state?.view ?? null;
  const floor = state?.meeting.status === "in_session" ? state?.current?.case_id ?? null : null;
  const caseId = (server && server.case_id === floor ? server.case_id : floor) || null;
  const drive = (canDrive ?? mayDrive(state)) && !!caseId;

  // the driver: the click not yet answered (optimistic), then the server's answer until the socket brings the same or a newer state
  const [optimistic, setOptimistic] = useState<(BoardPosition & { case_id: string }) | null>(null);
  const [confirmed, setConfirmed] = useState<BoardViewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  // a follower looking around: the local position, of the Case File it was taken on
  const [look, setLook] = useState<(BoardPosition & { case_id: string }) | null>(null);

  // another Case File on the floor: the local positions belong to the old one (a member looking around comes back to the room)
  useEffect(() => {
    setOptimistic((o) => (o && o.case_id !== caseId ? null : o));
    setConfirmed((c) => (c && c.case_id !== caseId ? null : c));
    setLook((l) => (l && l.case_id !== caseId ? null : l));
  }, [caseId]);
  // a driver no longer driving (the presenter after Next) follows; a driver never looks around on its own
  useEffect(() => { if (drive) setLook(null); else { setOptimistic(null); setConfirmed(null); } }, [drive]);
  useEffect(() => {
    if (!error) return;
    const t = window.setTimeout(() => setError(null), 8000);
    return () => window.clearTimeout(t);
  }, [error]);

  const room: BoardPosition = useMemo(() => {
    const s = server && server.case_id === caseId ? server : null;
    const c = confirmed && confirmed.case_id === caseId ? confirmed : null;
    // the driver's own answer wins a tie: the socket's event for it is on its way
    const v = drive && c && (!s || time(c.at) >= time(s.at)) ? c : s;
    return v ? { tab: v.tab, doc_id: v.doc_id, page: v.page, quote: v.quote, opened: v.opened } : SUMMARY;
  }, [server, confirmed, caseId, drive]);

  const mode: BoardMode = drive ? "drive" : look && canLook ? "look" : "follow";
  const shown: BoardPosition = mode === "drive" && optimistic ? keepOpened(optimistic, room) : mode === "look" && look ? look : room;

  const navigate: BoardNavigate = useCallback((tab, docId, page, quote) => {
    if (!caseId) return;
    const p = position(tab, docId, page, quote);
    setError(null);
    if (drive) {
      const n = ++seq.current;
      setOptimistic({ ...p, case_id: caseId });
      setView(mid, { tab: p.tab, doc_id: p.doc_id, page: p.page, quote: p.quote })
        .then((r) => {
          if (n !== seq.current) return;
          const v = r?.view;
          if (v && v.case_id === caseId) setConfirmed(v);
          setOptimistic(null);
        })
        .catch((e) => {
          if (n !== seq.current) return;
          setOptimistic(null);
          setError(errorText(e));
        });
      return;
    }
    if (!canLook) return;  // the room screen always follows
    setLook({ ...p, case_id: caseId });
  }, [caseId, drive, canLook, mid]);

  const lookAround = useCallback(() => {
    if (!caseId || drive || !canLook) return;
    setLook((l) => l ?? { ...room, case_id: caseId });
  }, [caseId, drive, canLook, room]);
  const backToRoom = useCallback(() => setLook(null), []);

  const by = server && server.case_id === caseId ? server : null;
  const presenter = state?.current?.presenter?.user;
  const followingName = by?.by_name ? (presenter && by.by === presenter ? drName(by.by_name) : by.by_name) : "";

  return {
    caseId, tab: shown.tab, docId: shown.doc_id, page: shown.page, quote: shown.quote, view: shown, mode, navigate, lookAround, backToRoom,
    followingName, canLook: canLook && !drive, pending: !!optimistic, error,
  };
}

/** The driver's click before the answer: what the server opened for the same record stays (a page turn of an open report). */
function keepOpened(p: BoardPosition, room: BoardPosition): BoardPosition {
  const same = room.opened && p.doc_id && room.opened.doc_id === p.doc_id && (p.tab === "images") === (room.opened.kind === "images");
  return { ...p, opened: same ? room.opened : null };
}
