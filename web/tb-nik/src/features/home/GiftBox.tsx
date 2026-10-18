// The gift: one UHID typed here fetches the records and shows what is missing, before anything else is asked.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Gift, Sparkles } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Illustration } from "@/components/Illustration";
import { cn } from "@/lib/utils";

export function GiftBox({ compact, className }: { compact?: boolean; className?: string }) {
  const [uhid, setUhid] = useState("");
  const navigate = useNavigate();
  return (
    <motion.section
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
      aria-label="Try it on one patient"
      className={cn("surface relative overflow-hidden p-5", compact ? "flex flex-col gap-3 sm:flex-row sm:items-center" : "flex flex-col items-center gap-4 text-center", className)}
    >
      <span className="pointer-events-none absolute -right-10 -top-10 size-40 rounded-full bg-secondary/60 blur-2xl" aria-hidden />
      {!compact ? <Illustration kind="gift" /> : null}
      <div className={cn("relative", compact && "flex-1")}>
        <h2 className="flex items-center gap-2 text-base"><Sparkles className="size-4 text-primary" aria-hidden /> See one patient's records in seconds</h2>
        <p className="mt-1 text-sm text-muted-foreground">Type a UHID, IP or OP number. Vaidyx fetches the reports from the hospital system and shows what is still missing for the board. Nothing is sent to anyone.</p>
      </div>
      <form className={cn("relative flex w-full gap-2", compact ? "sm:w-auto" : "max-w-md flex-col sm:flex-row")} onSubmit={(e) => { e.preventDefault(); if (uhid.trim()) navigate(`/cases/new?identifier=${encodeURIComponent(uhid.trim())}`); }}>
        <Input value={uhid} onChange={(e) => setUhid(e.target.value)} placeholder="UHID, IP No. or OP No." className="mono flex-1 sm:w-56" aria-label="UHID, IP or OP number" />
        <Button type="submit" disabled={!uhid.trim()} className="hover:bg-primary-hover active:scale-[0.97]"><Gift className="size-4" aria-hidden /> Fetch</Button>
      </form>
    </motion.section>
  );
}
