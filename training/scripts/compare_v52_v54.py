#!/usr/bin/env python3
"""Compare v5.2 (audit-batch-05) vs v5.4 (audit-batch-06).

Output: comparison_v5_2_v5_4.md in the v5.4 labels dir.

The pintle schema changed structurally in v5.4 so most pintle fields cannot
be directly delta'd. The report acknowledges this and reports v5.4 absolute
values for the new pintle fields, with v5.2 baselines only on the unchanged
side_view and lock_jaws metrics. See docs/LABELING_PIPELINE.md "Comparison
report" section for the required structure.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def load_folder(labels_dir: Path, folder: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted((labels_dir / folder).glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def block(d: dict[str, Any], evidence: str) -> dict[str, Any]:
    return (d.get("describe_output") or {}).get(evidence, {}) or {}


def fmt_counter(c: Counter, total: int) -> str:
    return ", ".join(f"`{k}`: {v}/{total}" for k, v in sorted(c.items(), key=lambda x: -x[1]))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v52-dir", type=Path, required=True)
    p.add_argument("--v54-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    out_path = args.out or (args.v54_dir / "comparison_v5_2_v5_4.md")

    v52_fw = load_folder(args.v52_dir, "fifth_wheel")
    v54_fw = load_folder(args.v54_dir, "fifth_wheel")
    v52_lj = load_folder(args.v52_dir, "lock_jaws")
    v54_lj = load_folder(args.v54_dir, "lock_jaws")
    v52_pin = load_folder(args.v52_dir, "pintle_hook")
    v54_pin = load_folder(args.v54_dir, "pintle_hook")

    v52_log = json.loads((args.v52_dir / "audit_log.json").read_text())
    v54_log = json.loads((args.v54_dir / "audit_log.json").read_text())

    L: list[str] = []
    L.append("# v5.2 → v5.4 comparison\n")
    L.append(
        f"Seed: {v54_log['seed']} (same 90-image audit subset). v5.2: `{args.v52_dir.name}`, "
        f"v5.4: `{args.v54_dir.name}`.\n"
    )
    L.append(
        "v5.4 introduces two changes against v5.2: (1) curated few-shot reference "
        "images embedded inline before each input image; (2) simplified pintle schema "
        "(`hitch_latch_state` + `safety_chains_count` + `safety_chains_clipped_to_bar`) "
        "with v5.2's `hook_visible` / `safety_pin_visible` / `lunette_ring_visible` / "
        "`safety_chains_crossed` removed. Pintle metrics are therefore reported as "
        "v5.4 absolute values, not v5.2 deltas.\n"
    )

    # ------------------------------------------------------------------
    # Section 1 — Headline metrics (direct comparison valid)
    # ------------------------------------------------------------------
    L.append("\n## 1. Headline metrics (direct comparison valid)\n")
    L.append("| Metric | v5.2 | v5.4 | Δ |")
    L.append("|---|---|---|---|")

    # Schema integrity (final_valid / attempted)
    v52_total = sum(v52_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel","lock_jaws","pintle_hook"))
    v54_total = sum(v54_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel","lock_jaws","pintle_hook"))
    L.append(f"| Schema integrity (final valid / 90) | {v52_total}/90 | {v54_total}/90 | {v54_total - v52_total:+d} |")

    # fifth_wheel_manufacturer non-not_visible
    v52_mfr_seen = sum(1 for d in v52_fw if block(d, "side_view").get("fifth_wheel_manufacturer") != "not_visible")
    v54_mfr_seen = sum(1 for d in v54_fw if block(d, "side_view").get("fifth_wheel_manufacturer") != "not_visible")
    L.append(f"| `fifth_wheel_manufacturer` non-`not_visible` / 30 | {v52_mfr_seen}/30 | {v54_mfr_seen}/30 | {v54_mfr_seen - v52_mfr_seen:+d} |")

    # Holland washer flush distribution
    v52_holl_yes = sum(1 for d in v52_fw if (block(d, "side_view").get("holland") or {}).get("washer_flush_against_body") == "yes")
    v52_holl_no = sum(1 for d in v52_fw if (block(d, "side_view").get("holland") or {}).get("washer_flush_against_body") == "no")
    v54_holl_yes = sum(1 for d in v54_fw if (block(d, "side_view").get("holland") or {}).get("washer_flush_against_body") == "yes")
    v54_holl_no = sum(1 for d in v54_fw if (block(d, "side_view").get("holland") or {}).get("washer_flush_against_body") == "no")
    L.append(f"| Holland `washer_flush=yes` | {v52_holl_yes} | {v54_holl_yes} | {v54_holl_yes - v52_holl_yes:+d} |")
    L.append(f"| Holland `washer_flush=no` | {v52_holl_no} | {v54_holl_no} | {v54_holl_no - v52_holl_no:+d} |")

    # Lock_jaws variant non-unclear
    v52_lj_seen = sum(1 for d in v52_lj if block(d, "lock_jaws_underneath").get("fifth_wheel_variant") != "unclear")
    v54_lj_seen = sum(1 for d in v54_lj if block(d, "lock_jaws_underneath").get("fifth_wheel_variant") != "unclear")
    L.append(f"| `fifth_wheel_variant` non-`unclear` / 30 | {v52_lj_seen}/30 | {v54_lj_seen}/30 | {v54_lj_seen - v52_lj_seen:+d} |")

    # Side_view sub-object consistency (informational: how many manufacturers had a populated sub-object matching their identification)
    def sub_consistency(rows: list[dict[str, Any]]) -> int:
        c = 0
        for d in rows:
            sv = block(d, "side_view")
            mfr = sv.get("fifth_wheel_manufacturer")
            if mfr in ("holland", "fontaine", "jost"):
                if sv.get(mfr) is not None:
                    c += 1
            elif mfr in ("other", "unclear", "not_visible"):
                if sv.get("holland") is None and sv.get("fontaine") is None and sv.get("jost") is None:
                    c += 1
        return c
    L.append(f"| Side_view sub-object consistency / 30 | {sub_consistency(v52_fw)}/30 | {sub_consistency(v54_fw)}/30 | {sub_consistency(v54_fw) - sub_consistency(v52_fw):+d} |")

    # Jost honest-unknown rate
    def jost_unknown(rows: list[dict[str, Any]]) -> tuple[int, int]:
        n, k = 0, 0
        for d in rows:
            sv = block(d, "side_view")
            if sv.get("fifth_wheel_manufacturer") == "jost":
                j = sv.get("jost") or {}
                n += 1
                if j.get("side_handle_position") == "not_clearly_visible":
                    k += 1
        return k, n
    v52_j = jost_unknown(v52_fw)
    v54_j = jost_unknown(v54_fw)
    L.append(f"| Jost honest-unknown rate | {v52_j[0]}/{v52_j[1]} | {v54_j[0]}/{v54_j[1]} | — |")

    # ------------------------------------------------------------------
    # Section 2 — Pintle new-schema absolute values (no v5.2 delta possible)
    # ------------------------------------------------------------------
    L.append("\n## 2. Pintle new-schema absolute values (v5.4 only)\n")
    n_pin = len(v54_pin)
    latch_c = Counter()
    chains_c = Counter()
    clip_c = Counter()
    joint_pass = 0
    for d in v54_pin:
        ra = block(d, "rear_assembly")
        latch_c[str(ra.get("hitch_latch_state"))] += 1
        chains_c[str(ra.get("safety_chains_count"))] += 1
        clip_c[str(ra.get("safety_chains_clipped_to_bar"))] += 1
        if (
            ra.get("hitch_latch_state") == "closed"
            and ra.get("safety_chains_count") == 2
            and ra.get("safety_chains_clipped_to_bar") == "both_clipped"
        ):
            joint_pass += 1

    L.append(f"- Pintle final_valid / attempted: **{len(v54_pin)}/30** (schema integrity check)")
    L.append(f"- `hitch_latch_state` distribution: {fmt_counter(latch_c, n_pin)}")
    L.append(f"- `safety_chains_count` distribution: {fmt_counter(chains_c, n_pin)}")
    L.append(f"- `safety_chains_clipped_to_bar` distribution: {fmt_counter(clip_c, n_pin)}")
    L.append(f"- **Joint pass** (`hitch_latch_state=closed` AND `safety_chains_count=2` AND `safety_chains_clipped_to_bar=both_clipped`): **{joint_pass}/{n_pin}**")

    # Breakdown of *why not* for non-pass
    L.append("\n### Why-not-pass breakdown for non-joint-pass pintle images\n")
    reasons = Counter()
    for d in v54_pin:
        ra = block(d, "rear_assembly")
        if (
            ra.get("hitch_latch_state") == "closed"
            and ra.get("safety_chains_count") == 2
            and ra.get("safety_chains_clipped_to_bar") == "both_clipped"
        ):
            continue
        if ra.get("hitch_latch_state") != "closed":
            reasons[f"latch_not_closed ({ra.get('hitch_latch_state')})"] += 1
        if ra.get("safety_chains_count") != 2:
            reasons[f"chains_count_not_2 ({ra.get('safety_chains_count')})"] += 1
        if ra.get("safety_chains_clipped_to_bar") != "both_clipped":
            reasons[f"clipped_not_both ({ra.get('safety_chains_clipped_to_bar')})"] += 1
    if reasons:
        for k, v in reasons.most_common():
            L.append(f"- `{k}`: {v}")
    else:
        L.append("- (all images joint-pass)")

    # ------------------------------------------------------------------
    # Section 3 — Lock_jaws breakdown
    # ------------------------------------------------------------------
    L.append("\n## 3. Lock_jaws breakdown — where the experiment lives\n")

    v52_lj_variant = Counter(block(d, "lock_jaws_underneath").get("fifth_wheel_variant") for d in v52_lj)
    v54_lj_variant = Counter(block(d, "lock_jaws_underneath").get("fifth_wheel_variant") for d in v54_lj)
    L.append("| variant | v5.2 | v5.4 |")
    L.append("|---|---|---|")
    for k in ("two_jaw", "single_bar", "unclear"):
        L.append(f"| `{k}` | {v52_lj_variant.get(k, 0)} | {v54_lj_variant.get(k, 0)} |")

    # Flipped: v5.2 unclear → v5.4 confident
    v52_by_id = {d["image_id"]: d for d in v52_lj}
    flipped: list[str] = []
    held_unclear: int = 0
    new_unclear: list[str] = []
    for d in v54_lj:
        stem = d["image_id"]
        v52d = v52_by_id.get(stem)
        if v52d is None:
            continue
        v52_var = block(v52d, "lock_jaws_underneath").get("fifth_wheel_variant")
        v54_var = block(d, "lock_jaws_underneath").get("fifth_wheel_variant")
        if v52_var == "unclear" and v54_var != "unclear":
            flipped.append(f"{stem}: unclear → {v54_var}")
        elif v52_var == "unclear" and v54_var == "unclear":
            held_unclear += 1
        elif v52_var != "unclear" and v54_var == "unclear":
            new_unclear.append(f"{stem}: {v52_var} → unclear")

    L.append(f"\n- v5.2 `unclear` → v5.4 confident: **{len(flipped)}**")
    for line in flipped[:10]:
        L.append(f"  - {line}")
    if len(flipped) > 10:
        L.append(f"  - ... ({len(flipped) - 10} more)")
    L.append(f"- v5.2 `unclear` → still `unclear` in v5.4: **{held_unclear}**")
    if new_unclear:
        L.append(f"- ⚠ regression — v5.2 confident → v5.4 `unclear`: **{len(new_unclear)}**")
        for line in new_unclear:
            L.append(f"  - {line}")

    # ------------------------------------------------------------------
    # Section 4 — Holland washer outliers follow-up
    # ------------------------------------------------------------------
    L.append("\n## 4. Holland washer outliers follow-up\n")
    L.append(
        "With flush-only few-shot in v5.4, an outcome flip cannot strongly distinguish "
        "'v5.2 misread' from 'v5.4 anchor pressure'. Holding `no` against the flush "
        "anchor strengthens the real-failure hypothesis.\n"
    )
    v52_by_id_fw = {d["image_id"]: d for d in v52_fw}
    v54_by_id_fw = {d["image_id"]: d for d in v54_fw}
    outliers = []
    for stem, d in v52_by_id_fw.items():
        h = (block(d, "side_view").get("holland") or {})
        if h.get("washer_flush_against_body") == "no":
            outliers.append(stem)
    for stem in outliers:
        v54d = v54_by_id_fw.get(stem)
        v54_h = (block(v54d, "side_view").get("holland") or {}) if v54d else {}
        v54_call = v54_h.get("washer_flush_against_body", "<not Holland in v5.4>")
        L.append(f"- `{stem}`: v5.2=`no` → v5.4=`{v54_call}`")
    if not outliers:
        L.append("- (no Holland `washer_flush=no` outliers in v5.2)")

    # ------------------------------------------------------------------
    # Section 5 — Cost
    # ------------------------------------------------------------------
    L.append("\n## 5. Cost\n")
    v52_sec = v52_log["total_elapsed_seconds"]
    v54_sec = v54_log["total_elapsed_seconds"]
    delta_pct = (v54_sec - v52_sec) / v52_sec * 100.0
    L.append(f"- v5.2 elapsed: **{v52_sec:.1f}s** ({v52_sec/60:.1f} min)")
    L.append(f"- v5.4 elapsed: **{v54_sec:.1f}s** ({v54_sec/60:.1f} min)")
    L.append(f"- delta: **{delta_pct:+.1f}%** (few-shot reference image prefill cost)")
    L.append("- stop-and-discuss threshold (16 min / 960s): " + ("**HIT** — investigate." if v54_sec > 960 else "below threshold."))

    # ------------------------------------------------------------------
    # Section 6 — Recommendation
    # ------------------------------------------------------------------
    L.append("\n## 6. Recommendation\n")
    L.append("Outcome bucket (per `docs/LABELING_PIPELINE.md` Success criteria):\n")

    pintle_schema_ok = len(v54_pin) == 30
    latch_engaged = sum(1 for d in v54_pin if block(d, "rear_assembly").get("hitch_latch_state") not in ("unclear", "not_visible"))
    pintle_engages = pintle_schema_ok and latch_engaged >= 25
    lj_strong = v54_lj_seen >= 18
    lj_partial = 10 <= v54_lj_seen <= 17
    mfr_holds = v54_mfr_seen >= 17  # doc threshold for regression is ≤16
    holland_stable = v54_holl_yes >= v52_holl_yes  # no spurious flips down

    if pintle_engages and lj_strong and holland_stable and mfr_holds:
        bucket = "**Strong win** — Scale on v5.4."
    elif pintle_engages and lj_partial and mfr_holds:
        bucket = "**Partial win** — Scale on v5.4, accept lock_jaws still imperfect. Plan `fifth_wheel_overview` evidence type for v6."
    elif pintle_engages and not (lj_strong or lj_partial) and mfr_holds:
        bucket = "**Pintle-only win** — Scale on v5.4. Lock_jaws variant ID confirmed as photo-supply problem, not prompt problem."
    else:
        bucket = "**No change or regression** — Stop, surface. Investigate."

    L.append(bucket)
    L.append("\n### Driving numbers")
    L.append(f"- Pintle schema valid: {pintle_schema_ok} ({len(v54_pin)}/30)")
    L.append(f"- Pintle latch engaged (non-unclear/not_visible): {latch_engaged}/30 (threshold ≥25)")
    L.append(f"- Lock_jaws variant ID: {v54_lj_seen}/30 (strong ≥18, partial 10-17)")
    L.append(f"- Side_view manufacturer hold: {v54_mfr_seen}/30 (regression at ≤16)")
    L.append(f"- Holland flush stability: v5.4 yes={v54_holl_yes} vs v5.2 yes={v52_holl_yes}")

    out_path.write_text("\n".join(L) + "\n")
    print(f"Wrote comparison to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
