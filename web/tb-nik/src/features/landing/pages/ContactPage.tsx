// Contact: the enquiry form. It is sent to the Vaidyx team through the site's own endpoint (/tb-nik/api/enquiry); when the
// server cannot send it, the visitor is given the direct address instead.
import { useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, Mail } from "lucide-react";
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Reveal } from "../components/Reveal";
import { CONTACT, SITE } from "../content";

type State = "idle" | "sending" | "sent" | "received" | "failed" | "invalid";

function mailto(): string {
  return `mailto:${SITE.email}?subject=${encodeURIComponent(CONTACT.subject)}`;
}

export default function ContactPage() {
  const [f, setF] = useState({ name: "", email: "", hospital: "", message: "", website: "" });
  const [state, setState] = useState<State>("idle");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (f.name.trim().length < 2 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim()) || f.message.trim().length < 10) { setState("invalid"); return; }
    setState("sending");
    try {
      const r = await fetch("/tb-nik/api/enquiry", { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "tb-nik" }, body: JSON.stringify(f) });
      if (!r.ok) { setState("failed"); return; }
      const body = (await r.json()) as { ok: boolean; sent: boolean };
      setState(body.sent ? "sent" : "received");
    } catch { setState("failed"); }
  };
  const field = (key: keyof typeof f, label: string, type = "text", textarea = false) => (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-[var(--l-fg-2)]">{label}</span>
      {textarea
        ? <textarea className="l-input min-h-[9rem]" value={f[key]} onChange={set(key)} required />
        : <input className="l-input" type={type} value={f[key]} onChange={set(key)} required={key !== "hospital"} autoComplete={key === "email" ? "email" : key === "name" ? "name" : "organization"} />}
    </label>
  );
  const done = state === "sent" || state === "received";
  return (
    <SiteFrame title="Contact the Vaidyx team" testId="contact">
      <PageHead eyebrow={CONTACT.eyebrow} title={[CONTACT.title[0], CONTACT.title[1]]} lead={CONTACT.lead} compact />
      <section className="l-section py-20 sm:py-24">
        <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
          <Reveal className="l-card mx-auto max-w-2xl p-7 sm:p-10">
            <AnimatePresence mode="wait" initial={false}>
              {done ? (
                <motion.div key="done" className="py-6 text-center" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="contact-done">
                  <span className="mx-auto grid size-14 place-items-center rounded-full" style={{ background: "var(--l-ok-bg)", color: "var(--l-ok)" }}><Check className="size-7" strokeWidth={2.5} aria-hidden /></span>
                  <p className="l-title mt-5 text-[1.5rem]">{state === "sent" ? CONTACT.form.sent : CONTACT.form.received}</p>
                </motion.div>
              ) : (
                <motion.form key="form" className="grid gap-4 sm:grid-cols-2" onSubmit={submit} data-testid="contact-form" initial={false} exit={{ opacity: 0 }}>
                  {field("name", CONTACT.form.name)}
                  {field("email", CONTACT.form.email, "email")}
                  <div className="sm:col-span-2">{field("hospital", CONTACT.form.hospital)}</div>
                  <div className="sm:col-span-2">{field("message", CONTACT.form.message, "text", true)}</div>
                  {/* a field people never see; a bot fills it */}
                  <input type="text" name="website" value={f.website} onChange={set("website")} tabIndex={-1} autoComplete="off" aria-hidden className="absolute -left-[9999px] h-0 w-0 opacity-0" />
                  <div className="sm:col-span-2">
                    <button type="submit" className="l-btn l-btn-primary" disabled={state === "sending"}>{state === "sending" ? CONTACT.form.sending : CONTACT.form.submit} <ArrowRight className="size-4" aria-hidden /></button>
                    {state === "invalid" ? <p className="mt-3 text-[13.5px]" style={{ color: "var(--l-warn)" }}>{CONTACT.form.invalid}</p> : null}
                    {state === "failed" ? <p className="mt-3 text-[13.5px]" style={{ color: "var(--l-warn)" }}>{CONTACT.form.failed} <a className="underline" href={mailto()}>{SITE.email}</a></p> : null}
                  </div>
                </motion.form>
              )}
            </AnimatePresence>
          </Reveal>
          <Reveal delay={0.1} className="mx-auto mt-6 max-w-2xl">
            <p className="l-muted flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-center text-[15px]">
              <Mail className="size-4 text-[var(--l-accent)]" aria-hidden />
              {CONTACT.direct} <a href={mailto()} className="font-semibold text-[var(--l-fg)] underline decoration-[var(--l-line-2)] underline-offset-4 hover:decoration-current" data-testid="contact-email">{SITE.email}</a>
            </p>
          </Reveal>
        </div>
      </section>
    </SiteFrame>
  );
}
