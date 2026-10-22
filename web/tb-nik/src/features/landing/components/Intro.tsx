// The website's entrance: the Vaidyx reveal (components/BrandEntrance), once per page load, the first time the Product page is
// shown. A reload plays it again; moving from About back to Product does not.
import { useEffect, useState } from "react";
import { BrandEntrance } from "@/components/BrandEntrance";
import { SITE } from "../content";

let played = false;   // per page load, not per visit of the route

export function Intro({ onDone }: { onDone: () => void }) {
  const [show] = useState(() => !played);
  useEffect(() => {
    if (show) played = true; else onDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!show) return null;
  return <div className="landing-intro-stage"><BrandEntrance onDone={onDone} background="var(--l-bg)" testId="site-intro" skipLabel={SITE.skip} /></div>;
}
