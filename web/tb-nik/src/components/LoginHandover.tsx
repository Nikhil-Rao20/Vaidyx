// The first login of a new or reset account, for an admin whose laptop has no mail program: the login name and the first password
// read from the mail draft Vaidyx made, shown only when the admin asks, with copy buttons. Vaidyx keeps no copy; the person must
// choose their own password at the first sign-in.
import { useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/CopyButton";

export function loginFromMailto(mailto: string): { login: string; password: string } | null {
  const q = mailto.indexOf("?");
  if (q < 0) return null;
  let body = "";
  try { body = new URLSearchParams(mailto.slice(q + 1)).get("body") ?? ""; } catch { return null; }
  const login = /Login name:\s*(\S+)/.exec(body)?.[1] ?? "";
  const password = /First password:\s*(\S+)/.exec(body)?.[1] ?? "";
  return password ? { login, password } : null;
}

export function LoginHandover({ mailto, className }: { mailto: string; className?: string }) {
  const [shown, setShown] = useState(false);
  const info = useMemo(() => loginFromMailto(mailto), [mailto]);
  if (!info) return null;
  return (
    <div className={className}>
      <Button type="button" variant="ghost" size="sm" onClick={() => setShown((s) => !s)} aria-expanded={shown}>
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />} {shown ? "Hide the first password" : "No mail program? Show the first password"}
      </Button>
      {shown ? (
        <div className="mt-2 grid gap-1.5 rounded-md border border-border bg-muted/60 p-3 text-sm" role="group" aria-label="First login">
          <div className="flex items-center gap-2"><span className="w-28 text-muted-foreground">Login name</span><span className="mono break-all">{info.login}</span><CopyButton text={info.login} label="Copy the login name" /></div>
          <div className="flex items-center gap-2"><span className="w-28 text-muted-foreground">First password</span><span className="mono break-all">{info.password}</span><CopyButton text={info.password} label="Copy the password" /></div>
          <p className="text-xs text-muted-foreground">Give it to the person directly (in person or by phone). They must choose their own at the first sign-in; Vaidyx keeps no copy.</p>
        </div>
      ) : null}
    </div>
  );
}
