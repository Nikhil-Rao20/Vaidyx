// Pieces the three layouts of "The problem" share: the badge colours and the source line.
import { PROBLEM } from "../../content";
import { SourceLink } from "../../components/Stats";

export const BADGES: Array<{ bg: string; shadow: string }> = [
  { bg: "linear-gradient(145deg, #0a8fb0, #0a6a86)", shadow: "rgba(10,106,134,0.55)" },
  { bg: "linear-gradient(145deg, #8f64fd, #5b3fc4)", shadow: "rgba(91,63,196,0.55)" },
  { bg: "linear-gradient(145deg, #1b7fb5, #0b4e74)", shadow: "rgba(11,78,116,0.55)" },
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
