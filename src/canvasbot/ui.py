import time

import httpx
import streamlit as st

from canvasbot.config import get_settings

TERMINAL_STATES = {"succeeded", "failed", "rejected"}
STAGE_LABELS = {
    "queued": "Waiting for the GPU worker",
    "starting": "Starting the workflow",
    "classification": "Classifying the request",
    "copywriting": "Developing the copy and art direction",
    "image_generation": "Generating the visual asset",
    "layout": "Planning the composition",
    "validation": "Checking typography and contrast",
    "rendering": "Rendering vector text and preview",
    "complete": "Design complete",
}


def api_get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def run() -> None:
    settings = get_settings()
    base_url = settings.api_url.rstrip("/")
    st.set_page_config(
        page_title="CanvasBot: Autonomous Print & Portrait Designer",
        page_icon="🎨",
        layout="centered",
    )
    st.title("CanvasBot")
    st.subheader("Autonomous Print & Portrait Designer")
    st.caption("From a natural-language brief to a print-oriented PDF with vector typography.")

    with st.sidebar:
        st.subheader("Pipeline")
        st.markdown(
            "Qwen plans the content and composition. Stable Diffusion creates only the visual "
            "asset. Deterministic Python code validates layout, contrast, bleed, and PDF output."
        )
        try:
            with httpx.Client(timeout=5) as client:
                api_get(client, f"{base_url}/health/ready")
            st.success("API and Qwen model ready")
        except (httpx.HTTPError, ValueError):
            st.warning("API or Qwen model is not ready")

    prompt = st.text_area(
        "Design brief",
        height=160,
        placeholder=(
            "Design a modern flyer for a coffee shop opening on Saturday. Include '20% off' "
            "and use warm orange and cream tones."
        ),
    )
    use_seed = st.checkbox("Use a reproducible image seed")
    seed = st.number_input("Seed", min_value=0, max_value=2**32 - 1, value=42) if use_seed else None

    if st.button("Generate design", type="primary", disabled=len(prompt.strip()) < 10):
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{base_url}/v1/designs", json={"prompt": prompt, "seed": seed}
                )
                response.raise_for_status()
                job = response.json()
                job_url = f"{base_url}/v1/designs/{job['id']}"
                status_box = st.status("Design queued", expanded=True)
                deadline = time.monotonic() + 900
                while job["state"] not in TERMINAL_STATES and time.monotonic() < deadline:
                    time.sleep(1.5)
                    job = api_get(client, job_url).json()
                    label = STAGE_LABELS.get(job["stage"], job["stage"].replace("_", " ").title())
                    status_box.update(label=label, state="running")
                if job["state"] == "succeeded":
                    status_box.update(label="Design complete", state="complete", expanded=False)
                    preview = api_get(client, f"{base_url}{job['preview_url']}").content
                    pdf = api_get(client, f"{base_url}{job['pdf_url']}").content
                    st.image(preview, caption=f"Generated {job['category'].replace('_', ' ')}")
                    st.download_button(
                        "Download PDF",
                        pdf,
                        file_name=f"canvasbot-{job['category']}.pdf",
                        mime="application/pdf",
                        type="primary",
                    )
                elif job["state"] in {"failed", "rejected"}:
                    status_box.update(label="Design was not generated", state="error")
                    st.error(job.get("error") or "The generation failed.")
                else:
                    status_box.update(label="Generation timed out", state="error")
                    st.error(
                        "The browser stopped waiting after 15 minutes. "
                        "The API job may still finish."
                    )
        except httpx.HTTPError as exc:
            st.error(f"Could not reach the CanvasBot API: {exc}")
