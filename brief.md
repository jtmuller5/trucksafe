# Image Sampling & Sync Brief — MacBook → GPU Rig

> Target: a coding agent running on the user's MacBook with the repo cloned locally. The user is also reachable to answer questions.
>
> Goal: sample ~2,000–3,000 images per category from a local archive of ~75k photos, transfer them to the GPU rig over Tailscale via rsync, and land them in the rig's `training/data/images/` directory in a structure the training pipeline can consume. Do not start training. Do not generate labels. Just sample, sync, and verify.

---

## Context

The user has a trucking-safety hackathon project (Gemma 4 Impact Challenge, deadline May 18, 2026). The repo (`trucksafe` or whatever the user named it) is already created and cloned on both their MacBook and a GPU rig. The repo has three top-level dirs that matter for this task: `training/`, `shared/schemas/`, and a `.gitignore` that already excludes `training/data/images/` from version control.

Three image categories, one folder per category on the MacBook:
- `fifth_wheel/` — ~30,000 photos of fifth wheel side-view inspections
- `lock_jaws/` — ~30,000 photos of lock jaws close-ups
- `pintle_hook/` — ~15,000 photos of pintle hook + safety chains inspections

The folder structure IS the metadata. Each image's category label is its parent folder name. There is no other metadata (no timestamps, no driver IDs, no truck IDs in this batch). The user is aware this limits some downstream analyses (natural-negative mining via resubmission detection, stratified splits by truck) and is fine with that for v1.

The GPU rig is reachable from the MacBook over Tailscale by hostname (no public IP, no port forwarding).

---

## Constraints, hard

- **Don't commit images to git.** The repo's `.gitignore` already covers `training/data/images/` — verify this before doing anything. If by some accident an image gets staged, abort and notify.
- **Don't modify originals on the MacBook.** All operations on the source archive are read-only. The sampled set is a copy.
- **Don't transfer the full 75k.** This task is the curated working set only.
- **Reproducible sampling.** The sampling must be seedable so the same call produces the same sample. Use a fixed seed and write it to a manifest the user can review.
- **Verify after transfer.** Confirm file counts and a checksum sample match between MacBook and rig before declaring success.
- **Ask the user before installing any tool not listed below.** Required tools: `rsync` (preinstalled on macOS), `python3` (preinstalled), the repo's `uv` env (already set up on rig but not strictly needed for this task).

## Constraints, soft

- The user types in Dvorak on a Moonlander. No impact on this task; mentioned for context.
- The user is comfortable in the terminal but prefers commands they can read top-to-bottom over clever one-liners.
- Keep the staging directory clean. After verifying the transfer, the local sampled copy on the MacBook can stay (it's small) but make sure it's not in a place that'll confuse later steps.

---

## What you're producing

By the end of this task:

1. **On the MacBook:** a staged sample directory at `~/projects/trucksafe-data/sample-batch-01/` (outside the repo) containing the sampled images organized by category, plus a manifest file recording exactly which images were sampled.
2. **On the GPU rig:** the same images landed at `~/projects/trucksafe/training/data/images/sample-batch-01/` in the same structure, with the manifest copied alongside.
3. **In the repo (committed):** a small `training/data/MANIFEST_sample-batch-01.md` that records *what* the batch contains (counts, sampling seed, source path on the MacBook) without containing the images themselves. This is the lightweight provenance record that *can* live in git.
4. **A short report back** to the user with counts, verification results, and any issues encountered.

---

## Step 1 — Confirm paths and connection details

The source path is known: **`../truck_safe/training_images/`** relative to the repo root on the MacBook. In absolute terms, that's a sibling directory of the repo — if the repo is at `~/projects/trucksafe/`, the images are at `~/projects/truck_safe/training_images/`. Verify this exists and has the three category subfolders before doing anything else:

```bash
SRC_DIR="$(cd "$(dirname "$0")/../truck_safe/training_images" && pwd)"
# Or, if running from the repo root:
SRC_DIR="$(cd ../truck_safe/training_images && pwd)"
ls -1 "$SRC_DIR"
# Expect: fifth_wheel  lock_jaws  pintle_hook
```

If the directory doesn't exist at that relative path, ask the user before guessing alternatives.

Ask the user for the connection details to the rig:

> "What's the Tailscale hostname for the GPU rig, and what username should I use for SSH/rsync?"

---

## Step 2 — Sanity check the source

Before doing anything else, count what's actually in each category folder:

```bash
# Confirm structure
ls -1 "$SRC_DIR"
# Expect: fifth_wheel  lock_jaws  pintle_hook

# Count per folder
for cat in fifth_wheel lock_jaws pintle_hook; do
  echo -n "$cat: "
  find "$SRC_DIR/$cat" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.heic' -o -iname '*.heif' \) | wc -l
done
```

Expected: roughly 30k, 30k, 15k respectively. If counts are wildly off (under 1,000 in any category, or one category is empty), stop and report to the user — something is wrong with the download.

Note any non-image files mixed in (`.DS_Store`, sidecar JSONs, etc.). Don't error on them; just note their presence.

---

## Step 3 — Sample the images

Write a small Python script. Put it in the repo at `training/scripts/sample_batch.py` so it's version-controlled and reproducible. The script:

1. Takes the source dir, output dir, samples-per-category, and seed as arguments.
2. For each category, enumerates all image files (case-insensitive extension match for jpg/jpeg/png/heic/heif), sorts the list deterministically, then uses `random.Random(seed)` to draw the sample.
3. Copies (not moves) each sampled file to the output dir, preserving the category folder structure.
4. Writes a `manifest.json` to the output dir recording: source path, output path, seed, per-category counts, total count, sampling timestamp, and the list of sampled filenames per category.

**Default parameters:** seed = `20260511`, samples-per-category = `2500`. Mention these in the user-facing summary so they can rerun with different values if desired.

**Edge cases to handle:**
- If a category has fewer images than the requested sample size, use all of them and log a warning.
- If an image file is unreadable or 0 bytes, skip it, log it, and draw a replacement from the same category.
- HEIC files: copy them as-is. We'll convert to JPEG on the rig if the labeling pipeline needs it (this is the kind of decision better made on the rig where the labeler runs).

Run the script. Confirm the output dir structure and counts look right.

---

## Step 4 — Transfer to the rig over Tailscale

Use `rsync` over SSH. The command should look like:

```bash
rsync -avh --progress \
  --include='*/' \
  --include='*.jpg' --include='*.jpeg' --include='*.JPG' --include='*.JPEG' \
  --include='*.png' --include='*.PNG' \
  --include='*.heic' --include='*.HEIC' --include='*.heif' --include='*.HEIF' \
  --include='manifest.json' \
  --exclude='*' \
  ~/projects/trucksafe-data/sample-batch-01/ \
  "$RIG_USER@$RIG_HOST:~/projects/trucksafe/training/data/images/sample-batch-01/"
```

(Adapt project name and remote path if the user's setup differs.)

Notes:
- `-h` for human-readable sizes, `--progress` so the user can watch it run.
- Explicit include/exclude pattern to keep stray `.DS_Store` files out.
- Use `-a` (archive mode) so timestamps and permissions survive — they don't matter much here but it's a defensive default.
- `~7,500 images × ~1 MB average = ~7-10 GB transfer`. Over typical home Tailscale this is minutes, not hours. If estimated time exceeds 30 minutes, pause and ask the user if they want to proceed.

If `rsync` fails partway through, it can be re-run safely — it'll skip files already transferred. Don't retry blindly more than twice without checking with the user.

---

## Step 5 — Verify the transfer

After rsync completes, run a verification on both sides:

**On the MacBook:**
```bash
cd ~/projects/trucksafe-data/sample-batch-01
for cat in fifth_wheel lock_jaws pintle_hook; do
  echo -n "$cat: "
  find "$cat" -type f -not -name '.DS_Store' | wc -l
done
```

**On the rig (via `ssh $RIG_USER@$RIG_HOST`):**
```bash
cd ~/projects/trucksafe/training/data/images/sample-batch-01
for cat in fifth_wheel lock_jaws pintle_hook; do
  echo -n "$cat: "
  find "$cat" -type f | wc -l
done
```

Counts must match exactly per category. If they don't, identify the gap (likely cause: rsync filter excluded something) and resync.

Then a checksum spot-check — pick 5 random files from each category and verify md5 matches between MacBook and rig:

```bash
# On MacBook, for each picked file:
md5 "$MAC_FILE"

# On rig:
ssh "$RIG_USER@$RIG_HOST" "md5sum ~/projects/trucksafe/training/data/images/sample-batch-01/$REL_PATH"
```

(macOS uses `md5`, Linux uses `md5sum`, and they print differently — extract just the hex digest from each before comparing.)

Don't checksum all 7,500 files; that's overkill. 15 spot checks (5 per category) is enough confidence.

---

## Step 6 — Write the committable manifest

Create `training/data/MANIFEST_sample-batch-01.md` in the repo. This is what *gets committed* — a small text record of the batch, not the images themselves. Format:

```markdown
# Sample Batch 01

- **Created:** YYYY-MM-DD HH:MM
- **Source archive:** (user-confirmed path on MacBook, anonymized if it contains a username — use `~/...` style)
- **Sampling seed:** 20260511
- **Samples requested per category:** 2,500
- **Categories:**
  - `fifth_wheel`: <actual count> images
  - `lock_jaws`: <actual count> images
  - `pintle_hook`: <actual count> images
- **Total:** <sum>
- **Total size on rig:** <e.g., 8.4 GB>
- **Rig path:** `~/projects/trucksafe/training/data/images/sample-batch-01/`
- **Provenance:** All images are real submissions from the user's uncle's commercial trucking fleet, captured via an existing photo-submission workflow. Folder name is the only metadata; no per-image timestamps or driver IDs in this batch.

## Limitations of this batch

- **No per-image metadata.** Without timestamps and driver/truck IDs, we cannot mine natural negatives via resubmission detection or stratify train/test splits to prevent the model from memorizing specific trucks. Train/test split will be random; resubmission-based negative mining is deferred to a future batch when richer metadata is available.
- **Positive-skewed.** These images were drawn from an archive where most photos represent approved inspections. The negative class will come primarily from staged failure photos shot by the user's uncle this weekend, plus open-web "high hook" reference images.

## Reproduction

```
cd training
uv run python scripts/sample_batch.py \
  --src ../../truck_safe/training_images \
  --out ~/projects/trucksafe-data/sample-batch-01 \
  --per-category 2500 \
  --seed 20260511
```
```

Commit this manifest to the repo with message: `Add sample batch 01 manifest (5,000-7,500 images per category sampled to rig)` (adjust counts based on actual). Do NOT commit the `manifest.json` from inside the batch directory — that's specific to the batch and contains the full filename list; it lives next to the images on the rig instead.

---

## Step 7 — Report back to the user

Summarize:
1. Per-category counts on the rig
2. Total transfer size
3. Verification result (checksums matched / didn't match)
4. Anything weird (non-image files in source, files that couldn't be read, count mismatches)
5. Suggested next step: "Ready to start labeling. The 31B labeling pipeline should consume from `~/projects/trucksafe/training/data/images/sample-batch-01/`."

Stop there. Do not start labeling. Do not write the labeling prompts. Do not download Gemma 4 31B weights. The user will direct the next task.

---

## Open questions to ask the user inline (don't proceed without answers)

1. Tailscale hostname and SSH username for the GPU rig.
2. Confirmation that the project name in `~/projects/<name>/` matches between MacBook and rig (in case they renamed it after the GitHub repo was created).

Source path is already known: `../truck_safe/training_images/` (sibling directory of the repo). Verify it resolves and skip asking about it unless the directory doesn't exist where expected.

## Things to NOT do in this task

- Don't try to deduplicate images. The user wants to know if there are duplicates, but de-duping is a labeling-pipeline concern, not a sampling concern.
- Don't try to detect blur, darkness, or other quality issues. Same reasoning — that's the labeler's job, or a separate curation pass.
- Don't HEIC→JPEG convert. Defer to the rig where the labeling pipeline can decide.
- Don't generate any image previews, thumbnails, or contact sheets. The user doesn't need them and they'd just slow this down.
- Don't run `uv add` for any new Python deps. The sampling script uses stdlib only — `os`, `pathlib`, `random`, `shutil`, `json`, `argparse`. Keep it that way.
- Don't push to GitHub at the end of this task. The manifest commit is fine, but the push can happen with the user's next batch of commits — no point burning a CI cycle on a single small markdown file.