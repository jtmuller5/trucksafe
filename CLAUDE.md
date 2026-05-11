# CLAUDE.md

Guidance for Claude Code working in this repo.

## Two-machine workflow

This project lives on two machines and Joe makes changes from both:

- **GPU rig** (Ubuntu, `chonky`) — `/home/joemuller/projects/trucksafe/` — training, labeling, fine-tuning.
- **MacBook** — mobile (Flutter), dashboard (Next.js), most editing.

**Before making any changes**, always pull first so you don't fork the history:

```bash
git pull --rebase
```

If you're about to make non-trivial edits, run `git status` and `git log --oneline -5` too — confirm the branch is clean and you're caught up. If `git pull` reports merge conflicts, stop and ask Joe rather than guessing.

After committing, push promptly so the other machine can pull. Don't leave commits sitting locally.

## Logs and guides

- **`JOURNEY.md`** — Timeline of major blockers, wins, and findings. Append to this as the build progresses so the journey is reconstructable later.
- **`GEMMA_TRAINING_GUIDE.md`** — Anything about training the Gemma model, the training pipeline, or troubleshooting. This is meant to be **reusable across projects**, so write it like a standalone reference, not a project diary.

Neither file exists yet — create when there's something real to record.
