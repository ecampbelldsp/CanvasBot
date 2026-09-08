import time
from typing import Any

import httpx
import streamlit as st

from canvasbot.config import get_settings

TERMINAL_STATES = {"succeeded", "failed", "rejected"}
STAGE_LABELS = {
    "queued": "⏳ Waiting for the GPU worker",
    "starting": "🚀 Starting the creative workflow",
    "classification": "🛡️ Analyzing the design request",
    "copywriting": "✍️ Developing copy and art direction",
    "image_generation": "🖼️ Generating the visual asset",
    "layout": "📐 Planning the composition",
    "validation": "✅ Checking typography and contrast",
    "rendering": "🖨️ Rendering the print-ready artwork",
    "complete": "✨ Design complete",
}

THEME_CSS = """
<style>
    :root {
        --canvas: #0d1117;
        --surface: #161b22;
        --surface-raised: #1f2630;
        --line: #303844;
        --text: #f4f6f8;
        --muted: #a7b0bd;
        --coral: #ff5c68;
        --amber: #ff9f1c;
        --teal: #2ec4b6;
    }
    .stApp {
        background:
            radial-gradient(circle at 82% 4%, rgba(46, 196, 182, 0.09), transparent 28rem),
            radial-gradient(circle at 10% 18%, rgba(255, 92, 104, 0.07), transparent 25rem),
            var(--canvas);
        color: var(--text);
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stToolbar"], .stDeployButton { display: none; }
    [data-testid="stAppViewContainer"] > .main .block-container {
        max-width: 900px;
        padding-top: 3.2rem;
        padding-bottom: 7rem;
    }
    .canvasbot-hero { margin-bottom: 1.4rem; }
    .canvasbot-kicker {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--teal);
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.7rem;
    }
    .canvasbot-kicker::before {
        content: "";
        width: 0.48rem;
        height: 0.48rem;
        border-radius: 50%;
        background: var(--teal);
        box-shadow: 0 0 0 0.28rem rgba(46, 196, 182, 0.13);
    }
    .canvasbot-title {
        margin: 0;
        color: var(--text);
        font-size: clamp(2.25rem, 7vw, 3.55rem);
        font-weight: 800;
        letter-spacing: -0.045em;
        line-height: 1.05;
    }
    .canvasbot-title span { color: var(--coral); }
    .canvasbot-subtitle {
        color: var(--muted);
        font-size: 1.02rem;
        line-height: 1.65;
        max-width: 690px;
        margin: 0.8rem 0 1rem;
    }
    .canvasbot-accent {
        display: flex;
        width: 8rem;
        height: 0.28rem;
        border-radius: 999px;
        overflow: hidden;
    }
    .canvasbot-accent span { flex: 1; }
    .canvasbot-accent span:nth-child(1) { background: var(--coral); }
    .canvasbot-accent span:nth-child(2) { background: var(--amber); }
    .canvasbot-accent span:nth-child(3) { background: var(--teal); }
    .service-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.8rem 1rem;
        margin: 1.45rem 0 1.1rem;
        border: 1px solid var(--line);
        border-radius: 0.75rem;
        background: rgba(22, 27, 34, 0.9);
    }
    .service-label { color: var(--muted); font-size: 0.88rem; }
    .service-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.42rem;
        border-radius: 999px;
        padding: 0.28rem 0.68rem;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .service-pill.ready { color: #8aeadf; background: rgba(46, 196, 182, 0.13); }
    .service-pill.waiting { color: #ffd08b; background: rgba(255, 159, 28, 0.13); }
    [data-testid="stChatMessage"] {
        border: 1px solid var(--line);
        border-radius: 0.85rem;
        background: rgba(22, 27, 34, 0.94);
        padding: 0.55rem 0.75rem;
        margin: 0.75rem 0;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.13);
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        border-left: 3px solid var(--coral);
        background: linear-gradient(110deg, rgba(255, 92, 104, 0.1), rgba(22, 27, 34, 0.96) 42%);
    }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
        border-left: 3px solid var(--amber);
        background: linear-gradient(110deg, rgba(255, 159, 28, 0.08), rgba(22, 27, 34, 0.96) 42%);
    }
    [data-testid="stChatMessageAvatarUser"] { background: var(--coral); }
    [data-testid="stChatMessageAvatarAssistant"] { background: var(--amber); }
    [data-testid="stExpander"] {
        border-color: var(--line);
        border-radius: 0.7rem;
        background: rgba(22, 27, 34, 0.72);
    }
    [data-testid="stStatusWidget"] {
        border-color: rgba(255, 159, 28, 0.42);
        background: rgba(255, 159, 28, 0.06);
    }
    [data-testid="stChatInput"] {
        border: 1px solid var(--line);
        border-radius: 0.85rem;
        background: var(--surface-raised);
        box-shadow: 0 16px 42px rgba(0, 0, 0, 0.35);
    }
    [data-testid="stChatInput"]:focus-within { border-color: var(--coral); }
    [data-testid="stChatInputSubmitButton"] { color: var(--coral); }
    .stDownloadButton > button {
        border: 0;
        color: #11151b;
        font-weight: 800;
        background: linear-gradient(100deg, var(--amber), #ffc15a);
    }
    .stDownloadButton > button:hover {
        color: #11151b;
        border: 0;
        transform: translateY(-1px);
    }
    @media (max-width: 640px) {
        [data-testid="stAppViewContainer"] > .main .block-container {
            padding: 1.7rem 1rem 6.5rem;
        }
        .canvasbot-title { font-size: 2.35rem; }
        .service-row { align-items: flex-start; flex-direction: column; gap: 0.55rem; }
        [data-testid="stChatMessage"] { padding: 0.35rem 0.45rem; }
    }
</style>
"""


def api_get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _api_is_ready(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=5) as client:
            api_get(client, f"{base_url}/health/ready")
    except (httpx.HTTPError, ValueError):
        return False
    return True


def _render_history(messages: list[dict[str, Any]]) -> None:
    for index, message in enumerate(messages):
        with st.chat_message(message["role"], avatar=message["avatar"]):
            st.markdown(message["content"])
            preview = message.get("preview")
            if preview:
                category = str(message["category"]).replace("_", " ")
                st.image(preview, caption=f"Print-ready {category}")
                st.download_button(
                    "Download print-ready PDF",
                    message["pdf"],
                    file_name=f"canvasbot-{message['category']}.pdf",
                    mime="application/pdf",
                    type="primary",
                    key=f"history-download-{index}-{message['job_id']}",
                )


def _remember(message: dict[str, Any]) -> None:
    history = st.session_state.messages
    history.append(message)
    if len(history) > 8:
        del history[:-8]


def run() -> None:
    settings = get_settings()
    base_url = settings.api_url.rstrip("/")
    st.set_page_config(
        page_title="CanvasBot: Autonomous Print & Portrait Designer",
        page_icon="🎨",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    is_ready = _api_is_ready(base_url)
    readiness_class = "ready" if is_ready else "waiting"
    readiness_label = "Ready to create" if is_ready else "Models unavailable"
    st.markdown(
        """
        <section class="canvasbot-hero">
            <div class="canvasbot-kicker">Local agentic design studio</div>
            <h1 class="canvasbot-title">🎨 Canvas<span>Bot</span></h1>
            <p class="canvasbot-subtitle">
                Describe the idea. CanvasBot directs the copy, artwork, composition, validation,
                and print-ready export—while you stay in creative control.
            </p>
            <div class="canvasbot-accent"><span></span><span></span><span></span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="service-row">
            <span class="service-label">Qwen planning · Stable Diffusion artwork · Vector PDF</span>
            <span class="service-pill {readiness_class}">● {readiness_label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    _render_history(st.session_state.messages)

    with st.expander("Generation settings"):
        use_seed = st.checkbox("Use a reproducible image seed")
        seed = (
            int(st.number_input("Seed", min_value=0, max_value=2**32 - 1, value=42))
            if use_seed
            else None
        )

    prompt = st.chat_input(
        "Describe a flyer, poster, or business card—portraits welcome…",
        disabled=not is_ready,
    )
    if not is_ready:
        st.caption("Start the API and Qwen service to enable the design prompt.")
    if prompt is None:
        return
    if len(prompt.strip()) < 10:
        st.warning("Please describe the design in at least 10 characters.")
        return

    normalized_prompt = " ".join(prompt.split())
    user_message = {"role": "user", "avatar": "🧑‍🎨", "content": normalized_prompt}
    _remember(user_message)
    with st.chat_message("user", avatar="🧑‍🎨"):
        st.markdown(normalized_prompt)

    with st.chat_message("assistant", avatar="🤖"):
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{base_url}/v1/designs", json={"prompt": normalized_prompt, "seed": seed}
                )
                response.raise_for_status()
                job = response.json()
                job_url = f"{base_url}/v1/designs/{job['id']}"
                status_box = st.status("🎨 Orchestrating the design agents…", expanded=True)
                deadline = time.monotonic() + 900
                while job["state"] not in TERMINAL_STATES and time.monotonic() < deadline:
                    time.sleep(1.5)
                    job = api_get(client, job_url).json()
                    label = STAGE_LABELS.get(job["stage"], job["stage"].replace("_", " ").title())
                    status_box.update(label=label, state="running")

                if job["state"] == "succeeded":
                    status_box.update(label="✨ Design complete", state="complete", expanded=False)
                    preview = api_get(client, f"{base_url}{job['preview_url']}").content
                    pdf = api_get(client, f"{base_url}{job['pdf_url']}").content
                    category = job["category"].replace("_", " ")
                    content = f"Your {category} is ready. The layout is optimized for print."
                    st.markdown(content)
                    st.image(preview, caption=f"Print-ready {category}")
                    st.download_button(
                        "Download print-ready PDF",
                        pdf,
                        file_name=f"canvasbot-{job['category']}.pdf",
                        mime="application/pdf",
                        type="primary",
                        key=f"result-download-{job['id']}",
                    )
                    _remember(
                        {
                            "role": "assistant",
                            "avatar": "🤖",
                            "content": content,
                            "preview": preview,
                            "pdf": pdf,
                            "category": job["category"],
                            "job_id": job["id"],
                        }
                    )
                elif job["state"] in {"failed", "rejected"}:
                    status_box.update(label="Design was not generated", state="error")
                    content = job.get("error") or "The generation failed."
                    st.error(content)
                    _remember({"role": "assistant", "avatar": "🤖", "content": content})
                else:
                    status_box.update(label="Generation timed out", state="error")
                    content = (
                        "The browser stopped waiting after 15 minutes. "
                        "The API job may still finish."
                    )
                    st.error(content)
                    _remember({"role": "assistant", "avatar": "🤖", "content": content})
        except httpx.HTTPError as exc:
            content = f"Could not reach the CanvasBot API: {exc}"
            st.error(content)
            _remember({"role": "assistant", "avatar": "🤖", "content": content})
