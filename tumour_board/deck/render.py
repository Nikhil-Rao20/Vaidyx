"""Render a deck to PDF and PNG pages for a look, with the portable LibreOffice when it is installed (a development tool, never called
by the app):

    /data/vaidyx/venv/app/bin/python -m tumour_board.deck.render case TB-2026-0001 /tmp/out
    /data/vaidyx/venv/app/bin/python -m tumour_board.deck.render meeting S20261025-c5d8 /tmp/out
    /data/vaidyx/venv/app/bin/python -m tumour_board.deck.render file some.pptx /tmp/out

LibreOffice: /data/vaidyx/tools/libreoffice/squashfs-root/AppRun (the 24.2 AppImage, unpacked), with libs/usr/lib64 on LD_LIBRARY_PATH
for libX11-xcb (fetched from the Rocky 8 mirror; the server has no X11 client libraries). PNGs through pypdfium2."""
import os
import subprocess
import sys
from pathlib import Path

LO = Path(os.environ.get("TB_LIBREOFFICE") or "/data/vaidyx/tools/libreoffice/squashfs-root/AppRun")
LO_LIBS = Path("/data/vaidyx/tools/libreoffice/libs/usr/lib64")


def to_pdf(pptx: Path, out_dir: Path) -> Path | None:
    """The PDF of a .pptx, or None when LibreOffice is not installed."""
    if not LO.exists():
        return None
    env = dict(os.environ, HOME=str(out_dir / ".lohome"), LD_LIBRARY_PATH=f"{LO_LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}")
    (out_dir / ".lohome").mkdir(parents=True, exist_ok=True)
    subprocess.run([str(LO), "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)], env=env, check=False, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pdf = out_dir / (pptx.stem + ".pdf")
    return pdf if pdf.exists() else None


def to_pngs(pdf: Path, out_dir: Path, scale: float = 1.0) -> list[Path]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    out = []
    for i in range(len(doc)):
        p = out_dir / f"{pdf.stem}-{i + 1:02d}.png"
        doc[i].render(scale=scale).to_pil().save(p)
        out.append(p)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    kind, ident, out = argv
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        pptx = Path(ident)
    else:
        from . import build_case, build_meeting
        data = build_case(ident) if kind == "case" else build_meeting(ident)
        pptx = out_dir / f"{kind}-{ident}.pptx"
        pptx.write_bytes(data)
    print("pptx:", pptx, pptx.stat().st_size, "bytes")
    pdf = to_pdf(pptx, out_dir)
    if not pdf:
        print("LibreOffice is not installed; the .pptx is ready, no PDF.")
        return 0
    pages = to_pngs(pdf, out_dir)
    print("pdf:", pdf, f"{len(pages)} pages ->", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
