// Documentation: a placeholder until the documentation is written.
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { SiteFrame } from "../components/SiteFrame";
import { PageHead } from "../components/PageHead";
import { Reveal } from "../components/Reveal";
import { DOCS, SITE } from "../content";

export default function DocsPage() {
  return (
    <SiteFrame title="Vaidyx documentation" testId="docs">
      <PageHead eyebrow={DOCS.eyebrow} title={[DOCS.title[0], DOCS.title[1]]} compact />
      <section className="l-paper py-20 sm:py-28">
        <div className="mx-auto max-w-[1280px] px-5 sm:px-8">
          <Reveal className="l-card max-w-3xl p-7 sm:p-10">
            <p className="l-lead l-muted">{DOCS.text}</p>
            <Link to="/sign-in" className="l-btn l-btn-dark mt-8">{SITE.signIn} <ArrowRight className="size-4" aria-hidden /></Link>
          </Reveal>
        </div>
      </section>
    </SiteFrame>
  );
}
