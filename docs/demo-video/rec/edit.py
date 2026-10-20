"""The editor of the Vaidyx-TB demo video.

  python edit.py layout     timeline from edit/plan.json + edit/voice/voice.json -> edit/timeline.json, overlay pages -> edit/ov/*.html
  node overlays.cjs         overlay pages -> PNGs (Playwright)
  python edit.py render     chapters rendered in parallel -> edit/pieces/<chapter>.mp4
  python edit.py final      concat, narration mix, captions (burned in and .srt), chapter markers -> out/

Canvas 1920x1080 at 30 fps. The app recording sits in a rounded frame on a quiet brand background; the caption bar is under it, so no
caption ever covers the app. Speed-ups are marked on screen. Runs in the pdf venv (Pillow, numpy, imageio-ffmpeg).
"""
import bisect
import html
import json
import math
import os
import shutil
import subprocess
import sys
import wave
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

RUN = os.environ.get("DEMO_RUN", "run2")
ROOT = "/data/vaidyx/demo_video"
RAW = f"{ROOT}/raw/{RUN}"
EDIT = f"{ROOT}/edit"
OV = f"{EDIT}/ov"
PIECES = f"{EDIT}/pieces"
OUTDIR = f"{ROOT}/out"
FPS, W, H = 30, 1920, 1080
SR = 24000
XFADE, PIECE_FADE = 0.35, 0.45
WEB = "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/public"

BOX_FULL = (160, 40, 1600, 900)
BOX_L, BOX_R = (166, 58, 786, 882), (968, 58, 786, 882)
BOX_PHONE = (757, 40, 407, 880)
PIP = (1296, 672, 448, 252)
CAP_Y = 940
TOP_H = 56


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---------------------------------------------------------------------------------------------------------------- layout
def voice_index():
    return json.load(open(f"{EDIT}/voice/voice.json"))


def schedule(seg, voice):
    """Frame count and narration placement of one segment (times in seconds from the segment start)."""
    lines = seg.get("lines", [])
    durs = [voice[l["id"]]["seconds"] for l in lines]
    if "t0" in seg:
        src = seg["t1"] - seg["t0"]
        speed = seg.get("speed", 1.0)
        for _ in range(3):
            starts, end = [], 0.0
            for l, d in zip(lines, durs):
                want = l["at"] / speed + (0.35 if l["at"] == 0 else 0.0)
                s = max(want, end + 0.35 if starts else want)
                starts.append(s)
                end = s + d
            need = end + 0.7
            vid = src / speed
            if need > vid and speed > 1.0:
                speed = max(1.0, src / need)
                continue
            break
        dur = max(vid, need)
    else:
        speed = 1.0
        starts, end = [], 0.0
        for l, d in zip(lines, durs):
            s = max(l["at"], end + 0.35 if starts else l["at"])
            starts.append(s)
            end = s + d
        base = seg.get("dur", 0) or (len(seg.get("images", [])) * seg.get("per", 3.0))
        dur = max(base, end + 0.8)
    nframes = int(round(dur * FPS))
    placed = [{"id": l["id"], "text": l["text"], "start": round(s, 3), "dur": d} for l, s, d in zip(lines, starts, durs)]
    return speed, nframes, placed


def layout():
    plan = json.load(open(f"{EDIT}/plan.json"))
    voice = voice_index()
    numbered = [c for c in plan if c.get("title")]
    timeline, t = [], 0.0
    for ch in plan:
        piece = {"id": ch["id"], "title": ch.get("title"), "number": ch.get("number"), "segments": [], "start": round(t, 3)}
        frames = 0
        for seg in ch["segments"]:
            speed, n, placed = schedule(seg, voice)
            s = dict(seg)
            s.update(speed_used=speed, frames=n, start_frame=frames, placed=placed)
            piece["segments"].append(s)
            frames += n
        piece["frames"] = frames
        timeline.append(piece)
        t += frames / FPS
    json.dump(timeline, open(f"{EDIT}/timeline.json", "w"), indent=1)
    write_overlays(timeline, numbered)
    total = sum(p["frames"] for p in timeline) / FPS
    for p in timeline:
        print(f"{p['id']}: {p['frames'] / FPS:6.1f} s  {p.get('title') or ''}")
    print(f"total {total / 60:.2f} min, {sum(p['frames'] for p in timeline)} frames")


# ---------------------------------------------------------------------------------------------------------------- overlays
CSS = """
@font-face { font-family: Inter; src: url(fonts/inter-latin-wght-normal.woff2) format("woff2"); font-weight: 100 900; }
@font-face { font-family: Inter; src: url(fonts/inter-latin-ext-wght-normal.woff2) format("woff2"); font-weight: 100 900;
  unicode-range: U+0100-024F, U+1E00-1EFF, U+2020, U+20A0-20AB, U+20AD-20CF, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: Serif; src: url(fonts/instrument-serif-latin-400-italic.woff2) format("woff2"); font-style: italic; }
@font-face { font-family: Serif; src: url(fonts/instrument-serif-latin-400-normal.woff2) format("woff2"); font-style: normal; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: transparent; }
body { font-family: Inter, sans-serif; -webkit-font-smoothing: antialiased; color: #0f172a; font-feature-settings: "cv11", "ss01"; }
.canvas { position: absolute; inset: 0; overflow: hidden; background: #eef2f6; }
.glow { position: absolute; border-radius: 50%; }
.g1 { width: 1300px; height: 1300px; right: -380px; top: -640px; background: radial-gradient(circle, rgba(1,203,211,.26) 0%, rgba(1,203,211,0) 68%); }
.g2 { width: 1200px; height: 1200px; left: -420px; bottom: -700px; background: radial-gradient(circle, rgba(143,100,253,.16) 0%, rgba(143,100,253,0) 68%); }
.grid { position: absolute; inset: 0; background-image: linear-gradient(rgba(15,23,42,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,.035) 1px, transparent 1px);
  background-size: 64px 64px; -webkit-mask-image: radial-gradient(ellipse at 60% 30%, #000 0%, transparent 75%); }
.box { position: absolute; border-radius: 18px; background: #fff; box-shadow: 0 34px 70px -24px rgba(15,23,42,.38), 0 0 0 1px rgba(15,23,42,.08); }
.box.active { box-shadow: 0 34px 70px -24px rgba(15,23,42,.38), 0 0 0 4px #01b4c2, 0 0 0 9px rgba(1,180,194,.18); }
.bezel { position: absolute; border-radius: 56px; background: #0b1220; box-shadow: 0 40px 80px -24px rgba(15,23,42,.5), inset 0 0 0 2px #273449; }
.logo { display: flex; align-items: center; gap: 14px; }
.logo img.icon { height: 100%; }
"""

def page(name, body, w=W, h=H, transparent=False):
    os.makedirs(OV, exist_ok=True)
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}
body {{ width: {w}px; height: {h}px; position: relative; overflow: hidden; }}</style></head><body>{body}</body></html>"""
    open(f"{OV}/{name}.html", "w").write(doc)
    return {"name": name, "w": w, "h": h, "transparent": transparent}


def canvas_html(extra=""):
    return f'<div class="canvas"><div class="glow g1"></div><div class="glow g2"></div><div class="grid"></div>{extra}</div>'


def box(b, cls="box"):
    x, y, w, h = b
    return f'<div class="{cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"></div>'


def logo(h=40, dark=False):
    word = "vaidyx-wordmark-dark.svg" if dark else "vaidyx-wordmark.svg"
    return (f'<div class="logo" style="height:{h}px"><img class="icon" src="brand/vaidyx-icon.svg" style="height:{h}px">'
            f'<img src="brand/{word}" style="height:{h * 0.72:.0f}px"></div>')


def esc(s):
    return html.escape(s or "")


def caption_html(ch, seg, text):
    num = f"{ch['number']:02d}" if ch.get("number") else ""
    title = esc(ch.get("title") or "Introduction")
    who = esc(seg.get("label") or "")
    chip = f'<span style="background:#0e7490;color:#fff;border-radius:6px;padding:3px 9px;font-variant-numeric:tabular-nums;letter-spacing:.04em">{num}</span>' if num else ""
    return f"""<div style="position:absolute;left:160px;width:1600px;top:12px">
  <div style="display:flex;align-items:center;gap:12px;font-size:15px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#0e7490">
    {chip}<span>{title}</span>{f'<span style="color:#94a3b8">·</span><span style="color:#475569;font-weight:500;letter-spacing:.02em;text-transform:none">{who}</span>' if who else ''}
    <span style="margin-left:auto;color:#94a3b8;font-weight:500;font-size:13px;letter-spacing:.03em;text-transform:none">Synthetic data · recorded live on localhost:7000</span></div>
  <div style="margin-top:9px;font-size:25px;line-height:1.36;font-weight:500;color:#0f172a;letter-spacing:-.005em">{esc(text)}</div>
</div>"""


def write_overlays(timeline, numbered):
    os.makedirs(OV, exist_ok=True)
    for sub in ("fonts", "brand"):
        if not os.path.exists(f"{OV}/{sub}"):
            shutil.copytree(f"{WEB}/{sub}", f"{OV}/{sub}")
    items = [
        page("bg_plain", canvas_html()),
        page("bg_full", canvas_html(box(BOX_FULL))),
        page("bg_split_left", canvas_html(box(BOX_L, "box active") + box(BOX_R))),
        page("bg_split_right", canvas_html(box(BOX_L) + box(BOX_R, "box active"))),
        page("bg_phone", canvas_html(f'<div class="bezel" style="left:{BOX_PHONE[0] - 16}px;top:{BOX_PHONE[1] - 16}px;width:{BOX_PHONE[2] + 32}px;height:{BOX_PHONE[3] + 32}px"></div>'
                                     f'<div style="position:absolute;left:{W // 2 - 36}px;top:{BOX_PHONE[1] - 10}px;width:72px;height:5px;border-radius:3px;background:#273449"></div>')),
    ]
    agenda = "".join(
        f'<div style="display:flex;gap:18px;align-items:baseline;padding:14px 0;border-top:1px solid rgba(15,23,42,.08)">'
        f'<span style="font-family:Serif;font-style:italic;font-size:34px;color:#0e7490;width:44px">{c["number"]}</span>'
        f'<span><span style="font-size:24px;font-weight:600">{esc(c["title"])}</span><br><span style="font-size:17px;color:#64748b">{esc(c["subtitle"])}</span></span></div>'
        for c in numbered)
    half = (len(numbered) + 1) // 2
    blocks = agenda.split("</div></div>")
    for p in timeline:
        for s in p["segments"]:
            sid = s["id"]
            if s["layout"] == "title":
                items.append(page(f"card_{sid}", canvas_html(f"""
<div style="position:absolute;left:0;right:0;top:318px;display:flex;flex-direction:column;align-items:center;text-align:center">
  {logo(86)}
  <div style="margin-top:20px;font-size:22px;letter-spacing:.32em;text-transform:uppercase;color:#0e7490;font-weight:600">Tumour Board</div>
  <div style="margin-top:46px;font-size:76px;font-weight:650;letter-spacing:-.035em;line-height:1.02">The platform, <span style="font-family:Serif;font-style:italic;font-weight:400;color:#0b4a6b">end to end.</span></div>
  <div style="margin-top:26px;font-size:26px;color:#475569">A walkthrough for the Vaidyx tech team · recorded live on the development server · 20 October 2026</div>
  <div style="margin-top:40px;display:inline-flex;gap:10px;align-items:center;font-size:19px;font-weight:600;color:#8a5200;background:#fdf1d6;border:1px solid #f3d38a;border-radius:999px;padding:10px 22px">
    Every patient, identifier and value in this video is synthetic</div>
</div>""")))
            elif s["layout"] == "agenda":
                left = "".join(f'<div style="display:flex;gap:18px;align-items:baseline;padding:13px 0;border-top:1px solid rgba(15,23,42,.09)"><span style="font-family:Serif;font-style:italic;font-size:34px;color:#0e7490;width:46px">{c["number"]:02d}</span><span><span style="font-size:24px;font-weight:600">{esc(c["title"])}</span><br><span style="font-size:17px;color:#64748b">{esc(c["subtitle"])}</span></span></div>' for c in numbered[:half])
                right = "".join(f'<div style="display:flex;gap:18px;align-items:baseline;padding:13px 0;border-top:1px solid rgba(15,23,42,.09)"><span style="font-family:Serif;font-style:italic;font-size:34px;color:#0e7490;width:46px">{c["number"]:02d}</span><span><span style="font-size:24px;font-weight:600">{esc(c["title"])}</span><br><span style="font-size:17px;color:#64748b">{esc(c["subtitle"])}</span></span></div>' for c in numbered[half:])
                items.append(page(f"card_{sid}", canvas_html(f"""
<div style="position:absolute;left:160px;top:70px">{logo(40)}</div>
<div style="position:absolute;left:160px;top:170px;font-size:18px;letter-spacing:.24em;text-transform:uppercase;color:#0e7490;font-weight:600">What you will see</div>
<div style="position:absolute;left:160px;top:208px;font-size:56px;font-weight:650;letter-spacing:-.03em">One patient, <span style="font-family:Serif;font-style:italic;font-weight:400;color:#0b4a6b">from records to a decision.</span></div>
<div style="position:absolute;left:160px;top:330px;width:760px">{left}</div>
<div style="position:absolute;left:1000px;top:330px;width:760px">{right}</div>""")))
            elif s["layout"] == "card":
                n = p["number"]
                dots = "".join(f'<span style="width:{46 if i + 1 == n else 22}px;height:6px;border-radius:3px;background:{"#01b4c2" if i + 1 == n else "rgba(15,23,42,.14)"}"></span>' for i in range(len(numbered)))
                ch = next(c for c in numbered if c["number"] == n)
                items.append(page(f"card_{sid}", canvas_html(f"""
<div style="position:absolute;left:160px;top:70px">{logo(40)}</div>
<div style="position:absolute;left:160px;top:300px">
  <div style="font-family:Serif;font-style:italic;font-size:190px;line-height:.9;color:#01a3b0">{n:02d}</div>
  <div style="margin-top:34px;font-size:84px;font-weight:650;letter-spacing:-.04em;line-height:1">{esc(p['title'])}</div>
  <div style="margin-top:24px;font-size:32px;color:#475569">{esc(ch['subtitle'])}</div>
</div>
<div style="position:absolute;left:160px;bottom:80px;display:flex;gap:8px;align-items:center">{dots}</div>
<div style="position:absolute;right:160px;bottom:74px;font-size:17px;color:#94a3b8">Synthetic data · recorded live on localhost:7000</div>""")))
            elif s["layout"] == "outro":
                bullets = ["Registration, the OPD visit and every report, in the hospital system",
                           "A Case File from the UHID, read in seconds, every value with its quote",
                           "A request to Pathology, answered in the hospital system, closed by itself",
                           "The summary and specialty briefs, the meeting, the decision and the minutes",
                           "Administration, the phone, and the public website"]
                lis = "".join(f'<div style="display:flex;gap:14px;align-items:baseline;font-size:25px;margin-top:14px"><span style="width:10px;height:10px;border-radius:50%;background:#01b4c2;flex:none;transform:translateY(-3px)"></span>{esc(b)}</div>' for b in bullets)
                items.append(page(f"card_{sid}", canvas_html(f"""
<div style="position:absolute;left:160px;top:70px">{logo(40)}</div>
<div style="position:absolute;left:160px;top:230px;width:1500px">
  <div style="font-size:72px;font-weight:650;letter-spacing:-.035em;line-height:1.04">From the hospital's records <span style="font-family:Serif;font-style:italic;font-weight:400;color:#0b4a6b">to a Board decision.</span></div>
  <div style="margin-top:44px">{lis}</div>
</div>
<div style="position:absolute;left:160px;bottom:74px;font-size:17px;color:#64748b">Recorded live with Playwright on localhost:7000, 20 October 2026 · narration: Kokoro-82M (af_heart), on the server · every patient and value is synthetic</div>""")))
            # captions of footage segments
            if s["layout"] not in ("title", "agenda", "card", "outro"):
                for k, l in enumerate(s["placed"]):
                    items.append(page(f"cap_{l['id']}", caption_html(p, s, l["text"]), w=W, h=H - CAP_Y, transparent=True))
                if not s["placed"]:
                    items.append(page(f"cap_{sid}-none", caption_html(p, s, ""), w=W, h=H - CAP_Y, transparent=True))
            if s["layout"] == "split":
                def lab(text, x, active, his):
                    dot = "#1f4e79" if his else "#01b4c2"
                    col = "#0f172a" if active else "#64748b"
                    return (f'<div style="position:absolute;left:{x}px;top:18px;display:flex;align-items:center;gap:10px;font-size:17px;font-weight:{650 if active else 550};color:{col}">'
                            f'<span style="width:11px;height:11px;border-radius:50%;background:{dot};box-shadow:0 0 0 {4 if active else 0}px {dot}33"></span>{esc(text)}</div>')
                items.append(page(f"top_{sid}", lab(s["llabel"], BOX_L[0] + 4, s["active"] == "left", False) + lab(s["rlabel"], BOX_R[0] + 4, s["active"] == "right", True), w=W, h=TOP_H, transparent=True))
            if s.get("speed", 1.0) >= 1.5 and "t0" in s:
                x = s["speed_used"]
                txt = f"{x:.0f}× faster" if x >= 3 else f"{x:.1f}× faster".replace(".0×", "×")
                items.append(page(f"tag_{sid}", f"""<div id="t" style="position:absolute;left:0;top:0;display:inline-flex;align-items:center;gap:8px;background:rgba(15,23,42,.8);color:#fff;
font-size:16px;font-weight:600;border-radius:999px;padding:8px 14px 8px 12px;letter-spacing:.01em">
<svg width="18" height="14" viewBox="0 0 18 14"><path d="M1 1l7 6-7 6zM9 1l7 6-7 6z" fill="#5fe3ea"/></svg>{txt}</div>""", w=220, h=40, transparent=True))
            if s["layout"] == "pip":
                items.append(page(f"piplabel_{sid}", f"""<div style="position:absolute;left:0;top:0;display:inline-flex;align-items:center;gap:8px;background:#0e7490;color:#fff;font-size:15px;font-weight:600;border-radius:8px;padding:6px 12px">{esc(s.get('piplabel', ''))}</div>""", w=260, h=36, transparent=True))
    json.dump(items, open(f"{OV}/manifest.json", "w"), indent=1)
    print(f"{len(items)} overlay pages")


# ---------------------------------------------------------------------------------------------------------------- rendering
class Source:
    """The frames of one recorded session: the frame shown at a wall-clock time, decoded and resized with a small cache."""

    def __init__(self, name):
        rows = [l.rstrip("\n").split("\t") for l in open(f"{RAW}/{name}/frames.tsv")]
        self.name = name
        self.ts = [float(r[0]) for r in rows]
        self.files = [r[1] for r in rows]
        self.cache = {}

    def index(self, t):
        return max(0, bisect.bisect_right(self.ts, t) - 1)

    def image(self, t, size):
        i = self.index(t)
        key = (i, size)
        if key not in self.cache:
            if len(self.cache) > 24:
                self.cache.pop(next(iter(self.cache)))
            im = Image.open(f"{RAW}/{self.name}/{self.files[i]}").convert("RGB")
            if im.size != size:
                im = im.resize(size, Image.LANCZOS)
            self.cache[key] = np.asarray(im)
        return self.cache[key]


def png(name):
    return Image.open(f"{OV}/{name}.png")


def rgb(name):
    return np.asarray(png(name).convert("RGB"))


def over(base_img, top_img, xy=(0, 0)):
    b = base_img.convert("RGBA")
    b.alpha_composite(top_img.convert("RGBA"), xy)
    return b.convert("RGB")


def corner_masks(r):
    yy, xx = np.mgrid[0:r, 0:r]
    d = np.sqrt((r - xx - 0.5) ** 2 + (r - yy - 0.5) ** 2)
    m = np.clip(r - d + 0.5, 0, 1)[..., None]  # top-left corner, 1 inside the rounded box
    return {"tl": m, "tr": m[:, ::-1], "bl": m[::-1, :], "br": m[::-1, ::-1]}


def paste(out, bg, img, b, r=18):
    x, y, w, h = b
    out[y:y + h, x:x + w] = img
    if r:
        m = corner_masks(r)
        for k, (cy, cx) in {"tl": (y, x), "tr": (y, x + w - r), "bl": (y + h - r, x), "br": (y + h - r, x + w - r)}.items():
            region = out[cy:cy + r, cx:cx + r].astype(np.float32)
            back = bg[cy:cy + r, cx:cx + r].astype(np.float32)
            out[cy:cy + r, cx:cx + r] = (region * m[k] + back * (1 - m[k])).astype(np.uint8)


def blend_rgba(out, top, xy):
    """Alpha-blend an RGBA numpy image onto out at xy."""
    x, y = xy
    h, w = top.shape[:2]
    a = top[..., 3:4].astype(np.float32) / 255
    out[y:y + h, x:x + w] = (top[..., :3] * a + out[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)


def render_piece(pid):
    timeline = json.load(open(f"{EDIT}/timeline.json"))
    piece = next(p for p in timeline if p["id"] == pid)
    os.makedirs(PIECES, exist_ok=True)
    out_path = f"{PIECES}/{pid}.mp4"
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "60", "-threads", "6",
           "-x264-params", "keyint=60:min-keyint=60:scenecut=0", out_path]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    sources = {}

    def src(name):
        if name not in sources:
            sources[name] = Source(name)
        return sources[name]

    plain = rgb("bg_plain")
    bgs = {k: rgb(k) for k in ("bg_full", "bg_split_left", "bg_split_right", "bg_phone")}
    prev_last = None
    total = piece["frames"]
    fade_n = int(PIECE_FADE * FPS)
    gidx = 0
    for seg in piece["segments"]:
        lay, n, sid = seg["layout"], seg["frames"], seg["id"]
        speed = seg.get("speed_used", 1.0)
        bg = {"full": bgs["bg_full"], "pip": bgs["bg_full"], "still": bgs["bg_full"], "phone": bgs["bg_phone"],
              "split": bgs["bg_split_left" if seg.get("active") == "left" else "bg_split_right"]}.get(lay)
        card = rgb(f"card_{sid}") if lay in ("title", "agenda", "card", "outro") else None
        # caption strips: background under the caption, composited once per line
        strips = []
        if card is None:
            names = [f"cap_{l['id']}" for l in seg["placed"]] or [f"cap_{sid}-none"]
            base = Image.fromarray(bg[CAP_Y:H])
            for k, nm in enumerate(names):
                show_from = 0 if k == 0 else int((seg["placed"][k]["start"] - 0.1) * FPS)
                strips.append((show_from, np.asarray(over(base, png(nm)))))
        top = None
        if lay == "split":
            top = np.asarray(over(Image.fromarray(bg[0:TOP_H]), png(f"top_{sid}")))
        tag = np.asarray(png(f"tag_{sid}").convert("RGBA")) if os.path.exists(f"{OV}/tag_{sid}.png") else None
        if tag is not None:  # crop to the pill
            a = tag[..., 3]
            ys, xs = np.where(a > 0)
            tag = tag[: ys.max() + 2, : xs.max() + 2]
        piplabel = None
        if lay == "pip":
            pl = np.asarray(png(f"piplabel_{sid}").convert("RGBA"))
            ys, xs = np.where(pl[..., 3] > 0)
            piplabel = pl[: ys.max() + 2, : xs.max() + 2]
        stills = [np.asarray(Image.open(p).convert("RGB")) for p in seg.get("images", [])]
        for i in range(n):
            tau = i / FPS
            if card is not None:
                frame = card.copy()
            else:
                frame = bg.copy()
                if "t0" in seg:
                    t = seg["t0"] + min(tau * speed, seg["t1"] - seg["t0"])
                if lay == "full":
                    paste(frame, bg, src(seg["src"]).image(t, BOX_FULL[2:]), BOX_FULL)
                elif lay == "pip":
                    paste(frame, bg, src(seg["src"]).image(t, BOX_FULL[2:]), BOX_FULL)
                    x, y, w, h = PIP
                    frame[y - 4:y + h + 4, x - 4:x + w + 4] = (255, 255, 255)
                    frame[y:y + h, x:x + w] = src(seg["pip"]).image(t, (w, h))
                    blend_rgba(frame, piplabel, (x, y - piplabel.shape[0] - 8))
                elif lay == "split":
                    paste(frame, bg, src(seg["left"]).image(t, BOX_L[2:]), BOX_L, r=14)
                    paste(frame, bg, src(seg["right"]).image(t, BOX_R[2:]), BOX_R, r=14)
                    frame[0:TOP_H] = top
                elif lay == "phone":
                    paste(frame, bg, src(seg["src"]).image(t, BOX_PHONE[2:]), BOX_PHONE, r=40)
                elif lay == "still":
                    per = n / len(stills)
                    k = min(len(stills) - 1, int(i // per))
                    local = (i - k * per) / per

                    def kb(img, u):
                        z = 1.0 + 0.045 * u
                        cw, chh = int(W / z), int(H / z)
                        x0, y0 = (W - cw) // 2, (H - chh) // 2
                        return np.asarray(Image.fromarray(img[y0:y0 + chh, x0:x0 + cw]).resize(BOX_FULL[2:], Image.BICUBIC))
                    img = kb(stills[k], local)
                    if k > 0 and local * per < XFADE * FPS:
                        a = (local * per) / (XFADE * FPS)
                        img = (img * a + kb(stills[k - 1], 1.0) * (1 - a)).astype(np.uint8)
                    paste(frame, bg, img, BOX_FULL)
                if tag is not None and lay != "split":
                    blend_rgba(frame, tag, (BOX_FULL[0] + BOX_FULL[2] - tag.shape[1] - 20, BOX_FULL[1] + 18))
                elif tag is not None:
                    blend_rgba(frame, tag, (BOX_R[0] + BOX_R[2] - tag.shape[1] - 16, BOX_R[1] + 16))
                strip = strips[0][1]
                for f0, s_ in strips:
                    if i >= f0:
                        strip = s_
                frame[CAP_Y:H] = strip
            # transitions: cross-fade from the previous segment, fade in from and out to the plain background
            if prev_last is not None and i < XFADE * FPS:
                a = i / (XFADE * FPS)
                frame = (frame.astype(np.float32) * a + prev_last.astype(np.float32) * (1 - a)).astype(np.uint8)
            if gidx < fade_n:
                a = gidx / fade_n
                frame = (frame.astype(np.float32) * a + plain.astype(np.float32) * (1 - a)).astype(np.uint8)
            if gidx >= total - fade_n:
                a = (total - 1 - gidx) / fade_n
                frame = (frame.astype(np.float32) * a + plain.astype(np.float32) * (1 - a)).astype(np.uint8)
            enc.stdin.write(np.ascontiguousarray(frame).tobytes())
            gidx += 1
            if i == n - 1:
                prev_last = frame
    enc.stdin.close()
    enc.wait()
    return pid, total


def render(only=None):
    timeline = json.load(open(f"{EDIT}/timeline.json"))
    ids = [p["id"] for p in timeline if not only or p["id"] in only]
    ids.sort(key=lambda i: -next(p["frames"] for p in timeline if p["id"] == i))
    with ProcessPoolExecutor(max_workers=min(10, len(ids))) as ex:
        for pid, n in ex.map(render_piece, ids):
            print(f"rendered {pid}: {n} frames", flush=True)


# ---------------------------------------------------------------------------------------------------------------- final
def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def final():
    timeline = json.load(open(f"{EDIT}/timeline.json"))
    os.makedirs(OUTDIR, exist_ok=True)
    total = sum(p["frames"] for p in timeline) / FPS
    mix = np.zeros(int((total + 1) * SR), dtype=np.float32)
    subs, chapters = [], []
    t_piece = 0.0
    for p in timeline:
        chapters.append((t_piece, p.get("title") or ("Introduction" if p["id"] == "c00" else "Close")))
        for s in p["segments"]:
            t_seg = t_piece + s["start_frame"] / FPS
            seg_end = t_seg + s["frames"] / FPS
            for k, l in enumerate(s["placed"]):
                path = f"{EDIT}/voice/{l['id']}.wav"
                with wave.open(path) as w:
                    data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
                i0 = int((t_seg + l["start"]) * SR)
                mix[i0:i0 + len(data)] += data[: len(mix) - i0]
                if s["layout"] not in ("card",):
                    end = (t_seg + s["placed"][k + 1]["start"] - 0.1) if k + 1 < len(s["placed"]) else seg_end - 0.05
                    subs.append((t_seg + max(0.0, l["start"] - 0.1), min(end, t_seg + l["start"] + l["dur"] + 1.5), l["text"]))
        t_piece += p["frames"] / FPS
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.89
    narr = f"{EDIT}/narration.wav"
    with wave.open(narr, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    srt = f"{OUTDIR}/transcript-captions.srt"
    with open(srt, "w") as f:
        for i, (a, b, text) in enumerate(subs, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n")
    meta = f"{EDIT}/chapters.txt"
    with open(meta, "w") as f:
        f.write(";FFMETADATA1\ntitle=Vaidyx Tumour Board: the platform, end to end\nartist=Vaidyx (TANUH)\ncomment=Synthetic data only. Recorded live on localhost:7000, 20 October 2026.\n")
        for i, (st, title) in enumerate(chapters):
            en = chapters[i + 1][0] if i + 1 < len(chapters) else total
            f.write(f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(st * 1000)}\nEND={int(en * 1000)}\ntitle={title}\n")
    lst = f"{EDIT}/pieces.txt"
    with open(lst, "w") as f:
        for p in timeline:
            f.write(f"file '{PIECES}/{p['id']}.mp4'\n")
    video = f"{EDIT}/video.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video], check=True)
    out = f"{OUTDIR}/vaidyx-tb-demo.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", video, "-i", narr, "-i", meta,
                    "-map", "0:v", "-map", "1:a", "-map_metadata", "2", "-map_chapters", "2",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                     "-metadata:s:a:0", "language=eng",
                    "-movflags", "+faststart", "-shortest", out], check=True)
    print(f"final: {out} ({os.path.getsize(out) / 1e6:.0f} MB, {total / 60:.2f} min), captions {srt}, {len(subs)} subtitles, {len(chapters)} chapters")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "layout":
        layout()
    elif cmd == "render":
        render(sys.argv[2:] or None)
    elif cmd == "final":
        final()
