// The frame every public page shares: the landing palette, smooth scrolling, the top bar, the footer, the page title, and a scroll
// to the location's hash once the page says it is ready (after the intro on the landing page).
import { useEffect, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import "../landing.css";
import { SmoothScroll, useScrollTo } from "./lenis";
import { Nav } from "../sections/Nav";
import { Footer } from "../sections/Footer";

function HashScroll({ ready }: { ready: boolean }) {
  const { hash, pathname } = useLocation();
  const scrollTo = useScrollTo();
  useEffect(() => {
    if (!ready) return;
    if (hash) { const t = window.setTimeout(() => scrollTo(hash), 120); return () => window.clearTimeout(t); }
    window.scrollTo({ top: 0 });
  }, [ready, hash, pathname, scrollTo]);
  return null;
}

export function SiteFrame({ title, children, ready = true, testId }: { title: string; children: ReactNode; ready?: boolean; testId?: string }) {
  useEffect(() => {
    const was = document.title;
    document.title = title;
    return () => { document.title = was; };
  }, [title]);
  return (
    <SmoothScroll>
      <div className="landing" data-testid={testId ?? "site"}>
        <HashScroll ready={ready} />
        <Nav />
        <main>{children}</main>
        <Footer />
      </div>
    </SmoothScroll>
  );
}
