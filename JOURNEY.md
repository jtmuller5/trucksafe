# JOURNEY

Timeline of major blockers, wins, and findings. Append entries newest-at-the-bottom; one heading per entry with a date.

---

## 2026-05-11 — Initial repo scaffold

Stood up `~/projects/trucksafe/` on the GPU rig and pushed to https://github.com/jtmuller5/trucksafe (public, Apache 2.0).

- Three inspection schemas locked in at `shared/schemas/` plus Pydantic mirrors at `training/src/trucksafe_training/schemas.py`. Contract test in `training/tests/test_schemas.py` keeps the two in sync — 16 tests passing.
- `training/` initialized with `uv` on Python 3.12, light runtime deps only (`pydantic`, `pillow`, `httpx`, `tqdm`, `python-dotenv`) + dev (`pytest`, `ruff`, `mypy`). Heavy ML deps deferred — `unsloth`/`transformers`/`vllm` have CUDA/torch pins that wedge `uv lock` if added too early.
- `mobile/`, `dashboard/`, `in-transit/` left as placeholder READMEs. Flutter scaffold happens on the MacBook, not the rig.
- `.gitignore` is aggressive on images and weights to keep the ~75k-photo archive and multi-GB model files out of the repo by default.
