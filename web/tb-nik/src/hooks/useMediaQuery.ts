import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const get = () => (typeof window !== "undefined" && "matchMedia" in window ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState<boolean>(get);
  useEffect(() => {
    if (typeof window === "undefined" || !("matchMedia" in window)) return;
    const m = window.matchMedia(query);
    const on = () => setMatches(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return matches;
}

/** The desktop layout starts at 1024 px (laptop first: 1366 and 1920); below it the Dock is the navigation. */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
