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


# ---------------------------------------------------------------------------
# Describe-only variants
#
# The labeler emits these; the runner then attaches a verdict from external
# provenance to produce a production-schema label. The model never decides
# pass/fail and never names failures — that's the v3 architectural shift.
# Mirrors `shared/schemas/*__describe_only.json`.
# ---------------------------------------------------------------------------

DescribeOnlyVerdict = Literal["describe_only"]


class FifthWheelSideViewDescribeOnly(BaseModel):
    category: Literal["fifth_wheel_side_view"]
    observations: FifthWheelObservations
    issues_detected: list[str] = Field(max_length=0)
    overall_status: DescribeOnlyVerdict
    confidence: DescribeOnlyVerdict
    human_readable_summary: str = Field(max_length=500)


class LockJawsCloseupDescribeOnly(BaseModel):
    category: Literal["lock_jaws_closeup"]
    observations: LockJawsObservations
    issues_detected: list[str] = Field(max_length=0)
    overall_status: DescribeOnlyVerdict
    confidence: DescribeOnlyVerdict
    human_readable_summary: str = Field(max_length=500)


class PintleHookAndChainsDescribeOnly(BaseModel):
    category: Literal["pintle_hook_and_chains"]
    observations: PintleHookObservations
    issues_detected: list[str] = Field(max_length=0)
    overall_status: DescribeOnlyVerdict
    confidence: DescribeOnlyVerdict
    human_readable_summary: str = Field(max_length=500)


DESCRIBE_ONLY_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel_side_view": FifthWheelSideViewDescribeOnly,
    "lock_jaws_closeup": LockJawsCloseupDescribeOnly,
    "pintle_hook_and_chains": PintleHookAndChainsDescribeOnly,
}


# ---------------------------------------------------------------------------
# v5 — inspection-level reframing
#
# Two inspections (fifth_wheel_coupling, pintle_hook). The fifth_wheel_coupling
# inspection accepts two evidence types (side_view, lock_jaws_underneath) and
# nests evidence-specific fields under matching sub-block keys. The other
# sub-block is null on any given label.
#
# Mirrors `shared/schemas/{fifth_wheel_coupling,pintle_hook}{,_describe_only}.json`.
# ---------------------------------------------------------------------------

from pydantic import model_validator  # noqa: E402  (deliberately late for grouping)


ImageQualityV5 = Literal["good", "acceptable", "poor"]
VerdictV5 = Literal["pass", "fail", "unclear"]


class SideView(BaseModel):
    """v5.6: simplified. Two primary signals + descriptive manufacturer.

    Manufacturer-conditional sub-objects (HollandHardware, FontaineHardware,
    JostHardware) were removed in v5.6 — the v5.5 audit confirmed those
    fields were unreliable evidence and the model was paying attention
    pressure on manufacturer ID at the expense of the primary signals.
    """
    trailer_seated_flush: Literal["yes", "no", "unclear"]
    gap_between_apron_and_plate: Literal["none", "minor", "obvious", "not_visible"]
    fifth_wheel_manufacturer: Literal["fontaine", "jost", "holland", "other", "unclear", "not_visible"]


class LockJawsUnderneath(BaseModel):
    fifth_wheel_variant: Literal["two_jaw", "single_bar", "unclear"]
    two_jaw_state: Literal["fully_closed", "partially_open", "open", "not_applicable", "not_visible"]
    single_bar_state: Literal["engaged_in_front_of_kingpin", "retracted", "not_applicable", "not_visible"]
    kingpin_visible: Literal["yes", "no"]


class RearAssembly(BaseModel):
    hitch_latch_state: Literal["closed", "open", "unclear", "not_visible"]
    safety_chains_count: Literal[0, 1, 2, "more_than_two", "not_visible"]
    safety_chains_clipped_to_bar: Literal[
        "at_least_one_clipped", "none_clipped", "unclear", "not_visible"
    ]


class _FifthWheelCouplingBase(BaseModel):
    inspection_type: Literal["fifth_wheel_coupling"]
    evidence_type: Literal["side_view", "lock_jaws_underneath"]
    image_quality: ImageQualityV5
    photo_matches_category: Literal["yes", "no", "unclear"]
    factual_summary: str = Field(max_length=1000)
    side_view: SideView | None = None
    lock_jaws_underneath: LockJawsUnderneath | None = None

    @model_validator(mode="after")
    def _exactly_one_evidence_block(self) -> "_FifthWheelCouplingBase":
        if self.evidence_type == "side_view":
            if self.side_view is None:
                raise ValueError("side_view must be populated when evidence_type='side_view'")
            if self.lock_jaws_underneath is not None:
                raise ValueError("lock_jaws_underneath must be null when evidence_type='side_view'")
        else:  # lock_jaws_underneath
            if self.lock_jaws_underneath is None:
                raise ValueError("lock_jaws_underneath must be populated when evidence_type='lock_jaws_underneath'")
            if self.side_view is not None:
                raise ValueError("side_view must be null when evidence_type='lock_jaws_underneath'")
        return self


class FifthWheelCoupling(_FifthWheelCouplingBase):
    verdict: VerdictV5
    issues_detected: list[str]


class FifthWheelCouplingDescribeOnly(_FifthWheelCouplingBase):
    verdict: Literal["describe_only"]
    issues_detected: list[str] = Field(max_length=0)


class PintleHook(BaseModel):
    inspection_type: Literal["pintle_hook"]
    evidence_type: Literal["rear_assembly"]
    image_quality: ImageQualityV5
    photo_matches_category: Literal["yes", "no", "unclear"]
    verdict: VerdictV5
    issues_detected: list[str]
    factual_summary: str = Field(max_length=1000)
    rear_assembly: RearAssembly


class PintleHookDescribeOnly(BaseModel):
    inspection_type: Literal["pintle_hook"]
    evidence_type: Literal["rear_assembly"]
    image_quality: ImageQualityV5
    photo_matches_category: Literal["yes", "no", "unclear"]
    verdict: Literal["describe_only"]
    issues_detected: list[str] = Field(max_length=0)
    factual_summary: str = Field(max_length=1000)
    rear_assembly: RearAssembly


V5_PRODUCTION_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel_coupling": FifthWheelCoupling,
    "pintle_hook": PintleHook,
}

V5_DESCRIBE_ONLY_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel_coupling": FifthWheelCouplingDescribeOnly,
    "pintle_hook": PintleHookDescribeOnly,
}
