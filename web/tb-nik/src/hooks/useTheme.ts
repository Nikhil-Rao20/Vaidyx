import { useCallback, useEffect, useState } from "react";
import { applyTextSize, applyTheme, currentTextSize, currentTheme, type TextSize, type Theme } from "@/lib/appearance";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";

function useAttribute<T extends string>(name: string, read: () => T): T {
  const [v, setV] = useState<T>(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setV(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: [name] });
    return () => obs.disconnect();
  }, [name, read]);
  return v;
}

/** The theme as applied on <html data-theme>; setTheme applies it at once and saves it to the profile when asked. */
export function useTheme(saveToProfile = true) {
  const theme = useAttribute<Theme>("data-theme", currentTheme);
  const setTheme = useCallback((t: Theme) => {
    applyTheme(t);
    if (saveToProfile) api.put(EP.profile, { theme: t }).catch(() => { /* the local choice stands; the profile copy can wait */ });
  }, [saveToProfile]);
  return { theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}

export function useTextSize(saveToProfile = true) {
  const size = useAttribute<TextSize>("data-text", currentTextSize);
  const setSize = useCallback((s: TextSize) => {
    applyTextSize(s);
    if (saveToProfile) api.put(EP.profile, { text_size: s }).catch(() => { /* same as the theme */ });
  }, [saveToProfile]);
  return { size, setSize };
}
