import pytest
from pydantic import ValidationError

from canvasbot.models import DesignRequest, VisualRegion


def test_prompt_is_normalized() -> None:
    request = DesignRequest(prompt="  Create   a modern flyer   for an event. ")
    assert request.prompt == "Create a modern flyer for an event."


def test_prompt_rejects_short_input() -> None:
    with pytest.raises(ValidationError):
        DesignRequest(prompt="poster")


def test_visual_region_requires_ordered_coordinates() -> None:
    with pytest.raises(ValidationError):
        VisualRegion(
            prompt="coffee cup",
            box_min_x=0.8,
            box_min_y=0.1,
            box_max_x=0.2,
            box_max_y=0.9,
        )
