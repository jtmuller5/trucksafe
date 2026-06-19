#!/usr/bin/env python3
"""Three-column HTML review for v4 labels: original | crop+box | describe JSON.

Renders the original image with the localization box overlaid in red,
the crop sent to Pass 2, and the describe-only/production-schema label.

Usage:
  audit_review_v4.py --labels-dir data/labels/audit-batch-03 \\
                     --images-dir data/images/sample-batch-01
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

CATEGORIES = ("fifth_wheel", "lock_jaws", "pintle_hook")
STATUS_COLORS = {
    "success": "#070",
    "refused": "#c70",
    "failed": "#c00",
    "too_large": "#c70",
    "parse_error": "#c00",
}


def load_labels(labels_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat in CATEGORIES:
        cat_dir = labels_dir / cat
        if not cat_dir.exists():
            continue
        for p in sorted(cat_dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text()))
            except json.JSONDecodeError:
                continue
    return out


def resolve_original(images_dir: Path, category: str, stem: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".JPG", ".JPEG"):
        candidate = images_dir / category / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def render(labels_dir: Path, images_dir: Path, out_path: Path, sample: int | None, seed: int) -> int:
    labels = load_labels(labels_dir)
    if sample:
        # Even split across categories if possible
        per_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
        for d in labels:
            per_cat[d["category"]].append(d)
        rng = random.Random(seed)
        picked: list[dict[str, Any]] = []
        per_each = sample // len(CATEGORIES)
        for c in CATEGORIES:
            picked.extend(rng.sample(per_cat[c], min(per_each, len(per_cat[c]))))
        labels = picked

    rows: list[str] = []
    for idx, d in enumerate(labels, 1):
        cat = d["category"]
        stem = d["image_id"]
        loc = d["localization"]
        ps = d["production_schema"]

        original = resolve_original(images_dir, cat, stem)
        original_src = ""
        original_natural = ""
        if original is not None:
            original_src = os.path.relpath(original.resolve(), out_path.parent.resolve())

        crop_src = ""
        if loc.get("crop_path"):
            crop_abs = (labels_dir / loc["crop_path"]).resolve()
            if crop_abs.exists():
                crop_src = os.path.relpath(crop_abs, out_path.parent.resolve())

        # Box-on-original overlay (CSS positioning).
        # box_pixels is [y1,x1,y2,x2] in original-image space.
        overlay_html = ""
        ebox = loc.get("expanded_box_pixels")
        if ebox and original is not None:
            from PIL import Image as _Img
            img_w, img_h = _Img.open(original).size
            y1, x1, y2, x2 = ebox
            top = y1 / img_h * 100
            left = x1 / img_w * 100
            height = (y2 - y1) / img_h * 100
            width = (x2 - x1) / img_w * 100
            overlay_html = (
                f'<div class="overlay" style="top:{top:.1f}%;left:{left:.1f}%;'
                f'width:{width:.1f}%;height:{height:.1f}%"></div>'
            )

        status = loc.get("status", "?")
        color = STATUS_COLORS.get(status, "#666")
        loc_summary = (
            f'<span class="badge" style="background:{color}">{html.escape(status)}</span>'
            f'<span class="muted"> aspect_corrected={loc.get("aspect_corrected")} '
            f'fallback={"yes" if loc.get("crop_path") is None else "no"}</span>'
        )

        describe_json = html.escape(json.dumps(d["describe_output"], indent=2))
        ps_summary = html.escape(ps.get("human_readable_summary", ""))
        ps_obs = html.escape(
            ", ".join(f"{k}={v}" for k, v in ps.get("observations", {}).items())
        )

        rows.append(f"""
<section class="card">
  <h3>[{idx}] {html.escape(cat)}/{html.escape(stem)}</h3>
  <div class="grid">
    <div class="col">
      <div class="col-label">original + expanded box</div>
      <div class="img-wrap">
        {f'<img src="{html.escape(original_src)}" loading="lazy"/>' if original_src else '<em>missing</em>'}
        {overlay_html}
      </div>
    </div>
    <div class="col">
      <div class="col-label">crop (input to Pass 2)</div>
      <div class="img-wrap">
        {f'<img src="{html.escape(crop_src)}" loading="lazy"/>' if crop_src else '<em>(no crop; fell back to full image)</em>'}
      </div>
    </div>
    <div class="col">
      <div class="col-label">describe + verdict</div>
      <p>{loc_summary}</p>
      <p class="summary">{ps_summary}</p>
      <p class="muted"><strong>obs:</strong> {ps_obs}</p>
      <p class="muted"><strong>status:</strong> {html.escape(ps.get('overall_status', ''))} • <strong>conf:</strong> {html.escape(ps.get('confidence', ''))}</p>
      <details><summary>raw describe JSON</summary><pre>{describe_json}</pre></details>
    </div>
  </div>
</section>
""")

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>v4 audit review — {html.escape(labels_dir.name)}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 18px; background: #fafafa; color: #222; }}
  h1 {{ margin: 0 0 20px; }}
  .card {{ background: white; padding: 14px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 8px; }}
  .card h3 {{ margin: 0 0 10px; font-family: ui-monospace, monospace; font-size: 13px; color: #444; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }}
  .col-label {{ font-size: 12px; color: #888; margin-bottom: 6px; }}
  .img-wrap {{ position: relative; background: #eee; border-radius: 4px; overflow: hidden; }}
  .img-wrap img {{ display: block; width: 100%; height: auto; }}
  .overlay {{ position: absolute; border: 3px solid #f00; box-shadow: 0 0 0 1px rgba(0,0,0,0.6) inset; pointer-events: none; }}
  .badge {{ display: inline-block; color: white; padding: 1px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
  .summary {{ line-height: 1.45; }}
  .muted {{ color: #666; font-size: 12px; margin: 4px 0; }}
  pre {{ background: #f3f3f3; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 11px; }}
  details summary {{ cursor: pointer; color: #06c; font-size: 12px; }}
</style>
</head>
<body>
<h1>v4 audit review — {html.escape(labels_dir.name)} • {len(labels)} cards</h1>
{''.join(rows)}
</body>
</html>
"""
    out_path.write_text(page)
    return len(labels)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--labels-dir", type=Path, required=True)
    p.add_argument("--images-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None, help="default: labels-dir/review.html")
    p.add_argument("--sample", type=int, default=None,
                   help="If set, only render this many cards (evenly across categories) — useful for the spot-check.")
    p.add_argument("--seed", type=int, default=20260511)
    args = p.parse_args()
    out_path = args.out or (args.labels_dir / "review.html")
    n = render(args.labels_dir, args.images_dir, out_path, args.sample, args.seed)
    print(f"Wrote {n} cards to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
