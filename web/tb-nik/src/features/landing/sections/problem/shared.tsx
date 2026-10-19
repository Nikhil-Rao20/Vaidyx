// Pieces the three layouts of "The problem" share: the badge colours and the source line.
import { PROBLEM } from "../../content";
import { SourceLink } from "../../components/Stats";

/** A tone per item: the glyph colour and its tint. */
export const BADGES: Array<{ tone: string; bg2: string }> = [
  { tone: "#0a6a86", bg2: "rgba(1, 180, 194, 0.14)" },
  { tone: "#5b3fc4", bg2: "rgba(143, 100, 253, 0.14)" },
  { tone: "#0b4e74", bg2: "rgba(11, 78, 116, 0.12)" },
];

export function Source({ className }: { className?: string }) {
  const s = PROBLEM.national.source;
  return (
    <p className={className}>
      <span className="l-faint text-[12.5px]">{s.text} </span>
      <SourceLink href={s.href} label="Open the study" />
    </p>
  );
}
