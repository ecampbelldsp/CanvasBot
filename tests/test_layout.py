from pathlib import Path

from PIL import Image

from canvasbot.layout import accessible_text_color, validate_layout, wrap_text
from canvasbot.models import BackgroundStyle, DesignLayout, TextElement


def test_wrap_text_respects_measured_width() -> None:
    lines = wrap_text("A deliberately long headline for a narrow card", "Helvetica", 14, 80)
    assert len(lines) > 1


def test_accessible_color_preserves_compliant_request() -> None:
    assert accessible_text_color("#FFFFFF", (0, 0, 0)) == "#FFFFFF"


def test_accessible_color_corrects_low_contrast() -> None:
    assert accessible_text_color("#FFFFFF", (255, 255, 255)) == "#000000"


def test_validator_positions_and_wraps(layout: DesignLayout) -> None:
    validated = validate_layout(layout, BackgroundStyle.SOLID_TEXT_ONLY, "#FFFFFF", None)
    element = validated.elements[0]
    assert element.lines == ["Grand Opening"]
    assert element.x_pos == 306
    assert element.y_pos < validated.height
    assert element.color == "#000000"


def test_validator_analyses_image_background(tmp_path: Path) -> None:
    image_path = tmp_path / "noise.png"
    image = Image.effect_noise((256, 256), 100).convert("RGB")
    image.save(image_path)
    layout = DesignLayout(
        spatial_reasoning="test",
        width=256,
        height=256,
        background_image=image_path,
        elements=[TextElement(text="Readable", size=24, vertical_zone="middle")],
    )
    validated = validate_layout(layout, BackgroundStyle.FULL_IMAGE, "#FFFFFF", None)
    assert validated.elements[0].needs_scrim is True
