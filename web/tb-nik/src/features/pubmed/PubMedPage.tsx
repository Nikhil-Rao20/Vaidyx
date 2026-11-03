// /pubmed: Ask PubMed on its own page (Home, no patient context; each login's own history). The Case Files home card opens it with
// ?q=<question>, which is asked once and then taken out of the address so a reload does not ask again.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { PubMedAsk } from "./PubMedAsk";
import { PubMedMark } from "./PubMedMark";

export default function PubMedPage() {
  const [params, setParams] = useSearchParams();
  const [seed] = useState(() => (params.get("q") ?? "").trim().slice(0, 600));
  useEffect(() => {
    if (params.has("q")) setParams((p) => { p.delete("q"); return p; }, { replace: true });
    // once, on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div data-testid="pubmed-page">
      <PageHeader
        title={<span className="inline-flex flex-wrap items-center gap-2.5">Ask PubMed <PubMedMark size="lg" className="align-middle" /></span>}
        subtitle="General questions, answered only from PubMed abstracts. Every line is quoted word for word, with a link to its paper. Published evidence, not advice for any patient."
      />
      <PubMedAsk variant="page" initialQuestion={seed || undefined} autoAsk={!!seed} />
    </div>
  );
}
