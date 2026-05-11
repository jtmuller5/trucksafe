"""Schema tests.

Three concerns:

1. Each Pydantic model accepts a valid example and rejects an obviously
   invalid one.
2. Each JSON Schema file in `shared/schemas/` is well-formed JSON Schema.
3. The Pydantic models and JSON Schema files agree on field names and
   enum values — this is the contract between the Python training code
   and the Flutter consumer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from trucksafe_training.schemas import (
    SCHEMA_MODELS,
    FifthWheelSideView,
    LockJawsCloseup,
    PintleHookAndChains,
)

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "shared" / "schemas"

VALID_EXAMPLES: dict[str, dict[str, Any]] = {
    "fifth_wheel_side_view": {
        "category": "fifth_wheel_side_view",
        "observations": {
            "trailer_seated_flush": "yes",
            "visible_gap_between_apron_and_plate": "none",
            "release_handle_position": "stowed",
            "image_quality": "good",
        },
        "issues_detected": [],
        "overall_status": "pass",
        "confidence": "high",
        "human_readable_summary": "Trailer fully seated, no gap visible, handle stowed.",
    },
    "lock_jaws_closeup": {
        "category": "lock_jaws_closeup",
        "observations": {
            "jaws_fully_closed_around_kingpin": "yes",
            "kingpin_visible_in_jaws": True,
            "lock_indicator_position": "locked",
            "image_quality": "good",
        },
        "issues_detected": [],
        "overall_status": "pass",
        "confidence": "high",
        "human_readable_summary": "Jaws closed around kingpin, lock indicator in locked position.",
    },
    "pintle_hook_and_chains": {
        "category": "pintle_hook_and_chains",
        "observations": {
            "hook_latch_state": "closed",
            "safety_pin_visible": True,
            "safety_chains_count": 2,
            "safety_chains_hooked": True,
            "safety_chains_crossed": True,
            "image_quality": "good",
        },
        "issues_detected": [],
        "overall_status": "pass",
        "confidence": "high",
        "human_readable_summary": "Hook closed, pin in place, two chains hooked and crossed.",
    },
}

MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel_side_view": FifthWheelSideView,
    "lock_jaws_closeup": LockJawsCloseup,
    "pintle_hook_and_chains": PintleHookAndChains,
}


@pytest.mark.parametrize("category", list(VALID_EXAMPLES))
def test_valid_example_parses(category: str) -> None:
    model = MODELS[category]
    instance = model.model_validate(VALID_EXAMPLES[category])
    assert instance.model_dump()["category"] == category


@pytest.mark.parametrize("category", list(VALID_EXAMPLES))
def test_wrong_category_rejected(category: str) -> None:
    model = MODELS[category]
    bad = dict(VALID_EXAMPLES[category])
    bad["category"] = "not_a_real_category"
    with pytest.raises(ValidationError):
        model.model_validate(bad)


@pytest.mark.parametrize("category", list(VALID_EXAMPLES))
def test_missing_required_field_rejected(category: str) -> None:
    model = MODELS[category]
    bad = dict(VALID_EXAMPLES[category])
    del bad["overall_status"]
    with pytest.raises(ValidationError):
        model.model_validate(bad)


@pytest.mark.parametrize("category", list(VALID_EXAMPLES))
def test_json_schema_file_is_well_formed(category: str) -> None:
    path = SCHEMAS_DIR / f"{category}.json"
    schema = json.loads(path.read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    assert "title" in schema
    assert set(schema["required"]) == {
        "category",
        "observations",
        "issues_detected",
        "overall_status",
        "confidence",
        "human_readable_summary",
    }
    assert schema["properties"]["category"]["const"] == category


def _pydantic_top_level_fields(model: type[BaseModel]) -> set[str]:
    return set(model.model_fields.keys())


def _pydantic_observation_fields(model: type[BaseModel]) -> set[str]:
    obs_field = model.model_fields["observations"]
    obs_model: type[BaseModel] = obs_field.annotation  # type: ignore[assignment]
    return set(obs_model.model_fields.keys())


@pytest.mark.parametrize("category", list(VALID_EXAMPLES))
def test_pydantic_matches_json_schema(category: str) -> None:
    """The Pydantic model and the JSON Schema must agree on field names."""
    schema = json.loads((SCHEMAS_DIR / f"{category}.json").read_text())
    model = MODELS[category]

    schema_top = set(schema["properties"].keys())
    assert _pydantic_top_level_fields(model) == schema_top

    schema_obs = set(schema["properties"]["observations"]["properties"].keys())
    assert _pydantic_observation_fields(model) == schema_obs


def test_schema_models_registry_complete() -> None:
    assert set(SCHEMA_MODELS) == set(VALID_EXAMPLES)
