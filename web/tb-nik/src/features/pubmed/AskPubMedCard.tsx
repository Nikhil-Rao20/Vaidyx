// The Ask PubMed card on the Case Files home: the mark, one line of what it does, a question box and "Ask PubMed", which opens
// /pubmed and asks it there. "Your PubMed questions" opens the page with the history.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { PubMedMark } from "./PubMedMark";

export function AskPubMedCard({ className }: { className?: string }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const ok = q.trim().length >= 3;
  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      aria-labelledby="h-pubmed-card"
      className={cn("surface relative overflow-hidden p-4 sm:p-5", className)}
      data-testid="pubmed-home-card"
    >
      <span className="pointer-events-none absolute -right-12 -top-14 size-44 rounded-full bg-pubmed-soft blur-2xl" aria-hidden />
      <div className="relative flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-6">
        <div className="min-w-0 lg:w-[40%]">
          <h2 id="h-pubmed-card" className="flex flex-wrap items-center gap-2 text-base">Ask <PubMedMark /></h2>
          <p className="mt-1 text-sm text-muted-foreground">A general question, answered only from published papers. Every line is quoted word for word, with its paper's link.</p>
        </div>
        <form className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (ok) navigate(`/pubmed?q=${encodeURIComponent(q.trim())}`); }}>
          <label htmlFor="pubmed-card-q" className="sr-only">Your general question for PubMed</label>
          <Input id="pubmed-card-q" value={q} onChange={(e) => setQ(e.target.value)} maxLength={600} className="h-10 min-w-0 flex-1"
            placeholder="For example: induction chemotherapy before chemoradiation in cervical cancer" data-testid="pubmed-card-input" />
          <Button type="submit" disabled={!ok} className="h-10 hover:bg-primary-hover active:scale-[0.97]" data-testid="pubmed-card-ask"><Search className="size-4" aria-hidden />Ask PubMed</Button>
        </form>
      </div>
      <div className="relative mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>Published evidence, not advice for any patient. Only search words go to PubMed.</span>
        <Link to="/pubmed" className="inline-flex min-h-9 items-center gap-1 font-medium text-link hover:underline sm:min-h-0" data-testid="pubmed-card-open">Your PubMed questions<ArrowRight className="size-3.5" aria-hidden /></Link>
      </div>
    </motion.section>
  );
}
