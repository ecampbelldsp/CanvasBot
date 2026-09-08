from pathlib import Path

import pytest

from canvasbot.errors import UnsupportedDesignError
from canvasbot.models import (
    BackgroundStyle,
    CopywritingResult,
    DesignCategory,
    DesignRequest,
    GatekeeperResult,
    LayoutDecision,
    TextBlock,
)
from canvasbot.workflow import DesignPipeline


class FakeLLM:
    category = DesignCategory.FLYER

    def classify(self, prompt: str) -> GatekeeperResult:
        return GatekeeperResult(category=self.category)

    def write_copy(self, prompt: str) -> CopywritingResult:
        return CopywritingResult(
            background_style=BackgroundStyle.SOLID_TEXT_ONLY,
            background_hex="#FFFFFF",
            global_background_prompt="minimal background",
            visual_style="abstract",
            blocks=[TextBlock(role="headline", content="Launch Day")],
        )

    def choose_layout(self, prompt: str, copy: CopywritingResult) -> LayoutDecision:
        return LayoutDecision(spatial_reasoning="Centered", horizontal_placement="center")


class NoImageGenerator:
    def generate(self, copy, category, output_path, seed):  # type: ignore[no-untyped-def]
        return None


def test_pipeline_runs_all_stages(tmp_path: Path) -> None:
    llm = FakeLLM()
    stages: list[str] = []
    result = DesignPipeline(llm, NoImageGenerator()).run(  # type: ignore[arg-type]
        DesignRequest(prompt="Create a launch event flyer"), tmp_path, stages.append
    )
    assert result["category"] == DesignCategory.FLYER
    assert stages == ["classification", "copywriting", "image_generation", "layout", "validation"]
    assert result["layout"].elements[0].text == "Launch Day"


def test_pipeline_rejects_unsupported_request(tmp_path: Path) -> None:
    llm = FakeLLM()
    llm.category = DesignCategory.UNSUPPORTED
    with pytest.raises(UnsupportedDesignError):
        DesignPipeline(llm, NoImageGenerator()).run(  # type: ignore[arg-type]
            DesignRequest(prompt="Write a complete science fiction book"), tmp_path, lambda _: None
        )
