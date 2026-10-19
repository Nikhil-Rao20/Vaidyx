// The footer: the lockup and the scope line, four short columns, the synthetic-data note, and the wordmark as a quiet sign-off.
import { Link } from "react-router-dom";
import { VaidyxIcon, VaidyxWordmark } from "@/components/Wordmark";
import { FOOTER, SITE } from "../content";

const TANUH_LOGO = "/static/tb-nik/brand/tanuh.png";

export function Footer() {
  return (
    <footer className="l-ink on-ink relative overflow-hidden border-t border-white/10">
      <div className="relative mx-auto max-w-[1280px] px-5 pb-10 pt-16 sm:px-8">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(4,minmax(0,1fr))]">
          <div>
            <div className="flex items-center gap-2.5"><VaidyxIcon tone="white" className="h-8" /><VaidyxWordmark tone="white" className="h-6" /><span className="ml-1 text-[13px] text-white/60">{SITE.product}</span></div>
            <p className="l-muted mt-4 max-w-sm text-[14.5px]">{FOOTER.scope}</p>
            <a href="https://tanuh.ai" target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-3 rounded-2xl bg-white/[0.04] p-2 pr-4 ring-1 ring-white/10 transition-colors hover:bg-white/[0.08]">
              <span className="grid size-11 place-items-center rounded-xl bg-white"><img src={TANUH_LOGO} alt="" className="h-8 w-auto" /></span>
              <span className="text-[13px] leading-tight text-white/80"><span className="block font-semibold text-white">A product of TANUH</span>The AI Centre of Excellence in Healthcare</span>
            </a>
          </div>
          {FOOTER.columns.map((col) => (
            <div key={col.title}>
              <p className="l-eyebrow text-white/50">{col.title}</p>
              <ul className="mt-4 space-y-2.5 text-[15px]">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.to.startsWith("http")
                      ? <a href={l.to} target="_blank" rel="noreferrer" className="text-white/80 transition-colors hover:text-white">{l.label}</a>
                      : <Link to={l.to} className="text-white/80 transition-colors hover:text-white">{l.label}</Link>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-14 flex flex-col gap-2 border-t border-white/10 pt-6 text-[13px] text-white/50 sm:flex-row sm:items-center sm:justify-between">
          <p>{FOOTER.note}</p>
          <p>{FOOTER.copyright}</p>
        </div>
      </div>
      <div className="l-footer-mark pointer-events-none mx-auto -mb-[4%] max-w-[1280px] px-5 sm:px-8" aria-hidden>
        <VaidyxWordmark tone="white" className="w-full opacity-[0.08]" />
      </div>
    </footer>
  );
}
