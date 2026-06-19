"""v5 labeler: inspection-level reframing.

Per image:
  1. Read the source folder to determine (inspection_type, evidence_type, prompt).
  2. For fifth_wheel + pintle_hook: localize → expand → crop → describe.
     For lock_jaws: skip localization, send full image to describe (v4 showed
     localization fails on close-ups and the crop hurts more than helps).
  3. Validate against the v5 describe-only Pydantic schema (which enforces
     exactly one of side_view / lock_jaws_underneath sub-blocks populated).
  4. Attach a verdict from `--provenance` (archive_pass → "pass").
  5. Validate against the v5 production schema.
  6. Write the per-image JSON to audit-batch-04/{source_folder}/{stem}.json.

The runner reuses the localization, crop, parsing, and request-build helpers
from `run_labeler_v4.py` rather than re-implementing them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from trucksafe_training.labeling.prompts_v5 import EVIDENCE_CONFIG
from trucksafe_training.labeling.run_labeler import PROVENANCE_CHOICES
from trucksafe_training.labeling.run_labeler_v4 import (
    box_area_fraction,
    describe,
    localize,
    make_crop,
    sample_images,
)
from trucksafe_training.schemas import (
    V5_DESCRIBE_ONLY_MODELS,
    V5_PRODUCTION_MODELS,
)

# Source-folder name → (inspection_type, evidence_type, prompt). Imported from prompts_v5.
SOURCE_FOLDERS = list(EVIDENCE_CONFIG.keys())

# Which source folders get the localize+crop pre-pass. lock_jaws is full-image
# only because v4 showed 37% localization with tiny 4.4% crops.
CROP_FOLDERS = {"fifth_wheel", "pintle_hook"}


def assemble_v5_label(describe_only: dict[str, Any], provenance: str) -> dict[str, Any]:
    """Attach verdict from provenance. issues_detected stays [] for archive_pass."""
    final = dict(describe_only)
    if provenance == "archive_pass":
        final["verdict"] = "pass"
        final["issues_detected"] = []
    elif provenance in ("staged_fail", "web_fail"):
        final["verdict"] = "fail"
        final["issues_detected"] = []  # user hand-fills later
    elif provenance == "unknown":
        final["verdict"] = "describe_only"
        final["issues_detected"] = []
    else:
        raise ValueError(f"unknown provenance: {provenance}")
    return final


@dataclass
class CategoryStats:
    attempted: int = 0
    describe_only_valid: int = 0
    final_valid: int = 0
    localization_success: int = 0
    localization_refused: int = 0
    localization_failed: int = 0
    localization_too_large: int = 0
    localization_parse_error: int = 0
    fellback_to_full_image: int = 0
    describe_errors: list[dict[str, str]] = field(default_factory=list)
    final_schema_failures: list[dict[str, str]] = field(default_factory=list)
    box_area_fractions: list[float] = field(default_factory=list)
    pass1_seconds: float = 0.0
    pass2_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        f = sorted(self.box_area_fractions)
        median = f[len(f) // 2] if f else None
        p95 = f[int(len(f) * 0.95)] if f else None
        return {
            "attempted": self.attempted,
            "describe_only_valid": self.describe_only_valid,
            "final_valid": self.final_valid,
            "localization": {
                "success": self.localization_success,
                "refused": self.localization_refused,
                "failed": self.localization_failed,
                "too_large": self.localization_too_large,
                "parse_error": self.localization_parse_error,
                "fellback_to_full_image": self.fellback_to_full_image,
                "box_area_fraction_median": round(median, 4) if median is not None else None,
                "box_area_fraction_p95": round(p95, 4) if p95 is not None else None,
            },
            "describe_errors": self.describe_errors,
            "final_schema_failures": self.final_schema_failures,
            "pass1_seconds": round(self.pass1_seconds, 1),
            "pass2_seconds": round(self.pass2_seconds, 1),
        }


def run_folder(
    client: httpx.Client,
    endpoint: str,
    model_name: str,
    source_folder: str,
    input_dir: Path,
    output_dir: Path,
    count: int,
    seed: int,
    use_json_mode: bool,
    provenance: str,
    max_images: int | None,
) -> CategoryStats:
    inspection_type, evidence_type, describe_prompt = EVIDENCE_CONFIG[source_folder]
    describe_cls = V5_DESCRIBE_ONLY_MODELS[inspection_type]
    final_cls = V5_PRODUCTION_MODELS[inspection_type]
    do_crop = source_folder in CROP_FOLDERS

    cat_dir = input_dir / source_folder
    out_dir = output_dir / source_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / source_folder / "crops"
    if do_crop:
        crops_dir.mkdir(parents=True, exist_ok=True)

    images = sample_images(cat_dir, count, seed)
    if max_images:
        images = images[:max_images]

    stats = CategoryStats()
    for i, image_path in enumerate(images, 1):
        stats.attempted += 1
        img = Image.open(image_path)
        img_w, img_h = img.size
        print(f"  [{i}/{len(images)}] {source_folder}/{image_path.name} ({img_w}x{img_h}) -> {evidence_type}", flush=True)

        loc_obj: dict[str, Any] | None = None
        crop_bytes: bytes
        crop_rel: str | None = None

        if do_crop:
            t0 = time.monotonic()
            loc = localize(client, endpoint, model_name, source_folder, image_path, img_w, img_h)
            stats.pass1_seconds += time.monotonic() - t0

            if loc.status == "success":
                stats.localization_success += 1
                assert loc.expanded_box_pixels is not None
                stats.box_area_fractions.append(box_area_fraction(loc.expanded_box_pixels, img_w, img_h))
                crop_bytes = make_crop(image_path, loc.expanded_box_pixels)
                crop_path = crops_dir / f"{image_path.stem}.jpg"
                crop_path.write_bytes(crop_bytes)
                crop_rel = str(crop_path.relative_to(output_dir))
            else:
                if loc.status == "refused": stats.localization_refused += 1
                elif loc.status == "failed": stats.localization_failed += 1
                elif loc.status == "too_large": stats.localization_too_large += 1
                elif loc.status == "parse_error": stats.localization_parse_error += 1
                stats.fellback_to_full_image += 1
                crop_bytes = image_path.read_bytes()
                print(f"      ↳ localization {loc.status}; falling back to full image", flush=True)

            loc_obj = {
                "status": loc.status,
                "raw_output": loc.raw_output,
                "box_normalized": loc.box_normalized,
                "box_pixels": loc.box_pixels,
                "expanded_box_pixels": loc.expanded_box_pixels,
                "aspect_corrected": loc.aspect_corrected,
                "crop_path": crop_rel,
            }
        else:
            # No localization for lock_jaws — send full image.
            crop_bytes = image_path.read_bytes()
            loc_obj = None

        t1 = time.monotonic()
        describe_only, err = describe(client, endpoint, model_name, describe_prompt, crop_bytes, use_json_mode, describe_cls)
        stats.pass2_seconds += time.monotonic() - t1

        if describe_only is None:
            stats.describe_errors.append({"image": image_path.name, "error": err})
            continue
        stats.describe_only_valid += 1

        final = assemble_v5_label(describe_only, provenance)
        if provenance != "unknown":
            try:
                final_cls.model_validate(final)
            except ValidationError as exc:
                stats.final_schema_failures.append({"image": image_path.name, "error": str(exc)[:300]})
                continue

        out_obj = {
            "image_id": image_path.stem,
            "source_folder": source_folder,
            "inspection_type": inspection_type,
            "evidence_type": evidence_type,
            "localization": loc_obj,
            "describe_output": describe_only,
            "production_schema": final,
            "provenance": provenance,
            "labeler_version": "v5",
        }
        (out_dir / f"{image_path.stem}.json").write_text(json.dumps(out_obj, indent=2) + "\n")
        stats.final_valid += 1

    L = stats.localization_success + stats.localization_refused + stats.localization_failed + stats.localization_too_large + stats.localization_parse_error
    print(
        f"  → {source_folder}: final {stats.final_valid}/{stats.attempted}  "
        f"describe-valid={stats.describe_only_valid}  "
        + (f"localize: success={stats.localization_success}/{L} fallback={stats.fellback_to_full_image}  " if do_crop else "(no localize)  ")
        + f"describe_err={len(stats.describe_errors)}  "
        f"final_schema_fail={len(stats.final_schema_failures)}  "
        f"pass1={stats.pass1_seconds:.1f}s pass2={stats.pass2_seconds:.1f}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v5 inspection-level labeler.")
    p.add_argument("--source-folder", choices=[*SOURCE_FOLDERS, "all"], required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--provenance", choices=PROVENANCE_CHOICES, required=True)
    p.add_argument("--endpoint", default="http://localhost:8000/v1")
    p.add_argument("--model", default="gemma-4-31b-labeler")
    p.add_argument("--max-images", type=int, default=None)
    p.add_argument("--no-json-mode", action="store_true")
    args = p.parse_args(argv)

    folders = SOURCE_FOLDERS if args.source_folder == "all" else [args.source_folder]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_json_mode = not args.no_json_mode

    started_at = datetime.now(timezone.utc)
    run_started = time.monotonic()
    per_folder: dict[str, dict[str, Any]] = {}

    with httpx.Client() as client:
        for folder in folders:
            print(f"\n== {folder} ==", flush=True)
            stats = run_folder(
                client, args.endpoint, args.model, folder,
                args.input_dir, args.output_dir, args.count, args.seed,
                use_json_mode, args.provenance, args.max_images,
            )
            per_folder[folder] = stats.to_dict()

    total_elapsed = time.monotonic() - run_started
    audit = {
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "seed": args.seed,
        "count_per_folder": args.count,
        "provenance": args.provenance,
        "labeler_version": "v5",
        "json_mode": use_json_mode,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "source_folders": per_folder,
    }
    (args.output_dir / "audit_log.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"\nDone in {total_elapsed:.1f}s. Audit log: {args.output_dir / 'audit_log.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
