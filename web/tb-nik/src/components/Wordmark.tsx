// The Vaidyx brand lockup: the icon (the two-blue "V" mark from the main app), the wordmark for the theme (black on light,
// the light-blue cut on dark) and the product name "Tumour Board". The files are the main app's SVGs, cleaned, in public/brand.
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

const BRAND = "/static/tb-nik/brand/";
export const ICON_SRC = `${BRAND}vaidyx-icon.svg`;
export const ICON_WHITE_SRC = `${BRAND}vaidyx-icon-white.svg`;
export const WORDMARK_SRC = `${BRAND}vaidyx-wordmark.svg`;
export const WORDMARK_DARK_SRC = `${BRAND}vaidyx-wordmark-dark.svg`;
export const WORDMARK_WHITE_SRC = `${BRAND}vaidyx-wordmark-white.svg`;

/** The icon alone (the "V" mark). `tone` white is for dark or brand-coloured backgrounds. */
export function VaidyxIcon({ className, tone = "colour", anchor }: { className?: string; tone?: "colour" | "white"; anchor?: boolean }) {
  return <img src={tone === "white" ? ICON_WHITE_SRC : ICON_SRC} alt="" aria-hidden className={cn("inline-block select-none", className)} draggable={false} data-brand-anchor={anchor ? "" : undefined} />;
}

/** The wordmark alone, following the theme (or forced white on a brand surface). */
export function VaidyxWordmark({ className, tone = "theme" }: { className?: string; tone?: "theme" | "white" }) {
  if (tone === "white") return <img src={WORDMARK_WHITE_SRC} alt="Vaidyx" className={cn("inline-block select-none", className)} draggable={false} />;
  return (
    <>
      <img src={WORDMARK_SRC} alt="Vaidyx" className={cn("inline-block select-none dark:hidden", className)} draggable={false} />
      <img src={WORDMARK_DARK_SRC} alt="Vaidyx" className={cn("hidden select-none dark:inline-block", className)} draggable={false} />
    </>
  );
}

/** Icon + wordmark (the same height) + "Tumour Board". A link to the Case Files unless `to` is null. `size` sm is the phone top bar. The icon carries
 * data-brand-anchor: the splash after a sign-in flies the mark to it. */
export function Wordmark({ to = "/cases", size = "md", className, product = true }: { to?: string | null; size?: "sm" | "md" | "lg"; className?: string; product?: boolean }) {
  const icon = size === "lg" ? "h-9" : size === "sm" ? "h-6" : "h-7";
  // The wordmark stands as tall as the icon (the owner's eye, 20 Oct): top of the mark to bottom of the mark.
  const word = icon;
  const label = size === "lg" ? "text-base" : size === "sm" ? "text-xs" : "text-[13px]";
  const inner = (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <VaidyxIcon className={icon} anchor />
      <VaidyxWordmark className={word} />
      {product ? (
        <span className={cn("hidden items-center gap-2.5 sm:inline-flex", label)}>
          <span className="h-4 w-px bg-border-strong" aria-hidden />
          <span className="font-medium tracking-[-0.005em] text-muted-foreground">Tumour Board</span>
        </span>
      ) : null}
    </span>
  );
  if (!to) return inner;
  return (
    <Link to={to} className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Vaidyx Tumour Board: Case Files">
      {inner}
    </Link>
  );
}
