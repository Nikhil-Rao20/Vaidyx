// Option B, "Illustrated": six cards, each with its drawing in a tinted header, the title and the text below. The drawings play
// their short sequence once as they scroll into view; nothing responds to the pointer.
import { SAFETY } from "../../content";
import { Stagger } from "../../components/Reveal";
import { ART } from "../SafetyArt";

export function OptionB() {
  return (
    <Stagger className="grid gap-5 md:grid-cols-2 lg:grid-cols-3" itemClassName="h-full">
      {SAFETY.principles.map((p, i) => {
        const Art = ART[p.key];
        return (
          <article key={p.key} className="l-tile flex h-full flex-col">
            <div className="l-tile-tint border-b border-[var(--l-line)] p-4"><Art /></div>
            <div className="flex flex-1 flex-col p-6 sm:p-7">
              <span className="l-eyebrow">0{i + 1}</span>
              <h3 className="l-title mt-2 text-[1.3rem]">{p.title}</h3>
              <p className="l-muted mt-2.5 text-[15px]">{p.text}</p>
            </div>
          </article>
        );
      })}
    </Stagger>
  );
}
