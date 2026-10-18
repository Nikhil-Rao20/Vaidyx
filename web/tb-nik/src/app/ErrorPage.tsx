// The full-page error (404 / 500 / 403) with the React Bits FuzzyText (vendor, MIT) for the number.
import { lazy, Suspense, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Home, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/Wordmark";
import { useTheme } from "@/hooks/useTheme";

const FuzzyText = lazy(() => import("@/components/vendor/FuzzyText"));

const WORDS: Record<number, { title: string; text: string }> = {
  404: { title: "This page does not exist", text: "The link may be old, or the page moved." },
  403: { title: "You do not have permission for this page", text: "Ask your department admin if you think you should." },
  500: { title: "Something broke on this page", text: "Your work is safe; nothing was lost. Reload the page, or go back to Home." },
};

export function ErrorPage({ code = 500, title, text, detail, actions, embedded }: {
  code?: 404 | 403 | 500;
  title?: string;
  text?: string;
  detail?: string;
  actions?: ReactNode;
  /** Inside the shell (no wordmark, smaller). */
  embedded?: boolean;
}) {
  const navigate = useNavigate();
  const { theme } = useTheme(false);
  const words = WORDS[code] ?? WORDS[500];
  const colour = theme === "dark" ? "#9aa8b5" : "#52606d";
  return (
    <main className={embedded ? "grid min-h-[60vh] place-items-center p-4" : "grid min-h-dvh place-items-center p-4"}>
      <div className="surface flex w-full max-w-lg flex-col items-center gap-4 p-8 text-center">
        {!embedded ? <Wordmark size="sm" /> : null}
        <div className="h-24" aria-hidden>
          <Suspense fallback={<p className="text-7xl font-bold text-muted-foreground">{code}</p>}>
            <FuzzyText fontSize={88} fontWeight={700} color={colour} baseIntensity={0.12} hoverIntensity={0.4} fontFamily="Atkinson Hyperlegible, system-ui, sans-serif">
              {String(code)}
            </FuzzyText>
          </Suspense>
        </div>
        <span className="sr-only">Error {code}</span>
        <h1>{title ?? words.title}</h1>
        <p className="max-w-md text-sm text-muted-foreground">{text ?? words.text}</p>
        {detail ? <pre className="max-w-full overflow-auto rounded-md bg-muted p-2 text-left text-xs text-muted-foreground mono whitespace-pre-wrap">{detail}</pre> : null}
        <div className="flex flex-wrap justify-center gap-2">
          {actions}
          {code === 500 ? <Button type="button" onClick={() => window.location.reload()}><RefreshCw className="size-4" aria-hidden /> Reload</Button> : null}
          <Button type="button" variant={code === 500 ? "outline" : "default"} asChild><Link to="/home"><Home className="size-4" aria-hidden /> Go to Home</Link></Button>
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}><ArrowLeft className="size-4" aria-hidden /> Go back</Button>
        </div>
      </div>
    </main>
  );
}
