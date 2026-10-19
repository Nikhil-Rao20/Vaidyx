// Option A, "Shield": the shield drawing on the left with the lead sentence, the six principles as a two-column list on the
// right, each with its badge.
import { SAFETY } from "../../content";
import { Reveal, Stagger } from "../../components/Reveal";
import { BADGES, ICONS, Shield } from "./shared";

export function OptionA() {
  return (
    <div className="grid items-center gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
      <Reveal className="mx-auto w-full max-w-[420px]">
        <Shield className="h-auto w-full" />
      </Reveal>
      <Stagger className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
        {SAFETY.principles.map((p, i) => {
          const Icon = ICONS[p.key];
          return (
            <div key={p.key} className="flex gap-4">
              <span className="l-badge shrink-0" style={{ "--badge": BADGES[i].bg, "--badge-shadow": BADGES[i].shadow } as React.CSSProperties}><Icon className="size-5" strokeWidth={1.9} aria-hidden /></span>
              <div>
                <h3 className="text-[1.1rem] font-semibold tracking-[-0.01em]">{p.title}</h3>
                <p className="l-muted mt-1.5 text-[15px]">{p.text}</p>
              </div>
            </div>
          );
        })}
      </Stagger>
    </div>
  );
}
