// The research figures (generated SVG, see docs/research/benchmark-paper/experiments/figures.py), imported as text for inline use.
import ranking from "./figures/ranking.svg?raw";
import reasoning from "./figures/reasoning.svg?raw";
import published from "./figures/published.svg?raw";
import q4 from "./figures/q4.svg?raw";
import images from "./figures/images.svg?raw";
import oncology from "./figures/oncology.svg?raw";
import size from "./figures/size.svg?raw";
import grounding from "./figures/grounding.svg?raw";
import tcga from "./figures/tcga.svg?raw";

export const FIG = { ranking, reasoning, published, q4, images, oncology, size, grounding, tcga } as Record<string, string>;
