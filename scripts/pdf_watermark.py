"""Overlay a text or image watermark onto every page of a PDF.

Usage:
    python scripts/pdf_watermark.py packet.pdf --text "DRAFT"
    python scripts/pdf_watermark.py packet.pdf --text "CONFIDENTIAL" \\
        --opacity 0.25 --rotation 45 --color "#cc0000"
    python scripts/pdf_watermark.py packet.pdf --image logo.png \\
        --position top-right --opacity 0.4

Position keywords (text + image): center, top-left, top-right,
bottom-left, bottom-right.

Dependencies:
    python -m pip install --user pypdf reportlab
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
from pathlib import Path

POSITIONS = {
    "center", "top-left", "top-right", "bottom-left", "bottom-right",
    "top", "bottom", "left", "right",
}

log = logging.getLogger("printwatcher.watermark")


def _read_path_constant(text: str, name: str) -> Path | None:
    match = re.search(rf'{name}\s*=\s*Path\(r"([^"]+)"\)', text)
    if not match:
        return None
    raw = match.group(1)
    if "YOUR_USERNAME" in raw:
        return None
    return Path(raw)


def discover_inbox() -> Path:
    sibling = Path(__file__).resolve().parent.parent / "print_watcher_tray.py"
    if sibling.exists():
        try:
            text = sibling.read_text(encoding="utf-8", errors="ignore")
            inbox = _read_path_constant(text, "WATCH_DIR")
            if inbox is not None:
                return inbox
        except OSError:
            pass
    onedrive = (
        os.environ.get("OneDrive")
        or os.environ.get("OneDriveCommercial")
        or os.environ.get("OneDriveConsumer")
    )
    base = Path(onedrive) if onedrive else Path.home() / "OneDrive"
    return base / "PrintInbox"


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    cleaned = hex_color.lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if len(cleaned) != 6:
        raise ValueError(f"invalid hex colour: {hex_color!r}")
    r = int(cleaned[0:2], 16) / 255
    g = int(cleaned[2:4], 16) / 255
    b = int(cleaned[4:6], 16) / 255
    return r, g, b


def _resolve_position(name: str, page_w: float, page_h: float,
                      content_w: float, content_h: float, padding: float = 36) -> tuple[float, float]:
    name = name.lower()
    if name == "center":
        return (page_w - content_w) / 2, (page_h - content_h) / 2
    if name == "top-left":
        return padding, page_h - content_h - padding
    if name == "top-right":
        return page_w - content_w - padding, page_h - content_h - padding
    if name == "bottom-left":
        return padding, padding
    if name == "bottom-right":
        return page_w - content_w - padding, padding
    if name == "top":
        return (page_w - content_w) / 2, page_h - content_h - padding
    if name == "bottom":
        return (page_w - content_w) / 2, padding
    if name == "left":
        return padding, (page_h - content_h) / 2
    if name == "right":
        return page_w - content_w - padding, (page_h - content_h) / 2
    raise ValueError(f"unknown position: {name!r}")


def _build_text_overlay(width: float, height: float, text: str,
                        rgb: tuple[float, float, float], opacity: float,
                        rotation: float, font_size: int, position: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica-Bold", font_size)
    c.setFillColorRGB(*rgb, alpha=opacity)
    text_width = c.stringWidth(text, "Helvetica-Bold", font_size)

    if position == "center" and rotation:
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(rotation)
        c.drawCentredString(0, -font_size / 3, text)
        c.restoreState()
    else:
        x, y = _resolve_position(position, width, height,
                                 text_width, font_size + 4)
        if rotation:
            c.saveState()
            c.translate(x + text_width / 2, y + font_size / 2)
            c.rotate(rotation)
            c.drawCentredString(0, -font_size / 3, text)
            c.restoreState()
        else:
            c.drawString(x, y, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def _build_image_overlay(width: float, height: float, image_path: Path,
                         opacity: float, position: str, max_width: float | None = None) -> bytes:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    image = ImageReader(str(image_path))
    iw, ih = image.getSize()
    target_w = max_width or width / 4
    scale = target_w / iw
    target_h = ih * scale
    x, y = _resolve_position(position, width, height, target_w, target_h)
    # Reportlab's drawImage doesn't support alpha; emulate via a
    # transparent fill rectangle layered with the image.
    c.saveState()
    c.setFillAlpha(opacity)
    c.drawImage(image, x, y, width=target_w, height=target_h,
                mask="auto", preserveAspectRatio=True)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def watermark_pdf(input_path: Path, output_path: Path, *,
                  text: str | None, image: Path | None,
                  rgb: tuple[float, float, float], opacity: float,
                  rotation: float, font_size: int, position: str) -> int:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(input_path))
    writer = PdfWriter()
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        if text is not None:
            overlay_bytes = _build_text_overlay(
                width, height, text, rgb, opacity, rotation, font_size, position,
            )
        else:
            overlay_bytes = _build_image_overlay(
                width, height, image, opacity, position,
            )
        overlay = PdfReader(io.BytesIO(overlay_bytes)).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        writer.write(fh)
    return len(reader.pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="source PDF")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="watermark text (e.g. DRAFT, CONFIDENTIAL)")
    source.add_argument("--image", type=Path, help="image file to overlay (PNG / JPG)")
    parser.add_argument("-o", "--out", type=Path, default=None,
                        help="output PDF path")
    parser.add_argument("--to-inbox", action="store_true",
                        help="write the watermarked PDF into PrintWatcher's inbox")
    parser.add_argument("--opacity", type=float, default=0.25,
                        help="0.0 invisible -> 1.0 solid (default 0.25)")
    parser.add_argument("--rotation", type=float, default=0.0,
                        help="degrees, counter-clockwise (default 0)")
    parser.add_argument("--position", default="center",
                        choices=sorted(POSITIONS),
                        help="placement on each page (default center)")
    parser.add_argument("--color", default="#ff0000",
                        help="hex RGB for text watermarks (default #ff0000)")
    parser.add_argument("--font-size", type=int, default=72,
                        help="text size in points (default 72)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.input.exists():
        parser.error(f"input not found: {args.input}")
    if args.image and not args.image.exists():
        parser.error(f"image not found: {args.image}")
    if not (0.0 <= args.opacity <= 1.0):
        parser.error("--opacity must be between 0.0 and 1.0")

    try:
        rgb = _hex_to_rgb(args.color)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    if args.to_inbox:
        output = discover_inbox() / f"{args.input.stem}-watermarked{args.input.suffix}"
    elif args.out:
        output = args.out
    else:
        output = args.input.with_name(f"{args.input.stem}-watermarked{args.input.suffix}")

    try:
        from pypdf import PdfReader  # noqa: F401  -- import early to fail fast
    except ImportError:
        log.error("pypdf + reportlab required: `python -m pip install --user pypdf reportlab`")
        return 2

    pages = watermark_pdf(
        args.input, output,
        text=args.text, image=args.image,
        rgb=rgb, opacity=args.opacity,
        rotation=args.rotation, font_size=args.font_size,
        position=args.position,
    )
    log.info("wrote %s (%d page(s) watermarked)", output, pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
