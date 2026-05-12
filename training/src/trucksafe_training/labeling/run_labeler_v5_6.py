"""v5.6 labeler — side_view schema simplification.

Changes vs v5.5:
  - side_view loses the manufacturer-conditional sub-objects
    (holland/fontaine/jost). Only `trailer_seated_flush`,
    `gap_between_apron_and_plate`, and a flat descriptive
    `fifth_wheel_manufacturer` remain. See prompts_v5_6 + the schema files
    in shared/schemas/.
  - Few-shot library consolidates the three manufacturer subfolders into a
    single `side_view_plate/`. Library load fails fast if that subfolder
    has no captioned images.

Unchanged from v5.5:
  - `photo_matches_category` top-level self-check.
  - Relaxed pintle chains-clipped enum (`at_least_one_clipped`).
  - Multi-image few-shot prompt assembly.
  - Per-image detection crop for fifth_wheel + pintle, fixed-band crop for
    lock_jaws.
"""

from __future__ import annotations

import argparse
import base64
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

from trucksafe_training.labeling.prompts_v5_6 import (
    EVIDENCE_CONFIG,
    FEW_SHOT_SUBFOLDERS,
    FewShotExample,
    load_few_shot_library,
)
from trucksafe_training.labeling.run_labeler import (
    PROVENANCE_CHOICES,
    REFUSAL_PATTERN,
    extract_json,
)
from trucksafe_training.labeling.run_labeler_v4 import (
    box_area_fraction,
    encode_image_bytes,
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
CENTER_CROP_AREA_FRACTION = 0.70    # fallback crop when localization refuses; keeps 70% of the image area, centered
LABELER_VERSION = "v5.6"


def fixed_band_crop(image_path: Path, band: tuple[float, float]) -> tuple[bytes, list[int]]:
    """Crop rows band[0]..band[1] (0–1 normalized), full width."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    y1 = int(round(band[0] * h))
    y2 = int(round(band[1] * h))
    crop = img.crop((0, y1, w, y2))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), [y1, 0, y2, w]


def center_crop(image_path: Path, area_fraction: float) -> tuple[bytes, list[int]]:
    """Center-crop the image so the result has `area_fraction` of the original
    area (e.g. 0.70 keeps the inner 70%). Returns (jpeg_bytes, [y1,x1,y2,x2]).

    Used as the localization-refusal fallback so the describe pass still
    receives a meaningfully framed image instead of the full original. The
    fraction is deterministic; the strategy is recorded in loc_obj so
    downstream review can distinguish detection crops from fallback crops.
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    linear = area_fraction ** 0.5
    margin_w = int(round((1.0 - linear) / 2.0 * w))
    margin_h = int(round((1.0 - linear) / 2.0 * h))
    x1 = margin_w
    y1 = margin_h
    x2 = w - margin_w
    y2 = h - margin_h
    crop = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), [y1, x1, y2, x2]


def build_few_shot_request(
    system_prompt: str,
    reference_examples: list[FewShotExample],
    input_image_b64: str,
    input_media_type: str,
    model_name: str,
    use_json_mode: bool,
) -> dict[str, Any]:
    """Build a chat-completion body with N reference images + 1 input image
    in a single user turn.

    Reference images are introduced by a header text block, then each
    reference is a (caption text, image_url) pair. The input image follows a
    "Now describe the INPUT image" separator. The model has been told via
    the system prompt that references precede the input.
    """
    user_content: list[dict[str, Any]] = []
    if reference_examples:
        user_content.append(
            {
                "type": "text",
                "text": (
                    "REFERENCE IMAGES — use these to calibrate your visual vocabulary. "
                    "Each is labeled with a diagnostic caption that names what to look for."
                ),
            }
        )
        for i, ex in enumerate(reference_examples, 1):
            user_content.append(
                {"type": "text", "text": f"Reference {i} ({ex.relative_path}): {ex.caption}"}
            )
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{ex.media_type};base64,{ex.image_b64}"},
                }
            )
        user_content.append(
            {
                "type": "text",
                "text": (
                    "INPUT IMAGE — now describe this image using the same vocabulary and "
                    "structure as the references. Emit the JSON label."
                ),
            }
        )
    else:
        user_content.append({"type": "text", "text": "Describe this image and emit the JSON label."})
    user_content.append(
        {
            "type": "image_url",
            "image_url": {"url": f"data:{input_media_type};base64,{input_image_b64}"},
        }
    )

    body: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": 800,
    }
    if use_json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def describe_with_few_shot(
    client: httpx.Client,
    endpoint: str,
    model: str,
    system_prompt: str,
    reference_examples: list[FewShotExample],
    input_image_bytes: bytes,
    use_json_mode: bool,
    describe_cls: type[BaseModel],
) -> tuple[dict[str, Any] | None, str]:
    body = build_few_shot_request(
        system_prompt,
        reference_examples,
        encode_image_bytes(input_image_bytes),
        "image/jpeg",  # crops are saved as JPEG
        model,
        use_json_mode,
    )
    try:
        resp = client.post(f"{endpoint}/chat/completions", json=body, timeout=240.0)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        return None, f"transport: {exc!r}"[:300]

    if not content.strip() or REFUSAL_PATTERN.search(content.strip()):
        return None, f"refusal: {content[:120]}"

    raw = extract_json(content)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"parse: {exc} :: {raw[:120]}"

    try:
        return describe_cls.model_validate(parsed).model_dump(), ""
    except ValidationError as exc:
        return None, f"schema: {str(exc)[:300]}"


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
    fellback_to_center_crop: int = 0
    fixed_band_applied: int = 0
    few_shot_count: int = 0  # how many reference images were sent per request
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
            "few_shot_reference_images_per_request": self.few_shot_count,
            "localization": {
                "strategy_per_image_detection": {
                    "success": self.localization_success,
                    "refused": self.localization_refused,
                    "failed": self.localization_failed,
                    "too_large": self.localization_too_large,
                    "parse_error": self.localization_parse_error,
                    "fellback_to_center_crop": self.fellback_to_center_crop,
                    "fellback_to_full_image": self.fellback_to_full_image,
                    "center_crop_area_fraction": CENTER_CROP_AREA_FRACTION,
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


def _load_image_ids_from_prior_audit(prior_dir: Path, source_folder: str) -> list[str]:
    """Read image_id stems from a prior audit's per-folder JSON outputs.
    Returns a sorted list of stems so the run order is deterministic.
    """
    folder_dir = prior_dir / source_folder
    if not folder_dir.exists():
        raise RuntimeError(f"prior audit folder missing: {folder_dir}")
    stems: list[str] = []
    for p in sorted(folder_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        sid = d.get("image_id") or p.stem
        stems.append(sid)
    return stems


def _resolve_images_from_ids(cat_dir: Path, stems: list[str]) -> list[Path]:
    paths: list[Path] = []
    missing: list[str] = []
    for s in stems:
        # Match v4 sample_images extension filter
        found: Path | None = None
        for ext in (".jpg", ".jpeg"):
            c = cat_dir / f"{s}{ext}"
            if c.exists():
                found = c
                break
        if found is None:
            missing.append(s)
        else:
            paths.append(found)
    if missing:
        raise RuntimeError(
            f"image IDs from prior audit not found in {cat_dir}: {missing[:5]}"
            + (f" (+{len(missing)-5} more)" if len(missing) > 5 else "")
        )
    return paths


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
    few_shot_library: dict[str, list[FewShotExample]],
    image_ids_from: Path | None = None,
) -> CategoryStats:
    inspection_type, evidence_type, describe_prompt = EVIDENCE_CONFIG[source_folder]
    describe_cls = V5_DESCRIBE_ONLY_MODELS[inspection_type]
    final_cls = V5_PRODUCTION_MODELS[inspection_type]
    do_detection_crop = source_folder in CROP_FOLDERS
    do_fixed_band = source_folder in FIXED_BAND_FOLDERS

    references: list[FewShotExample] = []
    for sub in FEW_SHOT_SUBFOLDERS.get(source_folder, []):
        references.extend(few_shot_library.get(sub, []))

    cat_dir = input_dir / source_folder
    out_dir = output_dir / source_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / source_folder / "crops"
    if do_detection_crop or do_fixed_band:
        crops_dir.mkdir(parents=True, exist_ok=True)

    if image_ids_from is not None:
        stems = _load_image_ids_from_prior_audit(image_ids_from, source_folder)
        images = _resolve_images_from_ids(cat_dir, stems)
        print(f"  (using pinned sample from {image_ids_from} — {len(images)} images)", flush=True)
    else:
        images = sample_images(cat_dir, count, seed)
    if max_images:
        images = images[:max_images]

    stats = CategoryStats()
    stats.few_shot_count = len(references)
    for i, image_path in enumerate(images, 1):
        stats.attempted += 1
        img = Image.open(image_path)
        img_w, img_h = img.size
        strat = "detection" if do_detection_crop else ("fixed_band" if do_fixed_band else "none")
        print(
            f"  [{i}/{len(images)}] {source_folder}/{image_path.name} "
            f"({img_w}x{img_h}) -> {evidence_type} [{strat}] +refs={len(references)}",
            flush=True,
        )

        loc_obj: dict[str, Any] | None = None
        crop_bytes: bytes
        crop_rel: str | None = None

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
                stats.fellback_to_center_crop += 1
                crop_bytes, box_px = center_crop(image_path, CENTER_CROP_AREA_FRACTION)
                crop_path = crops_dir / f"{image_path.stem}.jpg"
                crop_path.write_bytes(crop_bytes)
                crop_rel = str(crop_path.relative_to(output_dir))
                fallback_box_px = box_px
                print(
                    f"      ↳ localization {loc.status}; falling back to center crop "
                    f"({CENTER_CROP_AREA_FRACTION*100:.0f}% area)",
                    flush=True,
                )

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
            if loc.status != "success":
                loc_obj["fallback_strategy"] = "center_crop"
                loc_obj["fallback_box_pixels"] = fallback_box_px
                loc_obj["fallback_area_fraction"] = CENTER_CROP_AREA_FRACTION
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
        describe_only, err = describe_with_few_shot(
            client, endpoint, model_name, describe_prompt,
            references, crop_bytes, use_json_mode, describe_cls,
        )
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
            "few_shot_references": [
                {"path": ex.relative_path, "caption": ex.caption} for ex in references
            ],
            "describe_output": describe_only,
            "production_schema": final,
            "provenance": provenance,
            "labeler_version": LABELER_VERSION,
        }
        (out_dir / f"{image_path.stem}.json").write_text(json.dumps(out_obj, indent=2) + "\n")
        stats.final_valid += 1

    print(
        f"  → {source_folder}: final {stats.final_valid}/{stats.attempted}  "
        + (f"detection: success={stats.localization_success} center_crop_fallback={stats.fellback_to_center_crop}  " if do_detection_crop else "")
        + (f"fixed_band: applied={stats.fixed_band_applied}  " if do_fixed_band else "")
        + f"few_shot={len(references)}  "
        f"describe_err={len(stats.describe_errors)}  "
        f"schema_fail={len(stats.final_schema_failures)}  "
        f"pass1={stats.pass1_seconds:.1f}s pass2={stats.pass2_seconds:.1f}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="v5.6 labeler: side_view schema simplification (manufacturer demoted, sub-objects removed)."
    )
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
    p.add_argument(
        "--image-ids-from",
        type=Path,
        default=None,
        help="Path to a prior audit's labels dir. Overrides random sampling — uses that audit's exact image_ids.",
    )
    args = p.parse_args(argv)

    folders = SOURCE_FOLDERS if args.source_folder == "all" else [args.source_folder]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_json_mode = not args.no_json_mode

    few_shot_library = load_few_shot_library()
    library_summary = {sub: [ex.relative_path for ex in exs] for sub, exs in few_shot_library.items()}
    print(f"few-shot library loaded: {sum(len(v) for v in few_shot_library.values())} images across {len(few_shot_library)} subfolders", flush=True)

    # v5.6: side_view consolidated to a single subfolder. Stop-and-surface if
    # the user hasn't completed the consolidation step (see docs/labeling/v5-6.md).
    for needed in FEW_SHOT_SUBFOLDERS["fifth_wheel"]:
        if not few_shot_library.get(needed):
            raise SystemExit(
                f"v5.6 expects few-shot subfolder '{needed}' with at least one captioned image. "
                f"It is missing or empty in training/assets/few_shot_examples/captions.json. "
                f"Complete the side_view_plate/ consolidation before running (see docs/labeling/v5-6.md)."
            )

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
                few_shot_library,
                image_ids_from=args.image_ids_from,
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
        "labeler_version": LABELER_VERSION,
        "json_mode": use_json_mode,
        "image_ids_from": str(args.image_ids_from) if args.image_ids_from else None,
        "few_shot_library": library_summary,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "source_folders": per_folder,
    }
    (args.output_dir / "audit_log.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"\nDone in {total_elapsed:.1f}s. Audit log: {args.output_dir / 'audit_log.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
