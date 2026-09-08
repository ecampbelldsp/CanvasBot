import os
import time
from pathlib import Path

from canvasbot.jobs import JobManager
from canvasbot.models import DesignRequest, JobState


class WaitingPipeline:
    def run(self, request, work_dir, progress):  # type: ignore[no-untyped-def]
        raise RuntimeError("test failure")


def test_cleanup_removes_only_expired_terminal_jobs(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "data" / "jobs", WaitingPipeline(), 60, 72)  # type: ignore[arg-type]
    record = manager.submit(DesignRequest(prompt="Create a temporary test flyer"))
    for _ in range(100):
        current = manager.get(record.id)
        if current and current.state == JobState.FAILED:
            break
        time.sleep(0.01)
    directory = manager.root / record.id
    old = time.time() - 120
    os.utime(directory, (old, old))
    assert manager.cleanup_expired() == 1
    assert not directory.exists()
    manager.close()


def test_job_root_rejects_filesystem_root() -> None:
    try:
        JobManager(Path("/"), WaitingPipeline(), 60, 72)  # type: ignore[arg-type]
    except ValueError as exc:
        assert "dedicated subdirectory" in str(exc)
    else:
        raise AssertionError("filesystem root should not be accepted")
