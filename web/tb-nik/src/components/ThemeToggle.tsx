// Light / dark with the Magic UI animated toggler (vendor, MIT) in controlled mode: our data-theme attribute is the
// truth, the choice is kept in localStorage and in the profile.
import { Moon, Sun } from "lucide-react";
import { AnimatedThemeToggler } from "@/components/vendor/AnimatedThemeToggler";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

export function ThemeToggle({ withLabel, className, saveToProfile = true }: { withLabel?: boolean; className?: string; saveToProfile?: boolean }) {
  const { theme, setTheme } = useTheme(saveToProfile);
  const dark = theme === "dark";
  return (
    <AnimatedThemeToggler
      theme={theme}
      onThemeChange={setTheme}
      duration={450}
      aria-label={dark ? "Switch to the light theme" : "Switch to the dark theme"}
      aria-pressed={dark}
      title={dark ? "Light theme" : "Dark theme"}
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-md border border-border bg-card px-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent active:scale-95 disabled:opacity-50",
        !withLabel && "w-9 justify-center px-0",
        className,
      )}
    >
      {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
      {withLabel ? <span>{dark ? "Light theme" : "Dark theme"}</span> : null}
    </AnimatedThemeToggler>
  );
}
