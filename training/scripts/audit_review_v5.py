#!/usr/bin/env python3
"""HTML reviewer for v5 labels (nested schema).

Per-image card:
  - Original photo (with red overlay box if localization succeeded)
  - Crop sent to Pass 2 (or "full image — no localization" for lock_jaws)
  - Inspection / evidence type + factual summary + verdict
  - Evidence-block fields rendered as a flat key:value list, with the
    OTHER sub-block shown as `null` so the conditional structure is visible

Open `:8770/labels/audit-batch-04/review.html` to view over Tailscale.
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

SOURCE_FOLDERS = ("fifth_wheel", "lock_jaws", "pintle_hook")
STATUS_COLORS = {
    "success": "#070", "refused": "#c70", "failed": "#c00",
    "too_large": "#c70", "parse_error": "#c00", None: "#666",
}
VERDICT_COLORS = {"pass": "#070", "fail": "#c00", "unclear": "#c70", "describe_only": "#666"}


def load_labels(labels_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sf in SOURCE_FOLDERS:
        cat_dir = labels_dir / sf
        if not cat_dir.exists():
            continue
        for p in sorted(cat_dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text()))
            except json.JSONDecodeError:
                continue
    return out


def resolve_original(images_dir: Path, source_folder: str, stem: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".JPG", ".JPEG"):
        c = images_dir / source_folder / f"{stem}{ext}"
        if c.exists():
            return c
    return None


def render(labels_dir: Path, images_dir: Path, out_path: Path, sample: int | None, seed: int) -> int:
    labels = load_labels(labels_dir)
    if sample:
        per_sf: dict[str, list[dict[str, Any]]] = {sf: [] for sf in SOURCE_FOLDERS}
        for d in labels:
            per_sf[d["source_folder"]].append(d)
        rng = random.Random(seed)
        per_each = sample // len(SOURCE_FOLDERS)
        picked: list[dict[str, Any]] = []
        for sf in SOURCE_FOLDERS:
            picked.extend(rng.sample(per_sf[sf], min(per_each, len(per_sf[sf]))))
        labels = picked

    rows: list[str] = []
    for idx, d in enumerate(labels, 1):
        sf = d["source_folder"]
        stem = d["image_id"]
        ev = d["evidence_type"]
        loc = d.get("localization")
        ps = d["production_schema"]

        original = resolve_original(images_dir, sf, stem)
        original_src = os.path.relpath(original.resolve(), out_path.parent.resolve()) if original else ""

        crop_src = ""
        if loc and loc.get("crop_path"):
            crop_abs = (labels_dir / loc["crop_path"]).resolve()
            if crop_abs.exists():
                crop_src = os.path.relpath(crop_abs, out_path.parent.resolve())

        overlay_html = ""
        if loc and original is not None:
            box = loc.get("expanded_box_pixels") or loc.get("box_pixels")
            if box:
                from PIL import Image as _Img
                img_w, img_h = _Img.open(original).size
                y1, x1, y2, x2 = box
                overlay_html = (
                    f'<div class="overlay" style="top:{y1/img_h*100:.1f}%;'
                    f'left:{x1/img_w*100:.1f}%;'
                    f'width:{(x2-x1)/img_w*100:.1f}%;'
                    f'height:{(y2-y1)/img_h*100:.1f}%"></div>'
                )

        # Header line — handle both per-image-detection ("status") and
        # fixed-band ("strategy: fixed_band") localizations.
        if loc is None:
            loc_status = "skipped"
        elif loc.get("strategy") == "fixed_band":
            loc_status = f"fixed_band {loc.get('band_rows', [])}"
        else:
            loc_status = loc.get("status", "?")
        loc_color = STATUS_COLORS.get(loc_status if loc_status in STATUS_COLORS else None, "#666")
        verdict = ps.get("verdict", "?")
        v_color = VERDICT_COLORS.get(verdict, "#666")
        img_q = ps.get("image_quality", "?")

        # Render block fields. For side_view, expand the populated manufacturer
        # sub-object inline and collapse null sub-objects to a one-liner.
        block = ps.get(ev, {}) or {}
        rows_html: list[str] = []
        for k, v in block.items():
            if isinstance(v, dict):
                inner = "".join(
                    f"<li><b>{html.escape(ik)}</b>: <code>{html.escape(str(iv))}</code></li>"
                    for ik, iv in v.items()
                )
                rows_html.append(f"<li><b>{html.escape(k)}</b>: <ul class='block'>{inner}</ul></li>")
            elif v is None:
                rows_html.append(f"<li class='muted'><b>{html.escape(k)}</b>: null</li>")
            else:
                rows_html.append(f"<li><b>{html.escape(k)}</b>: <code>{html.escape(str(v))}</code></li>")
        block_html = "<ul class='block'>" + "".join(rows_html) + "</ul>"

        other_block_html = ""
        if d["inspection_type"] == "fifth_wheel_coupling":
            other = "lock_jaws_underneath" if ev == "side_view" else "side_view"
            other_block_html = f"<p class='muted'><i>{other}</i>: null</p>"

        summary = html.escape(ps.get("factual_summary", ""))

        crop_block = (
            f'<img src="{html.escape(crop_src)}" loading="lazy"/>' if crop_src
            else '<em>(no crop available)</em>'
        )

        rows.append(f"""
<section class="card">
  <h3>[{idx}] {html.escape(sf)}/{html.escape(stem)} → <span class="pill">{html.escape(ev)}</span></h3>
  <div class="grid">
    <div class="col">
      <div class="col-label">original{' + box' if overlay_html else ''}</div>
      <div class="img-wrap">
        {f'<img src="{html.escape(original_src)}" loading="lazy"/>' if original_src else '<em>missing</em>'}
        {overlay_html}
      </div>
    </div>
    <div class="col">
      <div class="col-label">describe input (crop or full)</div>
      <div class="img-wrap">{crop_block}</div>
      <p class="muted"><span class="badge" style="background:{loc_color}">localize: {html.escape(loc_status)}</span></p>
    </div>
    <div class="col">
      <div class="col-label">v5 output</div>
      <p>
        <span class="badge" style="background:{v_color}">{html.escape(verdict)}</span>
        <span class="muted">img_q: {html.escape(img_q)}</span>
      </p>
      <p class="summary">{summary}</p>
      <div class="col-label">{html.escape(ev)} block</div>
      {block_html}
      {other_block_html}
    </div>
  </div>
</section>
""")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>v5 audit review — {html.escape(labels_dir.name)}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 18px; background: #fafafa; color: #222; }}
  h1 {{ margin: 0 0 20px; }}
  .card {{ background: white; padding: 14px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 8px; }}
  .card h3 {{ margin: 0 0 10px; font-family: ui-monospace, monospace; font-size: 13px; color: #444; }}
  .pill {{ background: #06c; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-family: ui-monospace, monospace; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }}
  .col-label {{ font-size: 12px; color: #888; margin-bottom: 6px; }}
  .img-wrap {{ position: relative; background: #eee; border-radius: 4px; overflow: hidden; min-height: 80px; }}
  .img-wrap img {{ display: block; width: 100%; height: auto; }}
  .overlay {{ position: absolute; border: 3px solid #f00; box-shadow: 0 0 0 1px rgba(0,0,0,0.6) inset; pointer-events: none; }}
  .badge {{ display: inline-block; color: white; padding: 1px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
  .summary {{ line-height: 1.45; margin: 6px 0; }}
  .muted {{ color: #666; font-size: 12px; margin: 4px 0; }}
  .block {{ margin: 0; padding-left: 20px; font-size: 12px; }}
  .block li {{ margin: 2px 0; }}
  code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }}
</style></head><body>
<h1>v5 audit review — {html.escape(labels_dir.name)} • {len(labels)} cards</h1>
{''.join(rows)}
</body></html>
"""
    out_path.write_text(page)
    return len(labels)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--labels-dir", type=Path, required=True)
    p.add_argument("--images-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--sample", type=int, default=None)
    p.add_argument("--seed", type=int, default=20260511)
    args = p.parse_args()
    out_path = args.out or (args.labels_dir / "review.html")
    n = render(args.labels_dir, args.images_dir, out_path, args.sample, args.seed)
    print(f"Wrote {n} cards to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
