// The PubMed mark: the word "PubMed" with a book icon in the library's ink blue (--pubmed), apart from the brand teal so a PubMed
// answer is never mistaken for one from the records. Never the NLM logo (NLM asks that it is not used to suggest endorsement).
// The label line sits on top of every PubMed answer, always visible.
import { BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";

const SIZE = {
  sm: "gap-1 px-1.5 py-0.5 text-[11px] [&_svg]:size-3",
  md: "gap-1 px-2 py-0.5 text-xs [&_svg]:size-3.5",
  lg: "gap-1.5 px-2.5 py-1 text-sm [&_svg]:size-4",
} as const;

export function PubMedMark({ size = "md", className }: { size?: keyof typeof SIZE; className?: string }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center rounded-md bg-pubmed font-semibold tracking-[0.01em] text-pubmed-soft", SIZE[size], className)} data-testid="pubmed-mark">
      <BookOpen aria-hidden strokeWidth={2.25} />
      <span>PubMed</span>
    </span>
  );
}

/** The label of a PubMed answer: the mark and the server's sentence ("From PubMed. Every line is quoted word for word ..."). */
export function LabelLine({ label, className }: { label: string; className?: string }) {
  return (
    <p className={cn("flex items-start gap-2 rounded-md border border-pubmed-line bg-pubmed-soft px-2.5 py-2 text-xs leading-snug text-pubmed", className)} data-testid="pubmed-label">
      <PubMedMark size="sm" className="mt-px" />
      <span className="min-w-0">{label}</span>
    </p>
  );
}
