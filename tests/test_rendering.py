from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from canvasbot.models import BackgroundStyle, DesignLayout
from canvasbot.rendering import render_pdf, render_preview


def test_pdf_has_bleed_vector_text_and_preview(tmp_path: Path, layout: DesignLayout) -> None:
    layout.elements[0].lines = [layout.elements[0].text]
    layout.elements[0].x_pos = layout.width / 2
    layout.elements[0].y_pos = layout.height - 60
    output = tmp_path / "design.pdf"
    preview = tmp_path / "preview.png"

    render_pdf(layout, output, BackgroundStyle.SOLID_TEXT_ONLY, "#FFFFFF")
    render_preview(output, preview, 72)

    with pymupdf.open(output) as document:
        page = document[0]
        assert round(page.rect.width) == layout.width + 2 * layout.bleed_margin
        assert "Grand Opening" in page.get_text()
        assert document.metadata["author"] == ("CanvasBot: Autonomous Print & Portrait Designer")
    assert preview.is_file()
    assert preview.stat().st_size > 0


def test_full_image_render_applies_scrim(tmp_path: Path, layout: DesignLayout) -> None:
    background = tmp_path / "background.png"
    Image.new("RGB", (300, 400), "navy").save(background)
    layout.background_image = background
    layout.elements[0].lines = [layout.elements[0].text]
    layout.elements[0].x_pos = layout.width / 2
    layout.elements[0].y_pos = layout.height / 2
    layout.elements[0].color = "#FFFFFF"
    layout.elements[0].needs_scrim = True
    output = tmp_path / "full.pdf"

    render_pdf(layout, output, BackgroundStyle.FULL_IMAGE, "#FFFFFF")

    assert output.is_file()
    assert (tmp_path / "background_scrimmed.png").is_file()


@pytest.mark.parametrize(
    "style", [BackgroundStyle.SOLID_WITH_PHOTO, BackgroundStyle.SPLIT_HORIZONTAL]
)
def test_insert_image_rendering(
    tmp_path: Path, layout: DesignLayout, style: BackgroundStyle
) -> None:
    background = tmp_path / f"{style}.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 200)).save(background)
    layout.background_image = background
    layout.elements[0].lines = [layout.elements[0].text]
    layout.elements[0].alignment = "right"
    layout.elements[0].x_pos = layout.width - 20
    layout.elements[0].y_pos = 100
    output = tmp_path / f"{style}.pdf"
    render_pdf(layout, output, style, "#EFEFEF")
    assert output.stat().st_size > 0
