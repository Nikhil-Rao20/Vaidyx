"""Privacy QA of the public-image library: face check renders, burned-in text renders, and applying the recorded
decisions (removing face slices).

    python -I pacs_public/qa_check.py --render            # PNGs under <root>/qa/<SeriesInstanceUID>/ and contact sheets
    python -I pacs_public/qa_check.py --apply             # qa_decisions.json -> remove face slices, write qa/qa_results.json
    python -I pacs_public/qa_check.py --render --only <series uid or slot> ...

Rendering (pydicom + numpy + Pillow, never a model): for every series that may reach the head (manifest.face_check_required)
the top 3 and bottom 3 slices (by position along the slice normal; +z is the head in DICOM patient coordinates), a mid
sagittal reformat of axial volumes with z marks every 20 mm (to read the level of the orbits, nose and hard palate), and
for every series one mid slice for the burned-in text check. Window: the header VOI window when present, else a modality
default (CT soft tissue 40 / 400 HU) for CT, percentiles for MR, PET (shown inverted) and projection
images (MG, DX, CR: their header windows are often unfit, which hides marks). Contact sheets (sheet.png) put the
same renders side by side at full tile size; the single PNGs stay next to them.

Decisions are made by looking at the PNGs and are recorded in pacs_public/qa_decisions.json, one entry per series
uid: {"face": "clear" | "crop", "crop_from_z": <mm, axial volumes: remove every slice whose z is at or above it>,
"remove_instances": [<instance numbers>, for non-axial series], "text": "pass" | "fail", "burned_in": "yes" | "no",
"note": "..."}. --apply deletes the listed files from the extracted series folder (the zip stays as the provenance
record and is never imported) and writes qa/qa_results.json, which manifest.py merges into MANIFEST.json and .csv.

Downloaded files are untrusted data: this module parses them with pydicom only. Run it with python -I.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from . import manifest as M
except ImportError:  # run as a script with python -I: put the repo root (our code, not the data) on the path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pacs_public import manifest as M

HERE = Path(__file__).resolve().parent
DECISIONS = HERE / "qa_decisions.json"
TILE = 384
Z_TOLERANCE = 0.05        # mm: a slice stored at -124.29999 counts as -124.3
CT_DEFAULT = (40.0, 400.0)


# ------------------------------------------------------------------------ geometry
def _normal(ds):
    try:
        o = [float(x) for x in ds.ImageOrientationPatient]
    except (AttributeError, TypeError, ValueError):
        return None
    r, c = np.array(o[:3]), np.array(o[3:6])
    n = np.cross(r, c)
    return n / (np.linalg.norm(n) or 1.0)


def is_axial(ds):
    n = _normal(ds)
    return n is not None and abs(n[2]) > 0.9


def position(ds, normal):
    try:
        return float(np.dot(np.array([float(x) for x in ds.ImagePositionPatient]), normal))
    except (AttributeError, TypeError, ValueError):
        return None


def ordered(items):
    """[(path, header)] sorted from the top (head end for axial; the far end of the slice normal otherwise) to the
    bottom. 2D series (no geometry) keep their InstanceNumber order."""
    if not items:
        return items
    first = items[0][1]
    n = _normal(first)
    if n is None or position(first, n) is None:
        return list(items)
    if is_axial(first):
        return sorted(items, key=lambda t: -(M.z_of(t[1]) or 0.0))
    return sorted(items, key=lambda t: -(position(t[1], n) or 0.0))


# ------------------------------------------------------------------------ pixels to 8 bit
def _first(v):
    if v is None:
        return None
    try:
        return float(v[0]) if hasattr(v, "__len__") and not isinstance(v, str) else float(v)
    except (TypeError, ValueError, IndexError):
        return None


def modality_values(ds):
    import pydicom  # noqa: F401  (pixel handlers)
    arr = ds.pixel_array.astype(np.float32)
    if arr.ndim == 3 and ds.get("SamplesPerPixel", 1) == 1:   # multi-frame: take the middle frame
        arr = arr[arr.shape[0] // 2]
    slope = _first(ds.get("RescaleSlope")) or 1.0
    inter = _first(ds.get("RescaleIntercept")) or 0.0
    return arr * slope + inter


def to_uint8(ds, arr, modality=None):
    modality = modality or str(ds.get("Modality", ""))
    wc, ww = _first(ds.get("WindowCenter")), _first(ds.get("WindowWidth"))
    invert = str(ds.get("PhotometricInterpretation", "")) == "MONOCHROME1"
    if modality == "CT":
        wc, ww = (wc, ww) if (wc is not None and ww and ww > 1) else CT_DEFAULT
        lo, hi = wc - ww / 2, wc + ww / 2
    else:   # MR, PT and projection images (MG, DX, CR): percentiles, so faint or burned-in marks stay visible
        lo, hi = np.percentile(arr, 0.5), np.percentile(arr, 99.5)
        if modality == "PT":
            lo, invert = 0.0, not invert
    if hi <= lo:
        hi = lo + 1.0
    out = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    if invert:
        out = 1.0 - out
    return (out * 255.0 + 0.5).astype(np.uint8)


def render_slice(path, out_png, modality=None, max_side=1024):
    import pydicom
    from PIL import Image
    ds = pydicom.dcmread(str(path), force=True)
    img = Image.fromarray(to_uint8(ds, modality_values(ds), modality))
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return img


def sagittal_reformat(items, out_png, modality):
    """Mid sagittal reformat of an axial volume (column x = cols / 2), top of the image = head end, physical aspect,
    with a tick and the z value every 20 mm on the left edge."""
    import pydicom
    from PIL import Image, ImageDraw
    rows, zs = [], []
    for p, _ in items:
        ds = pydicom.dcmread(str(p), force=True)
        v = to_uint8(ds, modality_values(ds), modality)
        rows.append(v[:, v.shape[1] // 2])
        zs.append(M.z_of(ds))
    first = pydicom.dcmread(str(items[0][0]), stop_before_pixels=True, force=True)
    try:
        dy = float(first.PixelSpacing[0])
    except (AttributeError, TypeError, ValueError, IndexError):
        dy = 1.0
    img = np.stack(rows, axis=0)                 # (slices from top, rows of the image) = (z, y)
    z_top, z_bot = zs[0], zs[-1]
    height_mm = abs(z_top - z_bot) or float(len(zs))
    width_mm = img.shape[1] * dy
    scale = 1.0 if max(height_mm, width_mm) < 1024 else 1024.0 / max(height_mm, width_mm)
    pil = Image.fromarray(img).resize((max(1, int(width_mm * scale)), max(1, int(height_mm * scale))), Image.BILINEAR)
    canvas = Image.new("L", (pil.width + 70, pil.height), 0)
    canvas.paste(pil, (70, 0))
    d = ImageDraw.Draw(canvas)
    z = (z_top // 20) * 20
    while z >= z_bot:
        y = int((z_top - z) * scale)
        d.line([(55, y), (70, y)], fill=255)
        d.text((2, max(0, y - 6)), f"{z:+.0f}", fill=255)
        z -= 20
    canvas.save(out_png)
    return canvas


def contact_sheet(tiles, out_png, cols=4):
    """tiles: [(label, PIL image)] -> one sheet with every tile scaled to TILE x TILE (aspect kept) and labelled."""
    from PIL import Image, ImageDraw
    n = len(tiles)
    if not n:
        return None
    cols = min(cols, n)
    nrows = (n + cols - 1) // cols
    sheet = Image.new("L", (cols * TILE, nrows * (TILE + 16)), 40)
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        t = im.copy()
        t.thumbnail((TILE, TILE))
        x, y = (i % cols) * TILE, (i // cols) * (TILE + 16)
        sheet.paste(t, (x + (TILE - t.width) // 2, y + 16 + (TILE - t.height) // 2))
        d.text((x + 4, y + 2), label, fill=255)
    sheet.save(out_png)
    return out_png


# ------------------------------------------------------------------------ per series
def series_qa_dir(root, pick):
    return Path(root) / "qa" / pick["series"]


def render_series(root, pick):
    """Write the PNGs of one series; returns {"face_pngs": [...], "mid_png": ..., "sheet": ..., "reformat": ...}."""
    folder = M.series_dir(root, pick)
    items = ordered(M.sorted_instances(folder))
    out = series_qa_dir(root, pick)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    mod = pick["modality"]
    res = {"face_pngs": [], "mid_png": None, "sheet": None, "reformat": None, "instances": len(items)}
    if not items:
        return res
    tiles = []

    def one(tag, path, ds):
        inst = M.instance_number(ds)
        z = M.z_of(ds)
        name = f"{tag}_i{inst:04d}" + (f"_z{z:+.1f}" if z is not None else "") + ".png"
        im = render_slice(path, out / name, mod)
        tiles.append((f"{tag} inst {inst}" + (f" z {z:+.1f}" if z is not None else ""), im))
        return str(out / name)

    if M.face_check_required(pick):
        if len(items) <= 6:
            picks = [(f"img{k + 1}", t) for k, t in enumerate(items)]
        else:
            picks = [(f"top{k + 1}", items[k]) for k in range(3)] + \
                    [(f"bottom{3 - k}", items[len(items) - 3 + k]) for k in range(3)]
        for tag, (p, ds) in picks:
            res["face_pngs"].append(one(tag, p, ds))
    mid_p, mid_ds = items[len(items) // 2]
    res["mid_png"] = one("mid", mid_p, mid_ds)
    if M.face_check_required(pick) and len(items) > 20 and is_axial(items[0][1]):
        rf = sagittal_reformat(items, out / "reformat_sagittal.png", mod)
        res["reformat"] = str(out / "reformat_sagittal.png")
        tiles.append(("mid sagittal reformat (z marks every 20 mm)", rf))
    res["sheet"] = str(contact_sheet(tiles, out / "sheet.png"))
    return res


def render_all(root=M.DEFAULT_ROOT, only=None):
    root = Path(root)
    index = {}
    for pick in M.load_picks():
        if only and pick["series"] not in only and pick["slot"].replace(" ", "_") not in only:
            continue
        if not (M.series_dir(root, pick) / ".complete").exists():
            continue
        r = render_series(root, pick)
        index[pick["series"]] = {"slot": pick["slot"], "modality": pick["modality"], "desc": pick.get("desc"),
                                 "face_check_required": M.face_check_required(pick), **r}
        print(f"{pick['slot']:14s} {pick['modality']:2s} {str(pick.get('desc'))[:32]:32s} -> {r['sheet']}")
    idx = root / "qa" / "render_index.json"
    old = json.loads(idx.read_text()) if idx.exists() else {}
    old.update(index)
    idx.write_text(json.dumps(old, indent=1))
    return index


# ------------------------------------------------------------------------ decisions
def load_decisions(path=DECISIONS):
    """{series uid: decision}; the file may wrap them as {"reviewed", "how", "series": {...}}."""
    if not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text())
    return data.get("series", data) if isinstance(data, dict) else {}


def files_to_remove(items, decision):
    """[(path, instance number, z)] the decision removes from a series."""
    out = []
    crop_z = decision.get("crop_from_z")
    drop = set(decision.get("remove_instances") or [])
    for p, ds in items:
        inst, z = M.instance_number(ds), M.z_of(ds)
        if (crop_z is not None and z is not None and z >= float(crop_z) - Z_TOLERANCE) or inst in drop:
            out.append((p, inst, z))
    return out


def apply_decisions(root=M.DEFAULT_ROOT, decisions=None, dry_run=False):
    """Remove the face slices the decisions name and write qa/qa_results.json. Idempotent: instance numbers already
    removed are kept from the previous results file."""
    root = Path(root)
    decisions = load_decisions() if decisions is None else decisions
    res_path = root / "qa" / "qa_results.json"
    previous = json.loads(res_path.read_text()) if res_path.exists() else {}
    results = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for pick in M.load_picks():
        uid = pick["series"]
        dec = decisions.get(uid)
        if not dec:
            continue
        folder = M.series_dir(root, pick)
        items = M.sorted_instances(folder)
        removed = list((previous.get(uid) or {}).get("instances_removed") or [])
        removed_z = list((previous.get(uid) or {}).get("removed_z") or [])
        if dec.get("face") == "crop":
            for p, inst, z in files_to_remove(items, dec):
                if not dry_run:
                    p.unlink()
                if inst not in removed:
                    removed.append(inst)
                    removed_z.append(z)
        pairs = sorted(zip(removed, removed_z), key=lambda t: t[0])
        removed = [a for a, _ in pairs]
        removed_z = [b for _, b in pairs]
        if dec.get("face") == "crop" and removed:
            deface = f"cropped:{len(removed)}"
        elif dec.get("face") in ("clear", "crop"):
            deface = "clear"
        else:
            deface = "pending"
        results[uid] = {"slot": pick["slot"], "deface_check": deface, "instances_removed": removed,
                        "removed_z": removed_z, "crop_from_z": dec.get("crop_from_z"),
                        "text_check": dec.get("text", "pending"), "burned_in": dec.get("burned_in", "unknown"),
                        "face_check_method": dec.get("method", "visual"), "note": dec.get("note", ""),
                        "checked_at": (previous.get(uid) or {}).get("checked_at") or now}
    if not dry_run:
        res_path.parent.mkdir(parents=True, exist_ok=True)
        res_path.write_text(json.dumps(results, indent=1))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(M.DEFAULT_ROOT))
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="with --apply: report, delete nothing")
    ap.add_argument("--only", nargs="*", default=None, help="series uids or slots")
    args = ap.parse_args(argv)
    if not (args.render or args.apply):
        ap.error("give --render or --apply")
    if args.render:
        render_all(args.root, set(args.only) if args.only else None)
    if args.apply:
        res = apply_decisions(args.root, dry_run=args.dry_run)
        for uid, r in res.items():
            if r["deface_check"] != "clear" or r["text_check"] != "pass":
                print(f"{r['slot']:14s} {uid}: {r['deface_check']} text={r['text_check']} removed={r['instances_removed']}")
        print(f"{len(res)} series with a decision; "
              f"{sum(1 for r in res.values() if r['deface_check'].startswith('cropped'))} cropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
