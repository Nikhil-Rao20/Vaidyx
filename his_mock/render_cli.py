"""Turns a JSON job list into PDFs with WeasyPrint (plan item V2-1.2). SYNTHETIC documents only.

Runs in the pdf venv, started by his_mock/documents.py:

    LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib /data/vaidyx/venv/pdf/bin/python -I his_mock/render_cli.py jobs.json

jobs.json is a list of {"html": ..., "out": "<pdf path>"}; a job may add "scan": "<png path>" and "seed" to also write a
scanned-looking image of page 1 (pypdfium2 render, slight rotation, paper tone, noise and blur; the idea of
tumour_board/demo_data/make_corpus.to_scan, copied). Prints nothing but errors; exit status 1 when a job failed.
Standalone on purpose (no his_mock imports): the pdf venv has WeasyPrint 69, which writes the same bytes for the same HTML.
"""
import json
import logging
import random
import sys
from pathlib import Path


def to_scan(pdf_path, png_path, seed):
    import numpy as np
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        im = doc[0].render(scale=1.45).to_pil().convert("L")        # about 105 dpi, a fast office scanner
    finally:
        doc.close()
    im = im.rotate(rnd.uniform(-0.8, 0.8), resample=Image.BICUBIC, expand=False, fillcolor=255)
    a = np.asarray(im).astype(np.float32)
    a = a * 0.93 + 10 + np.random.default_rng(seed).normal(0, 6, a.shape)   # paper tone + sensor noise
    im = Image.fromarray(np.clip(a, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.35))
    Path(png_path).parent.mkdir(parents=True, exist_ok=True)
    im.save(png_path, optimize=True)


def main(argv):
    if len(argv) != 2:
        print("usage: render_cli.py <jobs.json>", file=sys.stderr)
        return 2
    for name in ("weasyprint", "fontTools", "fontTools.subset", "fontTools.ttLib"):
        logging.getLogger(name).setLevel(logging.ERROR)
    import weasyprint

    jobs = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    failed = 0
    for job in jobs:
        try:
            out = Path(job["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            weasyprint.HTML(string=job["html"]).write_pdf(str(out))
            if job.get("scan"):
                to_scan(out, job["scan"], int(job.get("seed") or 0))
        except Exception as exc:  # report every failed job, keep going
            failed += 1
            print(f"render_cli: {job.get('out')}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
