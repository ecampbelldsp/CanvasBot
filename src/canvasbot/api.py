import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from canvasbot import __version__
from canvasbot.config import Settings, get_settings
from canvasbot.image_generation import DiffusersImageGenerator
from canvasbot.jobs import JobManager
from canvasbot.layout import register_fonts
from canvasbot.llm import LLMService
from canvasbot.models import DesignRequest, JobRecord
from canvasbot.workflow import DesignPipeline

LOGGER = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    pipeline: DesignPipeline | None = None,
) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        registered = register_fonts(config.font_dir)
        LOGGER.info("Registered optional fonts: %s", sorted(registered))
        active_pipeline = pipeline or DesignPipeline(
            LLMService(config), DiffusersImageGenerator(config)
        )
        application.state.settings = config
        application.state.jobs = JobManager(
            config.job_root,
            active_pipeline,
            config.job_ttl_seconds,
            config.preview_dpi,
            config.max_concurrent_generations,
        )
        application.state.jobs.recover_interrupted()
        application.state.jobs.cleanup_expired()
        yield
        application.state.jobs.close()

    application = FastAPI(
        title="CanvasBot: Autonomous Print & Portrait Designer API",
        description="Autonomous generation of print-oriented flyers, posters, and business cards.",
        version=__version__,
        lifespan=lifespan,
    )

    @application.get("/health/live", tags=["operations"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @application.get("/health/ready", tags=["operations"])
    async def readiness() -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{config.vllm_base_url.rstrip('/')}/models")
                response.raise_for_status()
                model_ids = {item.get("id") for item in response.json().get("data", [])}
            if config.vllm_model not in model_ids:
                raise RuntimeError(f"configured model {config.vllm_model} is not served")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The configured vLLM model is not ready.",
            ) from exc
        return {"status": "ready", "model": config.vllm_model}

    @application.post(
        "/v1/designs",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["designs"],
    )
    async def create_design(request: DesignRequest) -> JobRecord:
        jobs = cast(JobManager, application.state.jobs)
        return jobs.submit(request)

    @application.get("/v1/designs/{job_id}", response_model=JobRecord, tags=["designs"])
    async def get_design(job_id: str) -> JobRecord:
        jobs = cast(JobManager, application.state.jobs)
        record = jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Design job not found or expired.")
        return record

    @application.get("/v1/designs/{job_id}/pdf", tags=["designs"])
    async def download_pdf(job_id: str) -> FileResponse:
        jobs = cast(JobManager, application.state.jobs)
        artifact = jobs.artifact(job_id, "design.pdf")
        if artifact is None:
            raise HTTPException(status_code=404, detail="PDF is not available.")
        return FileResponse(
            artifact, media_type="application/pdf", filename=f"canvasbot-{job_id}.pdf"
        )

    @application.get("/v1/designs/{job_id}/preview", tags=["designs"])
    async def download_preview(job_id: str) -> FileResponse:
        jobs = cast(JobManager, application.state.jobs)
        artifact = jobs.artifact(job_id, "preview.png")
        if artifact is None:
            raise HTTPException(status_code=404, detail="Preview is not available.")
        return FileResponse(artifact, media_type="image/png", filename=f"canvasbot-{job_id}.png")

    return application


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("canvasbot.api:app", host=settings.api_host, port=settings.api_port, workers=1)
