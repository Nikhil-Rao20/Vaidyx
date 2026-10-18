// The mobile navigation: a Dock at the bottom (our own small version with Motion; the React Bits Dock needs React 19).
// The active item carries a teal pill that glides between items; a press scales the icon; counts sit on the icon.
import { Link, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import type { NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

export function Dock({ items, className }: { items: NavItem[]; className?: string }) {
  const { pathname } = useLocation();
  if (!items.length) return null;
  return (
    <nav
      aria-label="Main"
      className={cn("fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 lg:hidden", className)}
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="mx-auto flex max-w-lg items-stretch justify-around px-2">
        {items.map((it) => {
          const active = it.match(pathname);
          const Icon = it.icon;
          return (
            <li key={it.key} className="flex-1">
              <Link
                to={it.to}
                aria-current={active ? "page" : undefined}
                className="relative flex h-14 flex-col items-center justify-center gap-0.5 rounded-md text-[11px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {active ? <motion.span layoutId="dock-pill" className="absolute inset-x-2 top-1 h-8 rounded-full bg-secondary" transition={{ type: "spring", stiffness: 500, damping: 40 }} aria-hidden /> : null}
                <motion.span whileTap={{ scale: 0.85 }} className={cn("relative grid size-8 place-items-center", active ? "text-secondary-foreground" : "text-muted-foreground")}>
                  <Icon className="size-5" aria-hidden />
                  {it.badge ? (
                    <span className="absolute -right-1 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-bold leading-4 text-primary-foreground" aria-label={`${it.badge} waiting`}>
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
