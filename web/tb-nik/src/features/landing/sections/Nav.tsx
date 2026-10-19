// The top bar of the public site: the lockup, the pages, the theme switch, Sign in (or Open Case Files for a signed-in person).
// A glass pill once the page scrolls, hidden while scrolling down, back when scrolling up. A full-screen menu on a phone.
import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { ArrowRight, Menu, X } from "lucide-react";
import { VaidyxIcon, VaidyxWordmark } from "@/components/Wordmark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { PAGES, SITE } from "../content";
import { L_EASE } from "../components/Reveal";

export function Nav() {
  const { me } = useSession();
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
  const action = (
    <Link to={me ? "/cases" : "/sign-in"} className="l-btn l-btn-primary !h-10 !px-4 text-[14px]" data-testid="landing-signin">
      {me ? SITE.open : SITE.signIn} <ArrowRight className="size-4" aria-hidden />
    </Link>
  );
  const item = (p: (typeof PAGES)[number], big = false) => (
    <NavLink
      key={p.to}
      to={p.to}
      end={p.to === "/"}
      onClick={() => setOpen(false)}
      className={({ isActive }) => cn(
        big
          ? "l-title border-b py-4 text-[2rem]"
          : "relative rounded-full px-3.5 py-2 text-[13.5px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--cyan)]",
        big && "border-[var(--l-line)]",
        isActive ? "text-[var(--l-fg)]" : "text-[var(--l-fg-2)] hover:text-[var(--l-fg)]",
      )}
    >
      {({ isActive }) => (
        <>
          {p.label}
          {!big && isActive ? <motion.span layoutId="site-nav-active" className="absolute inset-x-3.5 -bottom-px h-px bg-[var(--l-accent)]" transition={{ type: "spring", stiffness: 420, damping: 38 }} aria-hidden /> : null}
        </>
      )}
    </NavLink>
  );
  return (
    <motion.header className="fixed inset-x-0 top-0 z-50" initial={{ y: -40, opacity: 0 }} animate={{ y: hidden ? -110 : 0, opacity: 1 }} transition={{ duration: 0.55, ease: L_EASE }}>
      <div className="mx-auto max-w-[1280px] px-3 pt-3 sm:px-6 sm:pt-4">
        <div className={cn("flex h-14 items-center gap-2 rounded-full border pl-4 pr-2 transition-[background-color,border-color,box-shadow] duration-300", scrolled || open ? "border-[var(--l-line)] bg-[var(--l-nav-bg)] shadow-[var(--l-shadow)] backdrop-blur-xl" : "border-transparent")}>
          <Link to="/" className="flex items-center gap-2.5 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--cyan)]" aria-label={`${SITE.name}, home`}>
            <VaidyxIcon className="h-7" />
            <VaidyxWordmark className="h-7" />
            <span className="l-faint hidden items-center gap-2.5 text-[13px] md:inline-flex"><span className="h-4 w-px bg-[var(--l-line-2)]" aria-hidden />{SITE.product}</span>
          </Link>
          <nav aria-label="Pages" className="ml-auto hidden items-center gap-0.5 lg:flex">
            {PAGES.map((p) => item(p))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5 lg:ml-3">
            <ThemeToggle saveToProfile={false} className="!rounded-full" />
            <span className="hidden sm:inline-flex">{action}</span>
            <button type="button" className="grid size-10 place-items-center rounded-full text-[var(--l-fg)] transition-colors hover:bg-[var(--l-surface-2)] lg:hidden" aria-label={open ? "Close the menu" : "Open the menu"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
              {open ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
            </button>
          </div>
        </div>
      </div>
      <AnimatePresence>
        {open ? (
          <motion.div key="menu" className="fixed inset-0 -z-10 px-6 pt-24 backdrop-blur-xl lg:hidden" style={{ background: "color-mix(in srgb, var(--l-bg) 94%, transparent)" }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            <nav aria-label="Pages" className="flex flex-col">
              {PAGES.map((p, i) => (
                <motion.div key={p.to} initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.06 + i * 0.05, duration: 0.45, ease: L_EASE }}>{item(p, true)}</motion.div>
              ))}
            </nav>
            <motion.div className="mt-8 sm:hidden" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>{action}</motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.header>
  );
}
