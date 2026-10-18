// One way of matching a typed search everywhere (the Case File list, the Ctrl+K bar; the server's /case-list does the same):
// case-insensitive, every typed word must be found somewhere, and an identifier matches on any part of it with the separators
// ignored, so "00764", "vdx", "VDX/2026/00764", "vdx 764" and "2026 00764" all find "VDX/2026/00764" (the owner, 19 Oct 2026).
import type { CaseListItem } from "@/lib/types";

/** Letters and digits only, lower case: "VXH/26/004327" -> "vxh26004327". */
export function compact(s: string): string {
  return (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

/** compact() of the text with the leading zeros of every digit run dropped first: "VXH/26/004327" -> "vxh264327", so "4327" and
 *  "VXH/26/4327" match too (the zeros go before the separators do, else "26/004327" would read as one run). */
export function loose(s: string): string {
  return compact((s || "").replace(/(^|[^0-9])0+(?=[0-9])/g, "$1"));
}

export function tokens(q: string): string[] {
  return (q || "").toLowerCase().split(/\s+/).map((t) => t.trim()).filter(Boolean);
}

/** What a Case File row can be found by. */
export function haystack(c: CaseListItem): { words: string; compact: string; loose: string } {
  const ids = [c.patient?.uhid, ...(c.ids ?? []), ...(c.accessions ?? []), c.case_id].filter(Boolean) as string[];
  const parts = [
    c.patient?.name, c.patient?.agesex, ...ids, c.protocol_label, c.cancer_name, (c.setting || "").replace(/_/g, " "),
    c.owner?.doctor_name, c.owner?.department_label, c.status?.label, dmy(c.board_date),
  ].filter(Boolean) as string[];
  const words = parts.join(" ").toLowerCase();
  const idText = ids.join(" ");
  return { words, compact: compact(idText), loose: loose(idText) };
}

function dmy(iso?: string | null): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}

/** True when every word of `q` is found: as text, or as any part of an identifier. */
export function matches(c: CaseListItem, q: string): boolean {
  const ts = tokens(q);
  if (!ts.length) return true;
  const h = haystack(c);
  return ts.every((t) => {
    if (h.words.includes(t)) return true;
    const tc = compact(t);
    if (tc && h.compact.includes(tc)) return true;
    const tl = loose(t);
    return Boolean(tl) && h.loose.includes(tl);
  });
}

/** The pieces of `text` to show, with `hit` on the parts a word of `q` matched. Plain words are marked where they occur; an
 *  identifier is marked whole when a word matches any part of it (the separators make a partial mark misleading). */
export function pieces(text: string, q: string, id = false): Array<{ text: string; hit: boolean }> {
  const ts = tokens(q);
  if (!text || !ts.length) return [{ text, hit: false }];
  const lower = text.toLowerCase();
  const marks = new Array<boolean>(text.length).fill(false);
  let whole = false;
  for (const t of ts) {
    let i = lower.indexOf(t);
    let found = false;
    while (i >= 0) { found = true; for (let k = i; k < i + t.length; k++) marks[k] = true; i = lower.indexOf(t, i + t.length); }
    if (!found && id) {
      const tc = compact(t), tl = loose(t);
      if ((tc && compact(text).includes(tc)) || (tl && loose(text).includes(tl))) whole = true;
    }
  }
  if (whole) return [{ text, hit: true }];
  const out: Array<{ text: string; hit: boolean }> = [];
  let start = 0;
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || marks[i] !== marks[start]) { out.push({ text: text.slice(start, i), hit: marks[start] }); start = i; }
  }
  return out;
}
