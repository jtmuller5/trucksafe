#!/usr/bin/env python3
"""Build the eval-set candidate pool: archive minus sample-batch-01, seed-sampled.

Stage 1 of the eval-set pipeline (see docs/eval_set.md). For each source folder
(fifth_wheel, lock_jaws, pintle_hook):
  1. Enumerate .jpg/.jpeg files in <archive>/<folder>/ (matching the
     extensions the v5.6 labeler can resolve via sample_images / _resolve_images_from_ids).
  2. Subtract image IDs (stems) present in <exclude>/<folder>/ (the existing
     training sample, sample-batch-01).
  3. Seeded random.shuffle the remainder using random.Random(f"{seed}:{folder}")
     to match sample_batch.py's per-category seeding pattern.
  4. Take the first --per-category (default 800) stems and write
     <out>/candidate_ids/<folder>/<stem>.json each containing
     {"image_id": "<stem>"}. This format is consumed by the v5.6 labeler's
     --image-ids-from option (see run_labeler_v5_6._load_image_ids_from_prior_audit).
  5. Append a Stage 1 entry to <out>/draw_log.json with per-folder counts.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg"}
SOURCE_FOLDERS = ("fifth_wheel", "lock_jaws", "pintle_hook")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def enumerate_stems(cat_dir: Path) -> list[str]:
    stems: list[str] = []
    if not cat_dir.is_dir():
        return stems
    for entry in os.scandir(cat_dir):
        if not entry.is_file():
            continue
        p = Path(entry.path)
        if p.suffix.lower() in IMAGE_EXTS:
            stems.append(p.stem)
    stems.sort()
    return stems


def write_stub(stub_path: Path, image_id: str) -> None:
    stub_path.write_text(json.dumps({"image_id": image_id}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path,
                    help="Full archive root, e.g. ~/projects/trucksafe/training/data/images/archive-v1")
    ap.add_argument("--exclude", required=True, type=Path,
                    help="Path to sample-batch-01 (or any prior sample) whose image stems must be excluded.")
    ap.add_argument("--out", required=True, type=Path,
                    help="Output dir under the repo, e.g. eval/eval_set_v1")
    ap.add_argument("--per-category", type=int, default=800)
    ap.add_argument("--seed", type=int, default=20260512)
    ap.add_argument("--categories", default=",".join(SOURCE_FOLDERS),
                    help="Comma-separated source folder names.")
    args = ap.parse_args()

    archive: Path = args.archive.expanduser().resolve()
    exclude: Path = args.exclude.expanduser().resolve()
    out: Path = args.out.expanduser().resolve()

    if not archive.is_dir():
        log(f"ERROR: archive dir does not exist: {archive}")
        return 2
    if not exclude.is_dir():
        log(f"ERROR: exclude dir does not exist: {exclude}")
        return 2

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    out.mkdir(parents=True, exist_ok=True)
    candidate_ids_root = out / "candidate_ids"
    if candidate_ids_root.exists() and any(candidate_ids_root.iterdir()):
        log(f"ERROR: candidate_ids dir is not empty: {candidate_ids_root}")
        log("Refusing to overwrite a prior draw. Remove the dir if you really mean to redo.")
        return 2
    candidate_ids_root.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    per_folder: dict[str, dict[str, int]] = {}

    for folder in categories:
        archive_dir = archive / folder
        exclude_dir = exclude / folder

        archive_stems = enumerate_stems(archive_dir)
        exclude_stems = set(enumerate_stems(exclude_dir))
        eligible = [s for s in archive_stems if s not in exclude_stems]

        if len(eligible) < args.per_category:
            log(
                f"ERROR: {folder}: only {len(eligible)} eligible after excluding "
                f"sample-batch-01; need {args.per_category}. Aborting."
            )
            return 3

        rng = random.Random(f"{args.seed}:{folder}")
        indices = list(range(len(eligible)))
        rng.shuffle(indices)
        picked = [eligible[i] for i in indices[: args.per_category]]
        picked.sort()  # deterministic on-disk order; identity preserved in draw_log

        folder_out = candidate_ids_root / folder
        folder_out.mkdir(parents=True, exist_ok=True)
        for stem in picked:
            write_stub(folder_out / f"{stem}.json", stem)

        per_folder[folder] = {
            "archive_total": len(archive_stems),
            "excluded_in_sample_batch_01": len(set(archive_stems) & exclude_stems),
            "eligible_after_exclusion": len(eligible),
            "candidate_pool_size": len(picked),
        }
        log(
            f"{folder}: archive={len(archive_stems)} "
            f"excluded={per_folder[folder]['excluded_in_sample_batch_01']} "
            f"eligible={len(eligible)} sampled={len(picked)}"
        )

    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    draw_log_path = out / "draw_log.json"
    if draw_log_path.exists():
        try:
            draw_log = json.loads(draw_log_path.read_text())
        except json.JSONDecodeError:
            draw_log = {}
    else:
        draw_log = {}
    draw_log["stage_1_candidate_pool"] = {
        "started_utc": started,
        "finished_utc": finished,
        "archive_root": str(archive),
        "exclude_root": str(exclude),
        "per_category_requested": args.per_category,
        "eval_draw_seed": args.seed,
        "categories": categories,
        "per_folder": per_folder,
    }
    draw_log_path.write_text(json.dumps(draw_log, indent=2, sort_keys=True) + "\n")
    log(f"wrote draw_log -> {draw_log_path}")
    log(f"candidate stubs at -> {candidate_ids_root}")

    print(json.dumps({
        "candidate_ids_dir": str(candidate_ids_root),
        "per_folder": per_folder,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
