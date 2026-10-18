// Text with the parts a search matched marked (lib/search.pieces). `id` marks an identifier whole when any part of it matched.
import { pieces } from "@/lib/search";

export function Highlight({ text, q, id = false, className }: { text: string; q: string; id?: boolean; className?: string }) {
  if (!q) return <span className={className}>{text}</span>;
  return (
    <span className={className}>
      {pieces(text, q, id).map((p, i) => (p.hit ? <mark key={i} className="rounded-[3px] bg-primary/20 px-0.5 text-inherit">{p.text}</mark> : <span key={i}>{p.text}</span>))}
    </span>
  );
}
