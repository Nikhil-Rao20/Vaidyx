// Contact: the address with a fixed subject line, and an enquiry form that composes the email in the visitor's own mail
// application. Nothing is sent from the page.
import { useState, type FormEvent } from "react";
import { ArrowUpRight, Check, Copy, Mail } from "lucide-react";
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Reveal } from "../components/Reveal";
import { CONTACT } from "../content";

function mailto(body?: string): string {
  const q = new URLSearchParams();
  q.set("subject", CONTACT.subject);
  if (body) q.set("body", body);
  return `mailto:${CONTACT.email}?${q.toString().replace(/\+/g, "%20")}`;
}

export default function ContactPage() {
  const [copied, setCopied] = useState(false);
  const [f, setF] = useState({ name: "", hospital: "", role: "", message: "" });
  const Place = CONTACT.place.icon;
  const copy = async () => {
    try { await navigator.clipboard.writeText(CONTACT.email); setCopied(true); window.setTimeout(() => setCopied(false), 1800); } catch { /* no clipboard */ }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body = [`${CONTACT.form.name}: ${f.name}`, `${CONTACT.form.hospital}: ${f.hospital}`, `${CONTACT.form.role}: ${f.role}`, "", f.message].join("\n");
    window.location.href = mailto(body);
  };
  const field = (key: keyof typeof f, label: string, textarea = false) => (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-[var(--text-2)]">{label}</span>
      {textarea
        ? <textarea className="l-input min-h-[8rem]" value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
        : <input className="l-input" value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} />}
    </label>
  );
  return (
    <SiteFrame title="Contact the Vaidyx team" testId="contact">
      <PageHead eyebrow={CONTACT.eyebrow} title={[CONTACT.title[0], CONTACT.title[1]]} lead={CONTACT.lead} compact />
      <section className="l-paper py-20 sm:py-24">
        <div className="mx-auto grid max-w-[1280px] gap-6 px-5 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-10">
          <Reveal className="l-card p-7 sm:p-8">
            <span className="grid size-11 place-items-center rounded-xl bg-[rgba(1,180,194,0.12)] text-[#0a6a86]"><Mail className="size-5" aria-hidden /></span>
            <p className="l-eyebrow mt-6 text-[#0a6a86]">{CONTACT.emailTitle}</p>
            <a href={mailto()} className="mt-2 block break-all text-[1.2rem] font-semibold tracking-[-0.01em] text-[var(--text)] underline decoration-[rgba(10,106,134,0.3)] underline-offset-4 hover:decoration-current" data-testid="contact-email">{CONTACT.email}</a>
            <p className="l-muted mt-2 text-[14px]">Subject line: <span className="font-medium text-[var(--text)]">{CONTACT.subject}</span></p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a href={mailto()} className="l-btn l-btn-dark">{CONTACT.write} <ArrowUpRight className="size-4" aria-hidden /></a>
              <button type="button" className="l-btn l-btn-light" onClick={copy}>{copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />} {copied ? CONTACT.copied : CONTACT.copy}</button>
            </div>
            <p className="l-muted mt-8 flex items-center gap-2 text-[14.5px]"><Place className="size-4 text-[#0a6a86]" aria-hidden />{CONTACT.place.text}</p>
          </Reveal>
          <Reveal delay={0.1} className="l-card p-7 sm:p-8">
            <h2 className="l-title text-[1.45rem]">{CONTACT.form.title}</h2>
            <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={submit} data-testid="contact-form">
              {field("name", CONTACT.form.name)}
              {field("hospital", CONTACT.form.hospital)}
              <div className="sm:col-span-2">{field("role", CONTACT.form.role)}</div>
              <div className="sm:col-span-2">{field("message", CONTACT.form.message, true)}</div>
              <div className="sm:col-span-2">
                <button type="submit" className="l-btn l-btn-primary">{CONTACT.form.submit} <ArrowUpRight className="size-4" aria-hidden /></button>
                <p className="l-muted mt-3 text-[13px]">{CONTACT.form.note}</p>
              </div>
            </form>
          </Reveal>
        </div>
      </section>
    </SiteFrame>
  );
}
