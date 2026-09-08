from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from canvasbot.layout import bounding_box, hex_to_rgb, relative_luminance
from canvasbot.models import BackgroundStyle, DesignLayout


def _scrim_background(layout: DesignLayout, destination: Path) -> Path | None:
    if not layout.background_image or not layout.background_image.is_file():
        return None
    background = Image.open(layout.background_image).convert("RGBA")
    layer = Image.new("RGBA", background.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    scale_x = background.width / layout.width
    scale_y = background.height / layout.height
    drew_scrim = False

    for element in layout.elements:
        if not element.needs_scrim:
            continue
        drew_scrim = True
        left, bottom, right, top = bounding_box(element)
        padding = element.size
        box = (
            (left - padding) * scale_x,
            (layout.height - top - padding) * scale_y,
            (right + padding) * scale_x,
            (layout.height - bottom + padding) * scale_y,
        )
        dark_text = relative_luminance(hex_to_rgb(element.color)) < 0.5
        draw.rectangle(box, fill=(255, 255, 255, 215) if dark_text else (0, 0, 0, 215))

    if not drew_scrim:
        background.close()
        return layout.background_image
    radius = max(8, max(element.size for element in layout.elements) // 2)
    result = Image.alpha_composite(background, layer.filter(ImageFilter.GaussianBlur(radius)))
    result.convert("RGB").save(destination, "PNG")
    background.close()
    return destination


def render_pdf(
    layout: DesignLayout,
    output_path: Path,
    background_style: BackgroundStyle,
    background_hex: str,
) -> None:
    """Render a bleed-sized PDF with raster art and vector typography."""
    physical_width = layout.width + 2 * layout.bleed_margin
    physical_height = layout.height + 2 * layout.bleed_margin
    pdf = canvas.Canvas(
        str(output_path), pagesize=(physical_width, physical_height), pageCompression=1
    )
    pdf.setTitle("CanvasBot generated design")
    pdf.setAuthor("CanvasBot: Autonomous Print & Portrait Designer")

    red, green, blue = (component / 255 for component in hex_to_rgb(background_hex))
    if background_style != BackgroundStyle.FULL_IMAGE:
        pdf.setFillColorRGB(red, green, blue)
        pdf.rect(0, 0, physical_width, physical_height, fill=1, stroke=0)

    image_path = layout.background_image
    if background_style == BackgroundStyle.FULL_IMAGE:
        image_path = _scrim_background(layout, output_path.with_name("background_scrimmed.png"))
        if image_path:
            pdf.drawImage(str(image_path), 0, 0, physical_width, physical_height)
    elif image_path and image_path.is_file():
        if background_style == BackgroundStyle.SPLIT_HORIZONTAL:
            split = physical_width * 0.4
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(split, 0, physical_width - split, physical_height, fill=1, stroke=0)
            image_width = physical_width - split - 2 * layout.bleed_margin
            pdf.drawImage(
                str(image_path),
                split + layout.bleed_margin,
                (physical_height - image_width) / 2,
                image_width,
                image_width,
                mask="auto",
                preserveAspectRatio=True,
            )
        else:
            image_width = layout.width * 0.75
            pdf.drawImage(
                str(image_path),
                (physical_width - image_width) / 2,
                (physical_height - image_width) / 2,
                image_width,
                image_width,
                mask="auto",
                preserveAspectRatio=True,
            )

    for element in layout.elements:
        try:
            pdfmetrics.getFont(element.font)
            font = element.font
        except KeyError:
            font = "Helvetica"
        pdf.setFont(font, element.size)
        text_rgb = [component / 255 for component in hex_to_rgb(element.color)]
        pdf.setFillColorRGB(*text_rgb)
        x = element.x_pos + layout.bleed_margin
        y = element.y_pos + layout.bleed_margin
        for line in element.lines or [element.text]:
            if element.alignment == "center":
                pdf.drawCentredString(x, y, line)
            elif element.alignment == "right":
                pdf.drawRightString(x, y, line)
            else:
                pdf.drawString(x, y, line)
            y -= element.size * 1.2
    pdf.showPage()
    pdf.save()


def render_preview(pdf_path: Path, output_path: Path, dpi: int) -> None:
    with pymupdf.open(pdf_path) as document:  # type: ignore[no-untyped-call]
        page = document.load_page(0)
        matrix = pymupdf.Matrix(dpi / 72, dpi / 72)  # type: ignore[no-untyped-call]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        pixmap.save(output_path)
