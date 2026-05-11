# Sample Batch 01

- **Created:** 2026-05-11 (UTC)
- **Source archive:** `~/Dev/apps/truck_safe/training_images/` on the MacBook (sibling of the repo)
- **Sampling seed:** `20260511`
- **Samples requested per category:** 2,500
- **Categories:**
  - `fifth_wheel`: 2,500 images
  - `lock_jaws`: 2,500 images (source folder is `lock_jaw`; renamed in the staged copy to match `shared/schemas/lock_jaws_closeup.json`)
  - `pintle_hook`: 2,500 images
- **Total:** 7,500 images
- **Total size on rig:** 2.9 GB
- **Rig path:** `~/projects/trucksafe/training/data/images/sample-batch-01/` (host `chonky`, reached over Tailscale at `joemuller@100.77.220.87`)
- **Per-image metadata:** A `metadata.jsonl` in the source archive provides per-image fields (`submission_id`, `driver_id`, `tractor_number`, `trailer_one_number`, `trailer_two_number`, `date`, `source_field`, `label`, `url`, `relative_path`). A filtered copy containing only the 7,500 sampled rows lives next to the images on the rig as `metadata_sample-batch-01.jsonl`. All 7,500 sampled images had a matching metadata row.
- **Provenance:** All images are real submissions from the user's uncle's commercial trucking fleet, captured via an existing photo-submission workflow that uploads to Firebase Storage. Folder structure encodes the inspection category; per-image fields above provide submission, vehicle, and timing context.

## Verification

- Per-category file counts match exactly between MacBook (`~/projects/trucksafe-data/sample-batch-01/`) and rig: 2,500 / 2,500 / 2,500.
- md5 spot-check on 15 random files (5 per category) — all matched between MacBook and rig.

## Notes / deviations from the original brief

- Source folder was `lock_jaw` (singular), not `lock_jaws` (plural) as the brief assumed. Renamed in the staged copy to match the repo's schema name.
- `pintle_hook` source pool was ~11.3k images (brief expected ~15k). Still well above the 2,500 sample target; sample drawn normally.
- `metadata.jsonl` (77,789 rows) exists in the source archive — the brief assumed folder name was the only metadata. This **changes downstream options**: resubmission-based negative mining and stratified train/test splits by truck/driver are now both feasible. Train/test split for this batch is still TBD; the limitation noted below is **revised**.

## Limitations of this batch

- **Positive-skewed.** These images were drawn from an archive where most photos represent approved inspections. The negative class will come primarily from staged failure photos shot by the user's uncle this weekend, plus open-web reference images for high-hook and similar failure modes.
- **Metadata completeness varies.** Many rows in `metadata.jsonl` have `driver_id: null` or missing `date`; any stratification or resubmission mining will need to handle nulls explicitly.

## Reproduction

From the repo root on the MacBook:

```
python3 training/scripts/sample_batch.py \
  --src ../truck_safe/training_images \
  --out ~/projects/trucksafe-data/sample-batch-01 \
  --per-category 2500 \
  --seed 20260511 \
  --rename lock_jaw:lock_jaws \
  --metadata ../truck_safe/training_images/metadata.jsonl \
  --batch-name sample-batch-01
```

Then rsync over Tailscale:

```
rsync -a --stats \
  -e "ssh -i ~/.ssh/personal/id_ed25519" \
  --include='*/' \
  --include='*.jpg' --include='*.jpeg' --include='*.JPG' --include='*.JPEG' \
  --include='*.png' --include='*.PNG' \
  --include='*.heic' --include='*.HEIC' --include='*.heif' --include='*.HEIF' \
  --include='manifest.json' --include='*.jsonl' \
  --exclude='*' \
  ~/projects/trucksafe-data/sample-batch-01/ \
  joemuller@100.77.220.87:projects/trucksafe/training/data/images/sample-batch-01/
```

The full per-image filename list, warnings, and exact UTC timestamps live in `manifest.json` alongside the images on the rig (intentionally not committed to git).
