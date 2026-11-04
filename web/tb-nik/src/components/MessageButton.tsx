// "Message" (night-v3 Phase 8, owner decision D5): a small link to /messages/new for a person, a department or the MDT Coordinator,
// with an optional Case File chip (the chip grants nothing: the reader's own access decides what it shows). Rendered only when the
// signed-in person may use Messages (me.messages) and the target is not the person themself.
import type { ComponentProps } from "react";
import { Link } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";

type ButtonProps = ComponentProps<typeof Button>;
import { useSession } from "@/lib/session";
import { BASE } from "@/lib/base";

export type MessageTarget = { to: string } | { dept: string } | { coordinator: true };

/** The /messages/new link for a target, with the Case File to attach (only shown to the reader when they may open it). */
export function messageHref(target: MessageTarget, caseId?: string): string {
  const q = new URLSearchParams();
  if ("to" in target) q.set("to", target.to);
  else if ("dept" in target) q.set("dept", target.dept);
  else q.set("coordinator", "1");
  if (caseId) q.set("case", caseId);
  return `/messages/new?${q.toString()}`;
}

/** Whether a "Message" link may be shown for this target: the signed-in person may use Messages and is not the target. */
export function useMayMessage(target?: MessageTarget): boolean {
  const { me } = useSession();
  if (!me?.messages) return false;
  if (target && "to" in target && (!target.to || target.to === me.user)) return false;
  if (target && "coordinator" in target && me.roles?.coordinator) return false;  // a coordinator does not message the coordinator role
  return true;
}

export function MessageButton({ target, caseId, label = "Message", name, size = "xs", variant = "ghost", className, newTab, iconOnly }: {
  target: MessageTarget;
  caseId?: string;
  label?: string;
  /** The accessible name when several links sit together ("Message Dr Ravi Kumar"); it starts with the visible label. */
  name?: string;
  size?: ButtonProps["size"];
  variant?: ButtonProps["variant"];
  className?: string;
  /** Open in a new tab (inside a live meeting, so the room is not left). */
  newTab?: boolean;
  iconOnly?: boolean;
}) {
  const ok = useMayMessage(target);
  if (!ok) return null;
  const href = messageHref(target, caseId);
  const inner = (
    <>
      <MessageSquare className="size-3.5" aria-hidden />
      {iconOnly ? null : label}
    </>
  );
  if (newTab) {
    return (
      <Button asChild size={size} variant={variant} className={className}>
        <a href={`${BASE}${href}`} target="_blank" rel="noopener noreferrer" aria-label={name ?? label} data-testid="message-button">{inner}</a>
      </Button>
    );
  }
  return (
    <Button asChild size={size} variant={variant} className={className}>
      <Link to={href} aria-label={name ?? (iconOnly ? label : undefined)} data-testid="message-button">{inner}</Link>
    </Button>
  );
}
