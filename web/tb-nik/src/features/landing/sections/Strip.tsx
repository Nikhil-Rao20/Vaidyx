// A quiet moving strip of what the product stands on; pauses under the pointer.
import { STRIP } from "../content";

export function Strip() {
  const items = [...STRIP, ...STRIP, ...STRIP, ...STRIP];
  return (
    <div className="l-ink on-ink relative border-t border-white/10 py-5" aria-label="What Vaidyx stands on">
      <div className="l-marquee">
        <div className="l-marquee-track">
          {items.map((t, i) => (
            <span key={i} className="flex items-center gap-6 whitespace-nowrap px-6 text-[13.5px] font-medium text-white/65" aria-hidden={i >= STRIP.length}>
              {t}<span className="size-1 rounded-full bg-[var(--mint)]/70" aria-hidden />
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
