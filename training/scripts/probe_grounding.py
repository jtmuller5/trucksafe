#!/usr/bin/env python3
"""Probe Gemma 4 31B's bounding-box output format.

Sends a localize prompt to vLLM with a handful of inspection images and
prints the raw model output, plus the image dimensions for reference.
Run once at the start of v4 — let the model tell you its format, then
write the parser to match.
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from pathlib import Path

import httpx
from PIL import Image

CATEGORY_PROMPTS = {
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


def sample_image(category_dir: Path, seed: int) -> Path:
    files = sorted(p for p in category_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"})
    rng = random.Random(seed)
    return rng.choice(files)


def probe(client: httpx.Client, endpoint: str, model: str, category: str, image_path: Path) -> None:
    img = Image.open(image_path)
    w, h = img.size
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CATEGORY_PROMPTS[category]},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    resp = client.post(f"{endpoint}/chat/completions", json=body, timeout=120.0)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    print(f"=== {category} :: {image_path.name} (image {w}x{h}) ===")
    print(content)
    print()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, default=Path("data/images/sample-batch-01"))
    p.add_argument("--endpoint", default="http://localhost:8000/v1")
    p.add_argument("--model", default="gemma-4-31b-labeler")
    p.add_argument("--per-category", type=int, default=2)
    args = p.parse_args()

    with httpx.Client() as client:
        for category in CATEGORY_PROMPTS:
            cat_dir = args.input_dir / category
            for i in range(args.per_category):
                img_path = sample_image(cat_dir, seed=20260511 + i * 7)
                try:
                    probe(client, args.endpoint, args.model, category, img_path)
                except Exception as e:
                    print(f"ERR {category}/{img_path.name}: {e!r}")
                    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
