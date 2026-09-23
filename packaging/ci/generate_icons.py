#!/usr/bin/env python3
"""generate_icons.py — Convert SVG icon to platform-specific formats.

Outputs:
    packaging/linux/vinastudio.png   (512x512)
    packaging/windows/icon.ico       (multi-resolution: 16,32,48,64,128,256)

Usage:
    python packaging/ci/generate_icons.py

Requires:
    pip install cairosvg Pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SVG_PATH = REPO_ROOT / "vinastudio" / "desktop" / "assets" / "icon.svg"

LINUX_OUT = REPO_ROOT / "packaging" / "linux" / "vinastudio.png"
WINDOWS_OUT = REPO_ROOT / "packaging" / "windows" / "icon.ico"

ICO_SIZES = [16, 32, 48, 64, 128, 256]


def generate_png(svg_path: Path, out_path: Path, size: int = 512) -> None:
    """Render SVG to PNG at the given size."""
    try:
        import cairosvg
    except ImportError:
        print("ERROR: cairosvg is required. Install with: pip install cairosvg", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(url=str(svg_path), write_to=str(out_path), output_width=size, output_height=size)
    print(f"  PNG   {out_path.relative_to(REPO_ROOT)} ({size}x{size})")


def generate_ico(svg_path: Path, out_path: Path, sizes: list[int] | None = None) -> None:
    """Render SVG to multi-resolution ICO."""
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        print(f"ERROR: cairosvg and Pillow are required. Install with: pip install cairosvg Pillow", file=sys.stderr)
        sys.exit(1)

    if sizes is None:
        sizes = ICO_SIZES

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Render each size to a temporary PNG in memory, then combine into ICO
    images: list[Image.Image] = []
    for size in sizes:
        png_data = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
        from io import BytesIO

        img = Image.open(BytesIO(png_data))
        images.append(img)

    # Save as ICO with all sizes
    # The first image is used as the base; additional sizes are appended
    if images:
        images[0].save(
            str(out_path),
            format="ICO",
            sizes=[(s, s) for s in sizes],
            append_images=images[1:],
        )
        print(f"  ICO   {out_path.relative_to(REPO_ROOT)} (sizes: {', '.join(str(s) for s in sizes)})")


def main() -> None:
    if not SVG_PATH.exists():
        print(f"ERROR: SVG source not found: {SVG_PATH}", file=sys.stderr)
        sys.exit(1)

    print("Generating icons from SVG...")

    # Generate Linux PNG
    generate_png(SVG_PATH, LINUX_OUT, size=512)

    # Generate Windows ICO
    generate_ico(SVG_PATH, WINDOWS_OUT, sizes=ICO_SIZES)

    print("\nDone.")


if __name__ == "__main__":
    main()
