#!/usr/bin/env python3
"""Generate a print-ready APRIS destination marker on A4 paper."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing, Group, Rect
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


MARKER_DARK_SIZE_MM = 160
QUIET_ZONE_MODULES = 3


def qr_drawing(payload: str) -> tuple[Drawing, float, int]:
    widget = QrCodeWidget(payload, barBorder=QUIET_ZONE_MODULES)
    _, _, width, height = widget.getBounds()
    module_count = widget.qr.getModuleCount()
    total_modules = module_count + 2 * QUIET_ZONE_MODULES
    total_size = MARKER_DARK_SIZE_MM * mm * total_modules / module_count
    drawing = Drawing(total_size, total_size)
    drawing.add(Rect(0, 0, total_size, total_size, fillColor=white, strokeColor=None))
    scaled_qr = Group()
    scaled_qr.add(widget)
    scaled_qr.scale(total_size / width, total_size / height)
    drawing.add(scaled_qr)
    return drawing, total_size, module_count


def build_pdf(output: Path, marker_id: int, label: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = f"APRIS:MARKER:{marker_id}"
    page_width, page_height = A4
    drawing, total_size, module_count = qr_drawing(payload)
    x = (page_width - total_size) / 2
    y = 45 * mm

    pdf = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
    pdf.setTitle(f"APRIS Marker {marker_id} - {label}")
    pdf.setAuthor("APRIS Rover Platform")

    pdf.setFillColor(HexColor("#15251f"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(page_width / 2, page_height - 18 * mm, f"APRIS DESTINATION: {label.upper()}")
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 25 * mm,
        f"Marker {marker_id}  |  {payload}",
    )
    pdf.setFillColor(HexColor("#50665d"))
    pdf.setFont("Helvetica", 8.5)
    pdf.drawCentredString(
        page_width / 2,
        page_height - 31 * mm,
        "Print at 100% / Actual size. Do not use Fit to page.",
    )

    renderPDF.draw(drawing, pdf, x, y)

    black_left = x + QUIET_ZONE_MODULES * (MARKER_DARK_SIZE_MM * mm / module_count)
    black_right = black_left + MARKER_DARK_SIZE_MM * mm
    dimension_y = 37 * mm
    pdf.setStrokeColor(HexColor("#50665d"))
    pdf.setLineWidth(0.6)
    pdf.line(black_left, dimension_y, black_right, dimension_y)
    pdf.line(black_left, dimension_y - 2 * mm, black_left, dimension_y + 2 * mm)
    pdf.line(black_right, dimension_y - 2 * mm, black_right, dimension_y + 2 * mm)
    pdf.setFillColor(HexColor("#15251f"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(page_width / 2, 31 * mm, "Black QR area: 160 mm")
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(HexColor("#50665d"))
    pdf.drawCentredString(
        page_width / 2,
        24 * mm,
        "Mount the full page flat and vertical. Keep the white border unobstructed.",
    )
    pdf.drawCentredString(
        page_width / 2,
        19 * mm,
        "This marker is a navigation target, not an obstacle-safety sensor.",
    )
    pdf.showPage()
    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_pdf(args.output, args.id, args.label)


if __name__ == "__main__":
    main()
