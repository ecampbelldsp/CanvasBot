from pathlib import Path
from types import SimpleNamespace

import pytest

from canvasbot.config import Settings
from canvasbot.errors import PipelineError
from canvasbot.image_generation import DiffusersImageGenerator
from canvasbot.llm import LLMService
from canvasbot.models import BackgroundStyle, CopywritingResult, GatekeeperResult, TextBlock


def make_copy(style: BackgroundStyle) -> CopywritingResult:
    return CopywritingResult(
        background_style=style,
        background_hex="#FFFFFF",
        global_background_prompt="clean studio",
        visual_subject="a ceramic coffee cup",
        visual_style="photography",
        blocks=[TextBlock(role="headline", content="Coffee")],
    )


@pytest.mark.parametrize(
    ("style", "expected_size", "phrase"),
    [
        (BackgroundStyle.FULL_IMAGE, (512, 768), "immersive"),
        (BackgroundStyle.SOLID_WITH_PHOTO, (512, 512), "studio lighting"),
        (BackgroundStyle.SOLID_WITH_DECAL, (512, 512), "flat 2D vector"),
    ],
)
def test_image_prompt_routing(
    style: BackgroundStyle, expected_size: tuple[int, int], phrase: str
) -> None:
    prompt, width, height = DiffusersImageGenerator._prompt(make_copy(style))
    assert (width, height) == expected_size
    assert phrase in prompt


def test_text_only_generation_does_not_load_model(tmp_path: Path) -> None:
    generator = DiffusersImageGenerator(Settings())
    result = generator.generate(
        make_copy(BackgroundStyle.SOLID_TEXT_ONLY),
        "flyer",  # type: ignore[arg-type]
        tmp_path / "unused.png",
        None,
    )
    assert result is None
    assert generator._pipeline is None


def test_safety_rejection_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class RejectedPipeline:
        def __call__(self, **kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(images=[object()], nsfw_content_detected=[True])

    fake_torch = SimpleNamespace(
        Generator=lambda **kwargs: None,
        cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    generator = DiffusersImageGenerator(Settings())
    generator._pipeline = RejectedPipeline()
    with pytest.raises(PipelineError, match="safety checker"):
        generator.generate(
            make_copy(BackgroundStyle.FULL_IMAGE),
            "flyer",  # type: ignore[arg-type]
            tmp_path / "rejected.png",
            None,
        )


class StructuredRunner:
    def __init__(self, result=None, error: Exception | None = None) -> None:  # type: ignore[no-untyped-def]
        self.result = result
        self.error = error

    def invoke(self, messages):  # type: ignore[no-untyped-def]
        if self.error:
            raise self.error
        return self.result


class StructuredClient:
    def __init__(self, runner: StructuredRunner) -> None:
        self.runner = runner

    def with_structured_output(self, schema):  # type: ignore[no-untyped-def]
        return self.runner


def test_structured_llm_adapter_accepts_typed_result() -> None:
    expected = GatekeeperResult(category="flyer")
    result = LLMService._structured(  # type: ignore[arg-type]
        StructuredClient(StructuredRunner(expected)),
        GatekeeperResult,
        "system",
        "user",
        "classification",
    )
    assert result == expected


def test_structured_llm_adapter_wraps_provider_errors() -> None:
    with pytest.raises(PipelineError, match="classification"):
        LLMService._structured(  # type: ignore[arg-type]
            StructuredClient(StructuredRunner(error=RuntimeError("offline"))),
            GatekeeperResult,
            "system",
            "user",
            "classification",
        )


def test_structured_llm_adapter_rejects_wrong_type() -> None:
    with pytest.raises(PipelineError, match="invalid"):
        LLMService._structured(  # type: ignore[arg-type]
            StructuredClient(StructuredRunner({"category": "flyer"})),
            GatekeeperResult,
            "system",
            "user",
            "classification",
        )
