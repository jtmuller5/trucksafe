# Mobile App Setup Brief — Flutter + LiteRT-LM (Android + iOS)

> Target: a coding agent running on the user's MacBook (Apple Silicon, Flutter pre-installed, Xcode pre-installed, Android Studio pre-installed). Repo already cloned at `~/projects/trucksafe/` with `mobile/` as an empty placeholder directory.
>
> Goal: scaffold a Flutter app at `mobile/` and design + implement the integration layer that lets it run Gemma 4 E4B `.litertlm` models on-device on both Android and iOS. The app itself is minimal — three-step inspection checklist UI that captures a photo per step and emits the structured JSON via on-device inference.
>
> This task ends with: scaffolded Flutter project, working LiteRT-LM bindings on at least one platform end-to-end with a real model file (the user has the Gemmacademy `.litertlm` available for testing), inspection UI walkthrough working on that platform, and a clear plan for getting the second platform to parity. Do not wire up the real fine-tuned model — it doesn't exist yet. Use any working Gemma 4 E4B `.litertlm` for the integration test.

---

## Read these first

1. **`docs/gemma-finetune-deployment-guide.md`** at the repo root. Documents the previous project's deployment pipeline. The relevant section is Step 5 — "Verify on the target device" — which establishes how to know on-device inference is working correctly. The chat template gotcha (Step 4 of the guide) is especially relevant: training-side and on-device tokenization must be byte-identical, which means the same chat template file the training pipeline uses needs to live in this mobile project too.
2. **The PRD's Section 6.1, 6.4** — these define the three-step checklist UI and the three JSON schemas the app must consume. The schemas are canonical at `shared/schemas/*.json`; do not redefine them in Dart.

---

## Context

`trucksafe` is a hackathon project (Gemma 4 Impact Challenge, deadline May 18, 2026). The fine-tuned Gemma 4 E4B model will ship to drivers as a `.litertlm` file (~4.8 GB if quantized at wi8 per the deployment guide's default). The mobile app loads that model and runs three inspection categories:

1. Fifth wheel side view
2. Lock jaws close-up
3. Pintle hook + safety chains

For each, the driver takes a photo and the model returns structured JSON conforming to the corresponding schema in `shared/schemas/`. The app shows the human-readable summary and overall pass/fail status; the full JSON is stored locally.

The user's uncle's fleet has drivers with a mix of Android and iOS devices, which is why both platforms are in scope. iOS support in LiteRT-LM is rougher than Android (Swift API is still marked "in dev" per official docs; community Swift package exists but third-party; known mispackaging bug means iOS GPU acceleration via Metal doesn't currently work, only CPU). The plan accommodates that asymmetry.

---

## Constraints, hard

- **Cross-platform from day one.** Both Android and iOS must work end-to-end before this task ends — at minimum, both must successfully load a `.litertlm`, run inference on a test prompt, and return text. Full inspection UI does not need to ship on both platforms in this task; the second platform can have a "platform parity" follow-up before the demo.
- **FFI to LiteRT-LM C/C++ libraries on both platforms.** Per the user's explicit decision. The justification: LiteRT-LM exposes the same C API on both platforms, so a single Dart FFI binding works for both, with platform-specific binary loading. This is more upfront work than platform channels but produces a unified, maintainable API. **Exception:** if Step 0 research turns up a credible existing Flutter plugin that already does FFI to LiteRT-LM and supports both platforms, recommend it instead and wait for the user's decision before proceeding.
- **No platform-channel-based Kotlin/Swift bridge fallback without explicit user approval.** This is a structural choice; the agent cannot adopt it unilaterally. If FFI turns out to be infeasible, stop and report — don't pivot to platform channels on your own.
- **iOS GPU/Metal acceleration is out of scope.** A known bug (see https://github.com/google-ai-edge/LiteRT/issues/6745) mispackages the iOS arm64 Metal accelerator. iOS uses CPU inference only for v1. Android uses GPU acceleration via the Android NN API or the LiteRT GPU delegate.
- **No authentication, no user accounts, no cloud calls.** This app is fully local. Local SQLite for inspection records is fine; nothing else network-dependent at all. Airplane mode is the demo proof.
- **The model file does not ship inside the APK/IPA.** The model is ~4.8 GB; far over Play Store and App Store size limits. The app loads it from a local file path (initially: developer pushes the file to the device; later v2 will pull from a QR-scanned URL). For this task, the model file is loaded from a hardcoded device path that the user provides at runtime via a settings screen.
- **Don't reinvent the schemas in Dart.** Generate Dart types from `shared/schemas/*.json` using a JSON-Schema-to-Dart codegen step. If no good Dart codegen exists, hand-write the Dart types but include a CI-style check that compares them against the JSON Schema at startup.
- **The chat template the model was trained against must match the chat template the app uses at inference.** Per the deployment guide's hard rule. The training side will publish the template; the app needs to load it from a bundled asset. For now, bundle a placeholder template and document the swap point.

## Constraints, soft

- The user is a TypeScript developer who uses Flutter for side projects. Don't over-explain Flutter; do explain anything platform-specific (FFI binding patterns, iOS Podspec details, Android JNI ABIs).
- The user dislikes patronizing comments and excessive defensive error handling.
- Tooling preference: `fvm` for Flutter version management if not already in use. Confirm before installing.
- The user has a Moonlander Dvorak setup — no impact on this task.

---

## Step 0 — Research and decision checkpoint (mandatory)

Before scaffolding anything, the agent investigates the current state of Flutter + LiteRT-LM integration and reports back to the user. The user will then either confirm the default plan or pick a different path.

Research:

1. **Search for existing Flutter plugins for LiteRT-LM.** Try `pub.dev` searches for "litert", "litert-lm", "tflite", "gemma", "google ai edge". Note any plugins that exist, their last update date, star count, whether they support both platforms, whether they use FFI or platform channels under the hood, and whether they support `.litertlm` files (not just the older `.tflite` format).
2. **Search for community FFI examples.** GitHub topics `litert-lm`, `litert-lm-ios`. Note any working FFI integrations.
3. **Check the official LiteRT-LM repository's `examples/` directory.** Specifically look for Flutter examples, FFI examples, or anything that suggests Google has a recommended Flutter integration path.
4. **Verify the iOS arm64 Metal mispackaging issue is still open.** Check https://github.com/google-ai-edge/LiteRT/issues/6745 status. If it's been fixed, iOS GPU is back in scope.
5. **Check LiteRT-LM's current C API surface for binary distribution.** Specifically: does the project publish prebuilt `.so` files for Android ABIs? Does it publish a `.framework` or `.xcframework` for iOS? What's the recommended way to consume them?

Report back to the user with:

- The credibility of any existing Flutter plugin discovered (last commit, maintainer, breadth of API coverage, support for `.litertlm`)
- Whether Google has an official recommended integration path that's changed since this brief was written
- Whether iOS Metal acceleration is now viable
- A recommendation: proceed with rolled-from-scratch FFI bindings, OR adopt an existing plugin, OR escalate to the user with specific tradeoffs

**Stop here and wait for the user's decision before proceeding.** If they say "proceed with FFI bindings, no good plugin exists," continue with the rest of this brief. If they pick a plugin or want to revisit, that's a new direction.

---

## Step 1 — Scaffold the Flutter project

Assumes Step 0 concluded with FFI bindings as the path forward.

```bash
cd ~/projects/trucksafe/mobile
fvm use 3.27.0  # or whichever stable Flutter version is current; confirm with the user
flutter create . --org com.trucksafe --project-name trucksafe --platforms android,ios --description "On-device commercial truck pre-trip safety inspector"
```

Project layout that diverges from the default Flutter scaffold:

```
mobile/
├── lib/
│   ├── main.dart
│   ├── app.dart                         # MaterialApp + routing
│   ├── screens/
│   │   ├── home_screen.dart             # Start inspection / view past inspections
│   │   ├── inspection_screen.dart       # Three-step checklist walkthrough
│   │   ├── capture_screen.dart          # Camera capture for a single step
│   │   ├── result_screen.dart           # Pass/fail summary after all 3 steps
│   │   └── settings_screen.dart         # Set model file path
│   ├── inference/                       # Model inference layer
│   │   ├── litert_lm.dart               # Dart FFI bindings to the C API
│   │   ├── litert_lm_bindings.g.dart    # ffigen output (don't hand-edit)
│   │   ├── model_session.dart           # Higher-level wrapper: load, generate, dispose
│   │   ├── chat_template.dart           # Loads bundled chat template, formats messages
│   │   ├── prompts.dart                 # Three category prompts + schemas embedded
│   │   └── isolate_runner.dart          # Runs inference on a background isolate
│   ├── schemas/                         # Dart types derived from shared/schemas/
│   │   ├── fifth_wheel_side_view.dart
│   │   ├── lock_jaws_closeup.dart
│   │   └── pintle_hook_and_chains.dart
│   ├── storage/
│   │   └── inspection_repository.dart   # SQLite via drift or sqflite
│   └── widgets/                         # Shared UI components
├── assets/
│   ├── chat_template.jinja              # Bundled chat template (must match training)
│   └── schemas/                         # Copy of shared/schemas/ for asset access
├── android/
│   └── app/src/main/jniLibs/            # .so files per ABI (.gitignored, fetched at build)
├── ios/
│   └── Runner/Frameworks/               # .xcframework files (.gitignored, fetched at build)
└── scripts/
    └── fetch_litert_lm_binaries.sh      # Downloads platform binaries to the right paths
```

Add these Flutter deps to `pubspec.yaml`:

- `ffi` — for FFI bindings
- `path_provider` — for app data directory
- `camera` — for photo capture
- `image` — for image preprocessing (resize, format conversion)
- `sqflite` or `drift` — for local inspection storage; agent picks based on simplicity
- `flutter_riverpod` or `provider` for state — agent picks; default to `riverpod` for testability

Dev deps:

- `ffigen` — to regenerate the C bindings from headers
- `json_serializable` + `build_runner` — for schema-derived JSON parsing

---

## Step 2 — Set up the binary distribution

The LiteRT-LM C library ships as platform-specific binaries. The agent's job is to make these reproducible to fetch and bundle into the Flutter build.

Write `scripts/fetch_litert_lm_binaries.sh` that:

1. Reads a pinned LiteRT-LM version from a `LITERT_LM_VERSION` file at the script's location.
2. Downloads the prebuilt `.so` files for Android ABIs (`arm64-v8a` minimum, `armeabi-v7a` and `x86_64` if available) from the LiteRT-LM GitHub releases.
3. Downloads the iOS `.xcframework` from the same release.
4. Places `.so` files at `android/app/src/main/jniLibs/{abi}/libliteRtLm.so` (or whatever the actual file name is — confirm in Step 0).
5. Places the `.xcframework` at `ios/Runner/Frameworks/LiteRtLm.xcframework` and updates the Podspec to reference it.
6. Verifies checksums against a manifest file checked into the repo.

The `.so` and `.xcframework` files themselves are gitignored (they're binary and large). The fetch script and the version pin file are committed.

This script must be runnable both locally (developer setup) and in CI eventually. For now just local.

---

## Step 3 — Generate the C FFI bindings

Use `ffigen` to generate Dart bindings from the LiteRT-LM C headers.

Add a `ffigen.yaml` config:

```yaml
name: 'LiteRtLmBindings'
description: 'FFI bindings for LiteRT-LM C API.'
output: 'lib/inference/litert_lm_bindings.g.dart'
headers:
  entry-points:
    - 'native/include/litert_lm.h'  # Copied from the LiteRT-LM distribution
  include-directives:
    - '**litert_lm.h'
preamble: |
  // GENERATED FILE. Do not edit. Regenerate with: dart run ffigen
```

Then:

```bash
dart run ffigen
```

This produces `litert_lm_bindings.g.dart`. The hand-written wrapper `litert_lm.dart` provides an idiomatic Dart API on top of the generated bindings — opening a model, running generation, disposing of resources.

**The wrapper API surface is small:**

```dart
class LiteRtLmSession {
  static Future<LiteRtLmSession> open(String modelPath);
  Future<String> generate({
    required String systemPrompt,
    required String userPrompt,
    Uint8List? imageBytes,        // optional image input for multimodal models
    double temperature = 0.0,
    int maxTokens = 800,
  });
  Future<void> dispose();
}
```

Inference must run on a background isolate, not the main thread — model inference blocks for tens of seconds and would freeze the UI. Use `Isolate.run` or a long-lived background isolate per `model_session.dart`'s design.

---

## Step 4 — Generate Dart schema types

From `shared/schemas/*.json`, generate Dart classes with JSON serialization. The agent picks the approach:

- Easiest: `json_serializable` + hand-written classes matching each schema's fields
- Most rigorous: a JSON-Schema-to-Dart codegen tool if one exists on `pub.dev`

Either way, the result is three Dart classes (one per category) with `fromJson`/`toJson` methods and field-level validation that mirrors the JSON Schema enums.

Write a test that loads each `shared/schemas/*.json` file at runtime, picks the enum values out, and confirms the Dart class accepts exactly those enum values and rejects any others. This is the contract test that catches schema drift between Dart and Python.

---

## Step 5 — Build the inspection UI

A minimal three-screen walkthrough:

1. **Home screen.** Two actions: "Start new inspection" and "View past inspections." For now, past inspections just shows a list of inspection records from SQLite.
2. **Inspection screen.** Shows the three steps as a vertical list with checkmarks as each is completed. Tapping a step that hasn't been completed opens the capture screen for that category.
3. **Capture screen.** Live camera preview. Driver taps capture, sees the photo, and either retakes or submits. On submit, the photo is preprocessed (resize to ~896px on the long edge, JPEG-encode), passed to the inference layer with the appropriate system prompt for that category, and the result JSON is parsed into the appropriate schema type. The result is displayed: pass/fail, the `human_readable_summary`, and a list of any `issues_detected`. The driver can dismiss and return to the inspection screen.
4. **Result screen.** Once all three steps are done, shows an overall summary: each step's status, any issues across the full inspection, a timestamp. Inspection is saved to SQLite.
5. **Settings screen.** A single field: model file path on the device. For dev, the user manually pushes the model file to the device with `adb push` or via Xcode and pastes the path here. Persist the path in `shared_preferences`.

Visual design: warm, professional, not consumer-flashy. The drivers using this are working adults; the app should respect that. Material 3 defaults are fine. Use a single muted primary color (a deep teal or blue-gray). Generous spacing. No emoji.

For this task, the camera UI can be the platform default (no custom overlays, no framing guides). Polishing the capture UX with framing guides for each category is a follow-up.

---

## Step 6 — End-to-end integration test

The agent should manually run through the full app on at least one platform — preferably Android first since it's the more mature LiteRT-LM target — using the Gemmacademy `.litertlm` from the user's prior project as a placeholder model.

The integration test isn't checking that the model produces correct JSON for truck photos (Gemmacademy is a fractions tutor, not a truck inspector). It's checking that:

1. The model file loads without crashing
2. Inference returns text within a reasonable time (under 30 seconds per image on a modern Android phone)
3. The system prompt + user prompt + image are passed correctly to the model
4. Result text comes back to the UI
5. The app doesn't crash, leak memory, or freeze the main thread

Once Android works end-to-end with a placeholder model, repeat on iOS. iOS will be slower (CPU only) and may need different timeouts.

Document the device(s) tested, observed inference times, and any platform-specific issues encountered.

---

## Step 7 — Report back

When the task is complete, report:

1. The Step 0 research findings and the agent's recommendation (which path was taken)
2. Pinned LiteRT-LM version
3. Which platform was used for the integration test
4. Inference times observed on real hardware (prefill, decode, total)
5. Any deviations from this brief and why
6. Path to a known-working state — what command brings up the app on each platform
7. What's left for platform parity (which platform isn't yet at full integration, what needs to happen to get it there)
8. Known issues, especially around iOS

---

## What you should NOT do in this task

- Don't try to fine-tune anything. The model is supplied by the training side.
- Don't ship the model inside the app bundle. It's loaded from a runtime file path.
- Don't build a fleet dashboard. That's a separate project in `dashboard/`.
- Don't build the in-transit prototype. That's `in-transit/`, deferred.
- Don't add authentication, user accounts, or anything cloud-based.
- Don't pivot to platform channels (Kotlin/Swift) without explicit user approval. If FFI fails, stop and report.
- Don't add framing guides, custom camera overlays, or any UX polish beyond what's in Step 5.
- Don't add voice input, multilingual support, or accessibility audit tooling — out of hackathon scope.
- Don't commit the LiteRT-LM binaries (`.so`, `.xcframework`) to git. They're fetched via the script.

---

## Open questions to ask the user before proceeding past Step 0

1. The agent's research-derived recommendation on Flutter integration path (existing plugin / FFI from scratch / something else).
2. Confirmation of the pinned LiteRT-LM version to use (latest stable as of the start of this task, unless the user has a preference).
3. Whether the user wants Riverpod or Provider for state management (default: Riverpod).
4. Whether the agent should use the user's existing Gemmacademy `.litertlm` for the integration test, or download a fresh Gemma 4 E4B `.litertlm` from `litert-community/gemma-4-E4B-it-litert-lm` on HuggingFace.

After Step 0, no further pauses — proceed through Steps 1–7 and report back at the end.