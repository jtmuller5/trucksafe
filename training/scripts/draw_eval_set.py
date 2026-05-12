#!/usr/bin/env python3
"""Draw the locked eval set from v5.6 candidate labels.

Stage 3 of the eval-set pipeline (see docs/eval_set.md). Assumes Stage 2 has
already run v5.6 over the candidate stubs from build_eval_candidates.py and
written per-image JSON to <labels-dir>/<folder>/*.json.

For each source folder:
  1. Read v5.6 label JSON files; keep only those where
     describe_output.photo_matches_category == "yes". Schema-validity is
     already implied by the labeler only writing JSON for final-valid
     records, but we also count missing-from-disk against the original
     candidate ids list so the draw_log captures every filter stage.
  2. Sort eligible stems for determinism, then seeded-sample 500 with
     random.Random(f"{final_seed}:{folder}").
  3. Abort if any folder has fewer than 500 eligible (per the brief — the
     candidate pool needs to grow, or we discuss accepting < 500).
  4. Copy the selected images from <archive> to <eval-dest>/<folder>/.
  5. Write manifest.json (1500 entries with full v5.6 label embedded),
     README.md, and finalize draw_log.json.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IMAGE_EXTS = (".jpg", ".jpeg")
SOURCE_FOLDERS = ("fifth_wheel", "lock_jaws", "pintle_hook")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def read_label(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def list_candidate_stems(candidate_ids_dir: Path, folder: str) -> list[str]:
    folder_dir = candidate_ids_dir / folder
    if not folder_dir.is_dir():
        return []
    return sorted(p.stem for p in folder_dir.glob("*.json"))


def find_image_in_archive(archive: Path, folder: str, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        candidate = archive / folder / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def git_sha(repo_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
        return out
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def git_dirty(repo_root: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        )
        return bool(out.strip())
    except (subprocess.CalledProcessError, OSError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path,
                    help="Eval-set repo dir, e.g. eval/eval_set_v1")
    ap.add_argument("--labels-dir", required=True, type=Path,
                    help="Where v5.6 candidate labels live, e.g. eval/eval_set_v1/v5_6_candidate_labels")
    ap.add_argument("--candidate-ids-dir", type=Path, default=None,
                    help="Stage 1 candidate stubs dir (default: <out>/candidate_ids)")
    ap.add_argument("--archive", required=True, type=Path,
                    help="Archive root, used to resolve and copy selected images.")
    ap.add_argument("--eval-dest", required=True, type=Path,
                    help="Destination for the locked eval images, e.g. ~/projects/trucksafe/training/data/images/eval-set-v1")
    ap.add_argument("--final-seed", default="20260512_final",
                    help="String seed for the per-folder draw (will be combined with folder name).")
    ap.add_argument("--per-category", type=int, default=500)
    ap.add_argument("--categories", default=",".join(SOURCE_FOLDERS))
    ap.add_argument("--labeler-version", default="v5.6")
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2],
                    help="Repo root, used for git SHA capture (default: derive from script path)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Filter and report only; do not copy images or write manifest.")
    args = ap.parse_args()

    out: Path = args.out.expanduser().resolve()
    labels_dir: Path = args.labels_dir.expanduser().resolve()
    candidate_ids_dir: Path = (
        args.candidate_ids_dir.expanduser().resolve()
        if args.candidate_ids_dir
        else out / "candidate_ids"
    )
    archive: Path = args.archive.expanduser().resolve()
    eval_dest: Path = args.eval_dest.expanduser().resolve()
    repo_root: Path = args.repo_root.resolve()

    if not labels_dir.is_dir():
        log(f"ERROR: labels-dir does not exist: {labels_dir}")
        return 2
    if not archive.is_dir():
        log(f"ERROR: archive does not exist: {archive}")
        return 2

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sha = git_sha(repo_root)
    dirty = git_dirty(repo_root)

    per_folder_stats: dict[str, dict[str, int]] = {}
    selected_per_folder: dict[str, list[dict[str, Any]]] = {}

    for folder in categories:
        candidate_stems = list_candidate_stems(candidate_ids_dir, folder)
        candidate_count = len(candidate_stems)

        label_dir = labels_dir / folder
        if not label_dir.is_dir():
            log(f"ERROR: {folder}: labels dir missing at {label_dir}")
            return 2

        # Load labels keyed by image_id
        labels_by_id: dict[str, dict[str, Any]] = {}
        invalid_or_unreadable = 0
        for p in sorted(label_dir.glob("*.json")):
            obj = read_label(p)
            if obj is None or "image_id" not in obj or "describe_output" not in obj:
                invalid_or_unreadable += 1
                continue
            labels_by_id[obj["image_id"]] = obj

        # Cross-check against candidate stubs
        missing_label = [s for s in candidate_stems if s not in labels_by_id]

        # Filter by photo_matches_category == yes on the describe pass
        eligible_records: list[dict[str, Any]] = []
        rejected_no = 0
        rejected_unclear = 0
        rejected_other = 0
        for stem in candidate_stems:
            rec = labels_by_id.get(stem)
            if rec is None:
                continue
            pmc = rec.get("describe_output", {}).get("photo_matches_category")
            if pmc == "yes":
                eligible_records.append(rec)
            elif pmc == "no":
                rejected_no += 1
            elif pmc == "unclear":
                rejected_unclear += 1
            else:
                rejected_other += 1

        eligible_records.sort(key=lambda r: r["image_id"])

        if len(eligible_records) < args.per_category:
            log(
                f"STOP: {folder}: only {len(eligible_records)} eligible after v5.6 filter; "
                f"need {args.per_category}. The candidate pool needs to grow "
                f"or we accept a smaller bucket. Aborting before any images move."
            )
            log(json.dumps({
                "folder": folder,
                "candidates": candidate_count,
                "missing_label": len(missing_label),
                "rejected_photo_matches_no": rejected_no,
                "rejected_photo_matches_unclear": rejected_unclear,
                "rejected_other_or_missing": rejected_other,
                "eligible": len(eligible_records),
                "requested": args.per_category,
            }, indent=2))
            return 4

        rng = random.Random(f"{args.final_seed}:{folder}")
        selected = rng.sample(eligible_records, args.per_category)
        selected.sort(key=lambda r: r["image_id"])

        per_folder_stats[folder] = {
            "candidate_stubs": candidate_count,
            "v5_6_label_files_present": len(labels_by_id),
            "v5_6_label_unreadable_or_invalid": invalid_or_unreadable,
            "missing_label_for_candidate": len(missing_label),
            "rejected_photo_matches_no": rejected_no,
            "rejected_photo_matches_unclear": rejected_unclear,
            "rejected_other_or_missing": rejected_other,
            "eligible_after_filter": len(eligible_records),
            "final_selected": len(selected),
        }
        selected_per_folder[folder] = selected
        log(
            f"{folder}: candidates={candidate_count} labels={len(labels_by_id)} "
            f"eligible={len(eligible_records)} -> selected {len(selected)}"
        )

    if args.dry_run:
        log("--dry-run set; not copying images or writing manifest.")
        print(json.dumps({"per_folder": per_folder_stats}, indent=2))
        return 0

    # Copy selected images to eval-set destination.
    eval_dest.mkdir(parents=True, exist_ok=True)
    copied_per_folder: dict[str, int] = {}
    missing_image_files: list[str] = []
    for folder, selected in selected_per_folder.items():
        dest = eval_dest / folder
        if dest.exists() and any(dest.iterdir()):
            log(f"ERROR: eval-dest folder is not empty: {dest}")
            log("Refusing to overwrite a prior locked eval. Remove if intentional.")
            return 5
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for rec in selected:
            stem = rec["image_id"]
            src = find_image_in_archive(archive, folder, stem)
            if src is None:
                missing_image_files.append(f"{folder}/{stem}")
                continue
            shutil.copy2(src, dest / src.name)
            copied += 1
        copied_per_folder[folder] = copied
        log(f"{folder}: copied {copied}/{len(selected)} images -> {dest}")

    if missing_image_files:
        log(
            f"WARNING: {len(missing_image_files)} selected images had no .jpg/.jpeg in archive: "
            f"{missing_image_files[:5]}{' ...' if len(missing_image_files) > 5 else ''}"
        )

    # Build manifest entries
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest_entries: list[dict[str, Any]] = []
    for folder, selected in selected_per_folder.items():
        for rec in selected:
            manifest_entries.append({
                "image_id": rec["image_id"],
                "source_folder": folder,
                "inspection_type": rec.get("inspection_type"),
                "evidence_type": rec.get("evidence_type"),
                "v5_6_label": {
                    "describe_output": rec.get("describe_output"),
                    "production_schema": rec.get("production_schema"),
                    "localization": rec.get("localization"),
                    "few_shot_references": rec.get("few_shot_references"),
                    "provenance": rec.get("provenance"),
                    "labeler_version": rec.get("labeler_version"),
                },
            })

    manifest = {
        "eval_set_version": out.name,
        "generated_utc": finished,
        "git_sha": sha,
        "git_dirty": dirty,
        "labeler_version": args.labeler_version,
        "archive_root": str(archive),
        "exclusion_list_source": "sample-batch-01 (per draw_log stage_1_candidate_pool.exclude_root)",
        "eval_dest": str(eval_dest),
        "final_seed": args.final_seed,
        "per_category_target": args.per_category,
        "per_category_selected": {k: len(v) for k, v in selected_per_folder.items()},
        "total": sum(len(v) for v in selected_per_folder.values()),
        "filter_rule": "describe_output.photo_matches_category == 'yes' AND v5.6 wrote schema-valid label",
        "entries": manifest_entries,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    log(f"wrote manifest -> {manifest_path}  ({len(manifest_entries)} entries)")

    # Update draw_log.json with Stage 2 + Stage 3
    draw_log_path = out / "draw_log.json"
    if draw_log_path.exists():
        try:
            draw_log = json.loads(draw_log_path.read_text())
        except json.JSONDecodeError:
            draw_log = {}
    else:
        draw_log = {}
    draw_log["stage_2_v5_6_filter"] = {
        "labels_dir": str(labels_dir),
        "per_folder": {
            folder: {
                k: v
                for k, v in per_folder_stats[folder].items()
                if k not in {"final_selected"}
            }
            for folder in categories
        },
    }
    draw_log["stage_3_final_draw"] = {
        "started_utc": started,
        "finished_utc": finished,
        "eval_final_seed": args.final_seed,
        "git_sha": sha,
        "git_dirty": dirty,
        "per_category_target": args.per_category,
        "per_folder_selected": {k: len(v) for k, v in selected_per_folder.items()},
        "copied_per_folder": copied_per_folder,
        "missing_image_files_count": len(missing_image_files),
        "missing_image_files_sample": missing_image_files[:10],
    }
    draw_log_path.write_text(json.dumps(draw_log, indent=2, sort_keys=True) + "\n")
    log(f"updated draw_log -> {draw_log_path}")

    # README (write once; do not clobber an edited copy).
    readme_path = out / "README.md"
    if not readme_path.exists():
        readme_path.write_text(_render_readme(manifest, archive, eval_dest, labels_dir))
        log(f"wrote README -> {readme_path}")
    else:
        log(f"README already exists; left untouched: {readme_path}")

    print(json.dumps({
        "manifest": str(manifest_path),
        "total": manifest["total"],
        "per_category_selected": manifest["per_category_selected"],
    }, indent=2))
    return 0


def _render_readme(manifest: dict[str, Any], archive: Path, eval_dest: Path, labels_dir: Path) -> str:
    return f"""# {manifest['eval_set_version']}

Locked held-out eval set for the trucksafe Gemma fine-tune.

## What this is

- **{manifest['total']} images** ({', '.join(f"{k}={v}" for k, v in manifest['per_category_selected'].items())}).
- Drawn from the full archive at `{archive}`, **excluding** every image stem present in `sample-batch-01/` (the existing training sample).
- Pre-filtered through the v5.6 labeler's `photo_matches_category` self-check: only images where the labeler said the photo actually shows its claimed hardware (`photo_matches_category == "yes"`) were eligible for the final draw.
- Pass-cohort only. The archive is positive-skewed; failure-cohort eval is a separate brief (see `docs/eval_set.md` → "Open items").

## Provenance

| Field | Value |
| --- | --- |
| Labeler version | {manifest['labeler_version']} |
| Git SHA at draw time | `{manifest['git_sha']}` ({'dirty' if manifest['git_dirty'] else 'clean'}) |
| Generated (UTC) | {manifest['generated_utc']} |
| Candidate seed | see `draw_log.json` → `stage_1_candidate_pool.eval_draw_seed` |
| Final-draw seed | `{manifest['final_seed']}` |
| Filter rule | {manifest['filter_rule']} |

## Layout

```
{manifest['eval_set_version']}/
├── README.md                      # this file
├── manifest.json                  # 1,500 entries with full v5.6 reference label per image
├── draw_log.json                  # per-stage counts (candidate pool → v5.6 filter → final draw)
└── candidate_ids/                 # Stage 1 stubs, one .json per candidate image id
    ├── fifth_wheel/
    ├── lock_jaws/
    └── pintle_hook/
```

The locked images themselves live at:

```
{eval_dest}/
├── fifth_wheel/   (.jpg files)
├── lock_jaws/
└── pintle_hook/
```

The v5.6 raw candidate labels (2,400 image runs, used to pick the final 1,500) are at `{labels_dir}` on the rig and are intentionally not committed — they're inputs to this manifest, fully reconstructable from `candidate_ids/` plus a v5.6 re-run.

## Locking discipline

This eval set is **physically separated** from the labeler's input paths:

- Training/labeling pipelines point `--input-dir` at `sample-batch-01/` (or a future training batch). They never point at `{eval_dest.name}/`.
- Do not re-label, re-shuffle, or extend this set before the v1 fine-tune evaluation completes. If you find a real problem with the draw, version-bump it (`eval_set_v2`) rather than mutating v1.
- If you need to grow the eval pool later (e.g., the failure-cohort eval depending on uncle's shoot landing), create a sibling `eval/failure_cohort_v1/` rather than mixing failure images into this set.

The v5.6 labels embedded in `manifest.json` are **labeler reference output**, not ground truth. A small human spot-check (uncle on 50–100 images) would harden them; that is noted in `docs/eval_set.md` and not yet done.

## Reproduction

From the repo root on the rig:

```
# Stage 1: candidate pool (800 per category, exclude sample-batch-01)
python3 training/scripts/build_eval_candidates.py \\
  --archive ~/projects/trucksafe/training/data/images/archive-v1 \\
  --exclude ~/projects/trucksafe/training/data/images/sample-batch-01 \\
  --out {manifest['eval_set_version'].split('/')[-1] if '/' in manifest['eval_set_version'] else 'eval/' + manifest['eval_set_version']} \\
  --per-category 800 \\
  --seed 20260512

# Stage 2: run v5.6 over the candidates (vLLM serving on port 8000)
uv run python -m trucksafe_training.labeling.run_labeler_v5_6 \\
  --source-folder all \\
  --input-dir ~/projects/trucksafe/training/data/images/archive-v1 \\
  --output-dir eval/eval_set_v1/v5_6_candidate_labels \\
  --count 800 --seed 20260512 \\
  --provenance archive_pass \\
  --image-ids-from eval/eval_set_v1/candidate_ids

# Stage 3: final draw (filter on photo_matches_category=='yes', sample 500/category)
python3 training/scripts/draw_eval_set.py \\
  --out eval/eval_set_v1 \\
  --labels-dir eval/eval_set_v1/v5_6_candidate_labels \\
  --archive ~/projects/trucksafe/training/data/images/archive-v1 \\
  --eval-dest ~/projects/trucksafe/training/data/images/eval-set-v1 \\
  --final-seed 20260512_final
```

See `docs/eval_set.md` for the full design rationale.
"""


if __name__ == "__main__":
    raise SystemExit(main())
