// The hospital's logo for the meeting PDF covers and the website: a PNG or JPEG up to 1 MB, chosen from the laptop, previewed, sent at once
// (not with the step), removable. The preview reads /hospital/logo with a cache-busting stamp after each change.
import { useRef, useState } from "react";
import { ImagePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { cn } from "@/lib/utils";

const MAX = 1_000_000;

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("The file could not be read."));
    r.readAsDataURL(file);
  });
}

export function LogoUpload({ hasLogo, onChanged, className }: { hasLogo: boolean; onChanged?: (has: boolean) => void; className?: string }) {
  const [stamp, setStamp] = useState(() => Date.now());
  const [present, setPresent] = useState(hasLogo);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const upload = useAsyncAction(async () => {
    const f = input.current?.files?.[0];
    if (!f) throw new Error("Choose a PNG or JPEG file first.");
    if (!["image/png", "image/jpeg"].includes(f.type)) throw new Error("PNG or JPEG only.");
    if (f.size > MAX) throw new Error("At most 1 MB. A wide version of the logo, about 1200 px across, reads best.");
    const data = await readAsDataUrl(f);
    await api.post(EP.setupHospitalLogo, { data });
    setPresent(true); setPreview(null); setStamp(Date.now()); setError(null);
    if (input.current) input.current.value = "";
    onChanged?.(true);
  }, { onError: (m) => setError(m) });
  const remove = useAsyncAction(async () => {
    await api.del(EP.setupHospitalLogo);
    setPresent(false); setPreview(null); setStamp(Date.now()); setError(null);
    onChanged?.(false);
  }, { onError: (m) => setError(m) });
  const src = preview ?? (present ? `${EP.hospitalLogo}?v=${stamp}` : null);
  return (
    <div className={cn("grid gap-2", className)}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="grid h-20 w-40 place-items-center overflow-hidden rounded-md border border-dashed border-border-strong bg-muted/60">
          {src ? <img src={src} alt="Hospital logo" className="max-h-16 max-w-36 object-contain" /> : <span className="text-xs text-muted-foreground">No logo yet</span>}
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <input ref={input} type="file" accept="image/png,image/jpeg" className="sr-only" id="h-logo" onChange={async (e) => { const f = e.target.files?.[0]; setError(null); if (f) { try { setPreview(await readAsDataUrl(f)); } catch { setPreview(null); } } }} />
          <Button type="button" variant="outline" size="sm" onClick={() => input.current?.click()}><ImagePlus className="size-4" aria-hidden />{present ? "Choose another file" : "Choose a file"}</Button>
          {preview ? <ActionButton type="button" size="sm" state={upload.state} doneText="Saved" loadingText="Sending" onClick={() => void upload.run()}>Use this logo</ActionButton> : null}
          {present && !preview ? <ActionButton type="button" variant="ghost" size="sm" state={remove.state} doneText="Removed" onClick={() => void remove.run()} icon={<Trash2 className="size-4" aria-hidden />}>Remove</ActionButton> : null}
        </div>
      </div>
      <p className={cn("text-xs", error ? "text-bad" : "text-muted-foreground")}>{error ?? "PNG or JPEG, up to 1 MB. It goes on the cover of every meeting PDF and next to the Vaidyx mark."}</p>
    </div>
  );
}
