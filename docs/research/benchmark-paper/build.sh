#!/bin/bash
# Compile the benchmark paper to main.pdf with Tectonic (fetches LaTeX packages over the network on first run).
# Tables: run build_data.py first. Output: docs/research/benchmark-paper/main.pdf
set -e
cd "$(dirname "$0")"
/data/vaidyx/tools/tectonic/tectonic main.tex
