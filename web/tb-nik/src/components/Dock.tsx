// The phone navigation: a floating Dock above the bottom edge (our own small version with Motion; the React Bits Dock needs
// React 19). The active item carries a pill that glides between items; a press scales the icon; counts sit on the icon.
import { Link, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import type { NavItem } from "@/lib/nav";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

export function Dock({ items, className }: { items: NavItem[]; className?: string }) {
  const { pathname } = useLocation();
  if (!items.length) return null;
  return (
    <nav aria-label="Main" className={cn("fixed inset-x-0 bottom-0 z-40 px-3 pb-[max(10px,env(safe-area-inset-bottom))] lg:hidden", className)}>
      <ul className="mx-auto flex max-w-md items-stretch justify-around rounded-2xl border border-border bg-card/85 p-1 shadow-[var(--shadow-lift)] backdrop-blur-xl supports-[backdrop-filter]:bg-card/75">
        {items.map((it) => {
          const active = it.match(pathname);
          const Icon = it.icon;
          return (
            <li key={it.key} className="flex-1">
              <Link
                to={it.to}
                aria-current={active ? "page" : undefined}
                className="relative flex h-[52px] flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {active ? <motion.span layoutId="dock-pill" className="absolute inset-0 rounded-xl bg-secondary" transition={spring} aria-hidden /> : null}
                <motion.span whileTap={{ scale: 0.85 }} className={cn("relative grid size-7 place-items-center", active ? "text-secondary-foreground" : "text-muted-foreground")}>
                  <Icon className="size-[22px]" strokeWidth={active ? 2.25 : 1.9} aria-hidden />
                  {it.badge ? (
                    <span className="absolute -right-1.5 -top-1 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-bold leading-4 text-primary-foreground" aria-label={`${it.badge} waiting`}>
                      {it.badge > 99 ? "99+" : it.badge}
                    </span>
                  ) : null}
                </motion.span>
                <span className={cn("relative", active ? "text-foreground" : "text-muted-foreground")}>{it.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
