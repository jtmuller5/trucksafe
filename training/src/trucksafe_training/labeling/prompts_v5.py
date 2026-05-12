"""v5.1 describe-only prompts — manufacturer-aware side_view.

Three evidence types:
  - side_view (fifth_wheel_coupling): identifies fifth-wheel manufacturer
    (Holland / Fontaine / Jost / other) via a decision tree on diagnostic
    features, then describes manufacturer-specific hardware. Falls back to
    `unclear` or `not_visible` when the diagnostic feature isn't in frame.
  - lock_jaws_underneath (fifth_wheel_coupling): identifies mechanism variant
    (two_jaw vs single_bar) — orthogonal to manufacturer.
  - rear_assembly (pintle_hook): hook, latch, pin, chains.

Text-only — no reference visuals exist in the repo. Verbal descriptions of
the brand diagnostic features are inlined into the side_view prompt.
"""

from __future__ import annotations

import json
from pathlib import Path

_SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "shared" / "schemas"


def _load_schema(filename: str) -> str:
    return json.dumps(json.loads((_SCHEMAS_DIR / filename).read_text()), indent=2)


_FIFTH_WHEEL_COUPLING_SCHEMA = _load_schema("fifth_wheel_coupling_describe_only.json")
_PINTLE_HOOK_SCHEMA = _load_schema("pintle_hook_describe_only.json")


_MANUFACTURER_DECISION_TREE = """
Identify the fifth-wheel manufacturer using this decision tree on diagnostic features visible in the side view. Apply the tests in order; the first match wins:

1. **Pin assembly on the FRONT FACE of the fifth-wheel plate?** → **Holland**.
   - Holland's release mechanism uses a pin that protrudes from the front-facing surface of the fifth-wheel plate (the side of the plate that the driver sees while approaching from the rear).
   - When engaged: the front pin is fully retracted into the plate body, with the washer/nut behind it sitting flush against the casting.
   - When NOT engaged: the front pin is extended out, or the washer is visibly proud of the casting body.

2. **No front pin, but a pin on the SIDE of the plate body?** → **Fontaine**.
   - Fontaine and Jost both have a side-mounted release handle. The disambiguating feature is a SECONDARY side pin that Fontaine has but Jost does not.
   - The side pin sits in the side wall of the plate housing, distinct from the release handle itself.
   - When engaged: the side pin is retracted.

3. **No front pin, no side pin, but a strap or pull-cord hanging from the CENTER of the underside of the plate?** → **Jost**.
   - Jost uses a center release strap accessible from underneath/between the trailer and tractor.
   - From the side, the visible hardware is the same shape as Fontaine's (a side handle) but without the disambiguating side pin.
   - Jost engagement is HARD to read from the side. `side_handle_position: "not_clearly_visible"` is the correct, honest answer when the photo doesn't resolve it. Do not force a retracted/extended call.

4. **None of the above features are clearly visible** → `fifth_wheel_manufacturer: "unclear"` if you can see the plate but can't identify which brand, or `"not_visible"` if you cannot see the fifth-wheel hardware at all.

5. **Hardware visible but doesn't match any of the three patterns** → `"other"`.

Important caveats:
- Fontaine and Jost are visually similar from the side. The presence or absence of the side pin is the disambiguating feature. If the side angle doesn't reveal whether a side pin is present, mark `"unclear"` rather than guessing.
- Manufacturer identification is side-view-only. Lock-jaws underneath shots do NOT reveal manufacturer.
- Mechanism variant (two_jaw vs single_bar) is a separate axis — that's a lock_jaws_underneath field, not a side_view field. A Holland and a Jost might both ship two-jaw mechanisms.
"""


SIDE_VIEW_PROMPT = f"""You are describing a commercial truck fifth-wheel coupling photo for a fleet documentation system. The image is a side view of the tractor-trailer coupling area.

Your job is to describe what you see. You are NOT evaluating whether the coupling is safe. You are NOT identifying failures. You are populating observation fields based on visual evidence only. Verdicts come from a separate system.

Two tasks: (a) describe the seating of the trailer apron against the fifth-wheel plate, and (b) identify the fifth-wheel manufacturer and describe its specific release hardware.

{_MANUFACTURER_DECISION_TREE}

Look at the image carefully and report:

**Seating (apply regardless of manufacturer):**
- Whether the trailer apron appears flush against the fifth-wheel plate.
- The gap, if any, between the apron and plate. Distinguish none / minor (thin) / obvious / not_visible.

**Manufacturer:**
- Apply the decision tree above. Pick exactly one of: fontaine | jost | holland | other | unclear | not_visible.

**Manufacturer-specific hardware (populate ONLY the sub-object matching the identified manufacturer; set the other two to null):**

If `fifth_wheel_manufacturer: "holland"` — populate `holland` sub-object:
- `front_pin_visible`: yes/no — is the front-face pin assembly in the frame?
- `front_pin_position`: retracted (pin recessed into plate body) / extended (pin protruding) / not_visible.
- `washer_flush_against_body`: yes (washer sits flush against casting) / no (washer proud of casting) / unclear / not_visible.

If `fifth_wheel_manufacturer: "fontaine"` — populate `fontaine` sub-object:
- `side_pin_visible`: yes/no.
- `side_pin_position`: retracted / extended / not_visible.
- `side_handle_visible`: yes/no.
- `side_handle_position`: retracted / extended / not_clearly_visible.

If `fifth_wheel_manufacturer: "jost"` — populate `jost` sub-object:
- `center_release_strap_visible`: yes/no — is the center strap/pull-cord visible from this angle?
- `side_handle_visible`: yes/no.
- `side_handle_position`: retracted / extended / not_clearly_visible. **Default to `not_clearly_visible` for Jost — the side handle's state is genuinely hard to read from a side angle.**

If `fifth_wheel_manufacturer` is `other`, `unclear`, or `not_visible` — set `holland`, `fontaine`, AND `jost` all to `null`. Do not populate any sub-object.

**Image quality:**
- `image_quality`: good / acceptable / poor.

You will emit a single JSON object conforming exactly to this schema:

{_FIFTH_WHEEL_COUPLING_SCHEMA}

Rules:
- Set `evidence_type` to `"side_view"`. Populate the `side_view` sub-object. Set `lock_jaws_underneath` to `null`.
- `verdict`: emit the literal `"describe_only"`. `issues_detected`: `[]`.
- `factual_summary`: 2–3 factual sentences describing the apron, the plate, the visible hardware, the lighting. Do not use judgment words ("pass", "fail", "safe", "unsafe", "correct", "missing", "high hook").
- Default to `unclear` or `not_visible` when you cannot tell. Do not guess manufacturer.
- Never populate two manufacturer sub-objects. Never populate one that contradicts `fifth_wheel_manufacturer`.

Emit ONLY the JSON object. No preamble, no prose, no markdown fence. Start with `{{` and end with `}}`.

Examples of valid outputs:

Holland identified, engaged:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Side view of the coupling in daylight. The trailer apron is flush against the fifth-wheel plate. A pin assembly is visible on the front face of the plate with the pin retracted and the washer flush against the casting body.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"holland","holland":{{"front_pin_visible":"yes","front_pin_position":"retracted","washer_flush_against_body":"yes"}},"fontaine":null,"jost":null}},"lock_jaws_underneath":null}}

Fontaine identified (side pin disambiguates from Jost):
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Side view of the coupling. The trailer apron is flush with the plate. A side-mounted release handle is visible on the plate housing, and a secondary side pin is present and retracted, identifying the unit as Fontaine.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"fontaine","holland":null,"fontaine":{{"side_pin_visible":"yes","side_pin_position":"retracted","side_handle_visible":"yes","side_handle_position":"retracted"}},"jost":null}},"lock_jaws_underneath":null}}

Jost identified (no side pin, center strap):
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"acceptable","verdict":"describe_only","issues_detected":[],"factual_summary":"Side view of the coupling. The trailer apron contacts the plate. A side handle is visible on the plate housing with no secondary side pin; a release strap hangs from the center underside of the plate, identifying the unit as Jost. The handle's seated state is not clearly resolvable from this angle.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"jost","holland":null,"fontaine":null,"jost":{{"center_release_strap_visible":"yes","side_handle_visible":"yes","side_handle_position":"not_clearly_visible"}}}},"lock_jaws_underneath":null}}

Manufacturer not determinable, hardware partially out of frame:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"acceptable","verdict":"describe_only","issues_detected":[],"factual_summary":"Side view of the coupling area. The trailer apron is flush with the plate, but the side of the plate where the release hardware would sit is partially out of frame and cannot be assessed.","side_view":{{"trailer_seated_flush":"yes","gap_between_apron_and_plate":"none","fifth_wheel_manufacturer":"unclear","holland":null,"fontaine":null,"jost":null}},"lock_jaws_underneath":null}}

Dark, hardware not visible:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"side_view","image_quality":"poor","verdict":"describe_only","issues_detected":[],"factual_summary":"Side view taken in low light. The apron-to-plate contact line is in shadow and no release hardware is resolvable.","side_view":{{"trailer_seated_flush":"unclear","gap_between_apron_and_plate":"not_visible","fifth_wheel_manufacturer":"not_visible","holland":null,"fontaine":null,"jost":null}},"lock_jaws_underneath":null}}
"""


LOCK_JAWS_UNDERNEATH_PROMPT = f"""You are describing a commercial truck fifth-wheel coupling photo for a fleet documentation system. The image is taken from under the trailer, looking up at the underside of the fifth-wheel plate — you'll typically see the locking jaws (or single-bar) mechanism and possibly the kingpin shank passing down through the plate.

**Spatial prior (important):** the image you are about to see has been pre-cropped to a horizontal band just below the top edge of the fifth-wheel plate, where the locking mechanism sits. Focus your description on this region — that's where the mechanism is.

**What you are looking for:**
- A **two-jaw mechanism** appears as a pair of curved metal fingers (jaws) that wrap around a central vertical kingpin from both sides, forming a closed ring when engaged. From below, you see the two jaws meeting around the kingpin.
- A **single-bar mechanism** appears as a single straight horizontal bar positioned in front of the kingpin (between the kingpin and the rear of the tractor). When engaged, the bar sits across the front face of the kingpin, blocking it from moving forward and out.
- If neither pattern is visible — if you see only grease, shadow, or unidentified hardware — `fifth_wheel_variant: "unclear"` is the correct answer.

Your job is to describe what you see. You are NOT evaluating safety. You are NOT identifying failures. You are populating observation fields based on visual evidence only.

Close-up photos of this area are often taken at awkward angles in low light with grease and dirt present. That is normal. Do not interpret normal field conditions as failures. Grease and dirt by themselves do NOT make image_quality poor — only call image_quality poor if the features you need to observe are actually obscured.

**Do not attempt to identify the fifth-wheel manufacturer (Fontaine/Jost/Holland) from this view.** Manufacturer identification is side-view-only. From underneath, only the mechanism variant (two-jaw vs single-bar) is reliably visible — and these two variants are orthogonal to manufacturer.

The two fifth-wheel mechanism variants:

1. **Two-jaw** — two metal jaws that close around the kingpin from both sides, wrapping it. When engaged, the jaws form a closed ring around the kingpin shank.
2. **Single-bar** — a single straight horizontal bar that slides forward in front of the kingpin to lock it. When engaged, the bar sits across the front face of the kingpin.

Look at the image carefully and report:

- `fifth_wheel_variant`: `two_jaw`, `single_bar`, or `unclear`. **`unclear` is the catch-all for "I can't identify the mechanism" — use it whenever the hardware is occluded, the photo is of a different area, or the geometry is ambiguous.** This field does NOT accept `not_visible`.
- `two_jaw_state`: If you identified a two-jaw mechanism, its state — fully_closed / partially_open / open / not_visible. If this is a single-bar mechanism (or unclear), set to `not_applicable`.
- `single_bar_state`: If you identified a single-bar mechanism, its state — engaged_in_front_of_kingpin / retracted / not_visible. If this is a two-jaw mechanism (or unclear), set to `not_applicable`.
- `kingpin_visible`: yes/no — is the kingpin shank itself visible?
- `image_quality`: good / acceptable / poor.

You will emit a single JSON object conforming exactly to this schema:

{_FIFTH_WHEEL_COUPLING_SCHEMA}

Rules:
- Set `evidence_type` to `"lock_jaws_underneath"`. Populate the `lock_jaws_underneath` sub-object. Set `side_view` to `null`.
- `verdict`: `"describe_only"`. `issues_detected`: `[]`.
- `factual_summary`: 1–2 factual sentences. No judgment language.
- Do not invent a kingpin if you can't clearly see one — use `kingpin_visible: "no"`.
- If you identify a two-jaw mechanism, `single_bar_state` must be `not_applicable` (and vice versa). If `fifth_wheel_variant` is `unclear`, both states should be `not_applicable`.

Emit ONLY the JSON object. No preamble, no markdown fence.

Examples of valid outputs:

Two-jaw fully closed around visible kingpin:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"lock_jaws_underneath","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Close-up of the locking jaws taken from underneath the trailer. Two jaws are visibly closed around the kingpin shank.","side_view":null,"lock_jaws_underneath":{{"fifth_wheel_variant":"two_jaw","two_jaw_state":"fully_closed","single_bar_state":"not_applicable","kingpin_visible":"yes"}}}}

Single-bar mechanism, bar across front of kingpin:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"lock_jaws_underneath","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Underneath view of the fifth wheel. A single horizontal bar is visible engaged across the front face of the kingpin.","side_view":null,"lock_jaws_underneath":{{"fifth_wheel_variant":"single_bar","two_jaw_state":"not_applicable","single_bar_state":"engaged_in_front_of_kingpin","kingpin_visible":"yes"}}}}

Dark, occluded — can't identify mechanism:
{{"inspection_type":"fifth_wheel_coupling","evidence_type":"lock_jaws_underneath","image_quality":"poor","verdict":"describe_only","issues_detected":[],"factual_summary":"Underneath shot in deep shadow with grease covering the visible metal. The mechanism geometry is not resolvable in this lighting.","side_view":null,"lock_jaws_underneath":{{"fifth_wheel_variant":"unclear","two_jaw_state":"not_applicable","single_bar_state":"not_applicable","kingpin_visible":"no"}}}}
"""


REAR_ASSEMBLY_PROMPT = f"""You are describing a commercial truck pintle-hook coupling photo for a fleet documentation system. The image shows the pintle hook at the rear of a tractor connecting to a trailer (or dolly).

Your job is to describe what you see. You are NOT evaluating safety. You are NOT identifying failures.

────────────────────────────────────────────────────────────
**SAFETY PIN VISIBILITY — answer this BEFORE any other field.**
────────────────────────────────────────────────────────────

The safety pin is a small cylindrical pin or bolt — typically 1/4" to 1/2" in diameter, several inches long — that passes through a hole in the upper part of the latch mechanism, locking the latch closed. It is usually oriented horizontally, perpendicular to the hook's vertical axis. It often has a small ring, lanyard, or cotter clip on one end. The pin sits in a hole in the latch; from a typical phone-camera distance of 2–6 feet, it appears as a short horizontal cylinder protruding a fraction of an inch from each side of the latch body.

**Visual signature to look for:** a small horizontal cylinder, bolt-head, or pin protruding through the latch mechanism. Even if you can only see one end of the pin (the side facing the camera), that counts as visible.

**Do not default to reporting the safety pin as absent.** Phone photos taken from a few feet back rarely resolve the pin sharply, but the pin is typically present on a working coupling. If you can see ANY indication that a pin is through the latch — a protruding nub, a bolt-head shape, an interruption in the latch's silhouette where a pin would sit, a hint of a lanyard — report `safety_pin_visible: true` and note the uncertainty in `factual_summary`.

Only report `safety_pin_visible: false` when the latch hole is clearly visible AND clearly empty — you can see through it or see a clean unbroken latch surface with no horizontal pin element. If you are uncertain, the answer is `true`.

Commit to `safety_pin_visible` first. Then move on to the other fields.

────────────────────────────────────────────────────────────

A pintle hook in working condition has several small components that may be hard to see in a phone photo: a hook, a latch on top of the hook, a safety pin through the latch, the lunette ring of the towed unit, and two safety chains running between tractor and trailer. Small components may be present in the image but hard to resolve at typical phone-photo distance. Describe what is visible. If something is small and hard to see, say so — do not default to calling it absent.

After committing to `safety_pin_visible`, report:

- Whether the hook itself is visible.
- The position of the hook latch (closed / open / unclear / not_visible).
- Whether the lunette ring (the round eye on the towed unit that the hook captures) is visible.
- How many safety chains are visible — 0, 1, 2, more_than_two, or not_visible. Count carefully; chains may overlap.
- Whether visible chains appear crossed beneath the coupling (forming an X).
- Image quality (good / acceptable / poor).

You will emit a single JSON object conforming exactly to this schema:

{_PINTLE_HOOK_SCHEMA}

Rules:
- Set `inspection_type` to `"pintle_hook"` and `evidence_type` to `"rear_assembly"`. Populate the `rear_assembly` sub-object.
- `verdict`: `"describe_only"`. `issues_detected`: `[]`. `factual_summary`: 2–3 factual sentences.
- Do not use judgment language ("pass", "fail", "safe", "unsafe", "missing", "wrong", etc.).

Emit ONLY the JSON object. No preamble, no markdown fence.

Examples of valid outputs:

Daylight, all components visible:
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Daylight photo of the pintle hook area showing the closed hook latch with a safety pin inserted. The lunette ring is captured in the hook. Two safety chains are visible, both attached to the receiver crossmember and crossing beneath the coupling.","rear_assembly":{{"hook_visible":"yes","hook_latch_state":"closed","safety_pin_visible":true,"lunette_ring_visible":"yes","safety_chains_count":2,"safety_chains_crossed":"yes"}}}}

Pin area hard to resolve — commit to true per the rule:
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"acceptable","verdict":"describe_only","issues_detected":[],"factual_summary":"Photo of the pintle hook from a few feet back. The hook latch is closed and the lunette ring is engaged. The pin area is small in this frame; a pin appears to be present but is not sharply resolved. Two safety chains are visible, both hooked and crossing.","rear_assembly":{{"hook_visible":"yes","hook_latch_state":"closed","safety_pin_visible":true,"lunette_ring_visible":"yes","safety_chains_count":2,"safety_chains_crossed":"yes"}}}}

One chain visible, latch open:
{{"inspection_type":"pintle_hook","evidence_type":"rear_assembly","image_quality":"good","verdict":"describe_only","issues_detected":[],"factual_summary":"Close-up of the pintle hook with the latch in the raised open position. The lunette ring is visible. One safety chain is visible; the second is not in frame.","rear_assembly":{{"hook_visible":"yes","hook_latch_state":"open","safety_pin_visible":false,"lunette_ring_visible":"yes","safety_chains_count":1,"safety_chains_crossed":"no"}}}}
"""


EVIDENCE_CONFIG: dict[str, tuple[str, str, str]] = {
    "fifth_wheel": ("fifth_wheel_coupling", "side_view", SIDE_VIEW_PROMPT),
    "lock_jaws": ("fifth_wheel_coupling", "lock_jaws_underneath", LOCK_JAWS_UNDERNEATH_PROMPT),
    "pintle_hook": ("pintle_hook", "rear_assembly", REAR_ASSEMBLY_PROMPT),
}
