# Mobile inference notes

## Plugin choice — `flutter_gemma`

We adopted `flutter_gemma` (DenisovAV, MIT, v0.15.0 — released 2026-05-09)
instead of rolling Dart FFI bindings to the LiteRT-LM C API ourselves.

The original `mobile/SETUP.md` brief permitted this if Step 0 research turned
up a credible existing plugin. The deciding factors:

- `flutter_gemma` already does FFI to the LiteRT-LM C API on **both** Android
  and iOS for `.litertlm` files (see `ModelFileType.litertlm`). Multimodal
  vision is a first-class API.
- LiteRT-LM does not publish flat shared libraries — see
  [LiteRT-LM #2154](https://github.com/google-ai-edge/LiteRT-LM/issues/2154).
  Rolling our own FFI would inherit the patch-script burden flutter_gemma
  already maintains.
- iOS GPU/Metal acceleration is still broken upstream
  ([LiteRT #6745](https://github.com/google-ai-edge/LiteRT/issues/6745));
  CPU-only on iOS as the brief assumed.

## Chat-template parity

`GEMMA_TRAINING_GUIDE.md` Step 4 says the chat template is baked into the
`.litertlm` file at conversion time via
`--jinja_chat_template_override=…/reference-template/chat_template.jinja`.
That means the template lives **in the model file**, not in the app — and
`flutter_gemma`'s docs confirm this for `.litertlm`:

> `.litertlm` files — LiteRT-LM SDK handles templates on Android/Desktop,
> manual on iOS

Implication for this codebase:

- **Android (and Desktop)**: nothing to do app-side. The runtime reads the
  template embedded in the `.litertlm` file. The training pipeline must
  pass `--jinja_chat_template_override` at conversion time to get parity
  with the trained tokenization.
- **iOS**: `.litertlm` template handling is **manual** in `flutter_gemma`.
  When the real fine-tune lands, we may need to ship the same
  `chat_template.jinja` as an asset and feed it through the iOS path. For
  now this is a known platform-parity gap. If the Step 6 integration test
  shows pad tokens or garbage on iOS, this is the first thing to check
  (`GEMMA_TRAINING_GUIDE.md:288`).

## Data model: two inspections × N evidence photos

The PRD originally treated the three photos as three independent
inspections. That was wrong — fifth_wheel side view and lock_jaws
underneath both answer the same safety question ("is the front coupling
engaged?"). The Dart side now mirrors the corrected model:

- **`Inspection`** (enum) — `fifthWheelCoupling`, `pintleHook`. What
  the driver completes.
- **`EvidenceType`** (enum) — `sideView`, `lockJawsUnderneath`,
  `rearAssembly`. What gets photographed. Each evidence type maps to one
  inspection, carries `isRequired` / `isDominant` flags, and points at
  one `shared/schemas/<id>.json` file.

The per-photo model contract is unchanged — each photo gets a single
schema-shaped JSON. The app composes the per-photo verdicts into one
inspection-level verdict (see `state/composition.dart`).

Side view is the **dominant** (load-bearing) evidence for the front
coupling. Lock jaws underneath is optional confirmation — a hard shot to
get and the v5 audit flagged its low localizable rate. A clean side view
alone produces `pass` + `confidence: side_view_only`; adding the lock
jaws shot upgrades to `confidence: high`.

When the v5 schema files (`fifth_wheel_coupling.json`,
`pintle_hook.json`) land, the per-photo schemas in
`assets/schemas/` will be replaced and `prompts.dart` updated. The
two-inspection / evidence-type shape stays.

## What lives where

- `lib/inference/inspections.dart` — `Inspection` and `EvidenceType`
  enums plus their mapping.
- `lib/inference/prompts.dart` — per-evidence-type system prompt. The
  corresponding `shared/schemas/<id>.json` is loaded from
  `assets/schemas/` and inlined into the system prompt so Gemma 4's
  native structured-output behavior targets the right shape.
- `lib/inference/gemma_session.dart` — thin wrapper over
  `FlutterGemma.installModel().fromFile()` + `model.createSession()` +
  `session.addQueryChunk(Message.withImage(...))`. One session per
  inference call (we don't want chat history bleeding between photos).
- `lib/inference/image_prep.dart` — resize to ~896px on the long edge
  and JPEG-encode before handing bytes to the model.
- `lib/inference/result_parser.dart` — tolerant JSON extractor; falls
  back to `overall_status: "retake"` when the model returns something
  unparseable.
- `lib/state/composition.dart` — `ComposedVerdict.compose(inspection,
  photos)`. Rules: any `fail` → fail; all `pass` → pass with confidence
  scaled by evidence diversity; all `retake`/`unclear` → retake; mixed
  → pass with reduced confidence. Unit-tested in
  `test/composition_test.dart`.

## Test model for first-pass integration

Per the agreed plan, the first end-to-end run uses the existing
**Gemmacademy `.litertlm`** from the prior project. Output text will be
nonsensical for truck photos — Gemmacademy is a fractions tutor — but
Step 6 only validates pipeline plumbing: file load, vision-modality
session, image bytes through the C API, text back to the UI.

The real fine-tune lands on top of this plumbing without app-side
changes (other than pointing the Settings screen path at the new file).
