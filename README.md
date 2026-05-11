# TruckSafe

An on-device AI safety inspector for commercial truck pre-trip coupling checks, built on a fine-tuned Gemma 4 E4B multimodal model running via LiteRT-LM.

Drivers walk a three-step inspection on their phone — fifth wheel side view, lock jaws close-up, pintle hook with safety chains — and the on-device model returns a structured JSON verdict per step. Fleet owners review submissions in a separate dashboard.

## Repo layout

```
training/    Python (uv) on the GPU rig — labeler + Unsloth LoRA fine-tune
mobile/      Flutter app — Android/iOS, LiteRT-LM on-device inference
dashboard/   Next.js fleet-owner review console (scaffolded later)
shared/      Canonical JSON Schemas consumed by both training and mobile
docs/        PRD, system architecture
in-transit/  Optional recorded-footage prototype (not started)
```

## Quickstart

### Training (GPU rig)

```bash
cd training
uv sync
uv run pytest
```

Heavy ML deps (`unsloth`, `transformers`, `vllm`, etc.) are intentionally not in `pyproject.toml` yet — they get added when the labeling pipeline is wired up, to avoid wedging `uv lock` on CUDA/torch pins.

### Mobile (MacBook)

The Flutter project hasn't been scaffolded yet. On the MacBook:

```bash
cd mobile
flutter create .
```

Then port the existing LiteRT-LM integration from Joe's sibling Flutter project into this directory.

### Dashboard

Deferred. The Next.js scaffold gets done in its own pass so it stays consistent with Joe's other Next.js project.

## Inspection schemas

The three JSON Schemas in `shared/schemas/` are the source of truth for the model's output format; the Pydantic mirrors in `training/src/trucksafe_training/schemas.py` are kept in sync by `tests/test_schemas.py`.

- `fifth_wheel_side_view` — trailer fully seated against the fifth wheel plate with no visible gap.
- `lock_jaws_closeup` — locking jaws fully closed around the kingpin shank.
- `pintle_hook_and_chains` — pintle hook closed, safety pin inserted, two safety chains hooked and crossed.

## Hackathon

Gemma 4 Impact Challenge — submission deadline 2026-05-18. Tracks: Global Resilience, Safety & Trust, LiteRT Special Tech.

## License

Apache 2.0.
