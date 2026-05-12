#!/usr/bin/env python3
"""Generate comparison_v3_v4.md.

v3 layout: {labels-dir}/{category}/{stem}.json containing a production-schema label.
v4 layout: {labels-dir}/{category}/{stem}.json containing
    {image_id, category, localization, describe_output, production_schema, ...}

This script normalizes both into a production-schema label per image and then
reports the same metric family as compare_audits.py.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

CATEGORIES = ("fifth_wheel", "lock_jaws", "pintle_hook")
JUDGMENT_WORDS = (
    "pass", "fail", "safe", "unsafe", "high hook", "high-hook",
    "missing", "wrong", "correct", "incorrect", "broken",
)
EXCLUDE_PHRASES = (
    "safety pin", "safety pins", "safety chain", "safety chains",
    "safety system", "safety check", "safety net",
)
JUDGMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in JUDGMENT_WORDS) + r")\b",
    re.IGNORECASE,
)
EXCLUDE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in EXCLUDE_PHRASES) + r")\b",
    re.IGNORECASE,
)


def is_v4_label(d: dict[str, Any]) -> bool:
    return "production_schema" in d and "localization" in d


def normalize(d: dict[str, Any]) -> dict[str, Any]:
    return d["production_schema"] if is_v4_label(d) else d


def load_labels(root: Path) -> dict[str, list[dict[str, Any]]]:
    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for cat in CATEGORIES:
        cat_dir = root / cat
        if not cat_dir.exists():
            continue
        for p in sorted(cat_dir.glob("*.json")):
            try:
                by_cat[cat].append(json.loads(p.read_text()))
            except json.JSONDecodeError:
                continue
    return by_cat


def load_localization(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Pull just the localization sub-objects from v4 labels."""
    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for cat in CATEGORIES:
        cat_dir = root / cat
        if not cat_dir.exists():
            continue
        for p in sorted(cat_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            if is_v4_label(d):
                by_cat[cat].append(d["localization"])
    return by_cat


def count_field(labels: list[dict[str, Any]], path: list[str], match: Any) -> int:
    n = 0
    for d in labels:
        cur: Any = normalize(d)
        for k in path:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                cur = None
                break
        if callable(match):
            if match(cur):
                n += 1
        elif cur == match:
            n += 1
    return n


def judgment_hits(labels: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    hits: list[tuple[str, list[str]]] = []
    for d in labels:
        s = normalize(d).get("human_readable_summary", "") or ""
        scrubbed = EXCLUDE_RE.sub(" ", s)
        found = sorted({m.group(0).lower() for m in JUDGMENT_RE.finditer(scrubbed)})
        if found:
            hits.append((s, found))
    return hits


def fmt_delta(v3: int, v4: int) -> str:
    delta = v4 - v3
    if delta == 0:
        return f"{v3} → {v4} (=)"
    arrow = "↑" if delta > 0 else "↓"
    return f"{v3} → {v4} ({arrow}{abs(delta)})"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v3-dir", type=Path, required=True)
    p.add_argument("--v4-dir", type=Path, required=True)
    p.add_argument("--v4-audit-log", type=Path, default=None,
                   help="Path to v4 audit_log.json (defaults to v4-dir/audit_log.json)")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    v4_audit_path = args.v4_audit_log or (args.v4_dir / "audit_log.json")

    v3 = load_labels(args.v3_dir)
    v4 = load_labels(args.v4_dir)
    v4_loc = load_localization(args.v4_dir)

    lines: list[str] = []
    lines.append(f"# v3 vs v4 labeler audit comparison\n")
    lines.append(f"- v3 source: `{args.v3_dir}`")
    lines.append(f"- v4 source: `{args.v4_dir}`\n")

    # 1. Localization stats per category
    lines.append("## 1. Localization stats (v4 only)\n")
    lines.append("| category | success | refused | failed | too_large | parse_err | fallback | median area | p95 area |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    audit = json.loads(v4_audit_path.read_text()) if v4_audit_path.exists() else {"categories": {}}
    for cat in CATEGORIES:
        stats = audit.get("categories", {}).get(cat, {})
        L = stats.get("localization", {})
        lines.append(
            f"| {cat} | {L.get('success', '?')} | {L.get('refused', '?')} | "
            f"{L.get('failed', '?')} | {L.get('too_large', '?')} | {L.get('parse_error', '?')} | "
            f"{L.get('fellback_to_full_image', '?')} | {L.get('box_area_fraction_median', '?')} | "
            f"{L.get('box_area_fraction_p95', '?')} |"
        )

    # 2. Per-field deltas
    lines.append("\n## 2. Per-field deltas (v3 → v4)\n")

    # Headline pintle_hook safety_pin_visible
    a = count_field(v3["pintle_hook"], ["observations", "safety_pin_visible"], True)
    b = count_field(v4["pintle_hook"], ["observations", "safety_pin_visible"], True)
    lines.append(f"### pintle_hook `safety_pin_visible == true`\n")
    lines.append(f"{fmt_delta(a, b)} — was the v3 headline (0 → 28). Crop pass shouldn't regress.\n")

    # fifth_wheel gap distribution
    lines.append("### fifth_wheel `visible_gap_between_apron_and_plate` distribution\n")
    lines.append("| value | v3 | v4 |")
    lines.append("|---|---:|---:|")
    for v in ("none", "minor", "obvious"):
        a = count_field(v3["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], v)
        b = count_field(v4["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], v)
        lines.append(f"| {v} | {a} | {b} |")
    a = count_field(v3["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], lambda x: x in ("minor", "obvious"))
    b = count_field(v4["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], lambda x: x in ("minor", "obvious"))
    lines.append(f"\n`gap ∈ {{minor, obvious}}` on archive_pass images: {fmt_delta(a, b)}")
    lines.append("(Lower = fewer hallucinated gaps on a known-good archive.)\n")

    # lock_jaws jaws_fully_closed yes
    a = count_field(v3["lock_jaws"], ["observations", "jaws_fully_closed_around_kingpin"], "yes")
    b = count_field(v4["lock_jaws"], ["observations", "jaws_fully_closed_around_kingpin"], "yes")
    lines.append(f"### lock_jaws `jaws_fully_closed_around_kingpin == 'yes'`\n")
    lines.append(f"{fmt_delta(a, b)} — note most v4 lock_jaws labels fell back to full image because localization refused.\n")

    # image_quality poor
    lines.append("### `image_quality == 'poor'` (lower is better on archive_pass)\n")
    lines.append("| category | v3 → v4 |")
    lines.append("|---|---|")
    for cat in CATEGORIES:
        a = count_field(v3[cat], ["observations", "image_quality"], "poor")
        b = count_field(v4[cat], ["observations", "image_quality"], "poor")
        lines.append(f"| {cat} | {fmt_delta(a, b)} |")

    # Other observation deltas — chains_count, hook_latch
    lines.append("\n### pintle_hook secondary fields\n")
    a = count_field(v3["pintle_hook"], ["observations", "hook_latch_state"], "closed")
    b = count_field(v4["pintle_hook"], ["observations", "hook_latch_state"], "closed")
    lines.append(f"- `hook_latch_state == 'closed'`: {fmt_delta(a, b)}")
    a = count_field(v3["pintle_hook"], ["observations", "safety_chains_count"], lambda x: x == 2)
    b = count_field(v4["pintle_hook"], ["observations", "safety_chains_count"], lambda x: x == 2)
    lines.append(f"- `safety_chains_count == 2`: {fmt_delta(a, b)}")
    a = count_field(v3["pintle_hook"], ["observations", "safety_chains_hooked"], True)
    b = count_field(v4["pintle_hook"], ["observations", "safety_chains_hooked"], True)
    lines.append(f"- `safety_chains_hooked == true`: {fmt_delta(a, b)}")
    a = count_field(v3["pintle_hook"], ["observations", "safety_chains_crossed"], True)
    b = count_field(v4["pintle_hook"], ["observations", "safety_chains_crossed"], True)
    lines.append(f"- `safety_chains_crossed == true`: {fmt_delta(a, b)}")

    # 3. Elapsed time
    lines.append("\n## 3. Elapsed time\n")
    v3_total = "?"
    v3_audit = args.v3_dir / "audit_log.json"
    if v3_audit.exists():
        v3_d = json.loads(v3_audit.read_text())
        v3_total = f"{v3_d.get('total_elapsed_seconds', '?')}s"
    v4_total = f"{audit.get('total_elapsed_seconds', '?')}s"
    lines.append(f"- v3 (single-pass): {v3_total}")
    lines.append(f"- v4 (two-pass): {v4_total}")
    lines.append("\nPer-category pass1 + pass2 in v4:")
    lines.append("| category | pass1 (localize) | pass2 (describe) |")
    lines.append("|---|---:|---:|")
    for cat in CATEGORIES:
        s = audit.get("categories", {}).get(cat, {})
        lines.append(f"| {cat} | {s.get('pass1_seconds', '?')}s | {s.get('pass2_seconds', '?')}s |")

    # Judgment-language leak (sanity carryover)
    total_hits = sum(len(judgment_hits(v4[c])) for c in CATEGORIES)
    lines.append("\n## 4. Sanity: judgment-language leakage in v4 summaries\n")
    lines.append(f"Words checked: {', '.join(JUDGMENT_WORDS)}")
    lines.append(f"\nTotal v4 summaries with judgment words (excluding 'safety pin/chains'): **{total_hits}** / {sum(len(v4[c]) for c in CATEGORIES)}")

    args.out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
