import { AnimatePresence, motion } from "motion/react";
import { WifiOff } from "lucide-react";
import { useOnline } from "@/hooks/useOnline";

/** Shown under the top bar while navigator.onLine is false. */
export function OfflineBanner() {
  const online = useOnline();
  return (
    <AnimatePresence>
      {!online ? (
        <motion.div
          key="offline"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="overflow-hidden"
          role="status"
          aria-live="assertive"
        >
          <div className="flex items-center justify-center gap-2 status-warn px-4 py-2 text-sm font-medium">
            <WifiOff className="size-4" aria-hidden /> You are offline. What you see may be old; changes wait until the connection is back.
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
