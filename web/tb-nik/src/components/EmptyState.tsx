import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Illustration, type IllustrationKind } from "@/components/Illustration";
import { cn } from "@/lib/utils";

/** A small drawing, one plain sentence, one action. Used in place, never as a modal. */
export function EmptyState({ kind = "empty", title, text, action, className, compact }: {
  kind?: IllustrationKind;
  title: string;
  text?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex flex-col items-center text-center", compact ? "px-4 py-6 gap-2" : "px-6 py-10 gap-3", className)}
      role="status"
    >
      <Illustration kind={kind} className={compact ? "w-20 h-14" : undefined} />
      <h3 className="text-base font-bold">{title}</h3>
      {text ? <p className="max-w-md text-sm text-muted-foreground">{text}</p> : null}
      {action ? <div className="mt-1 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </motion.div>
  );
}
