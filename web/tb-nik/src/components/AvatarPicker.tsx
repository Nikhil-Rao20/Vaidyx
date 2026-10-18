// A photo for the profile: initials on a colour of the person's choice (drawn locally as SVG, no network), or an
// uploaded photo resized in the browser to a small JPEG. The result is a data URL under 200 KB (PUT /me/profile photo).
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Camera, Check, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

export const AVATAR_COLOURS = ["#00c0b5", "#046483", "#3e5cad", "#5b3fc4", "#1e6b45", "#8a5300", "#b23a2f", "#52606d"];

/** Initials on a colour, drawn on a canvas as a small PNG (the server takes PNG, JPEG, WebP or GIF data URLs only). */
export function initialsAvatar(name: string, colour: string): string {
  const text = initials(name);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 160;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no canvas");
    ctx.fillStyle = colour;
    const r = 32;
    ctx.beginPath();
    ctx.moveTo(r, 0);
    ctx.arcTo(160, 0, 160, 160, r);
    ctx.arcTo(160, 160, 0, 160, r);
    ctx.arcTo(0, 160, 0, 0, r);
    ctx.arcTo(0, 0, 160, 0, r);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 64px 'Atkinson Hyperlegible', system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 80, 84);
    return canvas.toDataURL("image/png");
  } catch {
    return "";
  }
}

async function fileToSmallJpeg(file: File, size = 192): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("That file is not a picture the browser can read."));
      i.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("The browser could not draw the picture.");
    const side = Math.min(img.naturalWidth, img.naturalHeight);
    const sx = (img.naturalWidth - side) / 2;
    const sy = (img.naturalHeight - side) / 2;
    ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
    for (const q of [0.85, 0.7, 0.55, 0.4]) {
      const out = canvas.toDataURL("image/jpeg", q);
      if (out.length < 190_000) return out;
    }
    throw new Error("The picture is too detailed to shrink enough; try a smaller one.");
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function AvatarPicker({ name, value, onChange, className }: { name: string; value?: string; onChange: (dataUrl: string) => void; className?: string }) {
  const [colour, setColour] = useState(AVATAR_COLOURS[0]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const isPhoto = Boolean(value && value.startsWith("data:image/jpeg"));
  // Initials drawn earlier follow the name as it is typed.
  const firstName = useRef(name);
  useEffect(() => {
    if (name === firstName.current) return;
    if (value && value.startsWith("data:image/png") && name.trim()) onChange(initialsAvatar(name, colour));
  }, [name]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = value || initialsAvatar(name || "?", colour) || undefined;

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      onChange(await fileToSmallJpeg(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not use that picture.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className={cn("flex flex-col gap-4 sm:flex-row sm:items-start", className)}>
      <motion.img
        key={(preview ?? "").slice(-48)}
        initial={{ scale: 0.9, opacity: 0.6 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 400, damping: 28 }}
        src={preview}
        alt={name ? `Picture for ${name}` : "Your picture"}
        className="size-24 shrink-0 rounded-2xl object-cover shadow-[var(--shadow-inner)]"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <p className="text-sm font-medium">Pick a colour for your initials</p>
          <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Colour">
            {AVATAR_COLOURS.map((c) => {
              const on = !isPhoto && c === colour;
              return (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  aria-label={`Colour ${c}`}
                  onClick={() => { setColour(c); onChange(initialsAvatar(name || "?", c)); }}
                  className={cn("grid size-8 place-items-center rounded-full outline-none ring-offset-2 ring-offset-background transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring active:scale-95", on && "ring-2 ring-foreground")}
                  style={{ background: c }}
                >
                  {on ? <Check className="size-4 text-white" aria-hidden /> : null}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" accept="image/*" className="sr-only" id="avatar-file" onChange={(e) => void pick(e.target.files?.[0])} />
          <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy} aria-busy={busy}>
            <Camera className="size-4" aria-hidden /> {busy ? "Shrinking the picture" : "Upload a photo"}
          </Button>
          {value ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange("")}>
              <Trash2 className="size-4" aria-hidden /> Remove
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">A photo is shrunk in your browser to a small square; only that small copy is saved.</p>
        {error ? <p role="alert" className="text-xs font-medium text-bad">{error}</p> : null}
      </div>
    </div>
  );
}
