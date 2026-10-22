# The benchmark paper

The arXiv-style technical report behind the website's Research page.

| File | What it is |
|---|---|
| `build_data.py` | Reads the raw benchmark results (`~/vaidyx/benchmark/results*/<model>/.../metrics.json`) and the published numbers transcribed in the script, writes every table to `tables/*.tex` and the website's numbers to `web/tb-nik/src/features/landing/research/data.ts`. |
| `main.tex` | The paper. Title, authors, e-mail addresses (placeholders at example.org) and the corresponding author are at the top. |
| `refs.bib` | References (natbib, `unsrtnat`). |
| `arxiv.sty` | The arXiv preprint style by George Kour (github.com/kourgeorge/arxiv-style, MIT licence). |
| `build.sh` | Compiles `main.pdf` with Tectonic (`/data/vaidyx/tools/tectonic/tectonic`). |
| `TODO.md` | Experiments still to run before the paper goes out (on hold until the owner says go). |

Rebuild after a change:

```
/data/vaidyx/venv/app/bin/python docs/research/benchmark-paper/build_data.py
docs/research/benchmark-paper/build.sh
cp docs/research/benchmark-paper/main.pdf web/tb-nik/public/research/vaidyx-benchmark-2026.pdf
cd web/tb-nik && npx vite build
```

Two kinds of numbers are not in the metrics files and are kept in `build_data.py`: the published scores (model cards and papers,
opened 9 October 2026) and the Baichuan-M2 direct scores, re-scored from the saved replies after a stray thinking tag broke the
parser. The Vaidyx evaluations come from `docs/tumour-board/DESIGN.md` and `data/tumour_board/eval/`.
