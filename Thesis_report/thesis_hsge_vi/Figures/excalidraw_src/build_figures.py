#!/usr/bin/env python3
"""Build all Excalidraw figures to print-quality PDFs for thesis_hsge_vi.

Usage:
    uv run python build_figures.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
RENDER_SCRIPT = REPO_ROOT / ".claude" / "skills" / "excalidraw-diagram" / "references" / "render_excalidraw.py"
OUTPUT_DIR = SCRIPT_DIR.parent

FIGURES = [
    "fig_roadmap",
    "fig_pipeline",
    "fig_twolevel",
    "fig_frontier",
    "fig_solver",
    "fig_discovery",
    "fig_semantic",
]

def main() -> None:
    # 1. Render all .excalidraw to .png
    sys.path.insert(0, str(RENDER_SCRIPT.parent))
    from render_excalidraw import render

    for name in FIGURES:
        src_path = SCRIPT_DIR / f"{name}.excalidraw"
        png_path = SCRIPT_DIR / f"{name}.png"
        pdf_path = OUTPUT_DIR / f"{name}.pdf"

        print(f"Rendering {src_path.name}...")
        render(src_path, png_path, scale=2, max_width=4000)

        print(f"Converting to {pdf_path.name}...")
        img = Image.open(png_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF", resolution=300.0)
        print(f"✓ Created {pdf_path} ({os.path.getsize(pdf_path):,} bytes)\n")

if __name__ == "__main__":
    main()
