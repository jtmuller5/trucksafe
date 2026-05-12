#!/usr/bin/env python3
"""Review aid for an audit-batch label run.

Two modes:
  * Text — dense one-liner per image (for SSH scrolling) or verbose (default).
  * HTML — static side-by-side page with thumbnails for review on the MacBook.
            Writes review.html next to the labels; serve the parent of the
            images directory with `python -m http.server`, or rsync the tree
            out to the MacBook.

Usage:
  audit_review.py --labels-dir data/labels/audit-batch-01 \\
                  --images-dir data/images/sample-batch-01

  audit_review.py --labels-dir ... --images-dir ... --dense
  audit_review.py --labels-dir ... --images-dir ... --status fail
  audit_review.py --labels-dir ... --images-dir ... --html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

CATEGORIES = ("fifth_wheel", "lock_jaws", "pintle_hook")
STATUS_ORDER = {"fail": 0, "retake": 1, "pass": 2}
STATUS_COLORS = {"fail": "#c00", "retake": "#c70", "pass": "#070"}


def load_labels(labels_dir: Path, category: str) -> list[tuple[str, dict[str, Any]]]:
    cat_dir = labels_dir / category
    if not cat_dir.exists():
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for p in sorted(cat_dir.glob("*.json")):
        try:
            out.append((p.stem, json.loads(p.read_text())))
        except json.JSONDecodeError:
            continue
    return out


def resolve_image(images_dir: Path, category: str, stem: str) -> Path | None:
    cat_dir = images_dir / category
    for ext in (".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"):
        candidate = cat_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def format_observations(label: dict[str, Any]) -> str:
    obs = label.get("observations", {})
    return ", ".join(f"{k}={v}" for k, v in obs.items())


def print_verbose(idx: int, total: int, category: str, stem: str, label: dict[str, Any], image_path: Path | None) -> None:
    status = label.get("overall_status", "?")
    confidence = label.get("confidence", "?")
    summary = label.get("human_readable_summary", "")
    issues = label.get("issues_detected", [])
    img = f" [{image_path}]" if image_path else " [image not found]"
    print(f"[{idx}/{total}] {category}/{stem}.jpg{img}")
    print(f"  status: {status} | confidence: {confidence}")
    print(f"  observations: {format_observations(label)}")
    print(f"  summary: {summary!r}")
    print(f"  issues: {issues}")
    print()


def print_dense(idx: int, total: int, category: str, stem: str, label: dict[str, Any]) -> None:
    status = label.get("overall_status", "?")
    confidence = label.get("confidence", "?")
    issues = ",".join(label.get("issues_detected", [])) or "-"
    print(f"[{idx:>3}/{total}] {category[:11]:11s} {stem:32s} {status:6s} {confidence:6s} {issues}")


def open_image(image_path: Path) -> None:
    opener = "xdg-open" if sys.platform.startswith("linux") else "open"
    subprocess.Popen([opener, str(image_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def filter_label(label: dict[str, Any], status: str | None) -> bool:
    if status is None:
        return True
    return label.get("overall_status") == status


def write_html(
    labels_dir: Path,
    images_dir: Path,
    status: str | None,
    out_path: Path,
) -> int:
    rows: list[str] = []
    count = 0
    for category in CATEGORIES:
        cat_labels = load_labels(labels_dir, category)
        cat_labels.sort(key=lambda kv: STATUS_ORDER.get(kv[1].get("overall_status", ""), 99))
        for stem, label in cat_labels:
            if not filter_label(label, status):
                continue
            count += 1
            image_path = resolve_image(images_dir, category, stem)
            img_src = ""
            if image_path is not None:
                img_src = os.path.relpath(image_path.resolve(), out_path.parent.resolve())
            color = STATUS_COLORS.get(label.get("overall_status", ""), "#666")
            label_json = html.escape(json.dumps(label, indent=2))
            issues = label.get("issues_detected", []) or []
            issues_str = html.escape(", ".join(issues)) if issues else "—"
            rows.append(
                f"""
<section class="card">
  <div class="img">{f'<img src="{html.escape(img_src)}" loading="lazy" />' if img_src else '<em>image missing</em>'}</div>
  <div class="meta">
    <h3>{html.escape(category)}/{html.escape(stem)}.jpg</h3>
    <p>
      <span class="status" style="background:{color}">{html.escape(label.get('overall_status', '?'))}</span>
      <span class="conf">confidence: {html.escape(label.get('confidence', '?'))}</span>
    </p>
    <p class="summary">{html.escape(label.get('human_readable_summary', ''))}</p>
    <p class="issues"><strong>issues:</strong> {issues_str}</p>
    <details><summary>raw JSON</summary><pre>{label_json}</pre></details>
  </div>
</section>
"""
            )

    title = f"audit review — {labels_dir.name}"
    if status:
        title += f" (status={status})"

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 24px; background: #fafafa; color: #222; }}
  h1 {{ margin: 0 0 24px; }}
  .card {{ display: grid; grid-template-columns: 360px 1fr; gap: 18px; background: white; padding: 16px; margin-bottom: 16px; border: 1px solid #ddd; border-radius: 8px; }}
  .img img {{ width: 100%; height: auto; border-radius: 4px; background: #eee; }}
  .meta h3 {{ margin: 0 0 8px; font-size: 14px; color: #555; font-family: ui-monospace, monospace; }}
  .status {{ display: inline-block; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 12px; }}
  .conf {{ margin-left: 12px; color: #666; font-size: 13px; }}
  .summary {{ margin: 8px 0; line-height: 1.5; }}
  .issues {{ margin: 4px 0; font-size: 13px; color: #555; }}
  pre {{ background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
  details {{ margin-top: 8px; }}
  summary {{ cursor: pointer; color: #06c; font-size: 13px; }}
</style>
</head>
<body>
<h1>{html.escape(title)} — {count} labels</h1>
{''.join(rows)}
</body>
</html>
"""
    out_path.write_text(page)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--category", choices=[*CATEGORIES, "all"], default="all")
    parser.add_argument("--status", choices=["pass", "fail", "retake"], default=None,
                        help="Show only labels with this overall_status.")
    parser.add_argument("--dense", action="store_true", help="One line per image.")
    parser.add_argument("--open", action="store_true",
                        help="Open each image with xdg-open/open. Local use only.")
    parser.add_argument("--html", action="store_true",
                        help="Write a side-by-side review.html into --labels-dir.")
    args = parser.parse_args(argv)

    cats = list(CATEGORIES) if args.category == "all" else [args.category]

    if args.html:
        out_path = args.labels_dir / "review.html"
        count = write_html(args.labels_dir, args.images_dir, args.status, out_path)
        print(f"Wrote {count} cards to {out_path}")
        return 0

    all_items: list[tuple[str, str, dict[str, Any]]] = []
    for cat in cats:
        for stem, label in load_labels(args.labels_dir, cat):
            if filter_label(label, args.status):
                all_items.append((cat, stem, label))

    total = len(all_items)
    if total == 0:
        print("No labels matched.")
        return 0

    if args.dense:
        print(f"  idx        category    image                            status confidence issues")
        for i, (cat, stem, label) in enumerate(all_items, 1):
            print_dense(i, total, cat, stem, label)
    else:
        for i, (cat, stem, label) in enumerate(all_items, 1):
            image_path = resolve_image(args.images_dir, cat, stem)
            print_verbose(i, total, cat, stem, label, image_path)
            if args.open and image_path is not None:
                open_image(image_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
