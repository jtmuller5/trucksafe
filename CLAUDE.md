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

- **`JOURNEY.md`** — Timeline of major blockers, wins, and findings. Append to this as the build progresses so the journey is reconstructable later. Newest entries at the bottom, one dated heading per entry.
- **`docs/setup.md`** — Original repo setup brief (kept for context).
- **`docs/LABELING_PIPELINE.md`** — Brief for the labeling-pipeline build (next task on the rig).

## Relevant tech docs (`~/.claude/technology/`)

Files in the global tech knowledge base that apply to this project. Read these before answering setup, deploy, version, or "why is this failing" questions in the relevant area.

- `gemma.md` — Gemma fine-tune + on-device `.litertlm` pipeline (rig). Anything new about training the model, the pipeline, or troubleshooting goes there, not in this repo.

When a tech doc proves useful here, add it to this list. When you add new content to a doc based on something learned in this project, make sure the doc is listed here.
