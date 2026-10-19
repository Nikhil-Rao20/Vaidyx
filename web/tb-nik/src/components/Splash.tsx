// The entrance after a sign-in: the official Vaidyx reveal (brand/animation.html) plays large on a clean field, the product
// name settles under it, then the mark glides into its place in the top bar as the field dissolves into the app. About 5.5 s;
// a click, a tap or Escape skips it. Shown once per sign-in (sessionStorage flag set by the sign-in page), never on a reload.
// Reduced motion: the finished lockup for a moment, then a fade.
import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { BrandLockup, BrandMark, BrandWord } from "@/components/BrandReveal";
import { MARK_W, WORD_H } from "@/components/BrandEntrance";

const FLAG = "tbnik.splash";
const SPEED = 1.35;
const T_TAGLINE = 3200;   // "Tumour Board" settles under the wordmark
const T_MORPH = 5000;     // the mark glides to the top bar
const T_MORPH_LEN = 800;

export function requestSplash() {
  try { sessionStorage.setItem(FLAG, "1"); } catch { /* no storage */ }
}

function hasFlag(): boolean {
  try { return sessionStorage.getItem(FLAG) === "1"; } catch { return false; }
}
function clearFlag() {
  try { sessionStorage.removeItem(FLAG); } catch { /* no storage */ }
}

/* Where the icon sits inside the reveal's view box (the paths do not fill it): the centre, as fractions of the SVG box. */
const ICON_CX = 0.5052;
const ICON_CY = 0.5278;
const ICON_H = 454.462 / 485;

interface Morph { x: number; y: number; scale: number }

export function Splash() {
  // Read only: a first render that suspends (a lazy page chunk) is thrown away, so the flag is cleared after the mount instead.
  const [show, setShow] = useState(() => hasFlag());
  const [tagline, setTagline] = useState(false);
  const [morph, setMorph] = useState<Morph | null>(null);
  const reduce = useReducedMotion();
  const markRef = useRef<HTMLDivElement>(null);

  const finish = useCallback(() => setShow(false), []);

  // The mark's flight to the top bar's icon ([data-brand-anchor]); a plain fade when there is none.
  const startMorph = useCallback(() => {
    const anchor = document.querySelector<HTMLElement>("[data-brand-anchor]");
    const svg = markRef.current?.querySelector("svg");
    if (!anchor || !svg) { setShow(false); return; }
    const a = anchor.getBoundingClientRect();
    const s = svg.getBoundingClientRect();
    if (!a.width || !s.width) { setShow(false); return; }
    const iconH = s.height * ICON_H;
    setMorph({ x: a.left + a.width / 2 - (s.left + s.width * ICON_CX), y: a.top + a.height / 2 - (s.top + s.height * ICON_CY), scale: a.height / iconH });
    window.setTimeout(() => setShow(false), T_MORPH_LEN);
  }, []);

  useEffect(() => { if (show) clearFlag(); }, [show]);

  useEffect(() => {
    if (!show) return;
    if (reduce) {
      const t = window.setTimeout(finish, 900);
      return () => window.clearTimeout(t);
    }
    const t1 = window.setTimeout(() => setTagline(true), T_TAGLINE);
    const t2 = window.setTimeout(startMorph, T_MORPH);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("keydown", onKey);
    return () => { window.clearTimeout(t1); window.clearTimeout(t2); window.removeEventListener("keydown", onKey); };
  }, [show, reduce, finish, startMorph]);

  return (
    <AnimatePresence>
      {show ? (
        <motion.div
          key="splash"
          role="presentation"
          data-testid="splash"
          data-phase={morph ? "morph" : tagline ? "tagline" : "reveal"}
          className="fixed inset-0 z-[100] overflow-hidden bg-background"
          initial={{ opacity: 1 }}
          animate={{ opacity: morph ? 0 : 1, transition: { duration: morph ? 0.55 : 0, delay: morph ? 0.25 : 0, ease: "easeInOut" } }}
          exit={{ opacity: 0, transition: { duration: 0.3 } }}
          onClick={finish}
        >
          <div className="absolute inset-0 grid place-items-center">
            <BrandLockup play={!reduce} still={!!reduce} speed={SPEED}>
              <motion.div
                ref={markRef}
                style={{ transformOrigin: `${ICON_CX * 100}% ${ICON_CY * 100}%` }}
                animate={morph ? { x: morph.x, y: morph.y, scale: morph.scale } : { x: 0, y: 0, scale: 1 }}
                transition={{ duration: T_MORPH_LEN / 1000, ease: [0.65, 0, 0.35, 1] }}
              >
                <BrandMark style={{ "--br-mark-w": MARK_W } as React.CSSProperties} />
              </motion.div>
              <motion.div animate={{ opacity: morph ? 0 : 1, y: morph ? 10 : 0 }} transition={{ duration: 0.35 }}>
                <BrandWord style={{ "--br-word-h": WORD_H } as React.CSSProperties} />
              </motion.div>
              <motion.p
                className="text-[13px] font-medium uppercase text-brand"
                initial={{ opacity: 0, letterSpacing: "0.55em", y: 6 }}
                animate={tagline && !morph ? { opacity: 0.8, letterSpacing: "0.3em", y: 0 } : reduce ? { opacity: 0.8, letterSpacing: "0.3em", y: 0 } : { opacity: 0, letterSpacing: "0.55em", y: 6 }}
                transition={{ duration: 0.9, ease: "easeOut" }}
              >
                Tumour Board
              </motion.p>
            </BrandLockup>
          </div>
          <motion.span className="absolute bottom-6 right-6 text-xs text-muted-foreground" initial={{ opacity: 0 }} animate={{ opacity: morph ? 0 : 1 }} transition={{ delay: morph ? 0 : 1.2, duration: 0.5 }}>
            Click to skip
          </motion.span>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
