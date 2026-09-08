from pathlib import Path

import pytest

from canvasbot.models import (
    BackgroundStyle,
    CopywritingResult,
    DesignCategory,
    DesignLayout,
    DesignRequest,
    TextBlock,
    TextElement,
)


@pytest.fixture
def copy_result() -> CopywritingResult:
    return CopywritingResult(
        background_style=BackgroundStyle.SOLID_TEXT_ONLY,
        background_hex="#F4C95D",
        global_background_prompt="warm geometric background",
        visual_style="illustration",
        blocks=[TextBlock(role="headline", content="Grand Opening", vertical_zone="top")],
    )


@pytest.fixture
def layout() -> DesignLayout:
    return DesignLayout(
        spatial_reasoning="Centered hierarchy",
        width=612,
        height=792,
        elements=[
            TextElement(
                text="Grand Opening",
                font="Helvetica-Bold",
                size=36,
                alignment="center",
                vertical_zone="top",
            )
        ],
    )


class SuccessfulPipeline:
    def __init__(self, copy: CopywritingResult, layout: DesignLayout) -> None:
        self.copy = copy
        self.layout = layout

    def run(self, request: DesignRequest, work_dir: Path, progress):  # type: ignore[no-untyped-def]
        for stage in ("classification", "copywriting", "layout", "validation"):
            progress(stage)
        return {
            "request": request,
            "work_dir": work_dir,
            "category": DesignCategory.FLYER,
            "copy": self.copy,
            "layout": self.layout,
        }
