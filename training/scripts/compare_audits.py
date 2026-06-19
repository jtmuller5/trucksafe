#!/usr/bin/env python3
"""Generate comparison_v2_v3.md between two audit batches.

Compares per-category, per-field counts between two label directories.
The v2 baseline came from the judge-style prompts; v3 comes from the
describe-only prompts plus runner-assembled verdicts.
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
# Multi-token phrases that legitimately contain a judgment word
# (e.g., "safety pin"). Strip these out before scanning for judgment-only hits.
EXCLUDE_PHRASES = (
    "safety pin", "safety pins", "safety chain", "safety chains",
    "safety system", "safety check", "safety pin appears", "safety net",
)


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


def count_field(labels: list[dict[str, Any]], path: list[str], match: Any) -> int:
    n = 0
    for d in labels:
        cur: Any = d
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


# Word-boundary regex — "safe" must be a standalone word, not part of "safety".
JUDGMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in JUDGMENT_WORDS) + r")\b",
    re.IGNORECASE,
)
EXCLUDE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in EXCLUDE_PHRASES) + r")\b",
    re.IGNORECASE,
)


def judgment_hits(labels: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    hits: list[tuple[str, list[str]]] = []
    for d in labels:
        s = d.get("human_readable_summary", "") or ""
        scrubbed = EXCLUDE_RE.sub(" ", s)
        found = sorted({m.group(0).lower() for m in JUDGMENT_RE.finditer(scrubbed)})
        if found:
            hits.append((s, found))
    return hits


def fmt_delta(v2: int, v3: int) -> str:
    delta = v3 - v2
    if delta == 0:
        return f"{v2} → {v3} (=)"
    arrow = "↑" if delta > 0 else "↓"
    return f"{v2} → {v3} ({arrow}{abs(delta)})"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v2-dir", type=Path, required=True)
    p.add_argument("--v3-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    v2 = load_labels(args.v2_dir)
    v3 = load_labels(args.v3_dir)

    lines: list[str] = []
    lines.append(f"# v2 vs v3 labeler audit comparison\n")
    lines.append(f"- v2 source: `{args.v2_dir}`\n")
    lines.append(f"- v3 source: `{args.v3_dir}`\n")

    # Label counts per category
    lines.append("\n## Per-category label counts\n")
    lines.append("| category | v2 | v3 |")
    lines.append("|---|---:|---:|")
    for cat in CATEGORIES:
        lines.append(f"| {cat} | {len(v2[cat])} | {len(v3[cat])} |")

    # image_quality: poor
    lines.append("\n## `image_quality: poor` counts (lower is better for archive_pass)\n")
    lines.append("| category | v2 → v3 |")
    lines.append("|---|---|")
    for cat in CATEGORIES:
        a = count_field(v2[cat], ["observations", "image_quality"], "poor")
        b = count_field(v3[cat], ["observations", "image_quality"], "poor")
        lines.append(f"| {cat} | {fmt_delta(a, b)} |")

    # fifth_wheel: minor|obvious gap
    a = count_field(v2["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], lambda x: x in ("minor", "obvious"))
    b = count_field(v3["fifth_wheel"], ["observations", "visible_gap_between_apron_and_plate"], lambda x: x in ("minor", "obvious"))
    lines.append(f"\n## fifth_wheel: `visible_gap_between_apron_and_plate ∈ {{minor, obvious}}`\n")
    lines.append(f"{fmt_delta(a, b)} — v3 should be lower (no priming to find gaps).")

    # lock_jaws: jaws_fully_closed_around_kingpin yes
    a = count_field(v2["lock_jaws"], ["observations", "jaws_fully_closed_around_kingpin"], "yes")
    b = count_field(v3["lock_jaws"], ["observations", "jaws_fully_closed_around_kingpin"], "yes")
    lines.append(f"\n## lock_jaws: `jaws_fully_closed_around_kingpin == 'yes'`\n")
    lines.append(f"{fmt_delta(a, b)} — v3 should be higher (grease/dirt no longer triggers retake).")

    # pintle_hook: safety_pin_visible true
    a = count_field(v2["pintle_hook"], ["observations", "safety_pin_visible"], True)
    b = count_field(v3["pintle_hook"], ["observations", "safety_pin_visible"], True)
    lines.append(f"\n## pintle_hook: `safety_pin_visible == true`\n")
    lines.append(f"{fmt_delta(a, b)} — v3 should be substantially higher (bias against defaulting to false).")

    # non-empty issues_detected
    lines.append("\n## Non-empty `issues_detected` counts (v3 should be 0 — verdict comes from provenance, not model)\n")
    lines.append("| category | v2 → v3 |")
    lines.append("|---|---|")
    for cat in CATEGORIES:
        a = count_field(v2[cat], ["issues_detected"], lambda x: bool(x))
        b = count_field(v3[cat], ["issues_detected"], lambda x: bool(x))
        lines.append(f"| {cat} | {fmt_delta(a, b)} |")

    # judgment-language leakage in summaries
    lines.append("\n## Judgment-language leakage in v3 summaries (should be near 0)\n")
    lines.append(f"Words checked: {', '.join(JUDGMENT_WORDS)}")
    total_hits = 0
    examples: list[tuple[str, str, list[str]]] = []
    for cat in CATEGORIES:
        cat_hits = judgment_hits(v3[cat])
        total_hits += len(cat_hits)
        for summary, words in cat_hits[:3]:
            examples.append((cat, summary, words))
    lines.append(f"\nTotal v3 summaries with judgment words: **{total_hits}** / {sum(len(v3[c]) for c in CATEGORIES)}")
    if examples:
        lines.append("\nExamples:")
        for cat, summ, words in examples[:10]:
            lines.append(f"- _{cat}_: words={words} — \"{summ[:180]}\"")

    # overall_status distribution (sanity check that runner did its job)
    lines.append("\n## v3 `overall_status` distribution (should be all `pass` for archive_pass provenance)\n")
    lines.append("| category | counts |")
    lines.append("|---|---|")
    for cat in CATEGORIES:
        c = Counter(d.get("overall_status") for d in v3[cat])
        lines.append(f"| {cat} | {dict(c)} |")

    args.out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
