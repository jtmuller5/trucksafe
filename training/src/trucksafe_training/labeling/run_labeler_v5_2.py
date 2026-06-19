"""v5.2 labeler — rear_assembly prompt recovery + lock_jaws fixed-band crop.

Two changes vs v5.1:
  1. rear_assembly prompt rewrite (handled in prompts_v5.py, not here).
  2. lock_jaws_underneath uses a deterministic fixed-band crop (rows 20–70%,
     full width) instead of per-image detection. The hypothesis (per the v5.2
     brief) is that lock_jaws photos are taken from underneath with the phone
     pointing up, producing predictable composition where the mechanism sits
     in a horizontal band in the upper portion of the frame.

fifth_wheel and pintle_hook continue to use v4's per-image localize-and-crop.
"""

from __future__ import annotations

import argparse
import io
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
from trucksafe_training.labeling.run_labeler_v5 import assemble_v5_label
from trucksafe_training.schemas import V5_DESCRIBE_ONLY_MODELS, V5_PRODUCTION_MODELS

SOURCE_FOLDERS = list(EVIDENCE_CONFIG.keys())
CROP_FOLDERS = {"fifth_wheel", "pintle_hook"}  # per-image detection (v4-style)
FIXED_BAND_FOLDERS = {"lock_jaws"}             # deterministic crop

LOCK_JAWS_BAND_ROWS = (0.20, 0.70)  # rows 20% → 70%, full width


def fixed_band_crop(image_path: Path, band: tuple[float, float]) -> tuple[bytes, list[int]]:
    """Crop rows band[0]..band[1] (0–1 normalized), full width. Returns
    (jpeg_bytes, pixel_box_y1_x1_y2_x2)."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    y1 = int(round(band[0] * h))
    y2 = int(round(band[1] * h))
    crop = img.crop((0, y1, w, y2))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), [y1, 0, y2, w]


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
    fixed_band_applied: int = 0
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
                "strategy_per_image_detection": {
                    "success": self.localization_success,
                    "refused": self.localization_refused,
                    "failed": self.localization_failed,
                    "too_large": self.localization_too_large,
                    "parse_error": self.localization_parse_error,
                    "fellback_to_full_image": self.fellback_to_full_image,
                    "box_area_fraction_median": round(median, 4) if median is not None else None,
                    "box_area_fraction_p95": round(p95, 4) if p95 is not None else None,
                },
                "strategy_fixed_band": {
                    "applied": self.fixed_band_applied,
                    "band_rows": list(LOCK_JAWS_BAND_ROWS),
                },
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
    do_detection_crop = source_folder in CROP_FOLDERS
    do_fixed_band = source_folder in FIXED_BAND_FOLDERS

    cat_dir = input_dir / source_folder
    out_dir = output_dir / source_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / source_folder / "crops"
    if do_detection_crop or do_fixed_band:
        crops_dir.mkdir(parents=True, exist_ok=True)

    images = sample_images(cat_dir, count, seed)
    if max_images:
        images = images[:max_images]

    stats = CategoryStats()
    for i, image_path in enumerate(images, 1):
        stats.attempted += 1
        img = Image.open(image_path)
        img_w, img_h = img.size
        strat = "detection" if do_detection_crop else ("fixed_band" if do_fixed_band else "none")
        print(f"  [{i}/{len(images)}] {source_folder}/{image_path.name} ({img_w}x{img_h}) -> {evidence_type} [{strat}]", flush=True)

        loc_obj: dict[str, Any] | None = None
        crop_bytes: bytes

        if do_detection_crop:
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
                crop_rel = None
                print(f"      ↳ localization {loc.status}; falling back to full image", flush=True)

            loc_obj = {
                "strategy": "per_image_detection",
                "status": loc.status,
                "raw_output": loc.raw_output,
                "box_normalized": loc.box_normalized,
                "box_pixels": loc.box_pixels,
                "expanded_box_pixels": loc.expanded_box_pixels,
                "aspect_corrected": loc.aspect_corrected,
                "crop_path": crop_rel,
            }
        elif do_fixed_band:
            crop_bytes, box_px = fixed_band_crop(image_path, LOCK_JAWS_BAND_ROWS)
            crop_path = crops_dir / f"{image_path.stem}.jpg"
            crop_path.write_bytes(crop_bytes)
            stats.fixed_band_applied += 1
            loc_obj = {
                "strategy": "fixed_band",
                "band_rows": list(LOCK_JAWS_BAND_ROWS),
                "box_pixels": box_px,
                "crop_path": str(crop_path.relative_to(output_dir)),
            }
        else:
            crop_bytes = image_path.read_bytes()

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
            "labeler_version": "v5.2",
        }
        (out_dir / f"{image_path.stem}.json").write_text(json.dumps(out_obj, indent=2) + "\n")
        stats.final_valid += 1

    print(
        f"  → {source_folder}: final {stats.final_valid}/{stats.attempted}  "
        + (f"detection: success={stats.localization_success} fallback={stats.fellback_to_full_image}  " if do_detection_crop else "")
        + (f"fixed_band: applied={stats.fixed_band_applied}  " if do_fixed_band else "")
        + f"describe_err={len(stats.describe_errors)}  "
        f"schema_fail={len(stats.final_schema_failures)}  "
        f"pass1={stats.pass1_seconds:.1f}s pass2={stats.pass2_seconds:.1f}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v5.2 labeler: rear_assembly prompt recovery + lock_jaws fixed-band crop.")
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
        "labeler_version": "v5.2",
        "json_mode": use_json_mode,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "source_folders": per_folder,
    }
    (args.output_dir / "audit_log.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"\nDone in {total_elapsed:.1f}s. Audit log: {args.output_dir / 'audit_log.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
