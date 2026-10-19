// Smooth scrolling for the landing page (Lenis, MIT): the wheel glides, anchors ease to their section. Off under reduced motion
// (native scrolling, instant anchors). Destroyed when the page unmounts so the app's own pages scroll natively.
import { createContext, useCallback, useContext, useEffect, useRef, type ReactNode } from "react";
import Lenis from "lenis";
import { useReducedMotion } from "motion/react";

type ScrollTo = (target: string | HTMLElement, offset?: number) => void;
const Ctx = createContext<ScrollTo>(() => undefined);

export function SmoothScroll({ children }: { children: ReactNode }) {
  const ref = useRef<Lenis | null>(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (reduce) return;
    const lenis = new Lenis({ lerp: 0.085, smoothWheel: true, autoRaf: true, anchors: false });
    ref.current = lenis;
    return () => { lenis.destroy(); ref.current = null; };
  }, [reduce]);
  const scrollTo = useCallback<ScrollTo>((target, offset = -84) => {
    const el = typeof target === "string" ? document.getElementById(target.replace(/^#/, "")) : target;
    if (!el) return;
    if (ref.current) ref.current.scrollTo(el, { offset, duration: 1.3, easing: (t) => 1 - Math.pow(1 - t, 3) });
    else window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY + offset, behavior: reduce ? "auto" : "smooth" });
  }, [reduce]);
  return <Ctx.Provider value={scrollTo}>{children}</Ctx.Provider>;
}

export const useScrollTo = () => useContext(Ctx);
