# CanvasBot — Production-Oriented Local AI Workflow for Automated Print Design

## The implementation challenge

CanvasBot began with two practical limitations. First, one consumer-grade 6 GB GPU had to support both language-model inference and image generation. Loading full-precision models and processing several requests in parallel would make the application vulnerable to out-of-memory failures.

There was a second constraint. Generative models are useful for creative direction, but they are unreliable at exact typography, page geometry, and print rules. Asking an image model to render the entire design would produce inconsistent spelling, unreadable text, and layouts that could not guarantee safe margins or bleed.

I solved these constraints by separating probabilistic creativity from deterministic production logic.

- Qwen handles request classification, copywriting, art direction, and high-level composition decisions.
- Stable Diffusion generates artwork without attempting to draw text, logos, watermarks, or interface elements.
- Typed Python models validate every AI-generated structure before it can move to the next stage.
- Deterministic layout and rendering code measures glyph widths, wraps and positions text, checks contrast, applies safe zones and bleed, and exports vector typography to PDF.

This division makes the system more predictable while preserving the creative value of generative AI. The result is a tested application that converts a natural-language brief into a flyer, poster, or business card through a versioned API and conversational web interface.

## Running a complete AI pipeline on a 6 GB GPU

The resource constraint shaped the architecture rather than being treated as an afterthought. I combined several complementary optimizations:

- **Quantized, capacity-aware LLM serving:** Qwen 2.5 3B Instruct runs through vLLM in AWQ format. vLLM is limited to 45% GPU utilization, with bounded sequence count and context length, leaving headroom for image generation.
- **Sequential CPU offload and slicing:** Stable Diffusion components move between CPU and GPU as needed, while attention and VAE slicing divide operations into smaller memory workloads. This trades some latency and system RAM for lower VRAM pressure.
- **LCM-LoRA acceleration:** a Latent Consistency Model adapter enables low-step generation; the application defaults to five inference steps.
- **Lazy loading:** Stable Diffusion is loaded only when a request actually needs an image. Text-only designs avoid loading it entirely.
- **Bounded concurrency:** GPU-heavy jobs pass through a controlled background executor. The target deployment intentionally uses a single generation worker rather than allowing simultaneous requests to exhaust GPU memory.
- **Operational isolation:** CUDA cleanup runs after generation, and vLLM is kept in a separate Python environment to reduce inference-server dependency conflicts.

Together, these decisions allow the language and image components to coexist on modest hardware while keeping behavior understandable and operationally controlled. This is a deliberately capacity-aware single-host design, not a claim of unlimited scalability.

## From user brief to downloadable design

1. A gatekeeper classifies the request and rejects unsupported design categories.
2. The language model returns validated copy and visual direction.
3. Stable Diffusion generates the requested artwork, with reproducible seeds when required.
4. A layout stage selects the composition without asking the model to calculate coordinates.
5. Deterministic validation applies typography, positioning, safe-zone, and accessibility rules.
6. The renderer produces a dimensioned PDF with vector text and a PNG preview for the browser.

The asynchronous API returns `202 Accepted` immediately and provides a pollable job identifier. Each job reports its active stage and ends in an explicit `succeeded`, `failed`, or `rejected` state.

## Reliability and low-risk delivery

Model integrations are isolated behind adapters, allowing the core behavior to be verified without downloading models or requiring a GPU. Deterministic fakes exercise the real workflow, API, layout, rendering, and failure contracts.

Verified quality signals from the repository include:

- 25 passing automated tests
- 82.88% branch-aware test coverage
- Strict mypy type checking with no reported issues
- Ruff linting and formatting checks passing
- Continuous integration covering all of these checks
- Health and readiness endpoints that distinguish process availability from model availability
- UUID-isolated job directories and allow-listed artifact downloads
- Atomic job metadata updates, interrupted-job recovery, and expiry cleanup
- Example hardened systemd units for running the API and interface as supervised services

These choices demonstrate how I approach client work: constrain failure modes, validate external output, make operational state visible, and test business-critical logic independently of expensive infrastructure.

## Current scope and production boundary

The generated PDF includes physical dimensions, bleed, safe zones, and vector typography. It is suitable as a print-oriented output, but it is not yet a press-certified PDF/X file. A commercial printing integration would still require the target printer's CMYK workflow, ICC profile, crop marks, and automated preflight rules.

The architecture is intentionally optimized for one local GPU and temporary artifacts. A public multi-user deployment would add authentication, rate limits, durable storage, a distributed queue, content-policy controls, and production observability. These boundaries prevent a focused single-host application from being misrepresented as an internet-scale platform.

## Niche skills and technologies showcased

### Resource-constrained AI and local inference

AWQ quantization, vLLM, GPU memory budgeting, CPU offloading, attention slicing, VAE slicing, lazy model loading, LCM-LoRA acceleration, inference-capacity planning, and bounded GPU concurrency.

### Agentic and structured AI workflows

LangGraph, Qwen 2.5, OpenAI-compatible model serving, prompt routing, structured LLM outputs, Pydantic validation, conditional workflow edges, reproducible generation, and deterministic post-processing.

### Generative imaging and document automation

Stable Diffusion, Hugging Face Diffusers, background removal, Pillow, ReportLab, PyMuPDF, vector typography, physical page geometry, bleed, safe zones, glyph-aware wrapping, WCAG contrast calculation, image-region analysis, and adaptive scrims.

### Backend productization and delivery

Python, FastAPI, Streamlit, asynchronous job APIs, dependency injection, temporary artifact lifecycle management, health checks, systemd, pytest, branch coverage, Ruff, mypy, and GitHub Actions.

## My contribution

I designed and implemented the project end to end: experimental notebooks, workflow architecture, local-model integration, GPU optimizations, deterministic layout engine, PDF renderer, API, user interface, automated tests, deployment configuration, and technical documentation.

The result showcases a specialty that is valuable beyond this individual application: turning resource-intensive generative-AI prototypes into bounded, testable, and maintainable products that can run on realistic client infrastructure.
