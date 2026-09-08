import gc
import logging
import threading
from pathlib import Path
from typing import Protocol

from canvasbot.config import Settings
from canvasbot.errors import PipelineError
from canvasbot.models import BackgroundStyle, CopywritingResult, DesignCategory

LOGGER = logging.getLogger(__name__)


class ImageGenerator(Protocol):
    def generate(
        self,
        copy: CopywritingResult,
        category: DesignCategory,
        output_path: Path,
        seed: int | None,
    ) -> Path | None: ...


class DiffusersImageGenerator:
    """Lazy Stable Diffusion adapter. One process-wide lock protects GPU memory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pipeline: object | None = None
        self._load_lock = threading.Lock()

    def _load(self) -> object:
        if self._pipeline is not None:
            return self._pipeline
        with self._load_lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                from diffusers import LCMScheduler, StableDiffusionPipeline

                pipeline = StableDiffusionPipeline.from_pretrained(
                    self._settings.image_model,
                    use_safetensors=True,
                )
                if self._settings.lora_model:
                    pipeline.load_lora_weights(self._settings.lora_model)
                    pipeline.scheduler = LCMScheduler.from_config(pipeline.scheduler.config)
                pipeline.enable_sequential_cpu_offload()
                pipeline.enable_attention_slicing(1)
                pipeline.vae.enable_slicing()
                pipeline.set_progress_bar_config(disable=True)
            except Exception as exc:
                raise PipelineError(
                    "image_generation",
                    "Stable Diffusion could not be loaded. Install the generation dependencies "
                    "and verify the model is available.",
                ) from exc
            self._pipeline = pipeline
            return pipeline

    @staticmethod
    def _prompt(copy: CopywritingResult) -> tuple[str, int, int]:
        subject = copy.visual_subject
        if not subject and copy.visual_regions:
            subject = copy.visual_regions[0].prompt
        subject = subject or copy.global_background_prompt
        style = copy.visual_style.replace("_", " ")
        if copy.background_style == BackgroundStyle.SOLID_WITH_PHOTO:
            return (
                f"high quality {style} of {subject}, isolated on a plain background, centered, "
                "studio lighting, crisp edges",
                512,
                512,
            )
        if copy.background_style == BackgroundStyle.SOLID_WITH_DECAL:
            return (
                f"flat 2D vector illustration of {subject}, vibrant minimal design asset, "
                "isolated on a plain background, clean crisp edges, solid colors",
                512,
                512,
            )
        return f"high quality {style} of {subject}, vibrant, detailed, immersive", 512, 768

    def generate(
        self,
        copy: CopywritingResult,
        category: DesignCategory,
        output_path: Path,
        seed: int | None,
    ) -> Path | None:
        if copy.background_style == BackgroundStyle.SOLID_TEXT_ONLY:
            return None
        pipeline = self._load()
        prompt, width, height = self._prompt(copy)
        if (
            category == DesignCategory.BUSINESS_CARD
            and copy.background_style == BackgroundStyle.FULL_IMAGE
        ):
            width, height = 768, 512
        generator = None
        try:
            import torch

            if seed is not None:
                generator = torch.Generator(device="cpu").manual_seed(seed)
            result = pipeline(  # type: ignore[operator]
                prompt=prompt,
                negative_prompt=(
                    "text, letters, words, logo, watermark, UI, blurry, low resolution, "
                    "distorted proportions, cut off, out of frame"
                ),
                num_inference_steps=self._settings.inference_steps,
                guidance_scale=self._settings.guidance_scale,
                width=width,
                height=height,
                generator=generator,
            )
            if not result.images:
                raise RuntimeError("image model returned no images")
            if result.nsfw_content_detected and any(result.nsfw_content_detected):
                raise PipelineError(
                    "image_generation",
                    "The image safety checker rejected the generated asset. "
                    "Try a different brief or seed.",
                )
            image = result.images[0]
            if copy.background_style in {
                BackgroundStyle.SOLID_WITH_PHOTO,
                BackgroundStyle.SOLID_WITH_DECAL,
                BackgroundStyle.SPLIT_HORIZONTAL,
            }:
                from rembg import new_session, remove

                session = new_session("u2net", providers=["CPUExecutionProvider"])
                image = remove(image, session=session)
            image.save(output_path)
        except PipelineError:
            raise
        except Exception as exc:
            LOGGER.exception("Image generation failed")
            raise PipelineError(
                "image_generation", "The image model failed to create an asset."
            ) from exc
        finally:
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            gc.collect()
        return output_path
