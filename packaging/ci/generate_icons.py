#!/usr/bin/env python3
"""generate_icons.py — Convert SVG icon to platform-specific formats.

Outputs:
    packaging/linux/vinastudio.png   (512x512)
    packaging/windows/icon.ico       (multi-resolution: 16,32,48,64,128,256)

Usage:
    python packaging/ci/generate_icons.py

Requires:
    Pillow, plus either cairosvg or PySide6 for rendering. cairosvg needs the cairo
    shared library, which does not exist on Windows (`libcairo-2.dll` is absent),
    so the Qt path — using a dependency the application already has — is what makes
    this step work there.
"""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SVG_PATH = REPO_ROOT / "vinastudio" / "desktop" / "assets" / "icon.svg"

LINUX_OUT = REPO_ROOT / "packaging" / "linux" / "vinastudio.png"
WINDOWS_OUT = REPO_ROOT / "packaging" / "windows" / "icon.ico"

ICO_SIZES = [16, 32, 48, 64, 128, 256]


def _render_with_qt(svg_path: Path, size: int) -> bytes:
    """Rasterise the SVG through QtSvg, which works wherever PySide6 does."""
    # No display on a build machine: Qt must not ask for one to draw into a QImage.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    QGuiApplication.instance() or QGuiApplication([])

    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise SystemExit(f"QtSvg could not read the icon: {svg_path}")

    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    buffer = QByteArray()
    sink = QBuffer(buffer)
    sink.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(sink, "PNG")
    return bytes(buffer)


def _render_svg(svg_path: Path, size: int) -> bytes:
    """Render the SVG to PNG bytes: cairo where it exists, Qt everywhere else."""
    try:
        import cairosvg

        return cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
    except ImportError:
        pass
    except OSError:
        # cairosvg is installed but its shared library is not (Windows).
        pass
    return _render_with_qt(svg_path, size)


def generate_png(svg_path: Path, out_path: Path, size: int = 512) -> None:
    """Render SVG to PNG at the given size."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_render_svg(svg_path, size))
    print(f"  PNG   {out_path.relative_to(REPO_ROOT)} ({size}x{size})")


def generate_ico(svg_path: Path, out_path: Path, sizes: list[int] | None = None) -> None:
    """Render SVG to multi-resolution ICO."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required. Install with: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    if sizes is None:
        sizes = ICO_SIZES

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Render each size to a PNG in memory, then combine into one ICO.
    images: list[Image.Image] = []
    for size in sizes:
        images.append(Image.open(BytesIO(_render_svg(svg_path, size))))

    # Save as ICO with all sizes
    if images:
        # Pillow's ICO writer takes one image as the base and *downsamples* it into
        # every requested size — it never scales one up, and it ignores
        # append_images. Passing the smallest first (as this used to) meant five of
        # the six sizes were silently dropped and the icon shipped 16x16 only.
        # `sizes` is ordered smallest-first, so the last entry is the largest.
        base = images[-1]
        base.save(str(out_path), format="ICO", sizes=[(s, s) for s in sizes])
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
