#!/usr/bin/env python3
"""Sample a fixed-size, reproducible batch of images per category.

Stdlib only. Reads from a source archive structured as:
    <src>/<category>/<image files>
Writes a parallel structure under <out>/, optionally renaming categories
(e.g. lock_jaw -> lock_jaws) to match downstream schemas.

Also writes manifest.json next to the sampled images, and optionally
filters a source metadata.jsonl down to just the sampled rows.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_rename(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in values:
        if ":" not in v:
            raise SystemExit(f"--rename expects from:to, got {v!r}")
        src, dst = v.split(":", 1)
        out[src.strip()] = dst.strip()
    return out


def enumerate_images(cat_dir: Path) -> list[Path]:
    files: list[Path] = []
    for root, _, names in os.walk(cat_dir):
        root_p = Path(root)
        for n in names:
            if Path(n).suffix.lower() in IMAGE_EXTS:
                files.append(root_p / n)
    files.sort()
    return files


def file_ok(p: Path) -> bool:
    try:
        st = p.stat()
    except OSError:
        return False
    if st.st_size == 0:
        return False
    try:
        with p.open("rb") as f:
            f.read(1)
    except OSError:
        return False
    return True


def sample_category(
    cat: str,
    cat_dir: Path,
    n: int,
    seed: int,
) -> tuple[list[Path], list[str]]:
    """Return (sampled paths, warnings)."""
    warnings: list[str] = []
    pool = enumerate_images(cat_dir)
    if not pool:
        warnings.append(f"{cat}: no images found")
        return [], warnings

    rng = random.Random(f"{seed}:{cat}")
    indices = list(range(len(pool)))
    rng.shuffle(indices)

    requested = n
    if n > len(pool):
        warnings.append(
            f"{cat}: requested {n} but only {len(pool)} available; using all"
        )
        n = len(pool)

    picked: list[Path] = []
    cursor = 0
    while len(picked) < n and cursor < len(indices):
        candidate = pool[indices[cursor]]
        cursor += 1
        if file_ok(candidate):
            picked.append(candidate)
        else:
            warnings.append(f"{cat}: skipped unreadable/empty {candidate.name}")

    if len(picked) < requested and len(picked) < len(pool):
        warnings.append(
            f"{cat}: only {len(picked)} usable after filtering (requested {requested})"
        )

    return picked, warnings


def copy_files(picked: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in picked:
        dst = dest_dir / src.name
        shutil.copy2(src, dst)


def filter_metadata(
    metadata_path: Path,
    sampled_rel_paths: set[str],
    out_path: Path,
) -> tuple[int, int]:
    """Stream metadata.jsonl, keep rows whose relative_path is in the sampled set.

    Returns (rows_read, rows_kept).
    """
    rows_read = 0
    rows_kept = 0
    with metadata_path.open("r", encoding="utf-8") as fin, out_path.open(
        "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            rows_read += 1
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                row = json.loads(line_stripped)
            except json.JSONDecodeError:
                continue
            rel = row.get("relative_path")
            if rel and rel in sampled_rel_paths:
                fout.write(line if line.endswith("\n") else line + "\n")
                rows_kept += 1
    return rows_read, rows_kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, type=Path,
                    help="Source archive root containing category subdirs")
    ap.add_argument("--out", required=True, type=Path,
                    help="Output batch directory (will be created)")
    ap.add_argument("--per-category", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=20260511)
    ap.add_argument("--categories", default="fifth_wheel,lock_jaw,pintle_hook",
                    help="Comma-separated source category folder names")
    ap.add_argument("--rename", action="append", default=[],
                    help="Rename source->output category, e.g. lock_jaw:lock_jaws. Repeatable.")
    ap.add_argument("--metadata", type=Path, default=None,
                    help="Optional source metadata.jsonl to filter to sampled rows")
    ap.add_argument("--batch-name", default=None,
                    help="Logical batch name (default: out dir basename)")
    args = ap.parse_args()

    src: Path = args.src.resolve()
    out: Path = args.out.expanduser().resolve()
    if not src.is_dir():
        log(f"ERROR: source dir does not exist: {src}")
        return 2
    if out.exists() and any(out.iterdir()):
        log(f"ERROR: output dir is not empty: {out}")
        return 2

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    rename = parse_rename(args.rename)
    batch_name = args.batch_name or out.name

    out.mkdir(parents=True, exist_ok=True)

    all_warnings: list[str] = []
    per_category_counts: dict[str, int] = {}
    per_category_filenames: dict[str, list[str]] = {}
    sampled_rel_paths_src: set[str] = set()

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for cat in categories:
        cat_dir = src / cat
        if not cat_dir.is_dir():
            all_warnings.append(f"{cat}: source folder missing at {cat_dir}")
            per_category_counts[cat] = 0
            per_category_filenames[cat] = []
            continue

        out_cat = rename.get(cat, cat)
        log(f"sampling {cat} -> {out_cat} (n={args.per_category}, seed={args.seed})")
        picked, warns = sample_category(cat, cat_dir, args.per_category, args.seed)
        all_warnings.extend(warns)

        dest_dir = out / out_cat
        copy_files(picked, dest_dir)

        per_category_counts[out_cat] = len(picked)
        per_category_filenames[out_cat] = sorted(p.name for p in picked)
        for p in picked:
            sampled_rel_paths_src.add(f"{cat}/{p.name}")
        log(f"  copied {len(picked)} -> {dest_dir}")

    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    metadata_info = None
    if args.metadata:
        meta_src = args.metadata.expanduser().resolve()
        if not meta_src.is_file():
            all_warnings.append(f"metadata file not found: {meta_src}")
        else:
            meta_out = out / f"metadata_{batch_name}.jsonl"
            rows_read, rows_kept = filter_metadata(
                meta_src, sampled_rel_paths_src, meta_out
            )
            metadata_info = {
                "source": str(meta_src),
                "output": str(meta_out.relative_to(out)),
                "rows_read": rows_read,
                "rows_kept": rows_kept,
            }
            log(f"metadata: kept {rows_kept}/{rows_read} rows -> {meta_out}")
            missing = len(sampled_rel_paths_src) - rows_kept
            if missing > 0:
                all_warnings.append(
                    f"metadata: {missing} sampled images had no matching row in {meta_src.name}"
                )

    manifest = {
        "batch_name": batch_name,
        "started_utc": started,
        "finished_utc": finished,
        "seed": args.seed,
        "per_category_requested": args.per_category,
        "source_dir": str(src),
        "output_dir": str(out),
        "categories_source": categories,
        "rename": rename,
        "per_category_counts": per_category_counts,
        "total": sum(per_category_counts.values()),
        "metadata": metadata_info,
        "warnings": all_warnings,
        "filenames": per_category_filenames,
    }
    manifest_path = out / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    log(f"wrote manifest -> {manifest_path}")

    print(json.dumps({
        "batch_name": batch_name,
        "total": manifest["total"],
        "per_category_counts": per_category_counts,
        "warnings_count": len(all_warnings),
        "output_dir": str(out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
