# training

Python package that runs on the GPU rig. Two pipelines live here:

1. **Labeler** — calls Gemma 4 31B via the local vLLM endpoint to generate structured-JSON labels from coupling inspection photos.
2. **Fine-tune** — Unsloth LoRA fine-tune of Gemma 4 E4B on the labeled photos, then exports to `.litertlm` for the mobile app.

## Setup

```bash
cd training
uv sync
uv run pytest
```

Python 3.12 is pinned via `.python-version`.

## Heavy ML deps

`unsloth`, `transformers`, `accelerate`, `peft`, `datasets`, `vllm` (and possibly `wandb`) are not in `pyproject.toml` yet — they have strict CUDA/PyTorch pins that tend to wedge `uv lock`. They get added when the labeling pipeline is wired up.

## Layout

```
src/trucksafe_training/
├── schemas.py          Pydantic mirrors of shared/schemas/*.json
├── labeling/           vLLM-driven label generation (stubs)
├── data/               image archive loaders + eval splits (stubs)
├── finetune/           Unsloth LoRA entrypoint (stub)
├── eval/               base-vs-fine-tuned comparison (stub)
└── export/             .litertlm export (stub)
```

## Data

The image archive (~75k photos) is never committed. It lives outside the repo and gets synced to the rig separately; see the `.gitignore` for the directories that are excluded.
