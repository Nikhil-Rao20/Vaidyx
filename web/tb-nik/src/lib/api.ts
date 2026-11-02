// The one place the new interface talks to the backend. Same-origin cookies,
// a custom header on every request (the server refuses state-changing calls
// without it, which stops cross-site form posts), plain error objects.

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;
  constructor(status: number, message: string, code = "", detail: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

type Listener = (err: ApiError) => void;
const listeners: { unauthenticated: Listener[]; mustChange: Listener[] } = { unauthenticated: [], mustChange: [] };

export function onUnauthenticated(fn: Listener) {
  listeners.unauthenticated.push(fn);
  return () => { listeners.unauthenticated = listeners.unauthenticated.filter((f) => f !== fn); };
}
export function onMustChangePassword(fn: Listener) {
  listeners.mustChange.push(fn);
  return () => { listeners.mustChange = listeners.mustChange.filter((f) => f !== fn); };
}

// The server signs a person out of the Tumour Board after 8 hours without activity. A request made while nobody has touched the
// page for a while (a poll, a background refresh) says so, so an open tab on an unattended workstation does not count as activity.
const QUIET_MS = 5 * 60_000;
let lastInput = Date.now();
if (typeof window !== "undefined") {
  for (const ev of ["pointerdown", "keydown", "wheel", "touchstart"]) {
    window.addEventListener(ev, () => { lastInput = Date.now(); }, { passive: true, capture: true });
  }
}

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: Method;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Do not route 401 to the sign-in page (used by the sign-in page itself). */
  quiet401?: boolean;
  headers?: Record<string, string>;
}

function messageFor(status: number, data: unknown): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    const m = d.message ?? d.detail ?? d.error;
    if (typeof m === "string") return m;
    if (m && typeof m === "object" && "message" in (m as object)) return String((m as { message: unknown }).message);
  }
  switch (status) {
    case 400: return "The request was not understood.";
    case 401: return "Please sign in.";
    case 403: return "You do not have permission for this.";
    case 404: return "Not found.";
    case 409: return "This clashes with the current state.";
    case 413: return "The file is too large.";
    case 429: return "Too many attempts. Please wait a moment.";
    default: return status >= 500 ? "The server could not answer. Your work is safe; nothing was lost." : "Something went wrong.";
  }
}

// Set while the page is being left (pagehide): a request started then must outlive the page, or the browser cancels it (2 Nov test pass).
let leaving = false;
/** Runs fn with every request it starts marked keepalive, so the request reaches the server after the page is gone. */
export function whileLeaving(fn: () => void) {
  leaving = true;
  try { fn(); } finally { leaving = false; }
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { "X-Requested-With": "tb-nik", Accept: "application/json", ...(opts.headers ?? {}) };
  if (Date.now() - lastInput > QUIET_MS) headers["X-TB-Background"] = "1";
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body, credentials: "same-origin", signal: opts.signal, keepalive: leaving || undefined });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "No connection to the server. Check the network and try again.", "network");
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) { try { data = JSON.parse(text); } catch { data = text; } }
  if (!res.ok) {
    // The code sits at the top level or inside FastAPI's {"detail": {"message", "code"}}.
    let code = "";
    if (data && typeof data === "object") {
      const d = data as Record<string, unknown>;
      if (typeof d.code === "string") code = d.code;
      else if (d.detail && typeof d.detail === "object" && typeof (d.detail as Record<string, unknown>).code === "string") code = String((d.detail as Record<string, unknown>).code);
    }
    const err = new ApiError(res.status, messageFor(res.status, data), code, data);
    if (res.status === 401 && !opts.quiet401) listeners.unauthenticated.forEach((f) => f(err));
    if (res.status === 409 && code === "password_change_required") listeners.mustChange.forEach((f) => f(err));
    throw err;
  }
  return data as T;
}

export const api = {
  get: <T = unknown>(path: string, opts: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...opts, method: "GET" }),
  post: <T = unknown>(path: string, body?: unknown, opts: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...opts, method: "POST", body }),
  put: <T = unknown>(path: string, body?: unknown, opts: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...opts, method: "PUT", body }),
  patch: <T = unknown>(path: string, body?: unknown, opts: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...opts, method: "PATCH", body }),
  del: <T = unknown>(path: string, body?: unknown, opts: Omit<RequestOptions, "method" | "body"> = {}) => request<T>(path, { ...opts, method: "DELETE", body }),
  upload: <T = unknown>(path: string, form: FormData, opts: Omit<RequestOptions, "method" | "body" | "form"> = {}) => request<T>(path, { ...opts, method: "POST", form }),
};

export const TB = "/api/tb";
export const AUTH = "/api/auth";
