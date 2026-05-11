# mobile

Flutter app for Android and iOS. Drivers walk a three-step coupling inspection and the on-device fine-tuned Gemma 4 E4B model returns structured JSON per step.

## Scaffold (on the MacBook)

```bash
cd mobile
flutter create .
```

This scaffold step is deliberately deferred to the MacBook — the GPU rig doesn't run mobile builds. After scaffolding, port the existing LiteRT-LM integration from Joe's sibling Flutter project.

## Schemas

The model's expected output is defined in `../shared/schemas/`. Dart models should be derived from those JSON Schema files so the contract stays in lockstep with the Python training code (see `../training/tests/test_schemas.py`).
