# Setup Brief — GPU Rig Repo Initialization

> Target: a coding agent running on a GPU rig with 2x RTX 5090s, Ubuntu, `gh` CLI authenticated, `uv` installed. The user is on a MacBook and will pull the repo locally after you push it to GitHub.
>
> Goal of this task: stand up the project repository so all subsequent work (model fine-tuning, mobile app, fleet dashboard) lives in one coordinated codebase. Do not start training yet. Do not pull training images yet. The user will sync those after pulling the repo on the MacBook.
>
> The user is an experienced TypeScript developer who also writes Python for ML work. They prefer `uv` for Python, dislike unnecessary tooling layers, and like clean monorepos. Ask before adding any dependency or tool not listed below.

---

## Context

This project is a hackathon entry for the Gemma 4 Impact Challenge (Kaggle / Google DeepMind, deadline May 18, 2026). It builds an on-device AI safety inspector for commercial trucking pre-trip inspections. Three components live in this repo:

1. **`training/`** — Python project on the GPU rig. Fine-tunes Gemma 4 E4B with Unsloth LoRA on commercial truck coupling inspection photos. Three image categories: fifth wheel side view, lock jaws close-up, pintle hook + safety chains. Uses Gemma 4 31B served via vLLM on the same rig to generate structured-JSON training labels from photos.
2. **`mobile/`** — Flutter app targeting Android and iOS. Uses LiteRT-LM for on-device inference of the fine-tuned Gemma 4 E4B model. Drivers walk through a 3-step inspection checklist; the app captures a photo per step and the model returns structured JSON verifying each safety criterion.
3. **`dashboard/`** — Next.js/TypeScript web app for fleet owners to review completed inspections. Out of scope for the hackathon beyond a minimal version sufficient for the demo video.

There is a fourth, optional, lower-priority piece — `in-transit/` — for a recorded-footage prototype showing the same model annotating live coupling video. Stub the directory but don't build anything in it yet.

The user has a separate Flutter project where they already got Gemma 4 E4B working on LiteRT-LM. They will port that integration into `mobile/` themselves; you do not need to figure out LiteRT-LM from scratch. But do scaffold `mobile/` as a fresh `flutter create` project ready to receive that code.

---

## Constraints, hard

- **Do not push training data, image archives, or model weights to GitHub.** The training image archive is ~75k photos; weights are multi-GB. Add comprehensive `.gitignore` entries for these before the first commit.
- **Public repo from creation.** Hackathon rules require it. License: Apache 2.0.
- **`uv` for all Python.** No conda, no plain venv, no Poetry, no Pipenv. The `training/` project uses `uv` with a `pyproject.toml` and `uv.lock` checked in.
- **Single repo, three apps.** Do not split into multiple repos. Do not introduce a monorepo tool (Nx, Turborepo, etc.) — `pnpm` workspaces for the TypeScript side and uv for Python is plenty.
- **Don't install Flutter, Android SDK, Xcode tooling, or any mobile build chain on the rig.** The mobile project gets scaffolded with `flutter create` but actual builds happen on the user's MacBook. Just confirm `flutter` is on the rig's PATH if it's already there; if not, skip and note it for the MacBook setup.
- **Don't start training, don't download model weights, don't run the labeler.** This task is repo setup only. The training data isn't on the rig yet — the user will sync it after pulling the repo on the MacBook.
- **Ask before adding any dependency or tool not listed in this brief.**

## Constraints, soft

- The user dislikes patronizing comments in code and READMEs. Write the README like you're writing to a peer who already knows the basics.
- Keep folder structures shallow. The user prefers obvious file locations over deep hierarchies.
- The user types in Dvorak on a Moonlander keyboard — no impact on this task, just don't be surprised if their commits have unusual typos.

---

## Repo structure

Create at `~/projects/trucksafe/` on the GPU rig. (Open question for the user: confirm the project name. If they haven't specified one yet, default to `trucksafe` and they can rename later. Suggest 2-3 alternatives at the end of the task for them to pick from.)

```
trucksafe/
├── README.md                          # Project-level README (see below)
├── LICENSE                            # Apache 2.0
├── .gitignore                         # Comprehensive ignores — see below
├── .gitattributes                     # LFS pointers if anything needs LFS later
├── docs/
│   ├── prd.md                         # Placeholder — user will paste PRD here
│   └── architecture.md                # Placeholder for system-level architecture
├── training/                          # Python, GPU rig
│   ├── README.md                      # Training-specific instructions
│   ├── pyproject.toml                 # uv-managed, see deps below
│   ├── uv.lock
│   ├── .python-version                # 3.12 (verify what the rig has; bump if needed)
│   ├── src/trucksafe_training/
│   │   ├── __init__.py
│   │   ├── schemas.py                 # Pydantic models for the 3 inspection schemas
│   │   ├── labeling/
│   │   │   ├── __init__.py
│   │   │   ├── prompts.py             # System prompts for the 31B labeler, per category
│   │   │   └── run_labeler.py         # Stub: orchestrates vLLM-based label generation
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── load.py                # Stub: load image archive, parse submission metadata
│   │   │   └── split.py               # Stub: held-out eval split, stratified by truck/driver
│   │   ├── finetune/
│   │   │   ├── __init__.py
│   │   │   └── train.py               # Stub: Unsloth LoRA fine-tune entrypoint
│   │   ├── eval/
│   │   │   ├── __init__.py
│   │   │   └── compare.py             # Stub: side-by-side fine-tuned vs base
│   │   └── export/
│   │       ├── __init__.py
│   │       └── to_litert.py           # Stub: export fine-tuned model to .litertlm
│   ├── scripts/
│   │   └── (empty for now — sync scripts go here later)
│   └── tests/
│       └── test_schemas.py            # Tests for the schema definitions
├── mobile/                            # Flutter, builds on MacBook
│   └── (scaffold via `flutter create` once user confirms project name)
│       — note in the README that the Flutter scaffold is deferred to MacBook setup
├── dashboard/                         # Next.js / TypeScript
│   ├── README.md                      # Placeholder, scaffold later
│   └── (empty — will be initialized later when the user has bandwidth)
├── in-transit/
│   └── README.md                      # Placeholder noting this is the optional prototype
└── shared/
    └── schemas/                       # Schema definitions in a language-neutral place
        ├── fifth_wheel_side_view.json # JSON Schema for category 1
        ├── lock_jaws_closeup.json     # JSON Schema for category 2
        └── pintle_hook_and_chains.json# JSON Schema for category 3
```

A note on `shared/schemas/`: this is the canonical location for the three inspection schemas. Both the Python training code (`schemas.py`) and the Flutter mobile code will derive from these JSON Schema files so the schema isn't redefined in two places. For now, just create the JSON Schema files; the Python `schemas.py` should mirror them as Pydantic models.

---

## The three inspection schemas

These need to land verbatim in `shared/schemas/` as JSON Schema files. The fields and pass criteria are non-negotiable — the user has already locked these in via the PRD. Mirror them as Pydantic models in `training/src/trucksafe_training/schemas.py`.

### `fifth_wheel_side_view.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "FifthWheelSideView",
  "description": "Verifies the trailer is fully seated against the fifth wheel plate with no visible gap.",
  "type": "object",
  "required": ["category", "observations", "issues_detected", "overall_status", "confidence", "human_readable_summary"],
  "properties": {
    "category": { "const": "fifth_wheel_side_view" },
    "observations": {
      "type": "object",
      "required": ["trailer_seated_flush", "visible_gap_between_apron_and_plate", "release_handle_position", "image_quality"],
      "properties": {
        "trailer_seated_flush": { "enum": ["yes", "no", "unclear"] },
        "visible_gap_between_apron_and_plate": { "enum": ["none", "minor", "obvious"] },
        "release_handle_position": { "enum": ["stowed", "extended", "unclear"] },
        "image_quality": { "enum": ["good", "poor"] }
      }
    },
    "issues_detected": { "type": "array", "items": { "type": "string" } },
    "overall_status": { "enum": ["pass", "fail", "retake"] },
    "confidence": { "enum": ["high", "medium", "low"] },
    "human_readable_summary": { "type": "string", "maxLength": 500 }
  }
}
```

### `lock_jaws_closeup.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "LockJawsCloseup",
  "description": "Verifies the locking jaws have fully closed around the kingpin shank.",
  "type": "object",
  "required": ["category", "observations", "issues_detected", "overall_status", "confidence", "human_readable_summary"],
  "properties": {
    "category": { "const": "lock_jaws_closeup" },
    "observations": {
      "type": "object",
      "required": ["jaws_fully_closed_around_kingpin", "kingpin_visible_in_jaws", "lock_indicator_position", "image_quality"],
      "properties": {
        "jaws_fully_closed_around_kingpin": { "enum": ["yes", "no", "unclear"] },
        "kingpin_visible_in_jaws": { "type": "boolean" },
        "lock_indicator_position": { "enum": ["locked", "unlocked", "not_visible"] },
        "image_quality": { "enum": ["good", "poor"] }
      }
    },
    "issues_detected": { "type": "array", "items": { "type": "string" } },
    "overall_status": { "enum": ["pass", "fail", "retake"] },
    "confidence": { "enum": ["high", "medium", "low"] },
    "human_readable_summary": { "type": "string", "maxLength": 500 }
  }
}
```

### `pintle_hook_and_chains.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PintleHookAndChains",
  "description": "Verifies the pintle hook is closed, safety pin inserted, and at least two safety chains are hooked and crossed.",
  "type": "object",
  "required": ["category", "observations", "issues_detected", "overall_status", "confidence", "human_readable_summary"],
  "properties": {
    "category": { "const": "pintle_hook_and_chains" },
    "observations": {
      "type": "object",
      "required": ["hook_latch_state", "safety_pin_visible", "safety_chains_count", "safety_chains_hooked", "safety_chains_crossed", "image_quality"],
      "properties": {
        "hook_latch_state": { "enum": ["closed", "open", "unclear"] },
        "safety_pin_visible": { "type": "boolean" },
        "safety_chains_count": { "type": "integer", "minimum": 0 },
        "safety_chains_hooked": { "type": "boolean" },
        "safety_chains_crossed": { "type": "boolean" },
        "image_quality": { "enum": ["good", "poor"] }
      }
    },
    "issues_detected": { "type": "array", "items": { "type": "string" } },
    "overall_status": { "enum": ["pass", "fail", "retake"] },
    "confidence": { "enum": ["high", "medium", "low"] },
    "human_readable_summary": { "type": "string", "maxLength": 500 }
  }
}
```

---

## Python dependencies for `training/`

Initialize with `uv init --package` and set Python to whatever the rig has installed in the 3.11–3.12 range. Add these dependencies via `uv add`:

**Runtime:**
- `pydantic>=2.6` — for the schema mirrors
- `pillow` — image handling
- `httpx` — for calling vLLM's OpenAI-compatible endpoint
- `tqdm`
- `python-dotenv`

**Dev:**
- `pytest`
- `ruff`
- `mypy`

**Do not add yet** (these come when we actually start training; flag them as a TODO comment in `pyproject.toml`):
- `unsloth` — for LoRA fine-tuning
- `transformers`, `accelerate`, `peft`, `datasets`
- `vllm`
- `wandb` (open question — ask the user whether they want experiment tracking; if so, default to W&B, otherwise leave it out)

Reason for the staged approach: the heavy ML deps have specific CUDA/PyTorch version requirements and tend to break `uv lock` if added prematurely. Get the skeleton landed first, add them when the labeling pipeline is ready to run.

---

## `.gitignore`

Use the standard Python + Node + Flutter ignore set, plus these project-specific entries. Be aggressive — accidentally committing the image archive would be a disaster:

```
# Image data — never commit
/training/data/images/
/training/data/labels/
/training/data/splits/
*.jpg
*.jpeg
*.png
*.heic
*.heif
!docs/**/*.png
!docs/**/*.jpg
!shared/**/*.png
!mobile/**/*.png
!mobile/**/*.jpg

# Model weights — never commit
*.safetensors
*.bin
*.pt
*.ckpt
*.litertlm
*.gguf
/training/checkpoints/
/training/exports/

# Python
__pycache__/
*.py[cod]
.venv/
.uv/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Environment
.env
.env.local

# OS / editor
.DS_Store
.idea/
.vscode/
*.swp

# Flutter — placeholder, populate when scaffolded
/mobile/build/
/mobile/.dart_tool/
/mobile/.flutter-plugins
/mobile/.flutter-plugins-dependencies

# Node — placeholder, populate when scaffolded
node_modules/
.next/
dist/

# Logs / experiments
*.log
wandb/
```

---

## README at repo root

Keep it short — under 250 lines. Sections:

1. **One-paragraph project summary.** Use the language: "an on-device AI safety inspector for commercial truck pre-trip coupling checks, built on a fine-tuned Gemma 4 E4B multimodal model running via LiteRT-LM."
2. **Repo layout** — 5-line tree showing what's in each top-level directory.
3. **Quickstart per component** — three small sections, each with a code block:
   - Training (on GPU rig): `cd training && uv sync && uv run pytest`
   - Mobile (on MacBook): note that `flutter create` hasn't been run yet and that the user will scaffold it locally.
   - Dashboard: note it's deferred.
4. **Inspection schemas** — one-paragraph pointer to `shared/schemas/` with a single sentence per category.
5. **Hackathon submission status** — placeholder section: deadline May 18, 2026; tracks: Global Resilience, Safety & Trust, LiteRT Special Tech.
6. **License** — Apache 2.0.

No badges. No "Built with ❤️". No emoji headers.

---

## Tests to write

In `training/tests/test_schemas.py`:

1. For each of the three Pydantic schemas, a test that constructs a valid example and a test that rejects an obviously invalid example (wrong category, missing required field).
2. A test that loads each JSON Schema file from `shared/schemas/` and confirms it parses as valid JSON Schema.
3. A test confirming the Pydantic models and JSON Schema files agree on field names and enums — this is the contract between the Python training code and the eventual Flutter consumer.

Don't overdo it. Three tests per schema is plenty.

---

## Commit and push

After the setup is complete and `uv run pytest` passes:

1. `git init`, `git add .`, commit with message: `Initial repo scaffold: training/mobile/dashboard layout, three inspection schemas, README`
2. `gh repo create trucksafe --public --source=. --remote=origin --push` (substitute project name if user picks a different one)
3. Confirm the repo URL and report it back to the user.

---

## What you should NOT do in this task

- Don't try to download Gemma 4 weights. The user already has them from a separate project; they'll arrange the symlink or path.
- Don't try to set up vLLM. That comes in a later task once we know the rig's CUDA/torch versions are good.
- Don't write the labeling prompts beyond a `prompts.py` stub with a clear TODO. The labeling prompt is a sensitive piece of the pipeline and the user will iterate on it interactively.
- Don't scaffold the dashboard yet — it's the lowest-priority piece and the user will do it themselves to keep the Next.js/tRPC setup consistent with their other project.
- Don't `flutter create` on the rig. Scaffolding happens on the MacBook.
- Don't push placeholder images or weights, ever, regardless of size.

---

## Open questions for the user (ask at the end of the task)

1. **Project name.** Is `trucksafe` fine, or do they want something else? Suggest 2-3 alternatives.
2. **W&B or similar experiment tracking?** If yes, will the user supply credentials, or should we defer until first training run?
3. **Python version on the rig.** Confirm `python3 --version` and bump `.python-version` if 3.12 isn't available.
4. **Flutter version on the rig.** Worth a `flutter --version` check just for visibility; not blocking.

---

## When done, report back

A short summary listing:
- The GitHub repo URL
- The local path on the rig
- Anything you deviated from in this brief and why
- The four open questions above with whatever defaults you took if you proceeded without answers

Then stop. Do not start any training, labeling, or model-download work. The user will pull the repo on their MacBook, set up the image sync, and tell you when to proceed.