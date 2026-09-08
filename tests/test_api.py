import time
from pathlib import Path

from fastapi.testclient import TestClient

from canvasbot.api import create_app
from canvasbot.config import Settings
from canvasbot.models import JobState


def test_api_job_lifecycle(
    tmp_path: Path,
    copy_result,
    layout,  # type: ignore[no-untyped-def]
) -> None:
    from conftest import SuccessfulPipeline

    settings = Settings(job_root=tmp_path / "data" / "jobs", font_dir=tmp_path)
    app = create_app(settings, SuccessfulPipeline(copy_result, layout))  # type: ignore[arg-type]
    with TestClient(app) as client:
        assert app.title == "CanvasBot: Autonomous Print & Portrait Designer API"
        assert client.get("/health/live").status_code == 200
        invalid = client.post("/v1/designs", json={"prompt": "short"})
        assert invalid.status_code == 422
        response = client.post(
            "/v1/designs", json={"prompt": "Create a modern opening event flyer", "seed": 12}
        )
        assert response.status_code == 202
        job_id = response.json()["id"]
        for _ in range(100):
            status_response = client.get(f"/v1/designs/{job_id}")
            if status_response.json()["state"] == JobState.SUCCEEDED:
                break
            time.sleep(0.01)
        assert status_response.json()["state"] == JobState.SUCCEEDED
        pdf_response = client.get(f"/v1/designs/{job_id}/pdf")
        assert pdf_response.headers["content-type"] == "application/pdf"
        assert f'filename="canvasbot-{job_id}.pdf"' in pdf_response.headers["content-disposition"]
        preview_response = client.get(f"/v1/designs/{job_id}/preview")
        assert preview_response.headers["content-type"] == "image/png"
        assert (
            f'filename="canvasbot-{job_id}.png"' in preview_response.headers["content-disposition"]
        )
        assert client.get(f"/v1/designs/{job_id}/missing").status_code == 404
        assert client.get("/v1/designs/not-a-uuid").status_code == 404
