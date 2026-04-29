"""Shrink large scanned/image-heavy PDFs.

Two passes are applied in sequence:

1. Stream compression (FlateEncode of every content stream). Always safe,
   no quality loss. Modest size reduction unless the PDF is already
   stream-compressed.
2. Image downsampling and re-encoding (optional). For PDFs whose bulk is
   raster scans, this is where the real savings live. Each image is
   resized to fit `--max-image-px` and re-encoded as JPEG at
   `--jpeg-quality`. Skipped for masks / 1-bit content. Requires Pillow.

Usage:
    python scripts/pdf_compress.py big.pdf -o small.pdf
    python scripts/pdf_compress.py big.pdf --max-image-px 1600 --jpeg-quality 70
    python scripts/pdf_compress.py big.pdf --target-mb 5      # iterate until under 5 MiB

Dependencies:
    python -m pip install --user pypdf pillow
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

DEFAULT_MAX_IMAGE_PX = 1800
DEFAULT_JPEG_QUALITY = 75

log = logging.getLogger("printwatcher.pdf_compress")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def _downsample_image(image_bytes: bytes, max_dim: int, quality: int) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        log.error("Pillow not installed; install with `python -m pip install --user pillow`")
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode in ("1", "L") and max(img.width, img.height) <= max_dim:
                return None  # 1-bit / grayscale tiny — leave alone
            scale = max(img.width, img.height) / max_dim
            if scale > 1:
                new_size = (int(img.width / scale), int(img.height / scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception as exc:
        log.debug("downsample skipped: %s", exc)
        return None


def compress(
    source: Path,
    output: Path,
    max_image_px: int,
    jpeg_quality: int,
    skip_images: bool,
) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    writer = PdfWriter()

    for page in reader.pages:
        page.compress_content_streams()
        writer.add_page(page)

    if not skip_images:
        for page in writer.pages:
            try:
                images = list(page.images)
            except Exception:
                continue
            for image_file in images:
                replacement = _downsample_image(image_file.data, max_image_px, jpeg_quality)
                if replacement is None or len(replacement) >= len(image_file.data):
                    continue
                try:
                    image_file.replace(replacement)
                except Exception as exc:
                    log.debug("image replace failed: %s", exc)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as fh:
        writer.write(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="source PDF")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="output path (default: <stem>-compressed.pdf)")
    parser.add_argument("--max-image-px", type=int, default=DEFAULT_MAX_IMAGE_PX,
                        help=f"max image dimension in pixels (default: {DEFAULT_MAX_IMAGE_PX})")
    parser.add_argument("--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY,
                        help=f"JPEG quality 1-95 (default: {DEFAULT_JPEG_QUALITY})")
    parser.add_argument("--skip-images", action="store_true",
                        help="stream compression only, leave images alone")
    parser.add_argument("--target-mb", type=float, default=None,
                        help="iterate, lowering image quality until file is below this size")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.input.exists():
        parser.error(f"input not found: {args.input}")

    output = args.output or args.input.with_name(f"{args.input.stem}-compressed{args.input.suffix}")
    original_size = args.input.stat().st_size

    if args.target_mb is None:
        compress(args.input, output, args.max_image_px, args.jpeg_quality, args.skip_images)
    else:
        target_bytes = int(args.target_mb * 1024 * 1024)
        max_dim = args.max_image_px
        quality = args.jpeg_quality
        attempt = 0
        while True:
            attempt += 1
            log.info("attempt %d: max_dim=%d quality=%d", attempt, max_dim, quality)
            compress(args.input, output, max_dim, quality, args.skip_images)
            size = output.stat().st_size
            if size <= target_bytes:
                break
            if max_dim <= 600 and quality <= 30:
                log.warning("could not reach target size; smallest produced: %s", _format_size(size))
                break
            if quality > 30:
                quality -= 10
            else:
                max_dim = int(max_dim * 0.8)

    new_size = output.stat().st_size
    ratio = (1 - new_size / original_size) * 100 if original_size else 0
    log.info("original  %s", _format_size(original_size))
    log.info("compressed %s  (%.1f%% reduction)", _format_size(new_size), ratio)
    log.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
