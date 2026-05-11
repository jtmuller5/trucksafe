# mobile

Flutter app for Android and iOS. Drivers walk a three-step coupling inspection
and the on-device fine-tuned Gemma 4 E4B model returns structured JSON per
step. See `../docs/INFERENCE.md` for the plugin/template decisions and
`SETUP.md` for the original brief.

## Run

```bash
cd mobile
flutter pub get
flutter run            # on a connected Android device, or iOS simulator
```

Set the on-device model file path from the in-app **Settings** screen before
starting an inspection. Push the `.litertlm` to the device first:

- **Android:** `adb push gemma-4-E4B.litertlm /sdcard/Download/`
- **iOS:** drag the file into the app's Documents directory via Xcode →
  Devices and Simulators → Installed Apps → trucksafe → Download container.

## Architecture

- `lib/main.dart` — boots `FlutterGemma.initialize()`, builds the
  `AppController` and runs the app.
- `lib/state/` — vanilla `ChangeNotifier` (`AppController`) wrapped in an
  `InheritedNotifier` (`AppScope`). No Riverpod, no Provider.
  `composition.dart` turns per-photo verdicts into per-inspection ones.
- `lib/inference/` — `.litertlm` plumbing on top of `flutter_gemma`.
  `inspections.dart` defines the two inspections and the evidence types
  that feed each.
- `lib/screens/` — Home / Inspection / Capture / Result / Settings.
  The inspection screen shows **two** inspections (front coupling, rear
  hitch), each gathering one or more evidence photos.
- `lib/storage/` — `sqflite` repository for inspection records.
- `assets/schemas/` — copy of `../shared/schemas/*.json` for runtime use.
- `test/composition_test.dart` — verdict composition rules.
- `test/schemas_contract_test.dart` — fails when the Dart enum keys drift
  from the canonical JSON Schemas.

## Schemas

Canonical schemas live at `../shared/schemas/*.json`. Don't edit the copies
in `assets/schemas/` directly — they're synced by hand for now (a small
build hook or pre-commit will eventually enforce this).
