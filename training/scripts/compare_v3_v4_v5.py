#!/usr/bin/env python3
"""Generate comparison_v3_v4_v5.md across three audit batches.

Layout differences:
  v3: bare production-schema label per file under {dir}/{category}/.
  v4: wrapper with production_schema at top; same flat observations inside.
  v5: wrapper with production_schema at top; nested side_view / lock_jaws_underneath
      / rear_assembly sub-blocks; field renames (overall_status → verdict, etc.).

Output: a markdown report that explicitly maps old fields to new locations
and reports per-field deltas only where the comparison is well-defined.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# v3/v4 use these category folder names; v5 uses the same source folder names.
SOURCE_FOLDERS = ("fifth_wheel", "lock_jaws", "pintle_hook")
JUDGMENT_WORDS = ("pass", "fail", "safe", "unsafe", "high hook", "high-hook",
                  "missing", "wrong", "correct", "incorrect", "broken")
EXCLUDE_PHRASES = ("safety pin", "safety pins", "safety chain", "safety chains",
                   "safety system", "safety check", "safety net")
JUDGMENT_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in JUDGMENT_WORDS) + r")\b", re.IGNORECASE)
EXCLUDE_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in EXCLUDE_PHRASES) + r")\b", re.IGNORECASE)


def unwrap(d: dict[str, Any]) -> dict[str, Any]:
    """v4/v5 wrap the schema under 'production_schema'; v3 doesn't."""
    return d.get("production_schema", d)


def load(dir_: Path, folder: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cat = dir_ / folder
    if not cat.exists():
        return out
    for p in sorted(cat.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out


# ---------------- v3/v4 accessors (flat) ----------------
def v34_obs(d: dict[str, Any]) -> dict[str, Any]:
    return unwrap(d).get("observations", {})


def v34_summary(d: dict[str, Any]) -> str:
    return unwrap(d).get("human_readable_summary", "") or ""


# ---------------- v5 accessors (nested) ----------------
def v5_block(d: dict[str, Any]) -> dict[str, Any]:
    """Return the populated evidence sub-block for a v5 label."""
    ps = unwrap(d)
    ev = ps.get("evidence_type")
    return ps.get(ev) or {}


def v5_summary(d: dict[str, Any]) -> str:
    return unwrap(d).get("factual_summary", "") or ""


def v5_image_quality(d: dict[str, Any]) -> str:
    return unwrap(d).get("image_quality", "") or ""


def fmt_delta(a: int, b: int) -> str:
    delta = b - a
    if delta == 0:
        return f"{a} → {b} (=)"
    return f"{a} → {b} ({'↑' if delta > 0 else '↓'}{abs(delta)})"


def fmt_three(a: int, b: int, c: int) -> str:
    return f"v3={a}  v4={b}  v5={c}"


def count(labels: list[dict[str, Any]], pred) -> int:
    return sum(1 for d in labels if pred(d))


def judgment_count(labels: list[dict[str, Any]], summary_fn) -> int:
    n = 0
    for d in labels:
        s = summary_fn(d)
        scrubbed = EXCLUDE_RE.sub(" ", s)
        if JUDGMENT_RE.search(scrubbed):
            n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v3-dir", type=Path, required=True)
    p.add_argument("--v4-dir", type=Path, required=True)
    p.add_argument("--v5-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    v3 = {f: load(args.v3_dir, f) for f in SOURCE_FOLDERS}
    v4 = {f: load(args.v4_dir, f) for f in SOURCE_FOLDERS}
    v5 = {f: load(args.v5_dir, f) for f in SOURCE_FOLDERS}

    L: list[str] = []
    L.append("# v3 vs v4 vs v5 labeler audit comparison\n")
    L.append(f"- v3 source: `{args.v3_dir}`")
    L.append(f"- v4 source: `{args.v4_dir}`")
    L.append(f"- v5 source: `{args.v5_dir}`")

    L.append("\n## 0. Label counts per source folder\n")
    L.append("| source folder | v3 | v4 | v5 |")
    L.append("|---|---:|---:|---:|")
    for f in SOURCE_FOLDERS:
        L.append(f"| {f} | {len(v3[f])} | {len(v4[f])} | {len(v5[f])} |")

    # ----- 1. Format compatibility map -----
    L.append("\n## 1. Field mapping (v3/v4 → v5)\n")
    L.append("Top-level renames:")
    L.append("- v3/v4 `overall_status` → v5 `verdict`")
    L.append("- v3/v4 `human_readable_summary` → v5 `factual_summary`")
    L.append("- v3/v4 `observations.image_quality` → v5 `image_quality` (top-level; enum widened to include `acceptable`)")
    L.append("- v3/v4 `confidence` → removed (was runner-derived from image_quality; redundant under v5)")
    L.append("")
    L.append("Per-folder field locations:")
    L.append("- v3/v4 `fifth_wheel.observations.visible_gap_between_apron_and_plate` → v5 `side_view.gap_between_apron_and_plate`")
    L.append("- v3/v4 `fifth_wheel.observations.release_handle_position` → v5 `side_view.release_handle_position` (+ new `release_handle_visible` boolean)")
    L.append("- v3/v4 `lock_jaws.observations.jaws_fully_closed_around_kingpin` (yes/no/unclear) → v5 `lock_jaws_underneath.two_jaw_state` (5-value enum). Not directly comparable.")
    L.append("- v3/v4 `pintle_hook.observations.*` → v5 `rear_assembly.*` (mostly direct rename; safety_chains_count enum widened; safety_chains_crossed bool → 4-value enum)")
    L.append("")
    L.append("New v5 fields with no v3/v4 equivalent:")
    L.append("- `side_view.locking_indicator_visible` / `locking_indicator_position`")
    L.append("- `side_view.fifth_wheel_variant`")
    L.append("- `lock_jaws_underneath.jaw_mechanism_type` / `single_bar_state`")
    L.append("- `rear_assembly.hook_visible` / `lunette_ring_visible`")

    # ----- 2. Per-field deltas where comparable -----
    L.append("\n## 2. Per-field deltas (v3 → v4 → v5)\n")

    # safety_pin_visible
    a = count(v3["pintle_hook"], lambda d: v34_obs(d).get("safety_pin_visible") is True)
    b = count(v4["pintle_hook"], lambda d: v34_obs(d).get("safety_pin_visible") is True)
    c = count(v5["pintle_hook"], lambda d: v5_block(d).get("safety_pin_visible") is True)
    L.append(f"### pintle_hook `safety_pin_visible == true`\n")
    L.append(f"{fmt_three(a, b, c)} out of 30")
    L.append("This was the v2→v3 headline (0 → 28). Watch for regression.\n")

    # fifth_wheel gap
    L.append("### fifth_wheel gap distribution\n")
    L.append("| value | v3 | v4 | v5 |")
    L.append("|---|---:|---:|---:|")
    v3_4_buckets = ("none", "minor", "obvious")
    for val in v3_4_buckets:
        a = count(v3["fifth_wheel"], lambda d: v34_obs(d).get("visible_gap_between_apron_and_plate") == val)
        b = count(v4["fifth_wheel"], lambda d: v34_obs(d).get("visible_gap_between_apron_and_plate") == val)
        c = count(v5["fifth_wheel"], lambda d: v5_block(d).get("gap_between_apron_and_plate") == val)
        L.append(f"| {val} | {a} | {b} | {c} |")
    a = count(v5["fifth_wheel"], lambda d: v5_block(d).get("gap_between_apron_and_plate") == "not_visible")
    L.append(f"| not_visible (v5 only) | — | — | {a} |")
    a = count(v3["fifth_wheel"], lambda d: v34_obs(d).get("visible_gap_between_apron_and_plate") in ("minor", "obvious"))
    b = count(v4["fifth_wheel"], lambda d: v34_obs(d).get("visible_gap_between_apron_and_plate") in ("minor", "obvious"))
    c = count(v5["fifth_wheel"], lambda d: v5_block(d).get("gap_between_apron_and_plate") in ("minor", "obvious"))
    L.append(f"\n`gap ∈ {{minor, obvious}}` (lower = fewer hallucinated gaps on archive_pass): {fmt_three(a, b, c)}\n")

    # image_quality poor
    L.append("### `image_quality` rates (top-level in v5; in observations in v3/v4)\n")
    L.append("| folder | v3 poor | v4 poor | v5 poor | v5 acceptable | v5 good |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for f in SOURCE_FOLDERS:
        v3p = count(v3[f], lambda d: v34_obs(d).get("image_quality") == "poor")
        v4p = count(v4[f], lambda d: v34_obs(d).get("image_quality") == "poor")
        v5p = count(v5[f], lambda d: v5_image_quality(d) == "poor")
        v5a = count(v5[f], lambda d: v5_image_quality(d) == "acceptable")
        v5g = count(v5[f], lambda d: v5_image_quality(d) == "good")
        L.append(f"| {f} | {v3p} | {v4p} | {v5p} | {v5a} | {v5g} |")

    # safety_chains_count == 2 (in pintle_hook)
    a = count(v3["pintle_hook"], lambda d: v34_obs(d).get("safety_chains_count") == 2)
    b = count(v4["pintle_hook"], lambda d: v34_obs(d).get("safety_chains_count") == 2)
    c = count(v5["pintle_hook"], lambda d: v5_block(d).get("safety_chains_count") == 2)
    L.append(f"\n### pintle_hook `safety_chains_count == 2`\n")
    L.append(f"{fmt_three(a, b, c)} out of 30")

    # safety_chains_crossed (true in v3/v4 → 'yes' in v5)
    a = count(v3["pintle_hook"], lambda d: v34_obs(d).get("safety_chains_crossed") is True)
    b = count(v4["pintle_hook"], lambda d: v34_obs(d).get("safety_chains_crossed") is True)
    c = count(v5["pintle_hook"], lambda d: v5_block(d).get("safety_chains_crossed") == "yes")
    L.append(f"\n### pintle_hook `safety_chains_crossed` (true / yes)\n")
    L.append(f"{fmt_three(a, b, c)} out of 30")

    # hook_latch closed
    a = count(v3["pintle_hook"], lambda d: v34_obs(d).get("hook_latch_state") == "closed")
    b = count(v4["pintle_hook"], lambda d: v34_obs(d).get("hook_latch_state") == "closed")
    c = count(v5["pintle_hook"], lambda d: v5_block(d).get("hook_latch_state") == "closed")
    L.append(f"\n### pintle_hook `hook_latch_state == 'closed'`\n")
    L.append(f"{fmt_three(a, b, c)} out of 30")

    # ----- 3. v5-only metrics -----
    L.append("\n## 3. v5-only metrics (manufacturer-aware)\n")
    L.append("### side_view: `fifth_wheel_manufacturer` distribution\n")
    mfr_counter = Counter(v5_block(d).get("fifth_wheel_manufacturer") for d in v5["fifth_wheel"])
    L.append(f"{dict(mfr_counter)}")
    non_nv = sum(v for k, v in mfr_counter.items() if k != "not_visible")
    bar = 0.60 * len(v5["fifth_wheel"])
    status = "✓ passes" if non_nv >= bar else "✗ FAILS"
    L.append(f"\nNon-`not_visible` rate: {non_nv}/{len(v5['fifth_wheel'])} ({non_nv / max(1, len(v5['fifth_wheel'])):.0%}) — {status} the ≥60% bar.\n")

    L.append("### lock_jaws_underneath: `fifth_wheel_variant` distribution\n")
    var_counter = Counter(v5_block(d).get("fifth_wheel_variant") for d in v5["lock_jaws"])
    L.append(f"{dict(var_counter)}")
    identified = sum(v for k, v in var_counter.items() if k in ("two_jaw", "single_bar"))
    bar = 0.60 * len(v5["lock_jaws"])
    status = "✓ passes" if identified >= bar else "✗ FAILS"
    L.append(f"\nIdentified (two_jaw + single_bar) rate: {identified}/{len(v5['lock_jaws'])} ({identified / max(1, len(v5['lock_jaws'])):.0%}) — {status} the ≥60% bar.\n")

    # Manufacturer sub-object population consistency
    L.append("### Manufacturer sub-object population consistency\n")
    consistent = 0
    contradictions: list[str] = []
    for d in v5["fifth_wheel"]:
        b = v5_block(d)
        mfr = b.get("fifth_wheel_manufacturer")
        populated = {k: b.get(k) is not None for k in ("holland", "fontaine", "jost")}
        if mfr in ("fontaine", "jost", "holland"):
            ok = populated[mfr] and not any(v for k, v in populated.items() if k != mfr)
        else:
            ok = not any(populated.values())
        if ok:
            consistent += 1
        else:
            contradictions.append(f"{d.get('image_id','?')[:30]} mfr={mfr} populated={[k for k,v in populated.items() if v]}")
    L.append(f"Coherent (manufacturer ↔ exactly the right sub-object populated): {consistent}/{len(v5['fifth_wheel'])}")
    for s in contradictions[:5]:
        L.append(f"- {s}")

    # Per-brand hardware visibility
    L.append("\n### Per-brand diagnostic feature visibility (within brand-identified labels)\n")
    L.append("| brand | n | diagnostic feature | visible (`yes`) |")
    L.append("|---|---:|---|---:|")
    for brand, feature in (
        ("holland", "front_pin_visible"),
        ("fontaine", "side_pin_visible"),
        ("jost", "center_release_strap_visible"),
    ):
        brand_labels = [d for d in v5["fifth_wheel"] if v5_block(d).get("fifth_wheel_manufacturer") == brand]
        with_feature = sum(1 for d in brand_labels if (v5_block(d).get(brand) or {}).get(feature) == "yes")
        L.append(f"| {brand} | {len(brand_labels)} | {feature} | {with_feature} |")

    # Holland washer engagement check
    holland_labels = [d for d in v5["fifth_wheel"] if v5_block(d).get("fifth_wheel_manufacturer") == "holland"]
    if holland_labels:
        L.append("\n### Holland engagement check (`washer_flush_against_body`)\n")
        c = Counter((v5_block(d).get("holland") or {}).get("washer_flush_against_body") for d in holland_labels)
        L.append(f"{dict(c)} (n={len(holland_labels)})")

    # Jost honest-unknown
    jost_labels = [d for d in v5["fifth_wheel"] if v5_block(d).get("fifth_wheel_manufacturer") == "jost"]
    if jost_labels:
        L.append("\n### Jost honest-unknown rate\n")
        c = Counter((v5_block(d).get("jost") or {}).get("side_handle_position") for d in jost_labels)
        ncv = c.get("not_clearly_visible", 0)
        L.append(f"`side_handle_position` distribution: {dict(c)}")
        L.append(f"`not_clearly_visible` rate: {ncv}/{len(jost_labels)} ({ncv / max(1, len(jost_labels)):.0%}) — Jost side-view engagement is inherently limited; high rate is calibrated honesty.")

    # Cross-field coherence on lock_jaws_underneath
    L.append("\n### Cross-field coherence (lock_jaws_underneath)\n")
    coherent = 0
    incoherent: list[str] = []
    for d in v5["lock_jaws"]:
        b = v5_block(d)
        var = b.get("fifth_wheel_variant")
        tj = b.get("two_jaw_state")
        sb = b.get("single_bar_state")
        ok = True
        if var == "two_jaw":
            ok = sb == "not_applicable"
        elif var == "single_bar":
            ok = tj == "not_applicable"
        if ok:
            coherent += 1
        else:
            incoherent.append(f"{d.get('image_id','?')[:30]} var={var} tj={tj} sb={sb}")
    L.append(f"Coherence (variant=two_jaw → sb=not_applicable; variant=single_bar → tj=not_applicable): {coherent}/{len(v5['lock_jaws'])}")
    for s in incoherent[:5]:
        L.append(f"- {s}")

    # ----- 4. Schema integrity -----
    L.append("\n## 4. Schema integrity (success bar 1)\n")
    v5_audit_path = args.v5_dir / "audit_log.json"
    v5_audit = json.loads(v5_audit_path.read_text()) if v5_audit_path.exists() else {}
    total = sum(s.get("attempted", 0) for s in v5_audit.get("source_folders", {}).values())
    valid = sum(s.get("final_valid", 0) for s in v5_audit.get("source_folders", {}).values())
    L.append(f"{valid}/{total} v5 labels validated against describe-only + production schemas — {'✓ passes' if valid == total else '✗ FAILS'}")

    # ----- 5. Elapsed time -----
    L.append("\n## 5. Elapsed time\n")
    def t(p: Path) -> str:
        if not p.exists():
            return "?"
        return f"{json.loads(p.read_text()).get('total_elapsed_seconds', '?')}s"
    L.append(f"- v3 single-pass: {t(args.v3_dir / 'audit_log.json')}")
    L.append(f"- v4 two-pass:    {t(args.v4_dir / 'audit_log.json')}")
    L.append(f"- v5 mixed:       {t(args.v5_dir / 'audit_log.json')}")

    # ----- 6. Judgment-language sanity -----
    total_hits = sum(judgment_count(v5[f], v5_summary) for f in SOURCE_FOLDERS)
    L.append("\n## 6. Sanity: judgment-language leakage in v5 summaries\n")
    L.append(f"Total v5 summaries with judgment words (excluding 'safety pin/chains'): **{total_hits}** / {sum(len(v5[f]) for f in SOURCE_FOLDERS)}")

    args.out.write_text("\n".join(L) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
