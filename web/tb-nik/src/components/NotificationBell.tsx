import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Bell, CheckCheck } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { DateText } from "@/components/DateText";
import { notify } from "@/components/Toasts";
import { useInvalidate, useNotifications, keys } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { groupByDay, kindInfo, notificationLink } from "@/lib/notifications";
import type { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = { ok: "status-ok", warn: "status-warn", bad: "status-bad", review: "status-review", neutral: "bg-muted text-muted-foreground" };

export function NotificationBell({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [marking, setMarking] = useState(false);
  const navigate = useNavigate();
  const invalidate = useInvalidate();
  const list = useNotifications();
  const unread = list.data?.unread ?? 0;
  const items = list.data?.notifications ?? [];

  const markRead = async (ids: string[] | "all") => {
    try {
      await api.post(EP.notificationsRead, ids === "all" ? { all: true } : { ids });
      await invalidate(keys.notifications);
    } catch (e) {
      notify.error("Could not mark as read", e instanceof Error ? e.message : undefined);
    }
  };

  const openItem = async (n: Notification) => {
    setOpen(false);
    if (!n.read) void markRead([n.id]);
    const to = notificationLink(n);
    if (to) navigate(to);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className={cn("relative active:scale-95", className)} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
          <motion.span animate={unread ? { rotate: [0, -12, 12, -8, 8, 0] } : { rotate: 0 }} transition={{ duration: 0.6 }} key={unread}>
            <Bell className="size-5" aria-hidden />
          </motion.span>
          <AnimatePresence>
            {unread ? (
              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} className="absolute right-1 top-1 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-bold leading-4 text-primary-foreground" aria-hidden>
                {unread > 99 ? "99+" : unread}
              </motion.span>
            ) : null}
          </AnimatePresence>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(92vw,380px)] p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-sm font-bold">Notifications</p>
          <Button type="button" variant="ghost" size="sm" disabled={!unread || marking} aria-busy={marking} onClick={async () => { setMarking(true); await markRead("all"); setMarking(false); }}>
            <CheckCheck className="size-4" aria-hidden /> {marking ? "Marking" : "Mark all read"}
          </Button>
        </div>
        <div className="max-h-[min(70vh,440px)] overflow-auto" aria-live="polite">
          {list.isLoading && !list.data ? (
            <div className="space-y-3 p-3" aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="flex gap-2"><div className="skeleton-line size-8 rounded-md" /><div className="flex-1 space-y-1.5"><div className="skeleton-line h-3.5 w-3/4" /><div className="skeleton-line h-3 w-1/2" /></div></div>)}
            </div>
          ) : list.error && !list.data ? (
            <ErrorState compact error={list.error} what="notifications" onRetry={() => void list.refetch()} retrying={list.isFetching} />
          ) : !items.length ? (
            <EmptyState compact kind="done" title="Nothing new" text="You are up to date." />
          ) : (
            groupByDay(items).map((g) => (
              <div key={g.label}>
                <p className="sticky top-0 bg-popover px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{g.label}</p>
                <ul>
                  {g.items.map((n) => {
                    const info = kindInfo(n.kind);
                    const Icon = info.icon;
                    return (
                      <li key={n.id}>
                        <button type="button" onClick={() => void openItem(n)} className={cn("flex w-full items-start gap-2.5 px-3 py-2 text-left hover:bg-accent", !n.read && "bg-secondary/40")}>
                          <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-md", TONE[info.tone])}><Icon className="size-4" aria-hidden /></span>
                          <span className="min-w-0 flex-1">
                            <span className={cn("block truncate text-sm", !n.read ? "font-bold text-foreground" : "text-foreground")}>{n.title || info.label}</span>
                            {n.text ? <span className="block truncate text-xs text-muted-foreground">{n.text}</span> : null}
                            <span className="block text-[11px] text-muted-foreground"><DateText value={n.ts} mode="ago" /></span>
                          </span>
                          {!n.read ? <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" /> : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
