import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  to?: string;
}

/** Title row of a page: optional back link or breadcrumbs, title, one line under it, actions on the right. */
export function PageHeader({ title, subtitle, back, crumbs, actions, className, children }: {
  title: ReactNode;
  subtitle?: ReactNode;
  back?: { to: string; label: string };
  crumbs?: Crumb[];
  actions?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <header className={cn("mb-4 flex flex-col gap-2", className)}>
      {back ? (
        <Link to={back.to} className="inline-flex w-fit items-center gap-1 text-sm text-link hover:underline">
          <ArrowLeft className="size-4" aria-hidden /> {back.label}
        </Link>
      ) : null}
      {crumbs?.length ? (
        <nav aria-label="Where you are" className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
          {crumbs.map((c, i) => (
            <span key={`${c.label}-${i}`} className="inline-flex items-center gap-1">
              {i > 0 ? <ChevronRight className="size-3.5" aria-hidden /> : null}
              {c.to ? <Link to={c.to} className="hover:text-foreground hover:underline">{c.label}</Link> : <span aria-current="page" className="text-foreground">{c.label}</span>}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </header>
  );
}
