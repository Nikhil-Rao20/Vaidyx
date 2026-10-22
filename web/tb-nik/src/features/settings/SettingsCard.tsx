import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";

/** One section of the Settings page: an anchor (so /settings#security lands on it), an icon, a title and one line. */
export function SettingsCard({ id, icon: Icon, title, text, children, actions }: { id: string; icon: LucideIcon; title: string; text?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <motion.section id={id} aria-labelledby={`${id}-title`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="surface scroll-mt-24 p-5 sm:p-6">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-secondary text-secondary-foreground"><Icon className="size-5" aria-hidden /></span>
          <div>
            <h2 id={`${id}-title`} className="text-lg">{title}</h2>
            {text ? <p className="text-sm text-muted-foreground">{text}</p> : null}
          </div>
        </div>
        {actions}
      </header>
      {children}
    </motion.section>
  );
}
