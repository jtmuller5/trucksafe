"""System prompts for the Gemma 4 31B labeler.

TODO: the actual prompts are intentionally not committed yet — Joe wants to
iterate on them interactively against the live model. Each prompt should
constrain the model to emit JSON matching the corresponding schema in
`shared/schemas/`.
"""

from __future__ import annotations

FIFTH_WHEEL_SIDE_VIEW_PROMPT = ""  # TODO
LOCK_JAWS_CLOSEUP_PROMPT = ""  # TODO
PINTLE_HOOK_AND_CHAINS_PROMPT = ""  # TODO

PROMPTS_BY_CATEGORY: dict[str, str] = {
    "fifth_wheel_side_view": FIFTH_WHEEL_SIDE_VIEW_PROMPT,
    "lock_jaws_closeup": LOCK_JAWS_CLOSEUP_PROMPT,
    "pintle_hook_and_chains": PINTLE_HOOK_AND_CHAINS_PROMPT,
}
