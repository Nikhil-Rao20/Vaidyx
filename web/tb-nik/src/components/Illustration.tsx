import { cn } from "@/lib/utils";

export type IllustrationKind = "empty" | "error" | "offline" | "search" | "done" | "inbox" | "notfound" | "gift" | "lock" | "people";

/** Small inline drawings in the theme colours (no files, no network). Decorative: hidden from screen readers. */
export function Illustration({ kind, className }: { kind: IllustrationKind; className?: string }) {
  const common = { className: cn("w-28 h-20", className), viewBox: "0 0 140 100", fill: "none", "aria-hidden": true as const };
  const line = "var(--border-strong)";
  const ink = "var(--muted-foreground)";
  const teal = "var(--primary)";
  const soft = "var(--secondary)";
  switch (kind) {
    case "error":
      return (
        <svg {...common}>
          <rect x="22" y="18" width="96" height="64" rx="10" fill={soft} stroke={line} strokeWidth="2" />
          <path d="M70 36v18" stroke="var(--bad)" strokeWidth="4" strokeLinecap="round" />
          <circle cx="70" cy="64" r="3" fill="var(--bad)" />
          <path d="M34 86h72" stroke={line} strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case "offline":
      return (
        <svg {...common}>
          <path d="M30 50a40 28 0 0 1 80 0" stroke={line} strokeWidth="3" strokeLinecap="round" strokeDasharray="6 6" />
          <path d="M46 62a24 16 0 0 1 48 0" stroke={ink} strokeWidth="3" strokeLinecap="round" />
          <circle cx="70" cy="76" r="5" fill={teal} />
          <path d="M40 30l60 50" stroke="var(--bad)" strokeWidth="3" strokeLinecap="round" />
        </svg>
      );
    case "search":
      return (
        <svg {...common}>
          <circle cx="62" cy="46" r="22" fill={soft} stroke={ink} strokeWidth="3" />
          <path d="M78 62l20 20" stroke={ink} strokeWidth="4" strokeLinecap="round" />
          <path d="M52 46h20M62 36v20" stroke={teal} strokeWidth="3" strokeLinecap="round" />
        </svg>
      );
    case "done":
      return (
        <svg {...common}>
          <circle cx="70" cy="50" r="30" fill="var(--ok-soft)" stroke="var(--ok)" strokeWidth="2.5" />
          <path d="M54 51l11 11 21-24" stroke="var(--ok)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "inbox":
      return (
        <svg {...common}>
          <path d="M28 54l10-30h64l10 30v26H28z" fill={soft} stroke={line} strokeWidth="2" />
          <path d="M28 54h26l6 10h20l6-10h26" stroke={ink} strokeWidth="2.5" strokeLinejoin="round" />
          <circle cx="104" cy="28" r="8" fill={teal} />
        </svg>
      );
    case "notfound":
      return (
        <svg {...common}>
          <path d="M38 24h44l20 20v36H38z" fill={soft} stroke={line} strokeWidth="2" />
          <path d="M82 24v20h20" stroke={line} strokeWidth="2" />
          <path d="M56 56l16 16M72 56L56 72" stroke={ink} strokeWidth="3.5" strokeLinecap="round" />
        </svg>
      );
    case "gift":
      return (
        <svg {...common}>
          <rect x="34" y="44" width="72" height="40" rx="6" fill={soft} stroke={line} strokeWidth="2" />
          <rect x="28" y="32" width="84" height="14" rx="4" fill={teal} />
          <path d="M70 32v52" stroke="var(--primary-foreground)" strokeWidth="4" />
          <path d="M70 32c-10-16-28-10-20 0M70 32c10-16 28-10 20 0" stroke={ink} strokeWidth="2.5" fill="none" />
        </svg>
      );
    case "lock":
      return (
        <svg {...common}>
          <rect x="44" y="44" width="52" height="40" rx="8" fill={soft} stroke={line} strokeWidth="2" />
          <path d="M54 44V34a16 16 0 0 1 32 0v10" stroke={ink} strokeWidth="3" />
          <circle cx="70" cy="64" r="5" fill={teal} />
        </svg>
      );
    case "people":
      return (
        <svg {...common}>
          <circle cx="52" cy="40" r="12" fill={soft} stroke={ink} strokeWidth="2.5" />
          <circle cx="88" cy="40" r="12" fill={soft} stroke={ink} strokeWidth="2.5" />
          <path d="M30 80c2-16 12-24 22-24s20 8 22 24M66 80c2-16 12-24 22-24s20 8 22 24" stroke={line} strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="70" cy="62" r="5" fill={teal} />
        </svg>
      );
    case "empty":
    default:
      return (
        <svg {...common}>
          <rect x="30" y="22" width="80" height="60" rx="8" fill={soft} stroke={line} strokeWidth="2" />
          <path d="M44 40h52M44 52h36M44 64h24" stroke={line} strokeWidth="3" strokeLinecap="round" />
          <circle cx="104" cy="74" r="12" fill={teal} />
          <path d="M98 74h12M104 68v12" stroke="var(--primary-foreground)" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      );
  }
}
