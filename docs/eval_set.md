# Trucksafe Eval Set Creation Brief

> **Goal:** Create a held-out evaluation set of 500 images per source category (1,500 total) drawn from the full ~75k archive, excluding images already in `sample-batch-01/`, pre-filtered through v5.6's `photo_matches_category` self-check, and locked away from the labeler before any fine-tuning begins.
>
> **Why this matters:** The fine-tune story in the writeup is "the fine-tuned model meaningfully beats base Gemma 4 on this task." To say that with a straight face, the eval needs to be a clean held-out set that the model has never seen, drawn from the same distribution as inference-time input, with category integrity confirmed.
>
> **Scope:** Pass-cohort eval only. Archive is positive-only; this eval measures false-negative behavior (does the model correctly recognize properly-coupled hardware?). False-positive behavior on actual coupling failures requires a separate failure-cohort eval — that depends on uncle's upcoming shoot landing and is not part of this brief.

---

## Why this design, not just "random 500 per category"

The handoff said "500 per category, random draw, locked away from labeler." That's the right size and the right discipline, but a few specifics needed locking down:

**Source pool: full archive (~75k), not the 7,500 training sample.** Drawing the eval set from the same 7,500 we plan to train on would mean either (a) carving 1,500 out of 7,500 and training on 6,000, or (b) drawing eval images that the training set has structural relationships to (sampling correlation). Drawing from the full 75k gives independent eval, broader coverage of the long tail, and full freedom on the training-set size.

**Exclusion list: `sample-batch-01/` file IDs.** The 7,500 already-sampled training images must be excluded from the eval draw or there's eval-on-training contamination. Cheap to do, must actually be done.

**Pre-filter: v5.6 miscategorization self-check.** Per user direction. v5.6 will be run over the candidate pool, and only images where `photo_matches_category == "yes"` are eligible for the eval draw. This ensures the eval set is composed of images that actually show their claimed hardware — matching the categorical assumptions of any per-category evaluation metric.

**Category granularity: source folder structure.** Per user direction. 3 buckets — fifth_wheel `side_view`, `lock_jaws_underneath`, pintle `rear_assembly`. This matches the way the archive is organized and the way per-evidence-type metrics will be reported.

**No further stratification.** Within each source folder, simple random sampling. Manufacturer mix, image_quality mix, and detection-success-vs-refused mix will fall where they fall. For 500 images per bucket this is probably fine; we accept the eval set is *approximately* archive-distributed rather than carefully stratified. This is a deliberate choice for hackathon timeline.

---

## Eligibility filters

An image is eligible for the eval set draw if and only if:

1. It is in one of the three source folders (fifth_wheel side_view, lock_jaws_underneath, pintle rear_assembly).
2. Its file ID is NOT in `sample-batch-01/` (the existing training sample).
3. When run through v5.6 with default settings, it returns `photo_matches_category == "yes"`.
4. v5.6 returns a schema-valid response for the image (no parsing errors, no validation failures).

Images failing any of these are excluded from the eval draw, but logged so we know how many were rejected at each filter stage.

---

## Implementation order

1. **Inventory.** Build a list of all archive image IDs per source folder. Subtract `sample-batch-01/` IDs. This is the candidate pool per category.

2. **Sample candidates for v5.6 pre-filter.** From each category's candidate pool, randomly select **800 images** (we want 500 to land in eval; 800 oversamples to give comfortable margin against v5.6 rejection rate of ~20% observed in audit-batch-08). Use a fresh, recorded seed — propose `eval_draw_seed = 20260512` for reproducibility.

3. **Run v5.6 over the 800-per-category candidates.** This is 2,400 inference calls total. At v5.6's observed throughput on audit-batch-08 (90 images in ~483 seconds), expect ~3.5 hours single-5090. Acceptable — and this is also useful coverage data (more images run through the production labeler with results logged).

4. **Filter candidates.** Keep only images where v5.6 returned schema-valid output AND `photo_matches_category == "yes"`. Report how many remain per category.

5. **Final draw.** From the filtered pool per category, randomly select 500 with a recorded sub-seed (propose `eval_final_seed = 20260512_final`). If any category has fewer than 500 eligible images after filtering, **stop and surface** — the candidate over-sample needs to grow, or we need to discuss whether <500 is acceptable for that bucket.

6. **Lock the eval set.** Write the final 1,500 image IDs to `eval/eval_set_v1/manifest.json` along with:
   - The draw seed
   - The exclusion list source (sample-batch-01/ snapshot ID or hash)
   - The v5.6 labeler version + git SHA used for pre-filter
   - The v5.6 labels themselves (per-image, full schema output) — this is *labeler reference output*, useful for comparing against fine-tuned student model later
   - Per-category counts after each filter stage (raw candidate → seed-sampled → v5.6-passed → final 500)
   - Timestamp

7. **Move eval set out of the labeler's reachable paths.** Two options:
   - **Soft lock:** add `eval/eval_set_v1/` to the labeler's exclusion config so it refuses to label these IDs unless explicitly overridden.
   - **Hard lock:** physically move the image files to a separate directory the labeler cannot access without a config change. More tamper-resistant.
   - Recommend hard lock if it's not a major refactor; soft lock as fallback.

8. **Write the eval-set integrity README** at `eval/eval_set_v1/README.md` documenting: how it was drawn, what filters were applied, what's in the manifest, and the rule that this set must not be relabeled or modified before fine-tune evaluation.

---

## Deliverables

- `eval/eval_set_v1/manifest.json` — 1,500 entries with image IDs, source category, v5.6 reference labels, draw metadata
- `eval/eval_set_v1/README.md` — integrity and provenance documentation
- `eval/eval_set_v1/draw_log.json` — per-category filter stage counts (raw → sampled → filtered → final)
- Updated labeler exclusion config (soft lock) or moved files (hard lock)
- JOURNEY.md entry documenting the eval set creation: rationale, counts, seeds

---

## Open items this brief does NOT address

1. **Failure-cohort eval set.** Archive is positive-only. False-positive behavior on actual coupling failures requires staged failures or open-web failure imagery. Depends on uncle's shoot. If failures arrive, plan a separate `eval/failure_cohort_v1/` with its own brief — the metrics are different (we care about whether the model correctly flags failures, which is a different question than whether it correctly accepts passes).

2. **The eval-time metrics themselves.** This brief creates the eval set. The fine-tune evaluation harness (what metrics get computed, on which fields, how it compares base-model vs fine-tuned-model performance) is a separate piece of work. The eval set being locked first is a prerequisite for that harness to mean anything.

3. **Whether v5.6 labels on the eval set are "ground truth."** They're not — they're labeler reference output. For genuine ground truth, we'd want uncle to spot-check a sample (say 50–100 images) and confirm the v5.6 labels match what he'd call. That's a small additional task on top of this brief and worth doing if his time permits.

---

## A note on the v5.6-as-pre-filter design

The pre-filter uses v5.6's `photo_matches_category` field to exclude miscategorized images from the eval. v5.6's miscategorization detection was independently audited as 75% precise (15/20 correct flags on the audit-batch-08 review). That's a real number to report in the writeup, not a glossed-over assumption.

What this means concretely: the eval set is composed of images that v5.6 says match their category. ~5% of those may actually be miscategorized that v5.6 missed (75% precision = 25% miss rate on the positive class, but on a base rate of ~20% miscategorization the absolute miss rate in the eligible pool is much lower). For 500 images per category that translates to ~5–10 sneak-throughs per bucket. Acceptable noise floor for a hackathon eval; worth noting in the writeup as a known limitation rather than hiding.