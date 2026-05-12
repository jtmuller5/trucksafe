#!/usr/bin/env python3
"""Compare v5.5 (audit-batch-07) vs v5.6 (audit-batch-08).

v5.6 simplifies the side_view schema. The previous report (compare_v54_v55)
checked >10% drift on the manufacturer field — that's no longer applicable
because the manufacturer field has been explicitly demoted in v5.6. The new
thresholds are:

- `trailer_seated_flush` drift >5% on yes-cohort → stop-and-surface.
- `gap_between_apron_and_plate` drift >5% on yes-cohort → stop-and-surface.
- `fifth_wheel_manufacturer` drift → informational only (drift is the
  *intended* outcome of the demotion).
- Lock_jaws + pintle fields → should be bit-for-bit identical to v5.5 on
  the same images (no prompt or schema change). Surface any drift.

See docs/labeling/v5-6.md "Comparison report" for the full spec.
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
    return (d.get("describe_output") or {}).get("photo_matches_category", "<missing>")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v55-dir", type=Path, required=True)
    p.add_argument("--v56-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    out_path = args.out or (args.v56_dir / "comparison_v5_5_v5_6.md")

    v55_fw = load_folder(args.v55_dir, "fifth_wheel")
    v56_fw = load_folder(args.v56_dir, "fifth_wheel")
    v55_lj = load_folder(args.v55_dir, "lock_jaws")
    v56_lj = load_folder(args.v56_dir, "lock_jaws")
    v55_pin = load_folder(args.v55_dir, "pintle_hook")
    v56_pin = load_folder(args.v56_dir, "pintle_hook")

    v55_log = json.loads((args.v55_dir / "audit_log.json").read_text())
    v56_log = json.loads((args.v56_dir / "audit_log.json").read_text())

    L: list[str] = []
    L.append("# v5.5 → v5.6 comparison\n")
    L.append(
        f"Seed: {v56_log['seed']} (same 90-image audit subset). v5.5: `{args.v55_dir.name}`, "
        f"v5.6: `{args.v56_dir.name}`.\n"
    )
    L.append(
        "v5.6 simplifies side_view: removes manufacturer-conditional sub-objects "
        "(holland/fontaine/jost) and demotes `fifth_wheel_manufacturer` to a flat "
        "descriptive field. Drift expectations differ from v5.4→v5.5 — see threshold "
        "notes below.\n"
    )

    # ------------------------------------------------------------------
    # Section 1 — Schema integrity
    # ------------------------------------------------------------------
    L.append("\n## 1. Schema integrity\n")
    v55_total = sum(v55_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel", "lock_jaws", "pintle_hook"))
    v56_total = sum(v56_log["source_folders"][k]["final_valid"] for k in ("fifth_wheel", "lock_jaws", "pintle_hook"))
    L.append(f"- v5.5 final_valid: **{v55_total}/90**")
    L.append(f"- v5.6 final_valid: **{v56_total}/90**")
    schema_ok = v56_total == 90

    # ------------------------------------------------------------------
    # Section 2 — photo_matches_category flag rate
    # ------------------------------------------------------------------
    L.append("\n## 2. photo_matches_category flag rate\n")
    def flag_counts(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
        c = Counter(pmc(d) for d in rows)
        return c.get("yes", 0), c.get("unclear", 0), c.get("no", 0)

    L.append("| Source folder | v5.5 yes | v5.5 unclear | v5.5 no | v5.6 yes | v5.6 unclear | v5.6 no |")
    L.append("|---|---|---|---|---|---|---|")
    grand = {"v55": [0, 0, 0], "v56": [0, 0, 0]}
    for folder, v55r, v56r in (("fifth_wheel", v55_fw, v56_fw), ("lock_jaws", v55_lj, v56_lj), ("pintle_hook", v55_pin, v56_pin)):
        a = flag_counts(v55r)
        b = flag_counts(v56r)
        for i in range(3):
            grand["v55"][i] += a[i]
            grand["v56"][i] += b[i]
        L.append(f"| `{folder}` | {a[0]} | {a[1]} | {a[2]} | {b[0]} | {b[1]} | {b[2]} |")
    L.append(f"| **total** | {grand['v55'][0]} | {grand['v55'][1]} | {grand['v55'][2]} | {grand['v56'][0]} | {grand['v56'][1]} | {grand['v56'][2]} |")
    v55_flagged = grand["v55"][1] + grand["v55"][2]
    v56_flagged = grand["v56"][1] + grand["v56"][2]
    L.append(f"\nFlagged (`unclear` + `no`): v5.5 = **{v55_flagged}/90**, v5.6 = **{v56_flagged}/90**.")

    # ------------------------------------------------------------------
    # Section 3 — Drift on primary side-view signals (stop-at-5%)
    # ------------------------------------------------------------------
    L.append("\n## 3. Side-view primary-signal drift on `photo_matches_category == yes` images\n")

    # Build by-id maps
    v55_by_id_fw = {d["image_id"]: d for d in v55_fw}
    v56_by_id_fw = {d["image_id"]: d for d in v56_fw}
    # yes-cohort = images that are yes in BOTH versions (so drift measurement isn't confounded by self-check flips)
    fw_yes_ids = sorted(
        sid for sid in v55_by_id_fw
        if sid in v56_by_id_fw
        and pmc(v55_by_id_fw[sid]) == "yes"
        and pmc(v56_by_id_fw[sid]) == "yes"
    )
    n_yes = len(fw_yes_ids)

    seated_drift: list[str] = []
    gap_drift: list[str] = []
    mfr_drift: list[str] = []
    for sid in fw_yes_ids:
        v55 = v55_by_id_fw[sid]
        v56 = v56_by_id_fw[sid]
        sv55 = block(v55, "side_view")
        sv56 = block(v56, "side_view")
        if sv55.get("trailer_seated_flush") != sv56.get("trailer_seated_flush"):
            seated_drift.append(f"{sid}: v5.5={sv55.get('trailer_seated_flush')} → v5.6={sv56.get('trailer_seated_flush')}")
        if sv55.get("gap_between_apron_and_plate") != sv56.get("gap_between_apron_and_plate"):
            gap_drift.append(f"{sid}: v5.5={sv55.get('gap_between_apron_and_plate')} → v5.6={sv56.get('gap_between_apron_and_plate')}")
        if sv55.get("fifth_wheel_manufacturer") != sv56.get("fifth_wheel_manufacturer"):
            mfr_drift.append(f"{sid}: v5.5={sv55.get('fifth_wheel_manufacturer')} → v5.6={sv56.get('fifth_wheel_manufacturer')}")

    seated_pct = (len(seated_drift) / n_yes * 100.0) if n_yes else 0.0
    gap_pct = (len(gap_drift) / n_yes * 100.0) if n_yes else 0.0
    mfr_pct = (len(mfr_drift) / n_yes * 100.0) if n_yes else 0.0

    L.append(f"Cohort (yes in both v5.5 and v5.6): **{n_yes}** fifth_wheel images")
    L.append("")
    L.append("| Field | Disagreements | % of cohort | Threshold | Status |")
    L.append("|---|---|---|---|---|")
    L.append(f"| `trailer_seated_flush` | {len(seated_drift)} | {seated_pct:.1f}% | 5% (stop-and-surface) | {'**TRIPPED**' if seated_pct > 5 else 'below'} |")
    L.append(f"| `gap_between_apron_and_plate` | {len(gap_drift)} | {gap_pct:.1f}% | 5% (stop-and-surface) | {'**TRIPPED**' if gap_pct > 5 else 'below'} |")
    L.append(f"| `fifth_wheel_manufacturer` | {len(mfr_drift)} | {mfr_pct:.1f}% | informational only (demoted) | n/a |")

    if seated_drift:
        L.append("\n<details><summary>`trailer_seated_flush` flips</summary>\n")
        for line in seated_drift:
            L.append(f"- {line}")
        L.append("\n</details>")
    if gap_drift:
        L.append("\n<details><summary>`gap_between_apron_and_plate` flips</summary>\n")
        for line in gap_drift:
            L.append(f"- {line}")
        L.append("\n</details>")
    if mfr_drift:
        L.append("\n<details><summary>`fifth_wheel_manufacturer` flips (informational)</summary>\n")
        for line in mfr_drift:
            L.append(f"- {line}")
        L.append("\n</details>")

    # ------------------------------------------------------------------
    # Section 4 — Lock_jaws parity vs v5.5
    # ------------------------------------------------------------------
    L.append("\n## 4. Lock_jaws parity check vs v5.5\n")
    v55_by_id_lj = {d["image_id"]: d for d in v55_lj}
    v56_by_id_lj = {d["image_id"]: d for d in v56_lj}
    lj_diffs: list[str] = []
    lj_pmc_diffs: list[str] = []
    for sid in v56_by_id_lj:
        if sid not in v55_by_id_lj:
            continue
        v55 = v55_by_id_lj[sid]
        v56 = v56_by_id_lj[sid]
        if pmc(v55) != pmc(v56):
            lj_pmc_diffs.append(f"{sid}: photo_matches v5.5={pmc(v55)} → v5.6={pmc(v56)}")
        b55 = block(v55, "lock_jaws_underneath")
        b56 = block(v56, "lock_jaws_underneath")
        for f in ("fifth_wheel_variant", "two_jaw_state", "single_bar_state", "kingpin_visible"):
            if b55.get(f) != b56.get(f):
                lj_diffs.append(f"{sid}.{f}: v5.5={b55.get(f)} → v5.6={b56.get(f)}")
    L.append(f"- lock_jaws field disagreements: **{len(lj_diffs)}/{len(v56_by_id_lj)}** "
             f"(parity expected: 0)")
    L.append(f"- lock_jaws photo_matches_category disagreements: **{len(lj_pmc_diffs)}/{len(v56_by_id_lj)}**")
    if lj_diffs:
        L.append("\n<details><summary>lock_jaws field flips</summary>\n")
        for line in lj_diffs[:30]:
            L.append(f"- {line}")
        if len(lj_diffs) > 30:
            L.append(f"- ... ({len(lj_diffs) - 30} more)")
        L.append("\n</details>")

    # ------------------------------------------------------------------
    # Section 5 — Pintle parity vs v5.5
    # ------------------------------------------------------------------
    L.append("\n## 5. Pintle parity check vs v5.5\n")
    v55_by_id_pin = {d["image_id"]: d for d in v55_pin}
    v56_by_id_pin = {d["image_id"]: d for d in v56_pin}
    pin_diffs: list[str] = []
    pin_pmc_diffs: list[str] = []
    for sid in v56_by_id_pin:
        if sid not in v55_by_id_pin:
            continue
        v55 = v55_by_id_pin[sid]
        v56 = v56_by_id_pin[sid]
        if pmc(v55) != pmc(v56):
            pin_pmc_diffs.append(f"{sid}: photo_matches v5.5={pmc(v55)} → v5.6={pmc(v56)}")
        b55 = block(v55, "rear_assembly")
        b56 = block(v56, "rear_assembly")
        for f in ("hitch_latch_state", "safety_chains_count", "safety_chains_clipped_to_bar"):
            if b55.get(f) != b56.get(f):
                pin_diffs.append(f"{sid}.{f}: v5.5={b55.get(f)} → v5.6={b56.get(f)}")
    L.append(f"- pintle rear_assembly field disagreements: **{len(pin_diffs)}/{len(v56_by_id_pin)}** "
             f"(parity expected: 0)")
    L.append(f"- pintle photo_matches_category disagreements: **{len(pin_pmc_diffs)}/{len(v56_by_id_pin)}**")
    if pin_diffs:
        L.append("\n<details><summary>pintle field flips</summary>\n")
        for line in pin_diffs[:30]:
            L.append(f"- {line}")
        if len(pin_diffs) > 30:
            L.append(f"- ... ({len(pin_diffs) - 30} more)")
        L.append("\n</details>")

    # ------------------------------------------------------------------
    # Section 6 — Cost
    # ------------------------------------------------------------------
    L.append("\n## 6. Cost\n")
    v55_sec = v55_log["total_elapsed_seconds"]
    v56_sec = v56_log["total_elapsed_seconds"]
    delta_pct = (v56_sec - v55_sec) / v55_sec * 100.0
    L.append(f"- v5.5 elapsed: **{v55_sec:.1f}s** ({v55_sec/60:.1f} min)")
    L.append(f"- v5.6 elapsed: **{v56_sec:.1f}s** ({v56_sec/60:.1f} min)")
    L.append(f"- delta: **{delta_pct:+.1f}%** (shorter side_view prompt, fewer fields per response)")

    # ------------------------------------------------------------------
    # Section 7 — Recommendation
    # ------------------------------------------------------------------
    L.append("\n## 7. Recommendation\n")
    if not schema_ok:
        bucket = "**Schema breakage** — Stop. Re-investigate schema or prompt assembly."
    elif seated_pct > 5 or gap_pct > 5:
        bucket = (
            "**Primary signal drift > 5%** — Stop and surface. Removing the manufacturer "
            "sub-objects somehow destabilized the primary side-view signals, which would be "
            "surprising and important."
        )
    elif lj_diffs or pin_diffs:
        bucket = (
            "**Unexpected drift on unchanged evidence types** — Surface. lock_jaws or pintle "
            "fields drifted despite no prompt or schema change. The side_view prompt change "
            "may be leaking into other evidence types."
        )
    else:
        bucket = (
            "**v5.6 passes the audit gate.** Primary side-view signals are stable, "
            "manufacturer demotion completed as designed, lock_jaws + pintle parity held. "
            "Proceed to user spot-check of the HTML reviewer, then to scale-up decision."
        )
    L.append(bucket)
    L.append("\n### Driving numbers")
    L.append(f"- Schema integrity: {v56_total}/90")
    L.append(f"- trailer_seated_flush drift: {seated_pct:.1f}% (threshold 5%)")
    L.append(f"- gap_between_apron_and_plate drift: {gap_pct:.1f}% (threshold 5%)")
    L.append(f"- fifth_wheel_manufacturer drift (informational): {mfr_pct:.1f}%")
    L.append(f"- lock_jaws field flips: {len(lj_diffs)}")
    L.append(f"- pintle field flips: {len(pin_diffs)}")
    L.append(f"- Cost delta: {delta_pct:+.1f}%")

    out_path.write_text("\n".join(L) + "\n")
    print(f"Wrote comparison to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
