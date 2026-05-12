#!/usr/bin/env python3
"""Generate comparison_v5_v5_2.md focused on v5.1 → v5.2 deltas.

Per the v5.2 brief: skip the v3/v4 history this round. v5.1 is the baseline,
v5.2 is the candidate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

SOURCE_FOLDERS = ("fifth_wheel", "lock_jaws", "pintle_hook")


def unwrap(d: dict[str, Any]) -> dict[str, Any]:
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


def block(d: dict[str, Any]) -> dict[str, Any]:
    ps = unwrap(d)
    return ps.get(ps.get("evidence_type"), {}) or {}


def count(labels, pred) -> int:
    return sum(1 for d in labels if pred(d))


def fmt(a: int, b: int) -> str:
    delta = b - a
    if delta == 0:
        return f"{a} → {b} (=)"
    return f"{a} → {b} ({'↑' if delta > 0 else '↓'}{abs(delta)})"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--v51-dir", type=Path, required=True)
    p.add_argument("--v52-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    a = {f: load(args.v51_dir, f) for f in SOURCE_FOLDERS}
    b = {f: load(args.v52_dir, f) for f in SOURCE_FOLDERS}

    L: list[str] = []
    L.append("# v5.1 vs v5.2 labeler audit comparison\n")
    L.append(f"- v5.1 source: `{args.v51_dir}`")
    L.append(f"- v5.2 source: `{args.v52_dir}`")
    L.append(f"\nv5.2 changes: rear_assembly prompt rewritten (pin-first, anti-default-to-false, visual signature); lock_jaws_underneath uses deterministic fixed-band crop (rows 20–70%) instead of full image; lock_jaws prompt gets a spatial-prior sentence.\n")

    # 1. Headline metrics
    L.append("## 1. Headline metrics (success bars)\n")
    L.append("| metric | v5.1 | v5.2 | target | result |")
    L.append("|---|---:|---:|---|---|")

    a_pin = count(a["pintle_hook"], lambda d: block(d).get("safety_pin_visible") is True)
    b_pin = count(b["pintle_hook"], lambda d: block(d).get("safety_pin_visible") is True)
    pin_pass = "✓" if b_pin >= 28 else "✗"
    L.append(f"| pintle_hook `safety_pin_visible == true` | {a_pin}/30 | **{b_pin}/30** | ≥28 | {pin_pass} |")

    a_var = count(a["lock_jaws"], lambda d: block(d).get("fifth_wheel_variant") in ("two_jaw", "single_bar"))
    b_var = count(b["lock_jaws"], lambda d: block(d).get("fifth_wheel_variant") in ("two_jaw", "single_bar"))
    var_pass = "✓" if b_var >= 18 else "✗"
    L.append(f"| lock_jaws `fifth_wheel_variant` non-`unclear` | {a_var}/30 | **{b_var}/30** | ≥18 | {var_pass} |")

    a_mfr = count(a["fifth_wheel"], lambda d: block(d).get("fifth_wheel_manufacturer") != "not_visible")
    b_mfr = count(b["fifth_wheel"], lambda d: block(d).get("fifth_wheel_manufacturer") != "not_visible")
    mfr_pass = "✓ no regression" if b_mfr >= 18 else "✗ REGRESSED"
    L.append(f"| side_view manufacturer non-`not_visible` (regression check) | {a_mfr}/30 | **{b_mfr}/30** | ≥18 | {mfr_pass} |")

    def consistency(labels):
        ok = 0
        for d in labels:
            blk = block(d)
            mfr = blk.get("fifth_wheel_manufacturer")
            pop = {k: blk.get(k) is not None for k in ("holland", "fontaine", "jost")}
            if mfr in ("fontaine", "jost", "holland"):
                if pop[mfr] and not any(v for k, v in pop.items() if k != mfr):
                    ok += 1
            else:
                if not any(pop.values()):
                    ok += 1
        return ok

    a_cons = consistency(a["fifth_wheel"])
    b_cons = consistency(b["fifth_wheel"])
    cons_pass = "✓" if b_cons == 30 else "✗"
    L.append(f"| manufacturer sub-object consistency | {a_cons}/30 | **{b_cons}/30** | 30/30 | {cons_pass} |")

    # Jost honest-unknown rate
    def jost_honest(labels):
        jost_lbls = [d for d in labels if block(d).get("fifth_wheel_manufacturer") == "jost"]
        ncv = sum(1 for d in jost_lbls if (block(d).get("jost") or {}).get("side_handle_position") == "not_clearly_visible")
        return ncv, len(jost_lbls)

    a_jh, a_jn = jost_honest(a["fifth_wheel"])
    b_jh, b_jn = jost_honest(b["fifth_wheel"])
    jh_pct_b = (b_jh / b_jn * 100) if b_jn else 0
    jh_pass = "✓" if jh_pct_b >= 75 else ("✗ REGRESSED" if a_jn > 0 else "n/a")
    L.append(f"| Jost honest-unknown rate | {a_jh}/{a_jn} | **{b_jh}/{b_jn}** ({jh_pct_b:.0f}%) | ≥75% | {jh_pass} |")

    # 2. Lock-jaws crop validation note
    L.append("\n## 2. Lock-jaws fixed-band crop validation\n")
    L.append("Crop applied: rows 20–70% of original height, full width, deterministic per image.")
    n_band = count(b["lock_jaws"], lambda d: (d.get("localization") or {}).get("strategy") == "fixed_band")
    L.append(f"Applied to {n_band}/30 lock_jaws images.\n")
    L.append("Visual spot-check of band placement is a manual step on the HTML reviewer. Pass criterion: band contains visible locking mechanism on ≥8/10 randomly-checked images.")

    # 3. Per-field deltas v5.1 → v5.2
    L.append("\n## 3. Per-field deltas (v5.1 → v5.2)\n")

    L.append("### pintle_hook secondary fields\n")
    L.append("| field | v5.1 | v5.2 |")
    L.append("|---|---|---|")
    for label, pred_a, pred_b in [
        ("hook_latch_state == 'closed'",
         lambda d: block(d).get("hook_latch_state") == "closed",
         lambda d: block(d).get("hook_latch_state") == "closed"),
        ("safety_chains_count == 2",
         lambda d: block(d).get("safety_chains_count") == 2,
         lambda d: block(d).get("safety_chains_count") == 2),
        ("safety_chains_crossed == 'yes'",
         lambda d: block(d).get("safety_chains_crossed") == "yes",
         lambda d: block(d).get("safety_chains_crossed") == "yes"),
        ("hook_visible == 'yes'",
         lambda d: block(d).get("hook_visible") == "yes",
         lambda d: block(d).get("hook_visible") == "yes"),
        ("lunette_ring_visible == 'yes'",
         lambda d: block(d).get("lunette_ring_visible") == "yes",
         lambda d: block(d).get("lunette_ring_visible") == "yes"),
    ]:
        L.append(f"| {label} | {count(a['pintle_hook'], pred_a)} | {count(b['pintle_hook'], pred_b)} |")

    L.append("\n### lock_jaws_underneath distribution\n")
    for fname in ("fifth_wheel_variant", "two_jaw_state", "single_bar_state", "kingpin_visible"):
        ca = Counter(block(d).get(fname) for d in a["lock_jaws"])
        cb = Counter(block(d).get(fname) for d in b["lock_jaws"])
        L.append(f"- `{fname}`: v5.1={dict(ca)} → v5.2={dict(cb)}")

    L.append("\n### fifth_wheel side_view manufacturer + sub-fields\n")
    L.append("| field | v5.1 distribution | v5.2 distribution |")
    L.append("|---|---|---|")
    for fname in ("fifth_wheel_manufacturer", "gap_between_apron_and_plate", "trailer_seated_flush"):
        ca = Counter(block(d).get(fname) for d in a["fifth_wheel"])
        cb = Counter(block(d).get(fname) for d in b["fifth_wheel"])
        L.append(f"| {fname} | {dict(ca)} | {dict(cb)} |")

    # image quality
    L.append("\n### image_quality per source folder (top-level)\n")
    L.append("| folder | v5.1 (poor/acceptable/good) | v5.2 (poor/acceptable/good) |")
    L.append("|---|---|---|")
    for f in SOURCE_FOLDERS:
        def iq(labels, v):
            return sum(1 for d in labels if unwrap(d).get("image_quality") == v)
        L.append(f"| {f} | {iq(a[f],'poor')}/{iq(a[f],'acceptable')}/{iq(a[f],'good')} | {iq(b[f],'poor')}/{iq(b[f],'acceptable')}/{iq(b[f],'good')} |")

    # 4. Holland engagement follow-up
    L.append("\n## 4. Holland `washer_flush_against_body` follow-up\n")
    def holland_engagement(labels):
        h = [d for d in labels if block(d).get("fifth_wheel_manufacturer") == "holland"]
        c = Counter((block(d).get("holland") or {}).get("washer_flush_against_body") for d in h)
        return h, c
    a_h, a_c = holland_engagement(a["fifth_wheel"])
    b_h, b_c = holland_engagement(b["fifth_wheel"])
    L.append(f"- v5.1: {dict(a_c)} (n={len(a_h)})")
    L.append(f"- v5.2: {dict(b_c)} (n={len(b_h)})")
    L.append("\nThe 2 v5.1 `no` cases (`washer_flush_against_body: no`) are listed below for spot-check:")
    a_no = [d.get("image_id") for d in a_h if (block(d).get("holland") or {}).get("washer_flush_against_body") == "no"]
    for img in a_no:
        L.append(f"- `{img}` — open in HTML reviewer to verify whether this is a real bad-engagement frame or a model misread.")

    # 5. Elapsed time
    L.append("\n## 5. Elapsed time\n")
    def t(d: Path) -> str:
        f = d / "audit_log.json"
        if not f.exists():
            return "?"
        return f"{json.loads(f.read_text()).get('total_elapsed_seconds', '?')}s"
    L.append(f"- v5.1: {t(args.v51_dir)}")
    L.append(f"- v5.2: {t(args.v52_dir)}")

    # Schema integrity (sanity)
    v52_audit_path = args.v52_dir / "audit_log.json"
    if v52_audit_path.exists():
        d = json.loads(v52_audit_path.read_text())
        total = sum(s.get("attempted", 0) for s in d.get("source_folders", {}).values())
        valid = sum(s.get("final_valid", 0) for s in d.get("source_folders", {}).values())
        L.append(f"\n## 6. Schema integrity\n")
        L.append(f"{valid}/{total} v5.2 labels validated — {'✓' if valid == total else '✗'}")

    args.out.write_text("\n".join(L) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
