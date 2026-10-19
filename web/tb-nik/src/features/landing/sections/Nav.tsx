// The landing page's top bar: a glass pill once the page scrolls, hidden while scrolling down, back when scrolling up. Anchors
// glide to their section; the one action is Sign in (or Open Case Files for a signed-in person). A full-screen menu on a phone.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { ArrowRight, Menu, X } from "lucide-react";
import { VaidyxIcon, VaidyxWordmark } from "@/components/Wordmark";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { HERO, NAV } from "../content";
import { useScrollTo } from "../components/lenis";
import { L_EASE } from "../components/Reveal";

export function Nav() {
  const { me } = useSession();
  const scrollTo = useScrollTo();
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { scrollY } = useScroll();
  useMotionValueEvent(scrollY, "change", (v) => {
    const prev = scrollY.getPrevious() ?? 0;
    setHidden(v > prev && v > 180 && !open);
    setScrolled(v > 24);
  });
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);
  const go = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); setOpen(false); scrollTo(id); };
  const action = (
    <Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-primary !h-10 !px-4 text-[14px]" data-testid="landing-signin">
      {me ? HERO.open : HERO.signIn} <ArrowRight className="size-4" aria-hidden />
    </Link>
  );
  return (
    <motion.header className="fixed inset-x-0 top-0 z-50" initial={{ y: -40, opacity: 0 }} animate={{ y: hidden ? -110 : 0, opacity: 1 }} transition={{ duration: 0.55, ease: L_EASE }}>
      <div className="mx-auto max-w-[1280px] px-3 pt-3 sm:px-6 sm:pt-4">
        <div className={cn("flex h-14 items-center gap-2 rounded-full border pl-4 pr-2 transition-[background-color,border-color,box-shadow] duration-300", scrolled || open ? "border-white/10 bg-[rgba(5,11,24,0.74)] shadow-[0_10px_40px_-18px_rgba(0,0,0,0.7)] backdrop-blur-xl" : "border-transparent")}>
          <a href="#top" onClick={go("top")} className="flex items-center gap-2.5 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]" aria-label="Vaidyx Tumour Board, top of the page">
            <VaidyxIcon tone="white" className="h-7" />
            <VaidyxWordmark tone="white" className="h-[21px]" />
            <span className="hidden items-center gap-2.5 text-[13px] text-white/60 md:inline-flex"><span className="h-4 w-px bg-white/20" aria-hidden />Tumour Board</span>
          </a>
          <nav aria-label="Sections" className="ml-auto hidden items-center gap-0.5 lg:flex">
            {NAV.map((n) => (
              <a key={n.id} href={`#${n.id}`} onClick={go(n.id)} className="rounded-full px-3.5 py-2 text-[13.5px] font-medium text-white/70 outline-none transition-colors hover:bg-white/[0.07] hover:text-white focus-visible:ring-2 focus-visible:ring-[var(--cyan)]">
                {n.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5 lg:ml-3">
            <span className="hidden sm:inline-flex">{action}</span>
            <button type="button" className="grid size-10 place-items-center rounded-full text-white/80 transition-colors hover:bg-white/10 lg:hidden" aria-label={open ? "Close the menu" : "Open the menu"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
              {open ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
            </button>
          </div>
        </div>
      </div>
      <AnimatePresence>
        {open ? (
          <motion.div key="menu" className="fixed inset-0 -z-10 bg-[rgba(5,11,24,0.96)] px-6 pt-24 backdrop-blur-xl lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            <nav aria-label="Sections" className="flex flex-col">
              {NAV.map((n, i) => (
                <motion.a key={n.id} href={`#${n.id}`} onClick={go(n.id)} className="l-title border-b border-white/10 py-4 text-[2rem] text-white" initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.06 + i * 0.05, duration: 0.45, ease: L_EASE }}>
                  {n.label}
                </motion.a>
              ))}
            </nav>
            <motion.div className="mt-8 sm:hidden" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>{action}</motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.header>
  );
}
