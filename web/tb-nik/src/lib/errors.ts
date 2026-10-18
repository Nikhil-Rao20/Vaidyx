// Reading the server's errors. The routes answer {"detail": {"message", "code"}} or {"detail": "message"}; a path the
// server does not have at all answers FastAPI's own {"detail": "Not Found"}. Only that last one means "not built yet".
import { ApiError } from "@/lib/api";

/** The machine code of an API error ("no_such_code", "weak_password"), from the top level or inside detail. */
export function errorCode(e: unknown): string {
  if (!(e instanceof ApiError)) return "";
  if (e.code) return e.code;
  const d = e.detail as Record<string, unknown> | null;
  const inner = d && typeof d === "object" ? (d.detail as Record<string, unknown> | string | undefined) : undefined;
  if (inner && typeof inner === "object" && typeof inner.code === "string") return inner.code;
  return "";
}

/** True when the path itself is missing on the server (the backend part is not built yet), not when a record is missing. */
export function isRouteMissing(e: unknown): boolean {
  if (!(e instanceof ApiError) || e.status !== 404) return false;
  const d = e.detail as Record<string, unknown> | string | null;
  if (d && typeof d === "object" && d.detail === "Not Found") return true;
  return !errorCode(e) && (d === null || d === "" || (typeof d === "object" && !("detail" in d)));
}
