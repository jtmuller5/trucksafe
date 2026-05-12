"""Run the Gemma 4 31B labeler over a sampled image batch (v3 — describe-only).

Pipeline per image:
  1. Send the image + describe-only system prompt to the vLLM endpoint.
  2. Validate the response against the describe-only Pydantic schema.
  3. Attach a verdict (`overall_status`, `confidence`, `issues_detected`)
     from external provenance via assemble_final_label.
  4. Validate the assembled label against the production schema.
  5. Write the final label to disk.

The model never decides pass/fail. Verdicts come from `--provenance`.
"""

from __future__ import annotations

import argparse
import base64
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
from pydantic import BaseModel, ValidationError

from trucksafe_training.labeling.prompts import CATEGORY_INFO
from trucksafe_training.schemas import (
    DESCRIBE_ONLY_MODELS,
    FifthWheelSideView,
    FifthWheelSideViewDescribeOnly,
    LockJawsCloseup,
    LockJawsCloseupDescribeOnly,
    PintleHookAndChains,
    PintleHookAndChainsDescribeOnly,
)

SHORT_TO_CANONICAL: dict[str, str] = {
    "fifth_wheel": "fifth_wheel_side_view",
    "lock_jaws": "lock_jaws_closeup",
    "pintle_hook": "pintle_hook_and_chains",
}

PRODUCTION_MODELS: dict[str, type[BaseModel]] = {
    "fifth_wheel": FifthWheelSideView,
    "lock_jaws": LockJawsCloseup,
    "pintle_hook": PintleHookAndChains,
}

PROVENANCE_CHOICES = ("archive_pass", "staged_fail", "web_fail", "unknown")

REFUSAL_PATTERN = re.compile(
    r"^(i (cannot|can't|am unable|am not able)|sorry,? i)",
    re.IGNORECASE,
)

USER_TURN_TEXT = "Describe this image and emit the JSON label."


@dataclass
class CategoryStats:
    attempted: int = 0
    describe_only_valid: int = 0
    final_valid: int = 0
    json_parse_failures: list[dict[str, str]] = field(default_factory=list)
    describe_schema_failures: list[dict[str, str]] = field(default_factory=list)
    final_schema_failures: list[dict[str, str]] = field(default_factory=list)
    refusals: list[dict[str, str]] = field(default_factory=list)
    transport_errors: list[dict[str, str]] = field(default_factory=list)
    requires_human_labeling: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "describe_only_valid": self.describe_only_valid,
            "final_valid": self.final_valid,
            "json_parse_failures": self.json_parse_failures,
            "describe_schema_failures": self.describe_schema_failures,
            "final_schema_failures": self.final_schema_failures,
            "refusals": self.refusals,
            "transport_errors": self.transport_errors,
            "requires_human_labeling": self.requires_human_labeling,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
        }


def sample_images(category_dir: Path, count: int, seed: int) -> list[Path]:
    files = sorted(p for p in category_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if len(files) < count:
        raise RuntimeError(f"Only {len(files)} images in {category_dir}; need {count}")
    rng = random.Random(seed)
    return rng.sample(files, count)


def encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def build_request(system_prompt: str, image_b64: str, model_name: str, use_json_mode: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_TURN_TEXT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 800,
    }
    if use_json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


def extract_json(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def assemble_final_label(describe_only: dict[str, Any], provenance: str) -> dict[str, Any]:
    """Attach verdict fields based on external provenance.

    The model's describe-only output has overall_status='describe_only',
    confidence='describe_only', issues_detected=[]. This function replaces
    those with real verdicts (or leaves them alone for the `unknown` case).
    """
    final = dict(describe_only)
    img_q = describe_only["observations"].get("image_quality", "good")

    if provenance == "archive_pass":
        final["overall_status"] = "pass"
        final["issues_detected"] = []
        final["confidence"] = "high" if img_q == "good" else "low"
    elif provenance in ("staged_fail", "web_fail"):
        final["overall_status"] = "fail"
        final["issues_detected"] = []  # user fills these later
        final["confidence"] = "high"
    elif provenance == "unknown":
        final["overall_status"] = "describe_only"
        final["confidence"] = "describe_only"
        final["issues_detected"] = []
    else:
        raise ValueError(f"unknown provenance: {provenance}")
    return final


def label_one(
    client: httpx.Client,
    endpoint: str,
    model_name: str,
    system_prompt: str,
    describe_cls: type[BaseModel],
    final_cls: type[BaseModel],
    image_path: Path,
    use_json_mode: bool,
    provenance: str,
    stats: CategoryStats,
) -> tuple[dict[str, Any] | None, bool]:
    """Returns (label_dict, is_pending_review). label_dict is None if anything failed."""
    stats.attempted += 1

    try:
        body = build_request(system_prompt, encode_image(image_path), model_name, use_json_mode)
        resp = client.post(f"{endpoint}/chat/completions", json=body, timeout=180.0)
        resp.raise_for_status()
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        body_snippet = ""
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                body_snippet = exc.response.text[:300]
            except Exception:
                pass
        stats.transport_errors.append({"image": image_path.name, "error": f"{exc!r}"[:300], "body": body_snippet})
        return None, False

    if not content.strip() or REFUSAL_PATTERN.search(content.strip()):
        stats.refusals.append({"image": image_path.name, "snippet": content[:200]})
        return None, False

    raw_json = extract_json(content)
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        stats.json_parse_failures.append(
            {"image": image_path.name, "error": str(exc), "snippet": raw_json[:200]}
        )
        return None, False

    try:
        describe_only = describe_cls.model_validate(parsed).model_dump()
    except ValidationError as exc:
        stats.describe_schema_failures.append({"image": image_path.name, "error": str(exc)[:500]})
        return None, False

    stats.describe_only_valid += 1

    final = assemble_final_label(describe_only, provenance)

    if provenance == "unknown":
        # describe-only label saved to pending_review/, do not validate against production schema
        stats.final_valid += 1
        return final, True

    try:
        final_cls.model_validate(final)
    except ValidationError as exc:
        stats.final_schema_failures.append({"image": image_path.name, "error": str(exc)[:500]})
        return None, False

    stats.final_valid += 1
    if provenance in ("staged_fail", "web_fail"):
        stats.requires_human_labeling.append({"image": image_path.name})
    return final, False


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
) -> CategoryStats:
    canonical, system_prompt = CATEGORY_INFO[short_cat]
    describe_cls = DESCRIBE_ONLY_MODELS[canonical]
    final_cls = PRODUCTION_MODELS[short_cat]
    cat_dir = input_dir / short_cat
    out_dir = output_dir / short_cat
    out_dir.mkdir(parents=True, exist_ok=True)
    pending_dir = output_dir / "pending_review" / short_cat

    images = sample_images(cat_dir, count, seed)
    stats = CategoryStats()
    started = time.monotonic()

    for i, image_path in enumerate(images, 1):
        print(f"  [{i}/{len(images)}] {short_cat}/{image_path.name}", flush=True)
        label, is_pending = label_one(
            client,
            endpoint,
            model_name,
            system_prompt,
            describe_cls,
            final_cls,
            image_path,
            use_json_mode,
            provenance,
            stats,
        )
        if label is None:
            continue
        if is_pending:
            pending_dir.mkdir(parents=True, exist_ok=True)
            out_path = pending_dir / f"{image_path.stem}.json"
        else:
            out_path = out_dir / f"{image_path.stem}.json"
        out_path.write_text(json.dumps(label, indent=2) + "\n")

    stats.elapsed_seconds = time.monotonic() - started
    print(
        f"  → {short_cat}: final {stats.final_valid}/{stats.attempted} "
        f"(describe-valid={stats.describe_only_valid}, "
        f"parse_fail={len(stats.json_parse_failures)}, "
        f"describe_schema_fail={len(stats.describe_schema_failures)}, "
        f"final_schema_fail={len(stats.final_schema_failures)}, "
        f"refusal={len(stats.refusals)}, "
        f"transport={len(stats.transport_errors)}, "
        f"needs_human={len(stats.requires_human_labeling)}) "
        f"in {stats.elapsed_seconds:.1f}s",
        flush=True,
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Describe-only labeler for inspection images via vLLM-served Gemma 4 31B.")
    parser.add_argument("--category", choices=["fifth_wheel", "lock_jaws", "pintle_hook", "all"], required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True, help="Images to sample per category.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--provenance", choices=PROVENANCE_CHOICES, required=True,
                        help="Source of truth for the verdict. archive_pass=fleet-confirmed safe; "
                             "staged_fail/web_fail=user will hand-fill issues_detected; "
                             "unknown=keep describe-only and save to pending_review/.")
    parser.add_argument("--endpoint", default="http://localhost:8000/v1")
    parser.add_argument("--model", default="gemma-4-31b-labeler", help="vLLM served-model-name.")
    parser.add_argument(
        "--no-json-mode",
        action="store_true",
        help="Disable OpenAI response_format=json_object. Set if vLLM/Gemma 4 rejects it.",
    )
    args = parser.parse_args(argv)

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
                client=client,
                endpoint=args.endpoint,
                model_name=args.model,
                short_cat=short_cat,
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                count=args.count,
                seed=args.seed,
                use_json_mode=use_json_mode,
                provenance=args.provenance,
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
        "json_mode": use_json_mode,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "categories": per_cat,
    }
    (args.output_dir / "audit_log.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"\nDone in {total_elapsed:.1f}s. Audit log: {args.output_dir / 'audit_log.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
