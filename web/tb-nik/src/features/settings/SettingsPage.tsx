// /settings: profile, appearance, saved filters, notifications, security. One page with a section list on the left
// (a laptop) or chips on top (a phone); /settings#security lands on the section.
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Activity, BellRing, Filter, Palette, ShieldCheck, UserRound } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/lib/utils";
import { ProfileSection } from "@/features/settings/ProfileSection";
import { AppearanceSection, SavedFiltersSection } from "@/features/settings/AppearanceSection";
import { NotificationsSection } from "@/features/settings/NotificationsSection";
import { SecuritySection } from "@/features/settings/SecuritySection";

const SECTIONS = [
  { id: "profile", label: "Profile", icon: UserRound },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "filters", label: "Saved filters", icon: Filter },
  { id: "notifications", label: "Notifications", icon: BellRing },
  { id: "security", label: "Security", icon: ShieldCheck },
];

export default function SettingsPage() {
  const { hash } = useLocation();
  const [active, setActive] = useState(hash.slice(1) || "profile");
  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => Boolean(e));
    if (!("IntersectionObserver" in window) || !els.length) return;
    const obs = new IntersectionObserver((entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (top) setActive(top.target.id);
    }, { rootMargin: "-96px 0px -55% 0px" });
    els.forEach((e) => obs.observe(e));
    return () => obs.disconnect();
  }, []);
  const nav = (
    <>
      {SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          onClick={(e) => { e.preventDefault(); document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); window.history.replaceState(null, "", `#${s.id}`); setActive(s.id); }}
          aria-current={active === s.id ? "location" : undefined}
          className={cn("inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", active === s.id ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground")}
        >
          <s.icon className="size-4" aria-hidden /> {s.label}
        </a>
      ))}
      <Link to="/activity" className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        <Activity className="size-4" aria-hidden /> Activity
      </Link>
    </>
  );
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Settings" subtitle="Your profile, how the site looks, what reaches you, and how you sign in." />
      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <nav aria-label="Settings sections" className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1 lg:sticky lg:top-20 lg:mx-0 lg:flex-col lg:self-start lg:overflow-visible lg:px-0">{nav}</nav>
        <div className="grid min-w-0 gap-6">
          <ProfileSection />
          <AppearanceSection />
          <SavedFiltersSection />
          <NotificationsSection />
          <SecuritySection />
        </div>
      </div>
    </div>
  );
}
