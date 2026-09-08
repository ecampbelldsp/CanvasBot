from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from CANVASBOT_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="CANVASBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_model: str = "Qwen/Qwen2.5-3B-Instruct-AWQ"
    vllm_api_key: str = "none"
    image_model: str = "Lykon/dreamshaper-8"
    lora_model: str | None = "latent-consistency/lcm-lora-sdv1-5"
    font_dir: Path = Path("notebooks/fonts")
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8001, ge=1, le=65535)
    api_url: str = "http://127.0.0.1:8001"
    job_root: Path = Path("data/jobs")
    job_ttl_seconds: int = Field(default=3600, ge=60)
    max_concurrent_generations: int = Field(default=1, ge=1, le=4)
    preview_dpi: int = Field(default=150, ge=72, le=300)
    inference_steps: int = Field(default=5, ge=1, le=100)
    guidance_scale: float = Field(default=1.5, ge=0, le=20)
    request_timeout_seconds: float = Field(default=120.0, gt=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
