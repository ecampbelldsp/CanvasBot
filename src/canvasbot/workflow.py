from collections.abc import Callable
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

from langgraph.graph import END, StateGraph

from canvasbot.errors import UnsupportedDesignError
from canvasbot.image_generation import ImageGenerator
from canvasbot.layout import PAGE_SIZES, validate_layout
from canvasbot.llm import LLMService
from canvasbot.models import (
    CopywritingResult,
    DesignCategory,
    DesignLayout,
    DesignRequest,
    LayoutDecision,
    TextElement,
)

ProgressCallback = Callable[[str], None]


class WorkflowState(TypedDict):
    request: DesignRequest
    work_dir: Path
    progress: ProgressCallback
    category: NotRequired[DesignCategory]
    copy: NotRequired[CopywritingResult]
    background_image: NotRequired[Path | None]
    decision: NotRequired[LayoutDecision]
    layout: NotRequired[DesignLayout]


class DesignPipeline:
    def __init__(self, llm: LLMService, image_generator: ImageGenerator) -> None:
        self._llm = llm
        self._image_generator = image_generator
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("gatekeeper", self._classify)
        graph.add_node("copywriter", self._write_copy)
        graph.add_node("image_generator", self._generate_image)
        graph.add_node("layout_designer", self._design_layout)
        graph.add_node("validator", self._validate)
        graph.set_entry_point("gatekeeper")
        graph.add_conditional_edges(
            "gatekeeper",
            lambda state: (
                "reject" if state["category"] == DesignCategory.UNSUPPORTED else "continue"
            ),
            {"reject": END, "continue": "copywriter"},
        )
        graph.add_edge("copywriter", "image_generator")
        graph.add_edge("image_generator", "layout_designer")
        graph.add_edge("layout_designer", "validator")
        graph.add_edge("validator", END)
        return graph.compile()

    def _classify(self, state: WorkflowState) -> dict[str, object]:
        state["progress"]("classification")
        result = self._llm.classify(state["request"].prompt)
        return {"category": result.category}

    def _write_copy(self, state: WorkflowState) -> dict[str, object]:
        state["progress"]("copywriting")
        return {"copy": self._llm.write_copy(state["request"].prompt)}

    def _generate_image(self, state: WorkflowState) -> dict[str, object]:
        state["progress"]("image_generation")
        path = state["work_dir"] / "background.png"
        image = self._image_generator.generate(
            state["copy"], state["category"], path, state["request"].seed
        )
        return {"background_image": image}

    def _design_layout(self, state: WorkflowState) -> dict[str, object]:
        state["progress"]("layout")
        decision = self._llm.choose_layout(state["request"].prompt, state["copy"])
        width, height = PAGE_SIZES[state["category"]]
        scale = {"small": 0.75, "standard": 1.0, "large": 1.4}[state["copy"].text_scale]
        base_sizes = {"headline": 36, "subtitle": 24, "body": 18, "cta": 22}
        if state["category"] == DesignCategory.BUSINESS_CARD:
            base_sizes = {"headline": 14, "subtitle": 10, "body": 8, "cta": 9}
        elements = [
            TextElement(
                text=block.content,
                font=(
                    "Caveat-Bold"
                    if block.emphasis == "script"
                    else "Poppins-Bold"
                    if block.role != "body"
                    else "Poppins-Regular"
                ),
                size=max(
                    8,
                    int(
                        base_sizes[block.role] * scale * (1.5 if block.emphasis == "script" else 1)
                    ),
                ),
                alignment=decision.horizontal_placement,
                emphasis=block.emphasis,
                vertical_zone=block.vertical_zone,
            )
            for block in state["copy"].blocks
        ]
        layout = DesignLayout(
            spatial_reasoning=decision.spatial_reasoning,
            horizontal_placement=decision.horizontal_placement,
            width=width,
            height=height,
            background_image=state["background_image"],
            elements=elements,
        )
        return {"decision": decision, "layout": layout}

    @staticmethod
    def _validate(state: WorkflowState) -> dict[str, object]:
        state["progress"]("validation")
        layout = validate_layout(
            state["layout"],
            state["copy"].background_style,
            state["copy"].background_hex,
            state["copy"].text_color,
        )
        return {"layout": layout}

    def run(
        self, request: DesignRequest, work_dir: Path, progress: ProgressCallback
    ) -> WorkflowState:
        result = self._graph.invoke(
            {"request": request, "work_dir": work_dir, "progress": progress}
        )
        if result["category"] == DesignCategory.UNSUPPORTED:
            raise UnsupportedDesignError(
                "Supported products are flyers, posters, and business cards."
            )
        return cast(WorkflowState, result)
