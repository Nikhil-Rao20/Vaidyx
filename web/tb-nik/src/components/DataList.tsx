import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ChevronRight } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { cn } from "@/lib/utils";

/** Rows that lift and show an arrow on hover; the whole row is the link. Roomy: 48 px minimum. */
export function DataRow({ to, onClick, children, className, arrow = true }: {
  to?: string;
  onClick?: () => void;
  children: ReactNode;
  className?: string;
  arrow?: boolean;
  /** Not used for the name: the row's own words are its accessible name (speech input matches what is seen). */
  ariaLabel?: string;
}) {
  const inner = (
    <>
      <div className="min-w-0 flex-1">{children}</div>
      {arrow && (to || onClick) ? <ChevronRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden /> : null}
    </>
  );
  const cls = cn("group surface-inner row-lift flex min-h-12 items-center gap-3 px-3 py-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring", (to || onClick) && "cursor-pointer hover:border-tint-line", className);
  if (to) return <Link to={to} className={cls}>{inner}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={cn(cls, "w-full")}>{inner}</button>;
  return <div className={cls}>{inner}</div>;
}

export function RowSkeleton({ lines = 2 }: { lines?: number }) {
  return (
    <div className="surface-inner flex min-h-12 items-center gap-3 px-3 py-2.5" aria-hidden>
      <div className="skeleton-line size-7 rounded-md" />
      <div className="flex-1 space-y-2">
        <div className="skeleton-line h-3.5 w-2/3" />
        {lines > 1 ? <div className="skeleton-line h-3 w-1/3" /> : null}
      </div>
      <div className="skeleton-line h-5 w-20 rounded-md" />
    </div>
  );
}

/**
 * The list with its four states: loading (skeleton rows), error (cause + Try again), empty (given), rows (staggered in).
 */
export function DataList<T>({ items, renderRow, keyFor, loading, error, onRetry, retrying, empty, what, skeletonRows = 6, className, header, footer }: {
  items: T[] | undefined;
  renderRow: (item: T, index: number) => ReactNode;
  keyFor: (item: T, index: number) => string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  empty: ReactNode;
  what?: string;
  skeletonRows?: number;
  className?: string;
  header?: ReactNode;
  footer?: ReactNode;
}) {
  if (loading && !items?.length) {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Loading">
        {header}
        {Array.from({ length: skeletonRows }).map((_, i) => <RowSkeleton key={i} />)}
      </div>
    );
  }
  if (error && !items?.length) return <ErrorState error={error} what={what} onRetry={onRetry} retrying={retrying} className={className} />;
  if (!items?.length) return <div className={className}>{empty}</div>;
  return (
    <div className={cn("space-y-2", className)}>
      {header}
      {items.map((item, i) => (
        <motion.div key={keyFor(item, i)} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, delay: Math.min(i, 12) * 0.025 }}>
          {renderRow(item, i)}
        </motion.div>
      ))}
      {footer}
    </div>
  );
}
