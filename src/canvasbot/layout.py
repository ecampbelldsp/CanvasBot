from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageStat
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from canvasbot.models import BackgroundStyle, DesignCategory, DesignLayout, TextElement

PAGE_SIZES: dict[DesignCategory, tuple[int, int]] = {
    DesignCategory.BUSINESS_CARD: (252, 144),  # 3.5 x 2 inches
    DesignCategory.FLYER: (612, 792),  # US Letter
    DesignCategory.POSTER: (1296, 1728),  # 18 x 24 inches
}

FONT_FILES = {
    "Poppins-Bold": "Poppins-Bold.ttf",
    "Poppins-Regular": "Poppins-Regular.ttf",
    "Caveat-Bold": "Caveat-Bold.ttf",
}


def register_fonts(font_dir: Path) -> set[str]:
    """Register bundled development fonts, falling back safely when unavailable."""
    registered: set[str] = set()
    for name, filename in FONT_FILES.items():
        path = font_dir / filename
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            registered.add(name)
    return registered


def available_font(preferred: str) -> str:
    try:
        pdfmetrics.getFont(preferred)
    except KeyError:
        return "Helvetica-Bold" if "Bold" in preferred else "Helvetica"
    return preferred


def text_width(text: str, font: str, size: int) -> float:
    return float(pdfmetrics.stringWidth(text, available_font(font), size))


def wrap_text(text: str, font: str, size: int, max_width: float) -> list[str]:
    """Wrap by measured glyph width and split individual oversized tokens."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

        while text_width(current, font, size) > max_width and len(current) > 1:
            split_at = max(1, int(len(current) * max_width / text_width(current, font, size)))
            while split_at > 1 and text_width(current[:split_at], font, size) > max_width:
                split_at -= 1
            lines.append(current[:split_at])
            current = current[split_at:]
    if current:
        lines.append(current)
    return lines


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    channels = [value / 255 for value in rgb]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: float, second: float) -> float:
    light, dark = max(first, second), min(first, second)
    return (light + 0.05) / (dark + 0.05)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.removeprefix("#")
    return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def accessible_text_color(requested: str | None, background_rgb: tuple[float, float, float]) -> str:
    background_luminance = relative_luminance(background_rgb)
    if requested:
        requested_luminance = relative_luminance(hex_to_rgb(requested))
        if contrast_ratio(background_luminance, requested_luminance) >= 4.5:
            return requested.upper()
    black_ratio = contrast_ratio(background_luminance, 0)
    white_ratio = contrast_ratio(background_luminance, 1)
    return "#000000" if black_ratio >= white_ratio else "#FFFFFF"


def bounding_box(element: TextElement) -> tuple[float, float, float, float]:
    lines = element.lines or [element.text]
    width = max(text_width(line, element.font, element.size) for line in lines)
    height = len(lines) * element.size * 1.2
    left = element.x_pos
    if element.alignment == "center":
        left -= width / 2
    elif element.alignment == "right":
        left -= width
    return left, element.y_pos - height + element.size, left + width, element.y_pos + element.size


def _place_zone(elements: Iterable[TextElement], start_y: float) -> None:
    current_y = start_y
    for element in elements:
        element.y_pos = current_y
        current_y -= len(element.lines or [element.text]) * element.size * 1.2


def validate_layout(
    layout: DesignLayout,
    background_style: BackgroundStyle,
    background_hex: str,
    requested_text_color: str | None,
) -> DesignLayout:
    """Apply deterministic typography, positioning, and contrast constraints."""
    validated = layout.model_copy(deep=True)
    max_width: float = validated.width - 2 * validated.safe_zone_margin
    if background_style == BackgroundStyle.SPLIT_HORIZONTAL:
        max_width = validated.width * 0.4 - 2 * validated.safe_zone_margin

    for element in validated.elements:
        element.font = available_font(element.font)
        while text_width(element.text, element.font, element.size) > max_width and element.size > 8:
            element.size -= 1
        element.lines = wrap_text(element.text, element.font, element.size, max_width)
        if element.alignment == "left":
            element.x_pos = validated.safe_zone_margin
        elif element.alignment == "right":
            element.x_pos = validated.width - validated.safe_zone_margin
        else:
            element.x_pos = validated.width / 2

    by_zone = {
        zone: [element for element in validated.elements if element.vertical_zone == zone]
        for zone in ("top", "middle", "bottom")
    }
    _place_zone(by_zone["top"], validated.height - validated.safe_zone_margin - 30)
    _place_zone(by_zone["middle"], validated.height / 2 + 40)
    bottom_height = sum(len(element.lines) * element.size * 1.2 for element in by_zone["bottom"])
    _place_zone(by_zone["bottom"], validated.safe_zone_margin + bottom_height)

    image: Image.Image | None = None
    if (
        background_style == BackgroundStyle.FULL_IMAGE
        and validated.background_image
        and validated.background_image.is_file()
    ):
        image = Image.open(validated.background_image).convert("RGB")

    solid_rgb = hex_to_rgb(background_hex)
    for element in validated.elements:
        background_rgb: tuple[float, float, float] = solid_rgb
        noisy = False
        if image:
            left, bottom, right, top = bounding_box(element)
            scale_x, scale_y = image.width / validated.width, image.height / validated.height
            crop = image.crop(
                (
                    max(0, int(left * scale_x)),
                    max(0, int((validated.height - top) * scale_y)),
                    min(image.width, max(1, int(right * scale_x))),
                    min(image.height, max(1, int((validated.height - bottom) * scale_y))),
                )
            )
            if crop.width and crop.height:
                stats = ImageStat.Stat(crop)
                background_rgb = tuple(stats.mean[:3])  # type: ignore[assignment]
                noisy = sum(stats.stddev[:3]) / 3 > 35
        element.color = accessible_text_color(requested_text_color, background_rgb)
        element.needs_scrim = noisy

    if image:
        image.close()
    return validated
