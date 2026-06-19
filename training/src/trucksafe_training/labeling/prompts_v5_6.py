"""v5.6 describe-only prompts — side_view schema simplification.

Changes vs v5.5:
  - `side_view` schema is now flat: `trailer_seated_flush`,
    `gap_between_apron_and_plate`, `fifth_wheel_manufacturer`. The
    manufacturer-conditional sub-objects (holland / fontaine / jost) are
    gone. The v5.5 audit confirmed they were unreliable evidence and the
    model was paying attention-pressure on manufacturer ID at the expense
    of the two primary signals.
  - Side-view prompt drops the manufacturer decision tree. Manufacturer is
    demoted to a single descriptive line; the priority is the two seating
    signals.
  - `FEW_SHOT_SUBFOLDERS["fifth_wheel"]` consolidates from three
    manufacturer folders to a single `side_view_plate/` folder. The
    library loader stop-and-surfaces if `side_view_plate/` has no captions.

Unchanged from v5.5:
  - `photo_matches_category` self-check (still at the top of every prompt).
  - lock_jaws_underneath prompt + schema.
  - rear_assembly prompt + relaxed chains-clipped schema.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import NamedTuple

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMAS_DIR = _REPO_ROOT / "shared" / "schemas"
_FEW_SHOT_DIR = _REPO_ROOT / "training" / "assets" / "few_shot_examples"


def _load_schema(filename: str) -> str:
    return json.dumps(json.loads((_SCHEMAS_DIR / filename).read_text()), indent=2)


_FIFTH_WHEEL_COUPLING_SCHEMA = _load_schema("fifth_wheel_coupling_describe_only.json")
_PINTLE_HOOK_SCHEMA = _load_schema("pintle_hook_describe_only.json")


# ---------------------------------------------------------------------------
# Few-shot reference image library loader (unchanged shape from v5.5)
# ---------------------------------------------------------------------------


class FewShotExample(NamedTuple):
    relative_path: str
    caption: str
    image_b64: str
    media_type: str


def _media_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    raise ValueError(f"unsupported reference image extension: {path}")


def load_few_shot_library() -> dict[str, list[FewShotExample]]:
    captions_path = _FEW_SHOT_DIR / "captions.json"
    if not captions_path.exists():
        raise RuntimeError(f"few-shot captions.json missing: {captions_path}")
    captions: dict[str, str] = json.loads(captions_path.read_text())

    library: dict[str, list[FewShotExample]] = {}
    for rel, caption in captions.items():
        full = _FEW_SHOT_DIR / rel
        if not full.exists():
            raise RuntimeError(
                f"few-shot reference image listed in captions.json but missing on disk: {full}"
            )
        subfolder = rel.split("/", 1)[0]
        b64 = base64.b64encode(full.read_bytes()).decode("ascii")
        library.setdefault(subfolder, []).append(
            FewShotExample(rel, caption, b64, _media_type_for(full))
        )

    for subfolder, examples in library.items():
        if not examples:
            raise RuntimeError(f"few-shot subfolder {subfolder} has no captioned images")
    return library


# v5.6: side_view consolidates to a single subfolder. lock_jaws + pintle unchanged.
FEW_SHOT_SUBFOLDERS: dict[str, list[str]] = {
    "fifth_wheel": ["side_view_plate"],
    "lock_jaws": ["lock_jaws"],
    "pintle_hook": ["pintle_hook"],
}


# ---------------------------------------------------------------------------
# photo_matches_category instruction block (unchanged from v5.5)
# ---------------------------------------------------------------------------


def _category_self_check_block(hardware_description: str) -> str:
    return f"""────────────────────────────────────────────────────────────
**FIRST: photo_matches_category self-check.**
────────────────────────────────────────────────────────────

Before describing the image, first determine whether it actually shows {hardware_description}. Set `photo_matches_category` to:

- `yes` if the image clearly shows {hardware_description};
- `no` if it shows something else entirely (different hardware, wrong angle, unrelated subject, severely blurred beyond recognition);
- `unclear` if you can see hardware that might be relevant but you cannot confidently confirm it's the right category.

This is independent of `image_quality`. A photo can be `photo_matches_category: yes` and still be unevaluable (poor lighting, occluded). A photo can be `photo_matches_category: no` even if it shows valid truck hardware that just isn't this category.

If `photo_matches_category` is `no` or `unclear`, **still complete the rest of the schema as best you can** — fill remaining fields with `not_visible` / `unclear` where appropriate, and use `factual_summary` to describe what the image actually shows.
"""


_SIDE_VIEW_SELF_CHECK = _category_self_check_block(
    "a side view of a fifth-wheel coupling, showing the trailer apron resting on the fifth-wheel plate"
)
_LOCK_JAWS_SELF_CHECK = _category_self_check_block(
    "an underneath view of fifth-wheel locking jaws engaging a kingpin"
)
_REAR_ASSEMBLY_SELF_CHECK = _category_self_check_block(
    "a view of a pintle hook coupling, including the hook itself and the safety chains"
)


# ---------------------------------------------------------------------------
# Side view prompt (v5.6: manufacturer decision tree removed, demoted)
# ---------------------------------------------------------------------------


SIDE_VIEW_PROMPT = f"""You are describing a commercial truck fifth-wheel coupling photo for a fleet documentation system. The image is a side view of the tractor-trailer coupling area.

Your job is to describe what you see. You are NOT evaluating safety. You are populating observation fields based on visual evidence only.

{_SIDE_VIEW_SELF_CHECK}

You will be shown a small set of REFERENCE images first, with captions that name what to look for. Use these as visual anchors. Then you will be shown the INPUT image to describe.

If `photo_matches_category == "yes"`, continue with the two primary signals below. If `no` or `unclear`, still emit the full schema (mostly `not_visible` / `unclear`) and describe what the image actually shows in `factual_summary`.

**Two primary signals (this is your priority):**

- `trailer_seated_flush`: Is the trailer apron seated flush against the fifth-wheel plate? Possible values: `yes`, `no`, `unclear`.
- `gap_between_apron_and_plate`: Is there a visible gap between the apron and the plate? Possible values: `none`, `minor` (thin), `obvious`, `not_visible`.

These two fields together describe whether the trailer is properly seated on the plate — the primary safety signal this view inspects.

**Descriptive only:**

- `fifth_wheel_manufacturer`: Report `fifth_wheel_manufacturer` (fontaine | jost | holland | other | unclear | not_visible) **only if a manufacturer is clearly identifiable from a logo or distinctive feature**. Otherwise report `unclear`. This field is descriptive only — your priority is `trailer_seated_flush` and `gap_between_apron_and_plate`. Do not spend effort on a borderline manufacturer call.

**Image quality:** `image_quality`: good / acceptable / poor.

You will emit a single JSON object conforming exactly to this schema:

{_FIFTH_WHEEL_COUPLING_SCHEMA}

Rules:
- Set `evidence_type` to `"side_view"`. Populate the `side_view` sub-object. Set `lock_jaws_underneath` to `null`.
- `verdict`: emit the literal `"describe_only"`. `issues_detected`: `[]`.
- `factual_summary`: 2–3 factual sentences describing the apron-to-plate contact, any visible gap, the lighting. No judgment language.
- Default to `unclear` or `not_visible` when you cannot tell.

Emit ONLY the JSON object. No preamble, no markdown fence. Start with `{{` and end with `}}`.

Examples of valid outputs:

Trailer seated, no gap, manufacturer logo not visible:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"good","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Side view of the coupling in daylight. The trailer apron is flush against the fifth-wheel plate with no visible gap. No manufacturer logo is resolved at this angle.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"unclear"}},"lock_jaws_underneath":null}}

Trailer seated, no gap, Jost logo clearly visible:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"good","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Side view of the coupling. Trailer apron is flush with the plate, no visible gap. A Jost logo is stamped on the plate body.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"jost"}},"lock_jaws_underneath":null}}

Visible gap, manufacturer not determinable:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"acceptable","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Side view of the coupling. A thin gap is visible between the apron and the fifth-wheel plate along the front edge. The angle does not reveal the manufacturer.","side_view":{{"trailer_seated_flush":"unclear","gap_between_apron_and_plate":"minor","fifth_wheel_manufacturer":"unclear"}},"lock_jaws_underneath":null}}

Hardware not visible (dark):
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"poor","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Side view taken in low light. The apron-to-plate contact line is in deep shadow and cannot be assessed.","side_view":{{"trailer_seated_flush":"unclear","gap_between_apron_and_plate":"not_visible","fifth_wheel_manufacturer":"not_visible"}},"lock_jaws_underneath":null}}
"""


# ---------------------------------------------------------------------------
# Lock jaws prompt (unchanged from v5.5)
# ---------------------------------------------------------------------------


LOCK_JAWS_UNDERNEATH_PROMPT = f"""You are describing a commercial truck fifth-wheel coupling photo for a fleet documentation system. The image is taken from under the trailer, looking up at the underside of the fifth-wheel plate.

**Spatial prior:** the image has been pre-cropped to a horizontal band just below the top edge of the fifth-wheel plate, where the locking mechanism sits. Focus your description on this region.

{_LOCK_JAWS_SELF_CHECK}

You will be shown REFERENCE images first that demonstrate the two mechanism variants you must distinguish:

- **Two-jaw**: a pair of curved metal fingers wrapping around the central kingpin from both sides.
- **Single-bar**: a single straight horizontal bar positioned in front of the kingpin, no curved fingers.

Calibrate your visual vocabulary against these references, then describe the INPUT image using the same labels.

Your job is to describe what you see. You are NOT evaluating safety.

Close-up photos of this area are often taken at awkward angles in low light with grease and dirt present. That is normal. Grease and dirt by themselves do NOT make image_quality poor — only call image_quality poor if the features you need to observe are actually obscured.

**Do not attempt to identify the fifth-wheel manufacturer from this view.** Manufacturer identification is side-view-only. From underneath, only the mechanism variant (two-jaw vs single-bar) is reliably visible.

Look at the input image carefully and report:

- `fifth_wheel_variant`: `two_jaw`, `single_bar`, or `unclear`. **`unclear` is the catch-all for "I can't identify the mechanism."** This field does NOT accept `not_visible`.
- `two_jaw_state`: If two-jaw — fully_closed / partially_open / open / not_visible. If single-bar or unclear — `not_applicable`.
- `single_bar_state`: If single-bar — engaged_in_front_of_kingpin / retracted / not_visible. If two-jaw or unclear — `not_applicable`.
- `kingpin_visible`: yes/no.
- `image_quality`: good / acceptable / poor.

You will emit a single JSON object conforming exactly to this schema:

{_FIFTH_WHEEL_COUPLING_SCHEMA}

Rules:
- Set `evidence_type` to `"lock_jaws_underneath"`. Populate the `lock_jaws_underneath` sub-object. Set `side_view` to `null`.
- `verdict`: `"describe_only"`. `issues_detected`: `[]`.
- `factual_summary`: 1–2 factual sentences. No judgment language.
- If `fifth_wheel_variant` is `unclear`, both states should be `not_applicable`.

Emit ONLY the JSON object. No preamble, no markdown fence.
"""


# ---------------------------------------------------------------------------
# Rear assembly prompt (unchanged from v5.5)
# ---------------------------------------------------------------------------


REAR_ASSEMBLY_PROMPT = f"""You are describing a commercial truck pintle-hook coupling photo for a fleet documentation system. The image shows the pintle hook at the rear of a tractor connecting to a trailer (or dolly).

Your job is to describe what you see for a TWO-ITEM inspection. You are NOT evaluating safety; you are populating observation fields.

{_REAR_ASSEMBLY_SELF_CHECK}

You will be shown REFERENCE images first that demonstrate a correctly-engaged pintle coupling: hitch latch fully closed around the lunette ring, at least one safety chain visibly clipped to the bottom bar (side-angle framing means the far-side chain may be off-frame — this is acceptable). Use these as positive anchors for your description vocabulary.

────────────────────────────────────────────────────────────
**The two inspection items (answer in order, ASSUMING `photo_matches_category == "yes"`):**

**Item 1 — Hitch latch state:** Is the hitch latch (the hinged metal piece on top of the hook) fully closed and wrapped around the lunette ring, or is it open/raised? Possible states: `closed`, `open`, `unclear`, `not_visible`.

**Item 2 — Safety chains clipped to the bottom bar:** Below the pintle hook, there is a horizontal bar or D-ring on the tractor where the trailer's safety chains terminate. Each chain ends in a metal clip (carabiner-style) that hooks onto the bar.

Report TWO fields for this item:
- `safety_chains_count`: how many safety chains are visible in the frame — `0`, `1`, `2`, `more_than_two`, or `not_visible`. Most archive photos are side-angle and show one chain clearly; the second is typically out of frame. Count what you actually see in this image.
- `safety_chains_clipped_to_bar`: of the visible chains, do you see at least one clipped onto the bar?
  - `at_least_one_clipped` — you can see at least one safety chain visibly clipped to the bottom bar with a metal clip. The far-side chain may or may not be visible; this is acceptable for the inspection because the photo was taken from a side angle. **This is the engagement-confirmed state.**
  - `none_clipped` — chain(s) visible but none are clipped to the bar.
  - `unclear` — chain(s) and/or bar partially visible, can't confirm the clipping with confidence.
  - `not_visible` — chains and/or bar are out of frame entirely.
────────────────────────────────────────────────────────────

**Image quality:** `image_quality`: good / acceptable / poor.

You will emit a single JSON object conforming exactly to this schema:

{_PINTLE_HOOK_SCHEMA}

Rules:
- Set `inspection_type` to `"pintle_hook"` and `evidence_type` to `"rear_assembly"`. Populate the `rear_assembly` sub-object.
- `verdict`: `"describe_only"`. `issues_detected`: `[]`. `factual_summary`: 2–3 factual sentences mentioning the photo-matches self-check result and the two inspection items.
- Do not use judgment language ("pass", "fail", "safe", "unsafe", "missing", "wrong", etc.).

Emit ONLY the JSON object. No preamble, no markdown fence.

Examples of valid outputs:

Side-angle photo showing one chain clearly clipped (most common archive case):
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"good","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Side-angle photo of the pintle hook area. The hitch latch is wrapped closed around the lunette ring. One safety chain is visible in the frame with its end-clip engaged onto the bottom bar; the far-side chain is off-frame.","rear_assembly":{{"hitch_latch_state":"closed","safety_chains_count":1,"safety_chains_clipped_to_bar":"at_least_one_clipped"}}}}

Wider-angle photo showing two chains both clipped:
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"good","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Daylight photo of the pintle hook area. The hitch latch is closed around the lunette. Two safety chains are visible, both with end-clips engaged onto the bottom bar.","rear_assembly":{{"hitch_latch_state":"closed","safety_chains_count":2,"safety_chains_clipped_to_bar":"at_least_one_clipped"}}}}

Latch open, chains hanging free with no clips on bar:
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"good","verdict":"describe_only","issues_detected":[],"photo_matches_category":"yes","factual_summary":"Pintle hook with the latch raised in the open position. Two safety chains are visible draped across the receiver but neither is clipped onto a bar.","rear_assembly":{{"hitch_latch_state":"open","safety_chains_count":2,"safety_chains_clipped_to_bar":"none_clipped"}}}}

Photo doesn't actually show a pintle hook (miscategorized):
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"acceptable","verdict":"describe_only","issues_detected":[],"photo_matches_category":"no","factual_summary":"Close-up of a metal bracket and a single chain link; no pintle hook or lunette ring is visible. Likely a detail shot of unrelated hardware.","rear_assembly":{{"hitch_latch_state":"not_visible","safety_chains_count":"not_visible","safety_chains_clipped_to_bar":"not_visible"}}}}
"""


# ---------------------------------------------------------------------------
# EVIDENCE_CONFIG
# ---------------------------------------------------------------------------


EVIDENCE_CONFIG: dict[str, tuple[str, str, str]] = {
    "fifth_wheel": ("fifth_wheel_coupling", "side_view", SIDE_VIEW_PROMPT),
    "lock_jaws": ("fifth_wheel_coupling", "lock_jaws_underneath", LOCK_JAWS_UNDERNEATH_PROMPT),
    "pintle_hook": ("pintle_hook", "rear_assembly", REAR_ASSEMBLY_PROMPT),
}
