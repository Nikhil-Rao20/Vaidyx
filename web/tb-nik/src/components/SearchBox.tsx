import { forwardRef, type ComponentProps } from "react";
import { Loader2, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

/** A search field with the icon, a clear button and a small spinner while results load. Esc clears. */
export const SearchBox = forwardRef<HTMLInputElement, Omit<ComponentProps<"input">, "onChange" | "value"> & {
  value: string;
  onChange: (value: string) => void;
  loading?: boolean;
  label?: string;
  wrapperClassName?: string;
}>(function SearchBox({ value, onChange, loading, label = "Search", className, wrapperClassName, placeholder = "Search", ...props }, ref) {
  return (
    <div className={cn("relative", wrapperClassName)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input
        ref={ref}
        type="search"
        role="searchbox"
        aria-label={label}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape" && value) { e.preventDefault(); onChange(""); } }}
        className={cn(
          "h-10 w-full rounded-md border border-input bg-card pl-9 pr-9 text-sm text-foreground placeholder:text-muted-foreground",
          "transition-shadow hover:border-border-strong focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/40 disabled:opacity-60",
          "[&::-webkit-search-cancel-button]:hidden",
          className,
        )}
        {...props}
      />
      <span className="absolute right-2 top-1/2 -translate-y-1/2">
        {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" aria-label="Searching" /> : value ? (
          <button type="button" onClick={() => onChange("")} className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Clear search">
            <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </span>
    </div>
  );
});
