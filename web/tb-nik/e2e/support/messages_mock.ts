// SYNTHETIC answers for the Messages screens in mock mode (night-v3 item 8.4): the routes of contract section 9.3 and the
// directory of 9.6, with their state kept in closures so a spec can send, edit, react and resolve; and the live socket
// (/api/tb/messages/ws) answering "pong" and passing on whatever the spec pushes. Fake people of the fictitious "Vaidyx Demo
// Hospital" only; Case File ids are the fixtures' synthetic ones. No real patient data.
import type { Page, Route, WebSocketRoute } from "@playwright/test";

export const ME = "rao@vxh.example";
export const C_DIRECT = "C1a2b3c4d5e";
export const C_RESOLVED = "C2b3c4d5e6f";
export const C_DEPT_MINE = "C3c4d5e6f7a";
export const C_DEPT_IN = "C4d5e6f7a8b";

type Presence = "online" | "away" | "offline";
type Person = { user: string; display_name: string; title: string; departments: Array<{ id: string; name: string; role: string }>; coordinator: boolean; online: Presence; photo: null; phone: null };
type Chip = { type: "case" | "meeting"; id: string; label: string | null; can_open: boolean; offer: boolean };
type Msg = {
  id: string; seq: number; ts: string; by: string; by_name: string; text: string; link: Chip | null; mentions: string[];
  edited: boolean; edited_ts: string | null; deleted: boolean; removed: boolean; reactions: Record<string, string[]>; can_edit_until: string | null;
};
type Conv = {
  id: string; kind: "direct" | "department" | "coordinator"; created_by: string; with: string | null; department: string | null;
  subtitle?: string; read: number; resolved: { by: string; ts: string } | null; muted: boolean; messages: Msg[]; seen_seq: number | null;
};

const PEOPLE: Person[] = [
  { user: "ravi@vxh.example", display_name: "Dr Ravi Kumar", title: "Consultant Radiologist", departments: [{ id: "radiology", name: "Radiology", role: "Consultant" }], coordinator: false, online: "online", photo: null, phone: null },
  { user: "menon@vxh.example", display_name: "Dr Suresh Menon", title: "Head of Radiology", departments: [{ id: "radiology", name: "Radiology", role: "Head" }], coordinator: false, online: "away", photo: null, phone: null },
  { user: "meena@vxh.example", display_name: "Dr Meena Iyer", title: "Consultant Pathologist", departments: [{ id: "pathology", name: "Pathology", role: "Head" }], coordinator: false, online: "away", photo: null, phone: null },
  { user: "verma@vxh.example", display_name: "Dr Anil Verma", title: "Consultant Medical Oncologist", departments: [{ id: "medical_oncology", name: "Medical Oncology", role: "Consultant" }], coordinator: false, online: "online", photo: null, phone: null },
  { user: "reddy@vxh.example", display_name: "Dr Kavya Reddy", title: "Resident", departments: [{ id: "breast_surgery", name: "Breast Surgery", role: "Resident" }], coordinator: false, online: "offline", photo: null, phone: null },
  { user: "mdt@vxh.example", display_name: "Priya Nair", title: "MDT Coordinator", departments: [], coordinator: true, online: "online", photo: null, phone: null },
  { user: ME, display_name: "Dr Lakshmi Rao", title: "Head of Breast Surgery", departments: [{ id: "breast_surgery", name: "Breast Surgery", role: "Head" }], coordinator: false, online: "online", photo: null, phone: null },
];
const DEPARTMENTS = [
  { id: "breast_surgery", name: "Breast Surgery", group: "treating", members: 5 },
  { id: "medical_oncology", name: "Medical Oncology", group: "treating", members: 3 },
  { id: "pathology", name: "Pathology", group: "supporting", members: 4 },
  { id: "radiology", name: "Radiology", group: "supporting", members: 6 },
];
const LINKS = {
  cases: [
    { id: "TB-2026-0031", label: "TB-2026-0031, Breast cancer" },
    { id: "TB-2026-0030", label: "TB-2026-0030, Breast cancer" },
    { id: "TB-2026-0029", label: "TB-2026-0029, Cervix cancer" },
    { id: "TB-2026-0019", label: "TB-2026-0019, Breast cancer" },
  ],
  meetings: [{ id: "M-1", label: "Tumour Board, Thursday (SYNTHETIC)" }],
};

const person = (u: string) => PEOPLE.find((p) => p.user === u);
const nameOf = (u: string) => person(u)?.display_name ?? u;
const caseChip = (id: string, open = true, offer = false): Chip => ({ type: "case", id, label: open ? LINKS.cases.find((c) => c.id === id)?.label ?? `${id}, Breast cancer` : null, can_open: open, offer: !open && offer });

export type MessagesMockOptions = { noticeSeen?: boolean; empty?: boolean; rateLimited?: boolean; notBuilt?: boolean };

/** Installs the Messages and directory routes (after prepare(); later routes win) and the socket. */
export async function routeMessages(page: Page, o: MessagesMockOptions = {}): Promise<{ push: (ev: Record<string, unknown>) => void; sent: () => Array<Record<string, unknown>> }> {
  const now = Date.now();
  const at = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString();
  let n = 0;
  const m = (seq: number, minAgo: number, by: string, text: string, extra: Partial<Msg> = {}): Msg => ({
    id: `M${String(++n).padStart(10, "0")}`, seq, ts: at(minAgo), by, by_name: nameOf(by), text, link: null, mentions: [], edited: false, edited_ts: null,
    deleted: false, removed: false, reactions: {}, can_edit_until: null, ...extra,
  });
  let noticeSeen = o.noticeSeen ?? true;
  const convs: Conv[] = o.empty ? [] : [
    { id: C_DIRECT, kind: "direct", created_by: ME, with: "ravi@vxh.example", department: null, read: 4, resolved: null, muted: false, seen_seq: 4, messages: [
      m(1, 26 * 60, ME, "Dr Ravi, could you look at the MRI in this Case File before Thursday's board?", { link: caseChip("TB-2026-0031"), reactions: { thumbs_up: ["ravi@vxh.example"] } }),
      m(2, 25 * 60, "ravi@vxh.example", "Yes, I will read it tomorrow morning and add the report.", { edited: true, edited_ts: at(25 * 60 - 3), reactions: { thanks: [ME] } }),
      m(3, 24 * 60, "ravi@vxh.example", "", { deleted: true }),
      m(4, 8, ME, "Thank you. The board meets at 2 pm on Thursday."),
      m(5, 5, "ravi@vxh.example", "The report is signed. There is an older CT in another department's Case File as well.", { link: caseChip("TB-2026-0027", false, true) }),
      m(6, 2, "ravi@vxh.example", "I can join the board from the reporting room."),
    ] },
    { id: C_RESOLVED, kind: "direct", created_by: "meena@vxh.example", with: "meena@vxh.example", department: null, read: 2, resolved: { by: ME, ts: at(20 * 60) }, muted: false, seen_seq: 2, messages: [
      m(1, 2 * 24 * 60, "meena@vxh.example", "The IHC slides of this Case File are ready for the board.", { link: caseChip("TB-2026-0030") }),
      m(2, 2 * 24 * 60 - 30, ME, "Thank you, I will present them on Thursday."),
    ] },
    { id: C_DEPT_MINE, kind: "department", created_by: ME, with: null, department: "radiology", subtitle: "Reaches 6 people", read: 2, resolved: null, muted: false, seen_seq: null, messages: [
      m(1, 3 * 24 * 60, ME, "Could someone add the mammogram report to this Case File?", { link: caseChip("TB-2026-0019") }),
      m(2, 3 * 24 * 60 - 45, "menon@vxh.example", "Added this morning. @Dr Lakshmi Rao please check the date on it.", { mentions: [ME] }),
    ] },
    { id: C_DEPT_IN, kind: "department", created_by: "verma@vxh.example", with: null, department: "breast_surgery", subtitle: "From Dr Anil Verma", read: 1, resolved: null, muted: true, seen_seq: null, messages: [
      m(1, 4 * 24 * 60, "verma@vxh.example", "Please share the date of the next breast clinic so the chemotherapy review can be planned around it."),
    ] },
  ];
  let next = 5;
  const sentBodies: Array<Record<string, unknown>> = [];

  const deptOf = (id: string | null) => DEPARTMENTS.find((d) => d.id === id);
  const lastMsg = (c: Conv) => c.messages[c.messages.length - 1];
  const unreadOf = (c: Conv) => c.messages.filter((x) => x.seq > c.read && x.by !== ME).length;
  const readersOf = (c: Conv) => {
    if (c.kind === "direct") return [ME, c.with!];
    if (c.kind === "coordinator") return [c.created_by, "mdt@vxh.example"];
    return [...new Set([c.created_by, ...PEOPLE.filter((p) => p.departments.some((d) => d.id === c.department)).map((p) => p.user)])];
  };
  const shapeMsg = (x: Msg): Msg => {
    const until = new Date(new Date(x.ts).getTime() + 600_000);
    return { ...x, text: x.deleted ? "" : x.text, can_edit_until: x.by === ME && !x.deleted && until.getTime() > Date.now() ? until.toISOString() : null };
  };
  const row = (c: Conv) => {
    const p = c.with ? person(c.with) : null;
    const d = deptOf(c.department);
    const last = lastMsg(c);
    return {
      id: c.id, kind: c.kind,
      title: c.kind === "direct" ? p?.display_name ?? c.with : c.kind === "department" ? d?.name ?? c.department : "MDT Coordinator",
      subtitle: c.subtitle ?? (p ? [p.title, ...p.departments.map((x) => x.name)].join(", ") : c.kind === "coordinator" ? "Reaches 1 coordinator" : ""),
      with: p ? { user: p.user, display_name: p.display_name, title: p.title, departments: p.departments.map((x) => x.name), online: p.online === "online", presence: p.online } : null,
      department: d ? { id: d.id, name: d.name, members: d.members } : null,
      created_by: c.created_by,
      last: last ? { seq: last.seq, ts: last.ts, by: last.by, by_name: last.by_name, preview: last.deleted ? "" : last.text.slice(0, 120) } : null,
      unread: unreadOf(c),
      resolved: c.resolved ? { ...c.resolved, by_name: nameOf(c.resolved.by) } : null,
      muted: c.muted,
    };
  };
  const view = (c: Conv) => ({
    conversation: row(c), messages: c.messages.map(shapeMsg), has_more: false,
    readers: readersOf(c).map((u) => ({ user: u, display_name: nameOf(u) })), seen_seq: c.kind === "direct" ? c.seen_seq : null, notice_seen: noticeSeen, retention_days: 365,
  });
  const total = () => convs.reduce((a, c) => a + unreadOf(c), 0);
  const sorted = () => [...convs].sort((a, b) => (lastMsg(b)?.ts ?? "").localeCompare(lastMsg(a)?.ts ?? ""));
  const chipFor = (link: unknown): Chip | null | "bad" => {
    if (!link || typeof link !== "object") return null;
    const l = link as { type?: string; id?: string };
    const list = l.type === "case" ? LINKS.cases : l.type === "meeting" ? LINKS.meetings : [];
    const hit = list.find((x) => x.id === l.id);
    return hit ? { type: l.type as "case" | "meeting", id: hit.id, label: hit.label, can_open: true, offer: false } : "bad";
  };
  const append = (c: Conv, body: { text?: string; link?: unknown; mentions?: string[] }): Msg | { status: number; body: unknown } => {
    const text = String(body.text ?? "").trim();
    if (!text) return { status: 400, body: { detail: { message: "Write a message first.", code: "empty" } } };
    if (text.length > 2000) return { status: 400, body: { detail: { message: "A message can have at most 2000 characters.", code: "too_long" } } };
    const chip = chipFor(body.link);
    if (chip === "bad") return { status: 400, body: { detail: { message: "You can only attach a Case File you can open.", code: "link_not_allowed" } } };
    const seq = (lastMsg(c)?.seq ?? 0) + 1;
    const x = m(seq, 0, ME, text, { link: chip, mentions: (body.mentions ?? []).slice(0, 8) });
    c.messages.push(x);
    c.read = seq;
    c.resolved = null;
    return x;
  };

  const handler = async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const meth = req.method();
    const p = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = (() => { try { return (req.postDataJSON() ?? {}) as Record<string, unknown>; } catch { return {}; } })();
    if (meth !== "GET") sentBodies.push({ method: meth, path: p, body });
    if (o.notBuilt) return json({ detail: "Not Found" }, 404);

    if (p === "/api/tb/directory") {
      const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
      const words = q.split(/\s+/).filter(Boolean);
      const hay = (s: string) => s.toLowerCase().split(/[\s,()]+/);
      const match = (s: string) => words.every((w) => hay(s).some((h) => h.startsWith(w)));
      const people = PEOPLE.filter((x) => !q || match([x.display_name, x.title, ...x.departments.map((d) => d.name)].join(" ")));
      return json({ people, departments: DEPARTMENTS.filter((d) => !q || match(d.name)), coordinators: PEOPLE.filter((x) => x.coordinator), me: ME });
    }
    const MP = "/api/tb/messages";
    if (p === `${MP}/unread`) return json({ unread_total: total() });
    if (p === `${MP}/links`) {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      return json({ cases: LINKS.cases.filter((x) => x.label.toLowerCase().includes(q)), meetings: LINKS.meetings.filter((x) => x.label.toLowerCase().includes(q)) });
    }
    if (p === `${MP}/notice` && meth === "POST") { noticeSeen = true; return json({ notice_seen: true }); }
    if (p === `${MP}/search`) {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const hits = q.length < 2 ? [] : sorted().flatMap((c) => c.messages.filter((x) => !x.deleted && (x.text.toLowerCase().includes(q) || x.by_name.toLowerCase().includes(q))).map((x) => ({ conversation_id: c.id, title: row(c).title, message: shapeMsg(x) })));
      return json({ hits: hits.slice(0, 50) });
    }
    if (p === `${MP}/conversations` && meth === "GET") {
      const f = url.searchParams.get("filter") ?? "all";
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const rows = sorted().map(row).filter((r) => (f === "unread" ? r.unread > 0 : f === "open" ? !r.resolved : f === "resolved" ? !!r.resolved : true))
        .filter((r) => !q || [r.title, r.subtitle, r.last?.preview ?? ""].join(" ").toLowerCase().includes(q));
      return json({ conversations: rows, unread_total: total() });
    }
    if (p === `${MP}/conversations` && meth === "POST") {
      const to = (body.to ?? {}) as { user?: string; department?: string; role?: string };
      if (to.user === ME) return json({ detail: { message: "You cannot message yourself.", code: "self_message" } }, 400);
      if (to.user && !person(to.user)) return json({ detail: { message: "That person cannot be reached.", code: "cannot_reach" } }, 400);
      if (to.department && !deptOf(to.department)) return json({ detail: { message: "That person cannot be reached.", code: "cannot_reach" } }, 400);
      let c = convs.find((x) => (to.user ? x.kind === "direct" && x.with === to.user : to.department ? x.kind === "department" && x.department === to.department && x.created_by === ME : x.kind === "coordinator" && x.created_by === ME));
      if (!c) {
        c = { id: `C${String(next++).padStart(10, "0")}`, kind: to.user ? "direct" : to.department ? "department" : "coordinator", created_by: ME, with: to.user ?? null, department: to.department ?? null,
          subtitle: to.department ? `Reaches ${deptOf(to.department)?.members ?? 0} people` : undefined, read: 0, resolved: null, muted: false, messages: [], seen_seq: to.user ? 0 : null };
        convs.push(c);
      }
      const x = append(c, body as { text?: string; link?: unknown; mentions?: string[] });
      if ("status" in x) return json(x.body, x.status);
      return json({ conversation: row(c), message: shapeMsg(x) }, 201);
    }
    const cm = /^\/api\/tb\/messages\/conversations\/([^/]+)(?:\/(.*))?$/.exec(p);
    if (cm) {
      const c = convs.find((x) => x.id === decodeURIComponent(cm[1]));
      if (!c) return json({ detail: { message: "No such conversation.", code: "not_found" } }, 404);
      const rest = cm[2] ?? "";
      if (!rest && meth === "GET") return json(view(c));
      if (rest === "messages" && meth === "POST") {
        if (o.rateLimited) return json({ detail: { message: "Too many messages. Please wait a moment.", code: "rate_limited" } }, 429);
        const x = append(c, body as { text?: string; link?: unknown; mentions?: string[] });
        if ("status" in x) return json(x.body, x.status);
        return json({ message: shapeMsg(x) });
      }
      if (rest === "read" && meth === "POST") { c.read = Math.max(c.read, Math.min(Number(body.seq) || 0, lastMsg(c)?.seq ?? 0)); return json({ unread_total: total() }); }
      if (rest === "resolve" && meth === "POST") { c.resolved = body.resolved ? { by: ME, ts: new Date().toISOString() } : null; return json({ conversation: row(c) }); }
      if (rest === "mute" && meth === "POST") { c.muted = !!body.muted; return json({ conversation: row(c) }); }
      const mm = /^messages\/([^/]+)(?:\/(react))?$/.exec(rest);
      if (mm) {
        const x = c.messages.find((y) => y.id === decodeURIComponent(mm[1]));
        if (!x) return json({ detail: { message: "No such message.", code: "not_found" } }, 404);
        if (mm[2] === "react" && meth === "POST") {
          const e = body.emoji as string | null;
          if (e === null) { for (const k of Object.keys(x.reactions)) x.reactions[k] = x.reactions[k].filter((u) => u !== ME); }
          else if (!["thumbs_up", "seen", "thanks", "will_do", "tick"].includes(e)) return json({ detail: { message: "That reaction is not one of the five.", code: "bad_reaction" } }, 400);
          else if (!(x.reactions[e] ?? []).includes(ME)) x.reactions[e] = [...(x.reactions[e] ?? []), ME];
          for (const k of Object.keys(x.reactions)) if (!x.reactions[k].length) delete x.reactions[k];
          return json({ message: shapeMsg(x) });
        }
        const own = x.by === ME && !x.deleted && Date.now() - new Date(x.ts).getTime() <= 600_000;
        if (meth === "PATCH" || meth === "DELETE") {
          if (!own) return json({ detail: { message: "You can only edit a message for 10 minutes.", code: "edit_window_over" } }, 403);
          if (meth === "PATCH") { x.text = String(body.text ?? "").trim(); x.edited = true; x.edited_ts = new Date().toISOString(); }
          else { x.deleted = true; x.text = ""; }
          return json({ message: shapeMsg(x) });
        }
      }
    }
    if (meth !== "GET") return json({ ok: true });
    return json({ detail: "Not Found" }, 404);
  };
  await page.route("**/api/tb/messages/**", handler);
  await page.route("**/api/tb/directory**", handler);

  let sockets: WebSocketRoute[] = [];
  await page.routeWebSocket(/\/api\/tb\/messages\/ws$/, (ws) => {
    sockets.push(ws);
    ws.onMessage((msg) => { try { const d = JSON.parse(String(msg)); if (d.type === "ping") ws.send(JSON.stringify({ type: "pong" })); else sentBodies.push({ ws: d }); } catch { /* not JSON */ } });
    ws.onClose(() => { sockets = sockets.filter((x) => x !== ws); });
  });
  return { push: (ev) => { for (const ws of sockets) ws.send(JSON.stringify(ev)); }, sent: () => sentBodies };
}
