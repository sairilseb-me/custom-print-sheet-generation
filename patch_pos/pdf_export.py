"""Export a composited sheet image to a print-accurate PDF."""

from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

POINTS_PER_INCH = 72.0


def export_pdf(image: Image.Image, output_path: str | Path, dpi: int = 300) -> None:
    """Write `image` as a single-page PDF, sized so it prints at `dpi`."""
    width_pt = image.width * POINTS_PER_INCH / dpi
    height_pt = image.height * POINTS_PER_INCH / dpi

    canvas = pdf_canvas.Canvas(str(output_path), pagesize=(width_pt, height_pt))
    canvas.drawImage(ImageReader(image), 0, 0, width=width_pt, height=height_pt)
    canvas.save()
