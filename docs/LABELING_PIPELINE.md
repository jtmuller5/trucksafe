# Labeling Pipeline Brief — GPU Rig

> Target: a coding agent on the GPU rig (2x RTX 5090s, Ubuntu, repo cloned at `~/projects/trucksafe/`, `uv` installed). The user has already downloaded Gemma 4 31B weights to the rig and synced ~7,500 truck inspection images organized by category.
>
> Goal: stand up a vLLM-served Gemma 4 31B labeler with three category-specific system prompts, then run a 30-image-per-category audit batch (90 total) for the user to manually review. Do not label at scale. Do not run any further batches. Stop and report after the audit batch.

---

## Context

This is the trucking safety hackathon project (`trucksafe`, Gemma 4 Impact Challenge, deadline May 18, 2026). The fine-tune that will eventually run on Android phones needs training labels — structured JSON output, one per image, conforming to category-specific schemas already locked in `shared/schemas/`. Those labels come from a larger model (Gemma 4 31B) served on this rig via vLLM and applied to the synced inspection images.

This task does NOT train anything. It builds and validates the labeler.

The user already has:
- ~7,500 inspection images at `~/projects/trucksafe/training/data/images/sample-batch-01/` in three category folders (`fifth_wheel/`, `lock_jaws/`, `pintle_hook/`), roughly 2,500 each
- Gemma 4 31B instruction-tuned weights downloaded somewhere on the rig
- A Python project at `~/projects/trucksafe/training/` managed with `uv`, with Pydantic schemas at `training/src/trucksafe_training/schemas.py` and JSON Schemas at `shared/schemas/`
- Two 5090 GPUs available, 32GB VRAM each

Three image categories, each with its own schema and pass criteria. See `shared/schemas/*.json` for the canonical schema definitions — do not redefine them, derive from those files.

---

## Constraints, hard

- **Don't train anything.** Don't run Unsloth, don't touch the E4B model. This task is about the 31B labeler only.
- **Don't run the at-scale label job.** Audit batch is 30 images per category = 90 total. Stop there. Do not even *write* the at-scale runner; that's a separate later task.
- **Don't pull the audit images into training/validation/test splits yet.** They're for audit only. The user will decide how to incorporate them after reviewing the labels.
- **Don't commit images, labels, model weights, or vLLM logs to git.** The repo's `.gitignore` covers `training/data/`, but be defensive: never `git add` anything under that path.
- **Don't add Python deps to `pyproject.toml` without flagging them in the report.** This task will add several heavy ones (`vllm`, `httpx`, `pydantic` is already there). Note each one and why.
- **vLLM gets both 5090s via tensor parallelism.** The user has explicitly requested this. Use `--tensor-parallel-size 2`.
- **System prompts go in `training/src/trucksafe_training/labeling/prompts.py` as Python string constants** — one per category, named `FIFTH_WHEEL_SYSTEM_PROMPT`, `LOCK_JAWS_SYSTEM_PROMPT`, `PINTLE_HOOK_SYSTEM_PROMPT`. The prompts are the highest-value artifact in this task; treat them as the deliverable, not boilerplate.

## Constraints, soft

- The user prefers `uv add` over manual edits to `pyproject.toml`.
- The user dislikes patronizing comments and overly defensive error handling. Catch the errors that matter (bad JSON output, model refusal, timeout); let unexpected exceptions surface with stack traces.
- Keep prompts in plain text strings in the Python file, not in a separate YAML/JSON file. The simpler the location, the easier to iterate.

---

## Step 1 — Confirm prerequisites

Before doing anything else:

1. Ask the user for the absolute path to the Gemma 4 31B weights on the rig. (Likely under `~/models/` or `~/.cache/huggingface/`, but don't guess.)
2. Confirm both 5090s are visible: `nvidia-smi` should show two devices.
3. Confirm the image batch exists and counts roughly match expectations:
   ```bash
   for cat in fifth_wheel lock_jaws pintle_hook; do
     echo -n "$cat: "
     find ~/projects/trucksafe/training/data/images/sample-batch-01/$cat -type f | wc -l
   done
   ```
4. Confirm the schemas exist at `shared/schemas/*.json` and the Pydantic mirrors exist at `training/src/trucksafe_training/schemas.py`. If they don't, stop and report — the earlier setup task should have produced them.

---

## Step 2 — Set up vLLM

Add `vllm` to the training project's deps:

```bash
cd ~/projects/trucksafe/training
uv add vllm
```

vLLM has nontrivial CUDA/PyTorch version constraints. If `uv add` fails or pins something incompatible, stop and report — don't try to force it.

Confirm install:

```bash
uv run python -c "import vllm; print(vllm.__version__)"
```

---

## Step 3 — Serve Gemma 4 31B with vLLM

Create a launch script at `training/scripts/serve_labeler.sh`:

```bash
#!/usr/bin/env bash
# Serve Gemma 4 31B for labeling via vLLM's OpenAI-compatible endpoint.
# Tensor-parallel across both 5090s.

set -euo pipefail

MODEL_PATH="${MODEL_PATH:-PUT_PATH_HERE}"  # User confirms this
PORT="${PORT:-8000}"

cd "$(dirname "$0")/.."

uv run python -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_PATH" \
  --tensor-parallel-size 2 \
  --port "$PORT" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --served-model-name gemma-4-31b-labeler
```

Make it executable. Replace `PUT_PATH_HERE` with the actual model path from Step 1.

Do NOT launch it in this task. Print the command for the user to run in a separate terminal, since vLLM is long-running and you don't want the agent's shell holding it. Instead, **the user will start the server, then signal you to proceed**.

Pause here and ask the user to run the script. Confirm vLLM is reachable:

```bash
curl http://localhost:8000/v1/models
```

If the response lists `gemma-4-31b-labeler`, proceed. If not, debug with the user — common issues: model path wrong, OOM (lower `--gpu-memory-utilization`), tensor parallel size mismatch with model architecture, vLLM version doesn't support Gemma 4 yet.

**If vLLM doesn't support Gemma 4 yet:** stop and report. The fallback options are running 31B via transformers directly (slower, no batching) or falling back to Gemma 4 26B if smaller works better. Both are user decisions, not agent decisions.

---

## Step 4 — Write the three system prompts

This is the most important part of the task. The system prompts shape every label and therefore every training example downstream. They go in `training/src/trucksafe_training/labeling/prompts.py`.

Each prompt has the same structure:
1. **Role statement** — what the model is doing and why it matters
2. **The schema** — embedded JSON Schema for the category
3. **The pass criteria** — plain-English rules for what counts as pass/fail for each observation
4. **Output instructions** — emit only valid JSON conforming to the schema, no prose preamble
5. **Calibration guidance** — when to use `confidence: low` or `overall_status: retake`

Each prompt should also include 2–3 concrete examples (few-shot) of correct outputs for the category. The examples matter more than the rules for getting the JSON shape consistently right.

The prompts below are the *starting drafts*. They will need iteration after the audit — that's expected and is exactly why we're doing the audit batch.

### `FIFTH_WHEEL_SYSTEM_PROMPT`

```python
FIFTH_WHEEL_SYSTEM_PROMPT = """You are inspecting a commercial truck coupling for a fleet safety system. The image you are about to see is a side view of a tractor-trailer fifth wheel coupling. Your job is to determine whether the trailer is fully and correctly seated against the fifth wheel plate.

A safe coupling means:
- The trailer apron sits flush against the fifth wheel plate with no visible daylight between them
- The release handle is in its stowed (in) position
- The trailer is not tilted on the plate (no gap on one side and contact on the other)

A common dangerous failure mode is "high hook" or "high pin": the kingpin sits on top of the closed locking jaws rather than being captured by them, producing a visible gap between trailer apron and fifth wheel plate. The trailer feels coupled but will dislodge under highway loads.

You will emit a single JSON object conforming exactly to this schema:

{SCHEMA_HERE — paste the contents of shared/schemas/fifth_wheel_side_view.json inline}

Rules for populating the fields:
- `trailer_seated_flush`: "yes" if the apron is in full contact with the plate across its visible width. "no" if there is any visible gap. "unclear" if the angle, lighting, or framing makes the contact line not visible.
- `visible_gap_between_apron_and_plate`: "none" if no daylight is visible between apron and plate. "minor" if a thin gap is visible but the trailer is mostly resting on the plate. "obvious" if there is a clear separation, including high-hook failures.
- `release_handle_position`: "stowed" if the handle is pushed in / against the housing. "extended" if pulled out. "unclear" if not visible in the frame.
- `image_quality`: "good" if you can clearly see the apron/plate contact line and the handle area. "poor" if motion blur, darkness, or occlusion prevents reliable judgment.
- `overall_status`: "pass" only if `trailer_seated_flush` is "yes" AND `visible_gap_between_apron_and_plate` is "none" AND `release_handle_position` is "stowed". "fail" if any of those is wrong. "retake" if `image_quality` is "poor" or any field is "unclear".
- `confidence`: "high" if you are certain of every observation. "medium" if minor ambiguity. "low" if you had to infer details that aren't clearly visible.
- `issues_detected`: short strings naming any failures (e.g., "obvious_gap_between_apron_and_plate", "release_handle_extended"). Empty array if pass.
- `human_readable_summary`: 1–2 sentences in plain English describing what you observe. Speak factually about the image, not about the regulation.

Emit ONLY the JSON object. No preamble, no prose, no markdown fence. Start your response with `{` and end with `}`.

Examples of valid outputs:

Pass:
{"category":"fifth_wheel_side_view","observations":{"trailer_seated_flush":"yes","visible_gap_between_apron_and_plate":"none","release_handle_position":"stowed","image_quality":"good"},"issues_detected":[],"overall_status":"pass","confidence":"high","human_readable_summary":"Trailer apron is flush against the fifth wheel plate with no visible gap. Release handle is stowed."}

Fail (high hook):
{"category":"fifth_wheel_side_view","observations":{"trailer_seated_flush":"no","visible_gap_between_apron_and_plate":"obvious","release_handle_position":"stowed","image_quality":"good"},"issues_detected":["obvious_gap_between_apron_and_plate","high_hook_suspected"],"overall_status":"fail","confidence":"high","human_readable_summary":"Clear gap visible between the trailer apron and the fifth wheel plate; the trailer appears to be sitting on top of the locking jaws rather than seated into them."}

Retake (ambiguous):
{"category":"fifth_wheel_side_view","observations":{"trailer_seated_flush":"unclear","visible_gap_between_apron_and_plate":"minor","release_handle_position":"unclear","image_quality":"poor"},"issues_detected":[],"overall_status":"retake","confidence":"low","human_readable_summary":"Image is taken at a low angle in shadow; cannot reliably determine whether the apron is flush with the plate or the position of the release handle."}
"""
```

### `LOCK_JAWS_SYSTEM_PROMPT`

```python
LOCK_JAWS_SYSTEM_PROMPT = """You are inspecting a commercial truck coupling for a fleet safety system. The image you are about to see is a close-up view of the locking jaws of a fifth wheel coupling. Your job is to determine whether the locking jaws have fully closed around the kingpin shank.

A safe coupling means:
- The locking jaws are fully closed around the kingpin
- The kingpin is captured between the jaws, not in front of or behind them
- If a lock indicator is visible, it shows the locked position

A common dangerous failure mode is the jaws appearing closed but with the kingpin sitting outside their grasp — the "high hook" or "missed kingpin" failure. The tug test alone can pass with the jaws in a partially-closed state; only this visual check confirms safe coupling.

You will emit a single JSON object conforming exactly to this schema:

{SCHEMA_HERE — paste the contents of shared/schemas/lock_jaws_closeup.json inline}

Rules for populating the fields:
- `jaws_fully_closed_around_kingpin`: "yes" if the jaws are visibly closed and the kingpin is captured between them. "no" if the jaws are open, partially closed, or closed but the kingpin is not between them. "unclear" if the camera angle does not show the jaw position relative to the kingpin.
- `kingpin_visible_in_jaws`: true if the kingpin shank is visible between the jaws. false otherwise.
- `lock_indicator_position`: "locked" if a lock indicator is visible and shows locked. "unlocked" if visible and shows unlocked. "not_visible" if no indicator is in frame.
- `image_quality`: "good" if you can clearly see the jaws and kingpin. "poor" if motion blur, darkness, dirt, grease, or occlusion prevents reliable judgment.
- `overall_status`: "pass" only if `jaws_fully_closed_around_kingpin` is "yes" AND `kingpin_visible_in_jaws` is true AND (`lock_indicator_position` is "locked" OR "not_visible"). "fail" if any failure mode is present. "retake" if `image_quality` is "poor" or `jaws_fully_closed_around_kingpin` is "unclear".
- `confidence`: "high" if you are certain. "medium" if minor ambiguity. "low" if you had to infer.
- `issues_detected`: short strings naming failures (e.g., "jaws_not_closed", "kingpin_outside_jaws", "lock_indicator_unlocked"). Empty array if pass.
- `human_readable_summary`: 1–2 sentences in plain English.

Emit ONLY the JSON object. No preamble, no prose, no markdown fence.

Examples of valid outputs:

Pass:
{"category":"lock_jaws_closeup","observations":{"jaws_fully_closed_around_kingpin":"yes","kingpin_visible_in_jaws":true,"lock_indicator_position":"locked","image_quality":"good"},"issues_detected":[],"overall_status":"pass","confidence":"high","human_readable_summary":"Locking jaws are fully closed around the kingpin and the lock indicator shows the locked position."}

Fail (missed kingpin):
{"category":"lock_jaws_closeup","observations":{"jaws_fully_closed_around_kingpin":"no","kingpin_visible_in_jaws":true,"lock_indicator_position":"not_visible","image_quality":"good"},"issues_detected":["jaws_not_closed_around_kingpin","kingpin_outside_jaws"],"overall_status":"fail","confidence":"high","human_readable_summary":"Locking jaws are closed but the kingpin is sitting in front of them rather than captured between them."}

Retake (poor image):
{"category":"lock_jaws_closeup","observations":{"jaws_fully_closed_around_kingpin":"unclear","kingpin_visible_in_jaws":false,"lock_indicator_position":"not_visible","image_quality":"poor"},"issues_detected":[],"overall_status":"retake","confidence":"low","human_readable_summary":"Image is dark and the jaw area is occluded by grease and shadow; cannot determine jaw position."}
"""
```

### `PINTLE_HOOK_SYSTEM_PROMPT`

```python
PINTLE_HOOK_SYSTEM_PROMPT = """You are inspecting a commercial truck coupling for a fleet safety system. The image you are about to see shows the pintle hook coupling at the rear of a tractor connecting to a trailer. Your job is to verify three independent safety criteria from this single image:

1. The hook latch is fully closed
2. A safety pin is inserted through the latch hole, securing the latch
3. At least two safety chains are hooked to the receiver crossmember and crossed beneath the connection

Each criterion is independent. A closed hook does not excuse missing chains. Hooked chains do not excuse an open hook. Evaluate each separately.

You will emit a single JSON object conforming exactly to this schema:

{SCHEMA_HERE — paste the contents of shared/schemas/pintle_hook_and_chains.json inline}

Rules for populating the fields:
- `hook_latch_state`: "closed" if the latch is down/closed over the eye of the towed trailer. "open" if the latch is up/open. "unclear" if the angle hides the latch position.
- `safety_pin_visible`: true if a pin is visibly inserted through the latch hole (preventing the latch from being lifted). false if no pin is visible. If `hook_latch_state` is "open", this is still answered based on whether a pin is in the latch hole.
- `safety_chains_count`: integer count of safety chains visible in the image, regardless of whether they are hooked. Typically 0, 1, or 2.
- `safety_chains_hooked`: true only if ALL visible chains are hooked to the receiver crossmember. false if any chain is dangling. If `safety_chains_count` is 0, this is false.
- `safety_chains_crossed`: true if the hooked chains cross beneath the coupling (forming an X under the connection). false otherwise. If chains are not hooked, this is false.
- `image_quality`: "good" if you can see the hook, latch, pin area, and chain attachments. "poor" if any of those areas is occluded or unclear.
- `overall_status`: "pass" only if `hook_latch_state` is "closed" AND `safety_pin_visible` is true AND `safety_chains_count` >= 2 AND `safety_chains_hooked` is true AND `safety_chains_crossed` is true. "fail" if any of those is wrong. "retake" if `image_quality` is "poor" or `hook_latch_state` is "unclear".
- `confidence`: "high" if you are certain of every observation. "medium" if minor ambiguity on one observation. "low" if multiple observations had to be inferred.
- `issues_detected`: short strings naming each failed criterion (e.g., "hook_latch_open", "safety_pin_missing", "only_one_chain", "chains_unhooked", "chains_not_crossed"). Empty array if pass.
- `human_readable_summary`: 1–3 sentences in plain English describing the state of each criterion.

Emit ONLY the JSON object. No preamble, no prose, no markdown fence.

Examples of valid outputs:

Pass:
{"category":"pintle_hook_and_chains","observations":{"hook_latch_state":"closed","safety_pin_visible":true,"safety_chains_count":2,"safety_chains_hooked":true,"safety_chains_crossed":true,"image_quality":"good"},"issues_detected":[],"overall_status":"pass","confidence":"high","human_readable_summary":"Pintle hook latch is closed with safety pin inserted. Both safety chains are hooked to the receiver crossmember and crossed beneath the connection."}

Fail (multiple criteria):
{"category":"pintle_hook_and_chains","observations":{"hook_latch_state":"closed","safety_pin_visible":false,"safety_chains_count":2,"safety_chains_hooked":false,"safety_chains_crossed":false,"image_quality":"good"},"issues_detected":["safety_pin_missing","chains_unhooked"],"overall_status":"fail","confidence":"high","human_readable_summary":"Pintle hook latch is closed but the safety pin is not inserted. Both safety chains are present but dangling unhooked beside the receiver."}

Fail (open hook):
{"category":"pintle_hook_and_chains","observations":{"hook_latch_state":"open","safety_pin_visible":false,"safety_chains_count":2,"safety_chains_hooked":true,"safety_chains_crossed":true,"image_quality":"good"},"issues_detected":["hook_latch_open","safety_pin_missing"],"overall_status":"fail","confidence":"high","human_readable_summary":"The pintle hook latch is in the open position with no pin inserted. Safety chains are correctly hooked and crossed but the primary coupling is not secure."}
"""
```

**Important:** the `{SCHEMA_HERE — ...}` placeholders need to be replaced with the actual JSON Schema contents from `shared/schemas/`. Do this in `prompts.py` by reading the schema files at module import time:

```python
import json
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "shared" / "schemas"

_FIFTH_WHEEL_SCHEMA = json.dumps(json.loads((SCHEMAS_DIR / "fifth_wheel_side_view.json").read_text()), indent=2)
_LOCK_JAWS_SCHEMA = json.dumps(json.loads((SCHEMAS_DIR / "lock_jaws_closeup.json").read_text()), indent=2)
_PINTLE_HOOK_SCHEMA = json.dumps(json.loads((SCHEMAS_DIR / "pintle_hook_and_chains.json").read_text()), indent=2)

FIFTH_WHEEL_SYSTEM_PROMPT = """... {schema} ...""".format(schema=_FIFTH_WHEEL_SCHEMA)
# etc.
```

Adjust path navigation as needed based on actual repo layout.

---

## Step 5 — Build the labeling script

Create `training/src/trucksafe_training/labeling/run_labeler.py`. Responsibilities:

1. Take CLI args: `--category` (fifth_wheel | lock_jaws | pintle_hook | all), `--input-dir`, `--output-dir`, `--count` (samples per category), `--seed`, `--endpoint` (defaults to `http://localhost:8000/v1`).
2. For each category requested:
   - Enumerate images in `{input-dir}/{category}/`
   - Deterministically sample `count` images using the seed
   - For each sampled image: encode as base64, call the vLLM `/v1/chat/completions` endpoint with the appropriate system prompt + the image, parse the response as JSON, validate against the Pydantic schema, write the result to `{output-dir}/{category}/{image_basename}.json`
3. Track failure modes and write a summary log at `{output-dir}/audit_log.json`:
   - Total images attempted per category
   - Successful labels (schema-valid JSON)
   - JSON parse failures (with first 200 chars of bad output)
   - Schema validation failures (with the validation error)
   - Model refusals (responses that look like "I cannot..." or empty content)
   - Timeouts / connection errors

4. Be polite about rate: serial requests are fine for 90 images; don't try to parallelize this. Each image is probably 10-30 seconds of inference on 31B.

5. Use `httpx` (already a dep). vLLM speaks the OpenAI chat completions format, so the request body looks like:

```python
{
    "model": "gemma-4-31b-labeler",
    "messages": [
        {"role": "system", "content": system_prompt_for_category},
        {"role": "user", "content": [
            {"type": "text", "text": "Inspect this image and emit the JSON label."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}
    ],
    "temperature": 0.0,
    "max_tokens": 800,
    "response_format": {"type": "json_object"}  # if vLLM supports it for Gemma 4; else omit
}
```

`temperature: 0.0` is important — we want deterministic labels for the same image given the same prompt. If you change anything about this default, flag it.

`response_format: json_object` enforces JSON output if vLLM/Gemma 4 supports the OpenAI-compatible JSON mode. If it doesn't, skip it; the prompts already instruct the model to emit only JSON, and the validator will catch failures.

For HEIC images (Apple phone default): convert to JPEG on-the-fly using Pillow + pillow-heif. Add the dep if needed and flag it. Don't modify the source images.

---

## Step 6 — Run the audit batch

Once Steps 1–5 are complete and the vLLM server is running:

```bash
cd ~/projects/trucksafe/training
uv run python -m trucksafe_training.labeling.run_labeler \
  --category all \
  --input-dir data/images/sample-batch-01 \
  --output-dir data/labels/audit-batch-01 \
  --count 30 \
  --seed 20260511 \
  --endpoint http://localhost:8000/v1
```

Expected: 90 labels written, audit log summarizing what worked and what didn't. Probably 15–45 minutes of wall clock depending on inference speed.

---

## Step 7 — Build the audit review aid

The user is going to look at every one of these 90 labels by hand. Make that easier.

Create `training/scripts/audit_review.py` — a small CLI tool that, for a given output dir, prints a tidy summary per image:

```
[1/30] fifth_wheel/IMG_2023_01_15_073012.jpg
  status: pass | confidence: high
  observations: trailer_seated_flush=yes, gap=none, release_handle=stowed, image_quality=good
  summary: "Trailer apron is flush against the fifth wheel plate..."
  issues: []

[2/30] fifth_wheel/IMG_2023_01_15_081244.jpg
  status: fail | confidence: high
  observations: trailer_seated_flush=no, gap=obvious, release_handle=stowed, image_quality=good
  summary: "Clear gap visible between..."
  issues: ['obvious_gap_between_apron_and_plate', 'high_hook_suspected']
```

Plus a one-line-per-image dense view that fits in a terminal for quick scrolling, and an option to open the image file with `open` (macOS) or `xdg-open` (Linux) for spot-checking. The user will be using this on the rig over SSH so include both modes.

Optional but high-value: dump an HTML page side-by-side with thumbnails, so the user can review on the MacBook by serving the directory or scp'ing the HTML out. If this is more than 30 minutes of work, skip it and let the user ask in a follow-up.

---

## Step 8 — Report back

When the audit batch is complete and the review tool is ready, report:

1. vLLM startup status (working / broken / Gemma 4 unsupported / OOM / other)
2. Audit batch counts:
   - Attempts per category
   - Schema-valid JSON outputs
   - JSON parse failures
   - Schema validation failures
   - Model refusals
3. Time elapsed for the labeling run
4. Path to the labels and audit log
5. How the user can run the review tool
6. Anything you noticed in the labels that looked off without auditing them in depth (e.g., "the model emitted `confidence: low` on 80% of pintle hook images — likely the prompt needs work")
7. Any deps you added (vllm, pillow-heif, etc.) so the user knows what landed in `pyproject.toml`

Stop. Do not start labeling at scale. Do not iterate on the prompts based on patterns you noticed — that's the user's call after their audit. Do not start fine-tune setup.

---

## What you should NOT do in this task

- Don't run the labeler against more than 30 images per category.
- Don't write the at-scale labeling job. That's a separate task after the audit is reviewed.
- Don't iterate on the system prompts after seeing initial outputs. Note your observations and let the user decide what to change.
- Don't try to "fix" labels that look wrong by re-prompting. The wrong labels ARE the data the user needs to see to evaluate the prompts.
- Don't download or convert all 7,500 images. Sample 30 per category, full stop.
- Don't commit the audit labels, the audit log, or any intermediate artifacts to git.
- Don't add `unsloth`, `peft`, or `transformers` for training. Those come later.
- Don't pre-compute splits, generate held-out sets, or organize anything for training. This task is purely about labeler validation.

---

## Open questions to ask the user inline

1. The absolute path to the Gemma 4 31B weights on the rig.
2. Whether the user wants the optional HTML review page (yes / no / "only if it's cheap").
3. Whether vLLM is already installed in the training env or needs adding (probably needs adding; just confirm before doing it).