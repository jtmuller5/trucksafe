#!/usr/bin/env python3
"""Compare v5.4 (audit-batch-06) vs v5.5 (audit-batch-07).

The headline question this report answers: **how many of the 90 audit
images are miscategorized, per the model's self-check?**

Sections (per docs/LABELING_PIPELINE.md):
  1. Miscategorization breakdown.
  2. Re-baselined v5.4 metrics excluding `photo_matches_category != yes`.
  3. Direct comparison v5.4 → v5.5 on yes-only images.
  4. Schema integrity.
  5. Elapsed time.
  6. HTML reviewer pointer.
  7. Recommendation.
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


def pmc(d: dict[str, Any]) -> str:
    """photo_matches_category value (returns '<missing>' for v5.4 records)."""
    return (d.get("describe_output") or {}).get("photo_matches_category", "<missing>")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v54-dir", type=Path, required=True)
    p.add_argument("--v55-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    out_path = args.out or (args.v55_dir / "comparison_v5_4_v5_5.md")

    v54_fw = load_folder(args.v54_dir, "fifth_wheel")
    v55_fw = load_folder(args.v55_dir, "fifth_wheel")
    v54_lj = load_folder(args.v54_dir, "lock_jaws")
    v55_lj = load_folder(args.v55_dir, "lock_jaws")
    v54_pin = load_folder(args.v54_dir, "pintle_hook")
    v55_pin = load_folder(args.v55_dir, "pintle_hook")

    v54_log = json.loads((args.v54_dir / "audit_log.json").read_text())
    v55_log = json.loads((args.v55_dir / "audit_log.json").read_text())

    L: list[str] = []
    L.append("# v5.4 → v5.5 comparison\n")
    L.append(
        f"Seed: {v55_log['seed']} (same 90-image audit subset). v5.4: `{args.v54_dir.name}`, "
        f"v5.5: `{args.v55_dir.name}`.\n"
    )
    L.append(
        "v5.5 adds two changes against v5.4: (1) `photo_matches_category` top-level "
        "self-check field on every record (yes / no / unclear) so the model reports "
        "whether the input actually shows the category's hardware; (2) `safety_chains_clipped_to_bar` "
        "relaxed from 5 values to 4 (`at_least_one_clipped` / `none_clipped` / `unclear` / "
        "`not_visible`), aligned to uncle's actual side-angle inspection workflow.\n"
    )

    # ------------------------------------------------------------------
    # Section 1 — Miscategorization breakdown
    # ------------------------------------------------------------------
    L.append("\n## 1. Miscategorization breakdown\n")

    pmc_by_folder: dict[str, Counter] = {}
    flagged: list[dict[str, Any]] = []
    for folder, rows in (("fifth_wheel", v55_fw), ("lock_jaws", v55_lj), ("pintle_hook", v55_pin)):
        c = Counter(pmc(d) for d in rows)
        pmc_by_folder[folder] = c
        for d in rows:
            if pmc(d) != "yes":
                flagged.append(d)

    L.append("| Source folder | `yes` | `unclear` | `no` |")
    L.append("|---|---|---|---|")
    total_yes = total_unclear = total_no = 0
    for folder in ("fifth_wheel", "lock_jaws", "pintle_hook"):
        c = pmc_by_folder[folder]
        y, u, n = c.get("yes", 0), c.get("unclear", 0), c.get("no", 0)
        total_yes += y
        total_unclear += u
        total_no += n
        L.append(f"| `{folder}` | {y} | {u} | {n} |")
    L.append(f"| **total /90** | **{total_yes}** | **{total_unclear}** | **{total_no}** |")

    L.append(f"\nTotal flagged (`unclear` + `no`): **{len(flagged)}/90**.\n")

    if flagged:
        L.append("### Flagged images (model self-check)\n")
        L.append("| image_id | folder | photo_matches | model's factual_summary |")
        L.append("|---|---|---|---|")
        for d in flagged:
            sid = d["image_id"]
            sf = d["source_folder"]
            val = pmc(d)
            fs = (d.get("describe_output") or {}).get("factual_summary", "")[:200]
            fs = fs.replace("|", "\\|").replace("\n", " ")
            L.append(f"| `{sid}` | `{sf}` | `{val}` | {fs} |")

        L.append(
            "\n**User spot-check pending:** review `:8770/labels/audit-batch-07/review.html` "
            "(filter: `photo_matches_category != yes` cohort at top of page). For each flagged "
            "image, tag agree/disagree. Update this report with the agreement count.\n"
        )
    else:
        L.append("- (no images flagged by the self-check)\n")

    # ------------------------------------------------------------------
    # Section 2 — Re-baselined metrics
    # ------------------------------------------------------------------
    L.append("\n## 2. Re-baselined v5.4 metrics (excluding v5.5-flagged miscategorizations)\n")

    flagged_ids = {d["image_id"] for d in flagged}

    def mfr_seen(rows: list[dict[str, Any]], exclude: set[str]) -> tuple[int, int]:
        rows = [d for d in rows if d["image_id"] not in exclude]
        n = len(rows)
        k = sum(1 for d in rows if block(d, "side_view").get("fifth_wheel_manufacturer") != "not_visible")
        return k, n

    def lj_seen(rows: list[dict[str, Any]], exclude: set[str]) -> tuple[int, int]:
        rows = [d for d in rows if d["image_id"] not in exclude]
        n = len(rows)
        k = sum(1 for d in rows if block(d, "lock_jaws_underneath").get("fifth_wheel_variant") != "unclear")
        return k, n

    def holland_yes(rows: list[dict[str, Any]], exclude: set[str]) -> int:
        return sum(
            1 for d in rows
            if d["image_id"] not in exclude
            and (block(d, "side_view").get("holland") or {}).get("washer_flush_against_body") == "yes"
        )

    v54_mfr_raw = mfr_seen(v54_fw, set())
    v54_mfr_reb = mfr_seen(v54_fw, flagged_ids)
    v55_mfr_raw = mfr_seen(v55_fw, set())
    v55_mfr_reb = mfr_seen(v55_fw, flagged_ids)

    v54_lj_raw = lj_seen(v54_lj, set())
    v54_lj_reb = lj_seen(v54_lj, flagged_ids)
    v55_lj_raw = lj_seen(v55_lj, set())
    v55_lj_reb = lj_seen(v55_lj, flagged_ids)

    L.append("| Metric | v5.4 raw | v5.4 re-baselined | v5.5 raw | v5.5 re-baselined |")
    L.append("|---|---|---|---|---|")
    L.append(
        f"| `fifth_wheel_manufacturer` non-`not_visible` | {v54_mfr_raw[0]}/{v54_mfr_raw[1]} | "
        f"{v54_mfr_reb[0]}/{v54_mfr_reb[1]} | {v55_mfr_raw[0]}/{v55_mfr_raw[1]} | "
        f"{v55_mfr_reb[0]}/{v55_mfr_reb[1]} |"
    )
    L.append(
        f"| `fifth_wheel_variant` non-`unclear` | {v54_lj_raw[0]}/{v54_lj_raw[1]} | "
        f"{v54_lj_reb[0]}/{v54_lj_reb[1]} | {v55_lj_raw[0]}/{v55_lj_raw[1]} | "
        f"{v55_lj_reb[0]}/{v55_lj_reb[1]} |"
    )
    L.append(
        f"| Holland `washer_flush=yes` | {holland_yes(v54_fw, set())} | "
        f"{holland_yes(v54_fw, flagged_ids)} | {holland_yes(v55_fw, set())} | "
        f"{holland_yes(v55_fw, flagged_ids)} |"
    )

    # Pintle joint-pass: v5.4 strict, v5.5 relaxed
    def v54_joint(rows: list[dict[str, Any]], exclude: set[str]) -> int:
        n = 0
        for d in rows:
            if d["image_id"] in exclude:
                continue
            ra = block(d, "rear_assembly")
            if (
                ra.get("hitch_latch_state") == "closed"
                and ra.get("safety_chains_count") == 2
                and ra.get("safety_chains_clipped_to_bar") == "both_clipped"
            ):
                n += 1
        return n

    def v55_joint(rows: list[dict[str, Any]], exclude: set[str]) -> int:
        n = 0
        for d in rows:
            if d["image_id"] in exclude:
                continue
            ra = block(d, "rear_assembly")
            count = ra.get("safety_chains_count")
            count_ok = (count in (1, 2)) or (isinstance(count, str) and count == "more_than_two")
            if (
                ra.get("hitch_latch_state") == "closed"
                and count_ok
                and ra.get("safety_chains_clipped_to_bar") == "at_least_one_clipped"
            ):
                n += 1
        return n

    L.append(
        f"| Pintle joint-pass (v5.4 strict / v5.5 relaxed) | {v54_joint(v54_pin, set())}/30 | "
        f"{v54_joint(v54_pin, flagged_ids)}/{30 - sum(1 for d in flagged if d['source_folder']=='pintle_hook')} | "
        f"{v55_joint(v55_pin, set())}/30 | "
        f"{v55_joint(v55_pin, flagged_ids)}/{30 - sum(1 for d in flagged if d['source_folder']=='pintle_hook')} |"
    )

    L.append(
        "\nv5.5 pintle joint-pass uses the relaxed criterion (`hitch_latch_state=closed` AND "
        "`safety_chains_count` ∈ {1, 2, more_than_two} AND `safety_chains_clipped_to_bar=at_least_one_clipped`). "
        "v5.4 joint-pass was strict (both chains required, both clipped). Both numbers are reported.\n"
    )

    # ------------------------------------------------------------------
    # Section 3 — Direct yes-only inspection-field drift
    # ------------------------------------------------------------------
    L.append("\n## 3. Inspection-field drift on `photo_matches_category == yes` images\n")
    L.append(
        "Cross-version per-image agreement on the same inspection fields. v5.5 changes "
        "only one inspection-field enum (`safety_chains_clipped_to_bar`), so we compare the "
        "v5.4 strict value against the v5.5 relaxed value with this mapping:\n"
        "- v5.4 `both_clipped` → expected v5.5 `at_least_one_clipped` (subset match).\n"
        "- v5.4 `one_clipped` → expected v5.5 `at_least_one_clipped` (subset match).\n"
        "- v5.4 `neither_clipped` → expected v5.5 `none_clipped` (rename).\n"
        "- v5.4 `unclear`/`not_visible` → v5.5 same.\n"
    )

    v54_by_id = {d["image_id"]: d for d in v54_fw + v54_lj + v54_pin}
    v55_by_id = {d["image_id"]: d for d in v55_fw + v55_lj + v55_pin}
    yes_ids = {d["image_id"] for d in (v55_fw + v55_lj + v55_pin) if pmc(d) == "yes"}

    # Manufacturer drift
    mfr_drift = 0
    for sid in yes_ids:
        v54d = v54_by_id.get(sid)
        v55d = v55_by_id.get(sid)
        if v54d is None or v55d is None or v54d["source_folder"] != "fifth_wheel":
            continue
        if block(v54d, "side_view").get("fifth_wheel_manufacturer") != block(v55d, "side_view").get("fifth_wheel_manufacturer"):
            mfr_drift += 1
    # Variant drift
    var_drift = 0
    for sid in yes_ids:
        v54d = v54_by_id.get(sid)
        v55d = v55_by_id.get(sid)
        if v54d is None or v55d is None or v54d["source_folder"] != "lock_jaws":
            continue
        if block(v54d, "lock_jaws_underneath").get("fifth_wheel_variant") != block(v55d, "lock_jaws_underneath").get("fifth_wheel_variant"):
            var_drift += 1
    # Pintle latch drift
    latch_drift = 0
    for sid in yes_ids:
        v54d = v54_by_id.get(sid)
        v55d = v55_by_id.get(sid)
        if v54d is None or v55d is None or v54d["source_folder"] != "pintle_hook":
            continue
        if block(v54d, "rear_assembly").get("hitch_latch_state") != block(v55d, "rear_assembly").get("hitch_latch_state"):
            latch_drift += 1
    # Chains-clipped drift under the v5.4→v5.5 mapping
    clip_map = {
        "both_clipped": "at_least_one_clipped",
        "one_clipped": "at_least_one_clipped",
        "neither_clipped": "none_clipped",
        "unclear": "unclear",
        "not_visible": "not_visible",
    }
    clip_drift = 0
    clip_total = 0
    for sid in yes_ids:
        v54d = v54_by_id.get(sid)
        v55d = v55_by_id.get(sid)
        if v54d is None or v55d is None or v54d["source_folder"] != "pintle_hook":
            continue
        clip_total += 1
        v54_val = block(v54d, "rear_assembly").get("safety_chains_clipped_to_bar")
        v55_val = block(v55d, "rear_assembly").get("safety_chains_clipped_to_bar")
        if clip_map.get(v54_val, v54_val) != v55_val:
            clip_drift += 1

    yes_total = len(yes_ids)
    L.append(f"- Cohort size (`yes` in v5.5): **{yes_total}** images")
    L.append(f"- `fifth_wheel_manufacturer` disagreement: {mfr_drift}")
    L.append(f"- `fifth_wheel_variant` disagreement: {var_drift}")
    L.append(f"- `hitch_latch_state` disagreement: {latch_drift}")
    L.append(f"- `safety_chains_clipped_to_bar` disagreement (under v5.4→v5.5 mapping): {clip_drift}/{clip_total}")
    total_drift = mfr_drift + var_drift + latch_drift + clip_drift
    drift_pct = (total_drift / yes_total * 100.0) if yes_total else 0.0
    L.append(f"\nTotal inspection-field drift on yes-cohort: **{total_drift}** ({drift_pct:.1f}% of {yes_total} images).")
    L.append(
        "Doc threshold: stop-and-surface if drift > 10%. "
        f"{'**THRESHOLD HIT** — investigate.' if drift_pct > 10 else 'Below threshold.'}"
    )

    # ------------------------------------------------------------------
    # Section 4 — Schema integrity
    # ------------------------------------------------------------------
    L.append("\n## 4. Schema integrity\n")
    v54_total = sum(v54_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel", "lock_jaws", "pintle_hook"))
    v55_total = sum(v55_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel", "lock_jaws", "pintle_hook"))
    L.append(f"- v5.4 final_valid: **{v54_total}/90**")
    L.append(f"- v5.5 final_valid: **{v55_total}/90**")

    # ------------------------------------------------------------------
    # Section 5 — Cost
    # ------------------------------------------------------------------
    L.append("\n## 5. Cost\n")
    v54_sec = v54_log["total_elapsed_seconds"]
    v55_sec = v55_log["total_elapsed_seconds"]
    delta_pct = (v55_sec - v54_sec) / v54_sec * 100.0
    L.append(f"- v5.4 elapsed: **{v54_sec:.1f}s** ({v54_sec/60:.1f} min)")
    L.append(f"- v5.5 elapsed: **{v55_sec:.1f}s** ({v55_sec/60:.1f} min)")
    L.append(f"- delta: **{delta_pct:+.1f}%** (one extra small field + short prompt addition)")
    L.append(
        "- doc threshold (+20%): "
        + ("**HIT** — investigate." if delta_pct > 20 else "below threshold.")
    )

    # ------------------------------------------------------------------
    # Section 6 — HTML reviewer
    # ------------------------------------------------------------------
    L.append("\n## 6. HTML reviewer\n")
    L.append("`:8770/labels/audit-batch-07/review.html` — flagged-cohort filter at the top of the page.")

    # ------------------------------------------------------------------
    # Section 7 — Recommendation
    # ------------------------------------------------------------------
    L.append("\n## 7. Recommendation\n")
    L.append("Outcome bucket (per docs/LABELING_PIPELINE.md):\n")
    n_flag = len(flagged)
    if v55_total < 90:
        bucket = "**Schema breakage** — Stop. Re-investigate schema or prompt assembly."
    elif drift_pct > 10:
        bucket = (
            "**Inspection-field drift exceeds 10% threshold** — Stop and investigate. "
            "The self-check instruction may be interfering with the existing prompt structure."
        )
    elif 5 <= n_flag <= 15:
        bucket = (
            "**Clean signal** — Proceed to scale-up decision with v5.5 schema. "
            "v5.5 is the version that goes to the full 7,500, pending user spot-check agreement on the flagged set."
        )
    elif n_flag > 25:
        bucket = (
            "**Over-flagging** — Iterate the threshold language. "
            "The prompt addition is being too aggressive; tighten 'clearly shows' wording."
        )
    elif n_flag < 3:
        bucket = (
            "**Under-flagging** — Iterate the prompt with a few-shot example of a miscategorized image. "
            "The instruction isn't landing on cases the user can find manually."
        )
    else:
        bucket = (
            "**Borderline signal** — Proceed cautiously to user spot-check, then decide. "
            "Either an over- or under-flag may show up after human review."
        )
    L.append(bucket)
    L.append("\n### Driving numbers")
    L.append(f"- Flagged miscategorizations: {n_flag}/90 ({total_no} `no`, {total_unclear} `unclear`)")
    L.append(f"- Inspection-field drift on yes-cohort: {drift_pct:.1f}% (threshold 10%)")
    L.append(f"- Schema integrity: {v55_total}/90")
    L.append(f"- Elapsed delta: {delta_pct:+.1f}% (threshold +20%)")

    out_path.write_text("\n".join(L) + "\n")
    print(f"Wrote comparison to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
