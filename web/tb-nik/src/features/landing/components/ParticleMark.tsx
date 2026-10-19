// The hero's living mark: a few thousand points scatter in from everywhere and settle into the Vaidyx "V" (records becoming one
// Case File), then breathe, turn slowly and lean with the pointer; as the page scrolls they drift apart and fade. Plain 2D canvas
// with a perspective projection, no library. Paused off-screen and in a hidden tab. Reduced motion: the finished mark, still.
import { useEffect, useRef } from "react";
import { useReducedMotion, type MotionValue } from "motion/react";
import { ICON_BOX, ICON_PATHS } from "@/components/brand-paths";

interface Dot { tx: number; ty: number; tz: number; sx: number; sy: number; sz: number; corner: number; jx: number; jy: number; d: number; ph: number; r: number; col: string; spark: boolean; arc: number }

const COLOURS: [string, string][] = [["#2e7fc9", "#19c1da"], ["#1db7cc", "#8fefe9"], ["#06cfd6", "#b8f6f7"]];
const VIOLET = "#9d7cff";

function hex(h: string): [number, number, number] { return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; }
function mix(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hex(a); const [r2, g2, b2] = hex(b);
  return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`;
}
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4);

/** Samples points inside the three icon paths (unit coordinates: x in [-1, 1], y keeps the aspect). */
function sample(count: number): Dot[] {
  if (typeof Path2D === "undefined") return [];
  const W = 335, H = 243;
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) return [];
  ctx.scale(W / ICON_BOX.w, H / ICON_BOX.h);
  ctx.translate(-ICON_BOX.x, -ICON_BOX.y);
  const keys = ["#ff0000", "#00ff00", "#0000ff"];
  ICON_PATHS.forEach((d, i) => { ctx.fillStyle = keys[i]; ctx.fill(new Path2D(d)); });
  const data = ctx.getImageData(0, 0, W, H).data;
  const cand: [number, number, number][] = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const o = (y * W + x) * 4;
    if (data[o + 3] > 90) cand.push([x, y, data[o] > 128 ? 0 : data[o + 1] > 128 ? 1 : 2]);
  }
  // shuffle, take `count`
  for (let i = cand.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [cand[i], cand[j]] = [cand[j], cand[i]]; }
  const take = cand.slice(0, Math.min(count, cand.length));
  const dots: Dot[] = take.map(([x, y, g]) => {
    const tx = (x - W / 2) / (W / 2) + (Math.random() - 0.5) * 0.004;
    const ty = (y - H / 2) / (W / 2) + (Math.random() - 0.5) * 0.004;
    const tz = (Math.random() - 0.5) * 0.22;
    // the start is set per corner of the screen once the canvas knows where it sits (placeStarts)
    const spark = Math.random() < 0.014;
    const t = (tx + 1) / 2;
    const [c0, c1] = COLOURS[g];
    return { tx, ty, tz, sx: tx, sy: ty, sz: tz, corner: Math.floor(Math.random() * 4), jx: (Math.random() - 0.5) * 0.5, jy: (Math.random() - 0.5) * 0.5, d: Math.random() * 0.7, ph: Math.random() * Math.PI * 2, r: spark ? 1.8 + Math.random() * 1.2 : 1.1 + Math.random() * 1.3, col: spark ? VIOLET : mix(c0, c1, t), spark, arc: (Math.random() - 0.5) * 0.6 };
  });
  dots.sort((p, q) => (p.col < q.col ? -1 : p.col > q.col ? 1 : 0));
  return dots;
}

function glowSprite(): HTMLCanvasElement {
  const s = document.createElement("canvas"); s.width = 64; s.height = 64;
  const g = s.getContext("2d")!;
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, "rgba(255,255,255,0.95)"); grd.addColorStop(0.25, "rgba(170,140,255,0.55)"); grd.addColorStop(1, "rgba(143,100,253,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  return s;
}

export function ParticleMark({ className, progress, count }: { className?: string; progress?: MotionValue<number>; count?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const fine = window.matchMedia("(pointer: fine)").matches;
    const n = count ?? (window.innerWidth < 768 ? 1300 : 2600);
    const dots = sample(n);
    if (!dots.length) return;
    const sprite = glowSprite();
    let w = 0, h = 0, dpr = 1, raf = 0, visible = true, running = true;
    let mx = 0, my = 0, tmx = 0, tmy = 0;
    const t0 = performance.now();

    /** Every point starts at one of the four corners of the screen (in the mark's unit space), with a little spread. */
    const placeStarts = (r: DOMRect) => {
      const R = Math.min(w * 0.46, h * 0.6) || 1;
      const ox = w / 2, oy = h / 2;
      const corners = [[-r.left, -r.top], [window.innerWidth - r.left, -r.top], [-r.left, window.innerHeight - r.top], [window.innerWidth - r.left, window.innerHeight - r.top]];
      for (const p of dots) {
        const [cx, cy] = corners[p.corner];
        p.sx = (cx - ox) / R + p.jx; p.sy = (cy - oy) / R + p.jy; p.sz = (Math.random() - 0.5) * 0.8;
      }
    };
    let placed = false;
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = Math.max(1, Math.round(r.width)); h = Math.max(1, Math.round(r.height));
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!placed && w > 1) { placeStarts(r); placed = true; }
      if (reduce) draw(performance.now());
    };

    const draw = (now: number) => {
      const t = (now - t0) / 1000;
      const dis = Math.min(1, Math.max(0, progress?.get() ?? 0));
      ctx.clearRect(0, 0, w, h);
      if (dis >= 0.999) return;
      mx += (tmx - mx) * 0.05; my += (tmy - my) * 0.05;
      const still = !!reduce;
      const rotY = still ? 0 : Math.sin(t * 0.22) * 0.28 + mx * 0.55;
      const rotX = still ? 0 : -my * 0.32 + Math.sin(t * 0.17) * 0.05;
      const cy = Math.cos(rotY), sy = Math.sin(rotY), cx = Math.cos(rotX), sx = Math.sin(rotX);
      const R = Math.min(w * 0.46, h * 0.6);
      const ox = w / 2, oy = h / 2;
      const f = 2.6;
      const spread = 1 + dis * 2.4;
      const fade = 1 - dis;
      let last = "";
      for (let i = 0; i < dots.length; i++) {
        const p = dots[i];
        const k = still ? 1 : easeOut(Math.min(1, Math.max(0, (t - 0.1 - p.d) / 2.0)));
        const fl = still ? 0 : 0.012;
        const bend = still ? 0 : Math.sin(k * Math.PI) * p.arc;   // a curved flight, straight at both ends
        const dx = p.tx - p.sx, dy = p.ty - p.sy;
        let x = p.sx + dx * k - dy * bend + Math.sin(t * 0.9 + p.ph) * fl * k;
        let y = p.sy + dy * k + dx * bend + Math.cos(t * 0.8 + p.ph * 1.3) * fl * k;
        let z = p.sz + (p.tz - p.sz) * k;
        // rotate about Y, then X
        const x1 = x * cy + z * sy; const z1 = -x * sy + z * cy;
        const y1 = y * cx - z1 * sx; const z2 = y * sx + z1 * cx;
        x = x1 * spread; y = y1 * spread; z = z2;
        const s = f / (f + z);
        const px = ox + x * s * R, py = oy + y * s * R;
        const depth = Math.min(1, Math.max(0, (s - 0.72) / 0.55));
        const a = (0.3 + 0.7 * k) * (0.45 + 0.55 * depth) * fade;
        if (a < 0.02) continue;
        const r = p.r * s;
        if (p.spark) {
          ctx.globalAlpha = a * (0.6 + 0.4 * Math.sin(t * 2.2 + p.ph));
          const g = r * 4;
          ctx.drawImage(sprite, px - g, py - g, g * 2, g * 2);
          continue;
        }
        if (p.col !== last) { ctx.fillStyle = p.col; last = p.col; }
        ctx.globalAlpha = a;
        ctx.fillRect(px - r / 2, py - r / 2, r, r);
      }
      ctx.globalAlpha = 1;
    };

    const loop = (now: number) => {
      if (!running) return;
      if (visible && !document.hidden) draw(now);
      raf = requestAnimationFrame(loop);
    };

    const onMove = (e: PointerEvent) => { tmx = e.clientX / window.innerWidth - 0.5; tmy = e.clientY / window.innerHeight - 0.5; };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    const io = new IntersectionObserver(([en]) => { visible = en.isIntersecting; }, { threshold: 0 });
    io.observe(canvas);
    if (fine && !reduce) window.addEventListener("pointermove", onMove, { passive: true });
    if (!reduce) raf = requestAnimationFrame(loop);
    const unsub = progress && reduce ? progress.on("change", () => draw(performance.now())) : undefined;
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect(); io.disconnect();
      window.removeEventListener("pointermove", onMove);
      unsub?.();
    };
  }, [reduce, progress, count]);
  return <canvas ref={ref} className={className} aria-hidden />;
}
