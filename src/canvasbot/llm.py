import logging
import warnings
from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from canvasbot.config import Settings
from canvasbot.errors import PipelineError
from canvasbot.models import CopywritingResult, GatekeeperResult, LayoutDecision

LOGGER = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

GATEKEEPER_PROMPT = """You classify print-design requests. Return exactly one category:
- flyer
- poster
- business_card
- unsupported_style
Do not classify books, magazines, comics, or unrelated requests as a supported category.
"""

COPYWRITER_PROMPT = """You are a brand strategist planning a print design.
Return a concise, structured creative direction.
- Use no more than three text blocks and preserve user-supplied names, dates, prices, and offers.
- Headlines should normally contain 1-5 words; CTAs 1-3 words.
- Never ask the image model to render text, logos, watermarks, or UI.
- Use full_image for immersive flyer/poster art; solid_color_with_photo for corporate designs;
  solid_color_text_only only when no image is needed; split_screen_horizontal for a text-heavy
  professional composition; solid_color_with_decal only for an explicitly minimal isolated object.
- visual_subject must describe only the visual content. Preserve requested colors.
- text_color must be null unless the user explicitly requested a text color.
"""

LAYOUT_PROMPT = """You are a typographic art director. Choose only the horizontal alignment for
the supplied structured copy and briefly explain the composition. Prefer a consistent alignment.
Do not rewrite copy and do not calculate coordinates; deterministic code handles geometry.
"""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self._creative = ChatOpenAI(
            base_url=settings.vllm_base_url,
            api_key=SecretStr(settings.vllm_api_key),
            model=settings.vllm_model,
            timeout=settings.request_timeout_seconds,
            max_retries=1,
            temperature=0.7,
        )
        self._analytical = ChatOpenAI(
            base_url=settings.vllm_base_url,
            api_key=SecretStr(settings.vllm_api_key),
            model=settings.vllm_model,
            timeout=settings.request_timeout_seconds,
            max_retries=1,
            temperature=0.0,
        )

    @staticmethod
    def _structured(
        client: ChatOpenAI,
        schema: type[StructuredModel],
        system_prompt: str,
        user_content: str,
        stage: str,
    ) -> StructuredModel:
        try:
            runner = client.with_structured_output(schema)
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=UserWarning,
                    message=".*Pydantic serializer warnings.*",
                )
                result = runner.invoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ]
                )
        except Exception as exc:
            LOGGER.exception("Structured LLM request failed", extra={"stage": stage})
            raise PipelineError(stage, f"The local language model failed during {stage}.") from exc
        if not isinstance(result, schema):
            raise PipelineError(stage, f"The local language model returned invalid {stage} data.")
        return result

    def classify(self, prompt: str) -> GatekeeperResult:
        return self._structured(
            self._analytical, GatekeeperResult, GATEKEEPER_PROMPT, prompt, "classification"
        )

    def write_copy(self, prompt: str) -> CopywritingResult:
        return self._structured(
            self._creative, CopywritingResult, COPYWRITER_PROMPT, prompt, "copywriting"
        )

    def choose_layout(self, prompt: str, copy: CopywritingResult) -> LayoutDecision:
        content = (
            f"Original request:\n{prompt}\n\nStructured copy:\n{copy.model_dump_json(indent=2)}"
        )
        return self._structured(self._analytical, LayoutDecision, LAYOUT_PROMPT, content, "layout")
