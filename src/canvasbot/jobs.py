import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from canvasbot.errors import PipelineError, UnsupportedDesignError
from canvasbot.models import DesignRequest, JobRecord, JobState
from canvasbot.rendering import render_pdf, render_preview
from canvasbot.workflow import DesignPipeline

LOGGER = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    """Thread-safe temporary job store with a bounded generation executor."""

    def __init__(
        self,
        root: Path,
        pipeline: DesignPipeline,
        ttl_seconds: int,
        preview_dpi: int,
        max_workers: int = 1,
    ) -> None:
        self.root = root.resolve()
        if self.root == Path(self.root.anchor) or len(self.root.parts) < 3:
            raise ValueError(
                "job_root must be a dedicated subdirectory, not a broad filesystem path"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        self._pipeline = pipeline
        self._ttl_seconds = ttl_seconds
        self._preview_dpi = preview_dpi
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="canvasbot-job"
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _directory(self, job_id: str) -> Path:
        UUID(job_id)
        return self.root / job_id

    def _metadata_path(self, job_id: str) -> Path:
        return self._directory(job_id) / "job.json"

    def _write(self, record: JobRecord) -> None:
        path = self._metadata_path(record.id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def get(self, job_id: str) -> JobRecord | None:
        try:
            path = self._metadata_path(job_id)
        except ValueError:
            return None
        if not path.is_file():
            return None
        with self._lock:
            try:
                return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                LOGGER.exception("Could not read job metadata", extra={"job_id": job_id})
                return None

    def _update(self, job_id: str, **changes: object) -> JobRecord:
        with self._lock:
            record = self.get(job_id)
            if record is None:
                raise FileNotFoundError(job_id)
            record = record.model_copy(update={**changes, "updated_at": utc_now()})
            self._write(record)
            return record

    def submit(self, request: DesignRequest) -> JobRecord:
        self.cleanup_expired()
        job_id = str(uuid4())
        created = utc_now()
        record = JobRecord(
            id=job_id,
            state=JobState.QUEUED,
            stage="queued",
            created_at=created,
            updated_at=created,
        )
        with self._lock:
            self._directory(job_id).mkdir(parents=False)
            self._write(record)
        self._executor.submit(self._execute, job_id, request)
        return record

    def _execute(self, job_id: str, request: DesignRequest) -> None:
        self._update(job_id, state=JobState.RUNNING, stage="starting")

        def progress(stage: str) -> None:
            self._update(job_id, stage=stage)

        try:
            work_dir = self._directory(job_id)
            result = self._pipeline.run(request, work_dir, progress)
            progress("rendering")
            pdf_path = work_dir / "design.pdf"
            preview_path = work_dir / "preview.png"
            render_pdf(
                result["layout"],
                pdf_path,
                result["copy"].background_style,
                result["copy"].background_hex,
            )
            render_preview(pdf_path, preview_path, self._preview_dpi)
            self._update(
                job_id,
                state=JobState.SUCCEEDED,
                stage="complete",
                category=result["category"],
                pdf_url=f"/v1/designs/{job_id}/pdf",
                preview_url=f"/v1/designs/{job_id}/preview",
            )
        except UnsupportedDesignError as exc:
            self._update(job_id, state=JobState.REJECTED, stage="rejected", error=str(exc))
        except PipelineError as exc:
            LOGGER.exception("Pipeline job failed", extra={"job_id": job_id, "stage": exc.stage})
            self._update(job_id, state=JobState.FAILED, stage=exc.stage, error=str(exc))
        except Exception:
            LOGGER.exception("Unexpected job failure", extra={"job_id": job_id})
            self._update(
                job_id,
                state=JobState.FAILED,
                stage="internal_error",
                error="The design could not be generated due to an internal error.",
            )

    def artifact(self, job_id: str, filename: str) -> Path | None:
        if filename not in {"design.pdf", "preview.png"}:
            return None
        record = self.get(job_id)
        if record is None or record.state != JobState.SUCCEEDED:
            return None
        path = self._directory(job_id) / filename
        return path if path.is_file() else None

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC).timestamp()
        removed = 0
        for child in self.root.iterdir():
            try:
                UUID(child.name)
            except ValueError:
                continue
            if not child.is_dir() or now - child.stat().st_mtime <= self._ttl_seconds:
                continue
            record = self.get(child.name)
            if record and record.state in {JobState.QUEUED, JobState.RUNNING}:
                continue
            shutil.rmtree(child)
            removed += 1
        return removed

    def recover_interrupted(self) -> int:
        """Mark non-terminal records left by a previous process as failed."""
        recovered = 0
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            record = self.get(child.name)
            if record and record.state in {JobState.QUEUED, JobState.RUNNING}:
                self._update(
                    record.id,
                    state=JobState.FAILED,
                    stage="interrupted",
                    error="The API restarted before this temporary job completed.",
                )
                recovered += 1
        return recovered
