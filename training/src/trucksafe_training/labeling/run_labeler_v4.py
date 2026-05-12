"""Two-pass labeler (v4) — localize, crop, describe.

Pass 1 asks Gemma 4 31B for a bounding box around the category-specific
hardware. Pass 2 sends the crop through the v3 describe-only prompt set.
The runner then assembles a production-schema label the same way v3 does.

Gemma 4 grounding output (probed 2026-05-11):

    ```json
    [{"box_2d": [y1, x1, y2, x2]}]
    ```

Coordinates are normalized 0–1000 (Pali-3 style: ymin, xmin, ymax, xmax).
Refusals are plain English ("I did not find any bounding box detections..."),
not JSON — handled by the parser as `status: refused`. On any failure we
fall back to the full image for Pass 2 so the run still produces a label.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from pydantic import BaseModel, ValidationError

from trucksafe_training.labeling.prompts import CATEGORY_INFO
from trucksafe_training.labeling.run_labeler import (
    PROVENANCE_CHOICES,
    REFUSAL_PATTERN,
    USER_TURN_TEXT,
    assemble_final_label,
    build_request,
    extract_json,
)
from trucksafe_training.schemas import (
    DESCRIBE_ONLY_MODELS,
    FifthWheelSideView,
    LockJawsCloseup,
    PintleHookAndChains,
)

PRODUCTION_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel": FifthWheelSideView,
    "lock_jaws": LockJawsCloseup,
    "pintle_hook": PintleHookAndChains,
}

LOCALIZE_PROMPTS = {
    "fifth_wheel": (
        "Locate the fifth wheel coupling assembly — the round metal plate on the tractor "
        "that the trailer kingpin sits in. Return a bounding box around the plate and the "
        "trailer apron above it. Output only the box coordinates."
    ),
    "lock_jaws": (
        "Locate the locking jaws of the fifth wheel coupling — the metal jaws that close "
        "around the kingpin. Return a bounding box around the jaws and the kingpin. "
        "Output only the box coordinates."
    ),
    "pintle_hook": (
        "Locate the pintle hook assembly — the hook on the rear of the truck and the lunette "
        "ring of the trailer. Return a bounding box including the hook, the lunette, the "
        "safety pin, and any visible safety chains. Output only the box coordinates."
    ),
}

# Pass-1 caps
LARGE_BOX_FRACTION = 0.90  # >90% of image area → treat as refusal
CROP_MARGIN_FRAC = 0.20    # expand 20% on each side
MAX_ASPECT_RATIO = 3.0     # crops narrower than this get padded toward 1:1


@dataclass
class LocalizationResult:
    status: str  # success | refused | failed | too_large | parse_error
    raw_output: str
    box_normalized: list[float] | None = None  # [y1,x1,y2,x2] on 0-1000 scale
    box_pixels: list[int] | None = None        # in original image space
    expanded_box_pixels: list[int] | None = None
    aspect_corrected: bool = False


def parse_grounding_output(content: str) -> tuple[list[float] | None, str]:
    """Returns (box_normalized [y1,x1,y2,x2], status). Status one of
    success | refused | parse_error.

    Picks the largest box if multiple are returned.
    """
    if not content or not content.strip():
        return None, "refused"

    # Refusal-style replies
    if REFUSAL_PATTERN.search(content.strip()) or "did not find" in content.lower():
        return None, "refused"

    text = extract_json(content)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a [y1,x1,y2,x2] bare-list anywhere as a fallback
        m = re.search(r"\[\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\]", content)
        if not m:
            return None, "parse_error"
        return [float(x) for x in m.groups()], "success"

    boxes: list[list[float]] = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict) and "box_2d" in item:
            b = item["box_2d"]
            if isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b):
                boxes.append([float(x) for x in b])
        elif isinstance(item, list) and len(item) == 4 and all(isinstance(v, (int, float)) for v in item):
            boxes.append([float(x) for x in item])

    if not boxes:
        return None, "parse_error"

    # Largest by area
    def area(b: list[float]) -> float:
        return max(0.0, (b[2] - b[0])) * max(0.0, (b[3] - b[1]))

    return max(boxes, key=area), "success"


def normalized_to_pixel(box_norm: list[float], img_w: int, img_h: int) -> list[int]:
    """[y1,x1,y2,x2] on 0-1000 → pixel coords as [y1,x1,y2,x2]. Clipped to image."""
    y1n, x1n, y2n, x2n = box_norm
    y1 = max(0, min(img_h, int(round(y1n / 1000.0 * img_h))))
    x1 = max(0, min(img_w, int(round(x1n / 1000.0 * img_w))))
    y2 = max(0, min(img_h, int(round(y2n / 1000.0 * img_h))))
    x2 = max(0, min(img_w, int(round(x2n / 1000.0 * img_w))))
    # Ensure ordering
    if y2 < y1: y1, y2 = y2, y1
    if x2 < x1: x1, x2 = x2, x1
    return [y1, x1, y2, x2]


def expand_and_correct(box_px: list[int], img_w: int, img_h: int) -> tuple[list[int], bool]:
    """Expand by CROP_MARGIN_FRAC and aspect-correct if narrower than MAX_ASPECT_RATIO.

    Returns (expanded_box [y1,x1,y2,x2], aspect_corrected).
    """
    y1, x1, y2, x2 = box_px
    bh = y2 - y1
    bw = x2 - x1
    if bh <= 0 or bw <= 0:
        return [0, 0, img_h, img_w], False

    # Expand by margin
    pad_h = int(round(bh * CROP_MARGIN_FRAC))
    pad_w = int(round(bw * CROP_MARGIN_FRAC))
    ey1 = max(0, y1 - pad_h)
    ex1 = max(0, x1 - pad_w)
    ey2 = min(img_h, y2 + pad_h)
    ex2 = min(img_w, x2 + pad_w)

    aspect_corrected = False
    ebh = ey2 - ey1
    ebw = ex2 - ex1
    if ebh == 0 or ebw == 0:
        return [ey1, ex1, ey2, ex2], False

    aspect = max(ebh, ebw) / min(ebh, ebw)
    if aspect > MAX_ASPECT_RATIO:
        # Pad the short axis toward a square (1:1).
        if ebh > ebw:
            # Need wider
            target = ebh
            need = target - ebw
            left = need // 2
            right = need - left
            ex1 = max(0, ex1 - left)
            ex2 = min(img_w, ex2 + right)
        else:
            target = ebw
            need = target - ebh
            top = need // 2
            bottom = need - top
            ey1 = max(0, ey1 - top)
            ey2 = min(img_h, ey2 + bottom)
        aspect_corrected = True

    return [ey1, ex1, ey2, ex2], aspect_corrected


def box_area_fraction(box_px: list[int], img_w: int, img_h: int) -> float:
    y1, x1, y2, x2 = box_px
    return max(0, (y2 - y1)) * max(0, (x2 - x1)) / float(img_w * img_h)


def encode_image_path(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def encode_image_bytes(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def localize(
    client: httpx.Client,
    endpoint: str,
    model: str,
    short_cat: str,
    image_path: Path,
    img_w: int,
    img_h: int,
) -> LocalizationResult:
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": LOCALIZE_PROMPTS[short_cat]},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image_path(image_path)}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    try:
        resp = client.post(f"{endpoint}/chat/completions", json=body, timeout=120.0)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        return LocalizationResult(status="failed", raw_output=repr(exc)[:300])

    box_norm, parse_status = parse_grounding_output(content)
    if parse_status != "success" or box_norm is None:
        return LocalizationResult(status=parse_status, raw_output=content[:300])

    box_px = normalized_to_pixel(box_norm, img_w, img_h)
    if box_area_fraction(box_px, img_w, img_h) > LARGE_BOX_FRACTION:
        return LocalizationResult(
            status="too_large",
            raw_output=content[:300],
            box_normalized=box_norm,
            box_pixels=box_px,
        )

    expanded, aspect_corrected = expand_and_correct(box_px, img_w, img_h)
    return LocalizationResult(
        status="success",
        raw_output=content[:300],
        box_normalized=box_norm,
        box_pixels=box_px,
        expanded_box_pixels=expanded,
        aspect_corrected=aspect_corrected,
    )


def make_crop(image_path: Path, box_px: list[int]) -> bytes:
    img = Image.open(image_path).convert("RGB")
    y1, x1, y2, x2 = box_px
    crop = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def describe(
    client: httpx.Client,
    endpoint: str,
    model: str,
    system_prompt: str,
    image_bytes: bytes,
    use_json_mode: bool,
    describe_cls: type[BaseModel],
) -> tuple[dict[str, Any] | None, str]:
    """Returns (describe-only dict | None, error_kind). error_kind in
    transport|refusal|parse|schema|"" """
    body = build_request(system_prompt, encode_image_bytes(image_bytes), model, use_json_mode)
    try:
        resp = client.post(f"{endpoint}/chat/completions", json=body, timeout=180.0)
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
        fractions = sorted(self.box_area_fractions)
        median = fractions[len(fractions) // 2] if fractions else None
        p95 = fractions[int(len(fractions) * 0.95)] if fractions else None
        return {
            "attempted": self.attempted,
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


def sample_images(category_dir: Path, count: int, seed: int) -> list[Path]:
    files = sorted(p for p in category_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"})
    if len(files) < count:
        raise RuntimeError(f"Only {len(files)} images in {category_dir}; need {count}")
    rng = random.Random(seed)
    return rng.sample(files, count)


def run_category(
    client: httpx.Client,
    endpoint: str,
    model_name: str,
    short_cat: str,
    input_dir: Path,
    output_dir: Path,
    count: int,
    seed: int,
    use_json_mode: bool,
    provenance: str,
    max_images: int | None,
) -> CategoryStats:
    canonical, describe_prompt = CATEGORY_INFO[short_cat]
    describe_cls = DESCRIBE_ONLY_MODELS[canonical]
    final_cls = PRODUCTION_MODELS[short_cat]

    cat_dir = input_dir / short_cat
    out_dir = output_dir / short_cat
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / short_cat / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    images = sample_images(cat_dir, count, seed)
    if max_images:
        images = images[:max_images]

    stats = CategoryStats()
    for i, image_path in enumerate(images, 1):
        stats.attempted += 1
        img = Image.open(image_path)
        img_w, img_h = img.size
        print(f"  [{i}/{len(images)}] {short_cat}/{image_path.name} ({img_w}x{img_h})", flush=True)

        t0 = time.monotonic()
        loc = localize(client, endpoint, model_name, short_cat, image_path, img_w, img_h)
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

        t1 = time.monotonic()
        describe_only, err = describe(client, endpoint, model_name, describe_prompt, crop_bytes, use_json_mode, describe_cls)
        stats.pass2_seconds += time.monotonic() - t1

        if describe_only is None:
            stats.describe_errors.append({"image": image_path.name, "error": err})
            continue

        final = assemble_final_label(describe_only, provenance)
        if provenance != "unknown":
            try:
                final_cls.model_validate(final)
            except ValidationError as exc:
                stats.final_schema_failures.append({"image": image_path.name, "error": str(exc)[:300]})
                continue

        out_obj = {
            "image_id": image_path.stem,
            "category": short_cat,
            "localization": {
                "status": loc.status,
                "raw_output": loc.raw_output,
                "box_normalized": loc.box_normalized,
                "box_pixels": loc.box_pixels,
                "expanded_box_pixels": loc.expanded_box_pixels,
                "aspect_corrected": loc.aspect_corrected,
                "crop_path": crop_rel,
            },
            "describe_output": describe_only,
            "production_schema": final,
            "provenance": provenance,
            "labeler_version": "v4",
        }
        out_path = out_dir / f"{image_path.stem}.json"
        out_path.write_text(json.dumps(out_obj, indent=2) + "\n")
        stats.final_valid += 1

    print(
        f"  → {short_cat}: final {stats.final_valid}/{stats.attempted}  "
        f"localize: success={stats.localization_success} refused={stats.localization_refused} "
        f"failed={stats.localization_failed} too_large={stats.localization_too_large} "
        f"parse_err={stats.localization_parse_error}  "
        f"describe_err={len(stats.describe_errors)}  "
        f"final_schema_fail={len(stats.final_schema_failures)}  "
        f"pass1={stats.pass1_seconds:.1f}s pass2={stats.pass2_seconds:.1f}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Two-pass crop-then-describe labeler.")
    p.add_argument("--category", choices=["fifth_wheel", "lock_jaws", "pintle_hook", "all"], required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--provenance", choices=PROVENANCE_CHOICES, required=True)
    p.add_argument("--endpoint", default="http://localhost:8000/v1")
    p.add_argument("--model", default="gemma-4-31b-labeler")
    p.add_argument("--max-images", type=int, default=None,
                   help="Stop after this many images per category (for the gate check).")
    p.add_argument("--no-json-mode", action="store_true")
    args = p.parse_args(argv)

    categories = (
        ["fifth_wheel", "lock_jaws", "pintle_hook"]
        if args.category == "all"
        else [args.category]
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_json_mode = not args.no_json_mode

    started_at = datetime.now(timezone.utc)
    run_started = time.monotonic()
    per_cat: dict[str, dict[str, Any]] = {}

    with httpx.Client() as client:
        for short_cat in categories:
            print(f"\n== {short_cat} ==", flush=True)
            stats = run_category(
                client, args.endpoint, args.model, short_cat,
                args.input_dir, args.output_dir, args.count, args.seed,
                use_json_mode, args.provenance, args.max_images,
            )
            per_cat[short_cat] = stats.to_dict()

    total_elapsed = time.monotonic() - run_started
    audit = {
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "seed": args.seed,
        "count_per_category": args.count,
        "provenance": args.provenance,
        "labeler_version": "v4",
        "json_mode": use_json_mode,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "categories": per_cat,
    }
    (args.output_dir / "audit_log.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"\nDone in {total_elapsed:.1f}s. Audit log: {args.output_dir / 'audit_log.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
