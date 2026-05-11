"""Pydantic mirrors of `shared/schemas/*.json`.

The JSON Schema files in `shared/schemas/` are the source of truth — both
this module and the Flutter mobile app derive from them. `tests/test_schemas.py`
asserts the two stay in sync.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

OverallStatus = Literal["pass", "fail", "retake"]
Confidence = Literal["high", "medium", "low"]
ImageQuality = Literal["good", "poor"]


class FifthWheelObservations(BaseModel):
    trailer_seated_flush: Literal["yes", "no", "unclear"]
    visible_gap_between_apron_and_plate: Literal["none", "minor", "obvious"]
    release_handle_position: Literal["stowed", "extended", "unclear"]
    image_quality: ImageQuality


class FifthWheelSideView(BaseModel):
    category: Literal["fifth_wheel_side_view"]
    observations: FifthWheelObservations
    issues_detected: list[str]
    overall_status: OverallStatus
    confidence: Confidence
    human_readable_summary: str = Field(max_length=500)


class LockJawsObservations(BaseModel):
    jaws_fully_closed_around_kingpin: Literal["yes", "no", "unclear"]
    kingpin_visible_in_jaws: bool
    lock_indicator_position: Literal["locked", "unlocked", "not_visible"]
    image_quality: ImageQuality


class LockJawsCloseup(BaseModel):
    category: Literal["lock_jaws_closeup"]
    observations: LockJawsObservations
    issues_detected: list[str]
    overall_status: OverallStatus
    confidence: Confidence
    human_readable_summary: str = Field(max_length=500)


class PintleHookObservations(BaseModel):
    hook_latch_state: Literal["closed", "open", "unclear"]
    safety_pin_visible: bool
    safety_chains_count: int = Field(ge=0)
    safety_chains_hooked: bool
    safety_chains_crossed: bool
    image_quality: ImageQuality


class PintleHookAndChains(BaseModel):
    category: Literal["pintle_hook_and_chains"]
    observations: PintleHookObservations
    issues_detected: list[str]
    overall_status: OverallStatus
    confidence: Confidence
    human_readable_summary: str = Field(max_length=500)


InspectionResult = Annotated[
    FifthWheelSideView | LockJawsCloseup | PintleHookAndChains,
    Field(discriminator="category"),
]

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel_side_view": FifthWheelSideView,
    "lock_jaws_closeup": LockJawsCloseup,
    "pintle_hook_and_chains": PintleHookAndChains,
}
