import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/** The teal square and the name. A link to Home unless `to` is null. */
export function Wordmark({ to = "/home", size = "md", className }: { to?: string | null; size?: "sm" | "md" | "lg"; className?: string }) {
  const box = size === "lg" ? "size-9 rounded-lg" : size === "sm" ? "size-6 rounded-md" : "size-7 rounded-md";
  const text = size === "lg" ? "text-xl" : size === "sm" ? "text-sm" : "text-base";
  const inner = (
    <span className={cn("inline-flex items-center gap-2 font-bold tracking-tight text-foreground", text, className)}>
      <span className={cn("grid place-items-center bg-primary text-primary-foreground shadow-[var(--shadow-outer)]", box)} aria-hidden>
        <svg viewBox="0 0 24 24" className="size-[62%]" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 6l7 12 7-12" />
        </svg>
      </span>
      <span>Vaidyx-TB</span>
    </span>
  );
  if (!to) return inner;
  return (
    <Link to={to} className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Vaidyx-TB home">
      {inner}
    </Link>
  );
}
