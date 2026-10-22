import { AnimatePresence, motion } from "motion/react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCopy } from "@/hooks/useCopy";
import { cn } from "@/lib/utils";

/** Icon-only copy button that slides a small "Copied" out for a moment. */
export function CopyButton({ text, label = "Copy", className, size = "icon-sm" }: { text: string; label?: string; className?: string; size?: "icon-xs" | "icon-sm" | "icon" }) {
  const { copied, copy } = useCopy();
  return (
    <span className={cn("relative inline-flex items-center", className)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button type="button" variant="ghost" size={size} aria-label={copied ? "Copied" : label} onClick={() => void copy(text)} className="active:scale-90">
            {copied ? <Check className="size-4 text-ok" aria-hidden /> : <Copy className="size-4" aria-hidden />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copied ? "Copied" : label}</TooltipContent>
      </Tooltip>
      <AnimatePresence>
        {copied ? (
          <motion.span
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 6 }}
            transition={{ duration: 0.18 }}
            className="pointer-events-none absolute left-full ml-1 whitespace-nowrap rounded-md status-ok px-1.5 py-0.5 text-[11px] font-medium"
            role="status"
            aria-live="polite"
          >
            Copied
          </motion.span>
        ) : null}
      </AnimatePresence>
    </span>
  );
}
