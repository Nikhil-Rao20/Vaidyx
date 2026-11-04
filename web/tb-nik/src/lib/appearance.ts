import { useEffect } from "react";
// Theme (light / dark) and text size are per-viewer conveniences: kept in
// localStorage, applied before the first paint, and also saved to the profile
// so they follow the person to another laptop.

export type Theme = "light" | "dark";
export type TextSize = "small" | "normal" | "large";

const KEY_THEME = "tbnik.theme";
const KEY_TEXT = "tbnik.text";

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* private window or blocked storage: the choice just does not persist */ }
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#0f1720" : "#00c0b5");
  write(KEY_THEME, theme);
}

export function applyTextSize(size: TextSize) {
  if (size === "normal") document.documentElement.removeAttribute("data-text");
  else document.documentElement.setAttribute("data-text", size);
  write(KEY_TEXT, size);
}

export function currentTheme(): Theme {
  return (document.documentElement.getAttribute("data-theme") as Theme) || "light";
}
export function currentTextSize(): TextSize {
  return (document.documentElement.getAttribute("data-text") as TextSize) || "normal";
}

export function applyStoredAppearance() {
  const t = read(KEY_THEME);
  applyTheme(t === "dark" ? "dark" : "light");
  const s = read(KEY_TEXT);
  applyTextSize(s === "large" || s === "small" ? s : "normal");
}

/** The meeting pages are always light (owner, 2 Nov 2026: "the meeting must be in light theme ... doctors are not dark theme guys"):
 *  a person who chose dark for the app sees the meeting light; their choice comes back when they leave the meeting (nothing is saved). */
export function useLightForMeeting() {
  useEffect(() => {
    const before = currentTheme();
    if (before === "light") return undefined;
    document.documentElement.setAttribute("data-theme", "light");
    return () => { document.documentElement.setAttribute("data-theme", before); };
  }, []);
}
