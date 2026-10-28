// Small formatting helpers: dates as DD/MM/YYYY, "how long ago", patient lines, initials. All plain words, no jargon.

export function parseDate(value?: string | number | Date | null): Date | null {
  if (value === undefined || value === null || value === "") return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") return new Date(value < 1e12 ? value * 1000 : value);
  const s = String(value).trim();
  const dmy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
  if (dmy) return new Date(Number(dmy[3]), Number(dmy[2]) - 1, Number(dmy[1]));
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** 18/10/2026 */
export function formatDate(value?: string | number | Date | null, fallback = ""): string {
  const d = parseDate(value);
  if (!d) return fallback;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** "Sunday 18/10/2026": the day of the week, then the date as Indian screens show it. */
export function formatDateWords(value?: string | number | Date | null, fallback = ""): string {
  const d = parseDate(value);
  if (!d) return fallback;
  return `${WEEKDAYS[d.getDay()]} ${formatDate(d)}`;
}

/** 18/10/2026, 14:05 */
export function formatDateTime(value?: string | number | Date | null, fallback = ""): string {
  const d = parseDate(value);
  if (!d) return fallback;
  return `${formatDate(d)}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "just now", "5 min ago", "3 h ago", "yesterday", "4 days ago", else the date. */
export function timeAgo(value?: string | number | Date | null, now: Date = new Date()): string {
  const d = parseDate(value);
  if (!d) return "";
  const diff = Math.round((now.getTime() - d.getTime()) / 1000);
  if (diff < 0) return formatDate(d);
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  const days = Math.round(diff / 86400);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDate(d);
}

/** "in 3 days", "today", "2 days late". */
export function dueWords(value?: string | null, now: Date = new Date()): { text: string; late: boolean; today: boolean } {
  const d = parseDate(value);
  if (!d) return { text: "", late: false, today: false };
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((target.getTime() - start.getTime()) / 86400000);
  if (days === 0) return { text: "due today", late: false, today: true };
  if (days === 1) return { text: "due tomorrow", late: false, today: false };
  if (days > 1) return { text: `due in ${days} days`, late: false, today: false };
  if (days === -1) return { text: "1 day late", late: true, today: false };
  return { text: `${-days} days late`, late: true, today: false };
}

/** "Lakshmi R., 58 F, UHID VXH/2026/000123" */
export function patientLine(p?: { name?: string; agesex?: string; uhid?: string; mrn?: string } | null): string {
  if (!p) return "";
  const parts = [p.name, p.agesex, p.uhid || p.mrn ? `UHID ${p.uhid || p.mrn}` : ""].filter(Boolean);
  return parts.join(", ");
}

/** "LR" from "Lakshmi R." or "Dr Lakshmi Rao" (the "Dr" is skipped); "BS" from "Dr Breast Surgery (demo)". */
export function initials(name?: string | null): string {
  if (!name) return "?";
  // "(demo)" or "(SYNTHETIC)" and other bracketed notes are not part of the name; words must start with a letter.
  const words = name.replace(/\([^)]*\)/g, " ").replace(/^(dr\.?|prof\.?|mr\.?|mrs\.?|ms\.?)\s+/i, "").trim().split(/\s+/).filter((w) => /^\p{L}/u.test(w));
  if (!words.length) return "?";
  const first = words[0][0] ?? "";
  const last = words.length > 1 ? words[words.length - 1][0] ?? "" : "";
  return (first + last).toUpperCase();
}

/** "Dr Rao" when the name has no title yet. */
export function drName(name?: string | null): string {
  if (!name) return "";
  return /^(dr|prof)\.?\s/i.test(name) ? name : `Dr ${name}`;
}

/** The consultant who signs off, titled ("Dr Rao"); "the consultant" when the name is not known ("The consultant" at the start of a
 *  sentence), never "Dr the consultant" (review 9 C, M18). */
export function consultantTitle(name?: string | null, start = false): string {
  const n = (name ?? "").trim();
  if (n) return drName(n);
  return start ? "The consultant" : "the consultant";
}

export function plural(n: number, one: string, many = one + "s"): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "58 F" from age and sex in whatever form the hospital system sends. */
export function ageSex(age?: number | string | null, sex?: string | null): string {
  const a = age === undefined || age === null || age === "" ? "" : String(age);
  const s = (sex || "").trim();
  const short = /^f/i.test(s) ? "F" : /^m/i.test(s) ? "M" : s ? s[0].toUpperCase() : "";
  return [a, short].filter(Boolean).join(" ");
}

/** A short id for display: "TB-2026-0012" stays, long hashes are cut. */
export function shortId(id?: string | null, keep = 14): string {
  if (!id) return "";
  return id.length > keep ? id.slice(0, keep) + "..." : id;
}

export function clampText(s: string, max = 120): string {
  return s.length > max ? s.slice(0, max - 3).trimEnd() + "..." : s;
}

/** A person from a login: the display name when given, else the part of an email login before the @. */
export function personWord(login?: string | null, name?: string | null): string {
  if (name && name.trim()) return name.trim();
  if (!login) return "";
  return login.includes("@") ? login.split("@")[0] : login;
}
