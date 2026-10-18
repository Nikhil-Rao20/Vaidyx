// The shell around every signed-in page: slim top bar on a laptop (wordmark, 3 to 5 items per role, action search,
// bell, profile), a top bar with wordmark + bell + avatar and the Dock at the bottom on a phone. Global toasts,
// the offline banner and a page error boundary live here. A 401 anywhere clears the session (lib/session.tsx) and the
// guard sends the person to /sign-in with the page they wanted.
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { LogOut, Search, X } from "lucide-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/Wordmark";
import { ActionSearch } from "@/components/ActionSearch";
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";
import { Dock } from "@/components/Dock";
import { Toasts } from "@/components/Toasts";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ErrorPage } from "@/app/ErrorPage";
import { useSession } from "@/lib/session";
import { navItems } from "@/lib/nav";
import { cn } from "@/lib/utils";

const BARE_PATHS = new Set(["/first-login", "/welcome"]);

function useScrollToHash() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const id = hash.slice(1);
      const t = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
      return () => window.clearTimeout(t);
    }
    window.scrollTo({ top: 0 });
  }, [pathname, hash]);
}

export function AppShell() {
  const { me, signOut } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchOpen, setSearchOpen] = useState(false);
  useScrollToHash();
  const items = useMemo(() => (me ? navItems(me) : []), [me]);
  useEffect(() => { setSearchOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (location.pathname.startsWith("/cases/") && location.pathname !== "/cases/new") {
      const id = location.pathname.split("/")[2];
      if (id) { try { localStorage.setItem("tbnik.lastCase", id); } catch { /* no storage */ } }
    }
  }, [location.pathname]);
  if (!me) return null;
  const bare = BARE_PATHS.has(location.pathname);
  const canCreate = (me.roles.treating || []).length > 0 || me.roles.coordinator;
  const unread = me.counts?.unread ?? 0;

  const page = (
    <ErrorBoundary resetKey={location.pathname} fallback={(err, reset) => <ErrorPage embedded code={500} detail={import.meta.env.DEV ? err.message : undefined} actions={<Button type="button" variant="outline" onClick={reset}>Try this page again</Button>} />}>
      <Outlet />
    </ErrorBoundary>
  );

  return (
    <TooltipProvider delayDuration={300}>
      <div className="min-h-dvh bg-background">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[60] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow-[var(--shadow-lift)]">Skip to content</a>
        <header className="sticky top-0 z-40 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/85">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4">
            <Wordmark to={bare ? null : "/home"} />
            {bare ? (
              <div className="ml-auto flex items-center gap-2">
                <ThemeToggle saveToProfile={false} />
                <Button type="button" variant="ghost" size="sm" onClick={async () => { await signOut(); navigate("/sign-in", { replace: true }); }}>
                  <LogOut className="size-4" aria-hidden /> Sign out
                </Button>
              </div>
            ) : (
              <>
                <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
                  {items.map((it) => {
                    const active = it.match(location.pathname);
                    const Icon = it.icon;
                    return (
                      <NavLink
                        key={it.key}
                        to={it.to}
                        aria-current={active ? "page" : undefined}
                        className={cn("relative inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]", active ? "text-foreground" : "text-muted-foreground hover:text-foreground")}
                      >
                        <Icon className="size-4" aria-hidden />
                        {it.label}
                        {it.badge ? <span className="ml-0.5 rounded-full bg-primary px-1.5 text-[11px] font-bold leading-4 text-primary-foreground">{it.badge}</span> : null}
                        {active ? <motion.span layoutId="topnav-underline" className="absolute inset-x-2 -bottom-[13px] h-0.5 rounded-full bg-primary" transition={{ type: "spring", stiffness: 500, damping: 40 }} aria-hidden /> : null}
                      </NavLink>
                    );
                  })}
                </nav>
                <div className="ml-auto hidden w-full max-w-xl lg:block">
                  <ActionSearch canCreate={canCreate} />
                </div>
                <div className="ml-auto flex items-center gap-1 lg:ml-0">
                  <Button type="button" variant="ghost" size="icon" className="lg:hidden" aria-label={searchOpen ? "Close search" : "Search"} aria-expanded={searchOpen} onClick={() => setSearchOpen((o) => !o)}>
                    {searchOpen ? <X className="size-5" aria-hidden /> : <Search className="size-5" aria-hidden />}
                  </Button>
                  <NotificationBell />
                  <ProfileMenu />
                </div>
              </>
            )}
          </div>
          {searchOpen && !bare ? (
            <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="border-t border-border px-4 py-2 lg:hidden">
              <ActionSearch canCreate={canCreate} compact />
            </motion.div>
          ) : null}
          <OfflineBanner />
        </header>
        <main id="main" className={cn("mx-auto w-full max-w-[1400px] px-4 py-4 md:py-6", !bare && "pb-24 lg:pb-8")} tabIndex={-1}>
          {page}
        </main>
        {!bare ? <Dock items={items} /> : null}
        <Toasts />
        <span className="sr-only" aria-live="polite">{unread ? `${unread} unread notifications` : ""}</span>
        {!bare && location.pathname !== "/home" ? <span className="sr-only"><Link to="/home">Home</Link></span> : null}
      </div>
    </TooltipProvider>
  );
}
