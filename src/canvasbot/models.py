from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class DesignCategory(StrEnum):
    FLYER = "flyer"
    POSTER = "poster"
    BUSINESS_CARD = "business_card"
    UNSUPPORTED = "unsupported_style"


class BackgroundStyle(StrEnum):
    FULL_IMAGE = "full_image"
    SOLID_WITH_PHOTO = "solid_color_with_photo"
    SOLID_TEXT_ONLY = "solid_color_text_only"
    SPLIT_HORIZONTAL = "split_screen_horizontal"
    SOLID_WITH_DECAL = "solid_color_with_decal"


class GatekeeperResult(BaseModel):
    category: DesignCategory


class VisualRegion(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    box_min_x: float = Field(ge=0, le=1)
    box_min_y: float = Field(ge=0, le=1)
    box_max_x: float = Field(ge=0, le=1)
    box_max_y: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_box(self) -> "VisualRegion":
        if self.box_min_x >= self.box_max_x or self.box_min_y >= self.box_max_y:
            raise ValueError("visual region minimum coordinates must be below maximums")
        return self


class TextBlock(BaseModel):
    role: Literal["headline", "subtitle", "body", "cta"]
    content: str = Field(min_length=1, max_length=240)
    emphasis: Literal["none", "script"] = "none"
    vertical_zone: Literal["top", "middle", "bottom"] = "middle"


class CopywritingResult(BaseModel):
    background_style: BackgroundStyle
    background_hex: HexColor = "#FFFFFF"
    global_background_prompt: str = Field(min_length=1, max_length=1000)
    visual_regions: list[VisualRegion] = Field(default_factory=list, max_length=4)
    visual_subject: str | None = Field(default=None, max_length=1000)
    visual_style: Literal["photography", "illustration", "3d_render", "abstract"]
    text_scale: Literal["small", "standard", "large"] = "standard"
    blocks: list[TextBlock] = Field(min_length=1, max_length=3)
    text_color: HexColor | None = None


class LayoutDecision(BaseModel):
    spatial_reasoning: str = Field(min_length=1, max_length=500)
    horizontal_placement: Literal["left", "center", "right"] = "center"


class TextElement(BaseModel):
    text: str
    font: str = "Helvetica-Bold"
    size: int = Field(default=12, ge=6, le=240)
    x_pos: float = 0
    y_pos: float = 0
    color: HexColor = "#000000"
    alignment: Literal["left", "center", "right"] = "center"
    emphasis: Literal["none", "script"] = "none"
    vertical_zone: Literal["top", "middle", "bottom"] = "middle"
    lines: list[str] = Field(default_factory=list)
    needs_scrim: bool = False


class DesignLayout(BaseModel):
    spatial_reasoning: str
    horizontal_placement: Literal["left", "center", "right"] = "center"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    bleed_margin: int = Field(default=9, ge=0)
    safe_zone_margin: int = Field(default=18, ge=0)
    background_image: Path | None = None
    elements: list[TextElement]


class DesignRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        return " ".join(value.split())


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class JobRecord(BaseModel):
    id: str
    state: JobState
    stage: str
    created_at: str
    updated_at: str
    category: DesignCategory | None = None
    error: str | None = None
    pdf_url: str | None = None
    preview_url: str | None = None
