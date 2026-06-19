# Manual setup

## Technology knowledge base — finish cross-machine setup

A new cross-project knowledge base lives at `~/.claude/technology/` (git repo
at https://github.com/jtmuller5/technology, already pushed from the Mac).
Each session, Claude reads from / appends to it for hard-won
technology-specific knowledge — setup commands, gotchas, version pins, your
preferences. See `~/.claude/technology/README.md` and the new section in
`~/.claude/CLAUDE.md` for how it's used.

**Mac status**: Local repo set up, remote `origin` configured to
`jtmuller5/technology`, all commits pushed. Includes the migrated
`gemma.md` (formerly `trucksafe/technology/GEMMA_TRAINING_GUIDE.md`). Just
needs a `git push` from the Mac to send the latest `gemma.md` commit:

```bash
cd ~/.claude/technology && git push
```

### On the GPU rig `chonky` (one-time)

1. SSH in.
2. Clone the repo into place:
   ```bash
   git clone git@github.com:jtmuller5/technology.git ~/.claude/technology
   ```
3. Mirror the global CLAUDE.md change so Claude on the rig also knows about
   the directory. The Mac version is at `~/.claude/CLAUDE.md` — either scp
   it across or manually copy the new "Technology knowledge base" section
   (and the `~/.claude/` carve-out on line 1) into the rig's existing
   `~/.claude/CLAUDE.md`.
4. Add the auto-sync `Stop` hook to the rig's `~/.claude/settings.json`.
   Inside the top-level `"hooks": { ... }` object, add this entry alongside
   any existing events (don't replace them):
   ```json
   "Stop": [
     {
       "hooks": [
         {
           "type": "command",
           "command": "$HOME/.claude/technology/.auto-sync.sh",
           "timeout": 30
         }
       ]
     }
   ]
   ```
   If the rig doesn't yet have any `"hooks"` block, create one with just
   the `"Stop"` event. Verify git identity is set on the rig
   (`git config --global user.email` and `user.name`); the hook commits
   with the email/name baked into the script (`jtmuller5@gmail.com` /
   `Joseph Muller`), so this is fine even if global git config differs.

## Mobile app — on-device integration test (Step 6 of `mobile/SETUP.md`)

This requires a real device; I can't run it from the agent. After connecting
a phone over USB:

### Android (preferred — full LiteRT-LM support, GPU acceleration available)

```bash
cd mobile
flutter devices            # confirm the phone shows up
adb push /path/to/gemmacademy.litertlm /sdcard/Download/
flutter run -d <android-device-id>
```

In the app: tap the gear icon → paste
`/sdcard/Download/gemmacademy.litertlm` into the model path field → Save →
back to Home → **Start new inspection**. Pick any step, take a photo, tap
**Inspect**. Expect 20–60 s on the first run (model load) and a few seconds
per subsequent inference.

Output text will be nonsensical — Gemmacademy is a fractions tutor, not a
truck inspector. You're verifying:

1. The model loads without crashing.
2. The capture screen runs inference and returns text within ~30 s.
3. The result tile shows a status pill (likely "retake" since the JSON won't
   parse) and the inspections list shows the saved record after all three
   steps.

### iOS (platform-parity follow-up — CPU only)

```bash
cd mobile
open ios/Runner.xcworkspace
# In Xcode: set the team in Signing & Capabilities, then run on a physical
# device (simulator can't load .litertlm models). Add the
# "Increased Memory Limit" entitlement on iOS 16+ for multi-GB models.
# Xcode → Devices & Simulators → Installed Apps → trucksafe → Container →
# Download → drag the .litertlm into the app's Documents folder.
# Then in the app's Settings, paste the in-container path (the field
# accepts arbitrary absolute paths; shown after a first run via the logs).
```

iOS note: `flutter_gemma` requires manual chat-template handling for
`.litertlm` on iOS (the SDK handles it on Android/Desktop). If responses
come back as pad tokens or garbage, that's the first thing to check — see
`docs/INFERENCE.md`.

## Real fine-tuned model swap-in

When `gemma-4-E4B-trucksafe.litertlm` lands:
1. `adb push` (or Xcode container drop) onto the device
2. Update the Settings → Model file path in the app
3. The app will re-load the model on the next inference call

No code changes required.

---

## Old (sample-batch-01 transfer) — completed

The SSH-auth setup steps from the earlier task were carried out and the
batch landed on the rig. Keeping this section short as a record:

- Key at `~/.ssh/personal/id_ed25519.pub` is now authorized on
  `joemuller@100.77.220.87`.
- 7,500 images live at
  `~/projects/trucksafe/training/data/images/sample-batch-01/` with
  `manifest.json` + `metadata_sample-batch-01.jsonl` alongside.
- Committed manifest: `training/data/MANIFEST_sample-batch-01.md`.
