import 'package:flutter/services.dart' show rootBundle;

import 'categories.dart';

/// Per-category system prompt + schema JSON loaded from bundled assets.
/// The schema content is the JSON Schema string itself, embedded directly
/// into the system prompt so Gemma 4's native structured-output behavior
/// targets the right shape.
class CategoryPrompt {
  CategoryPrompt({
    required this.category,
    required this.systemPrompt,
    required this.userPrompt,
  });

  final InspectionCategory category;
  final String systemPrompt;
  final String userPrompt;
}

const _baseRules = '''
You are TruckSafe, a commercial-vehicle pre-trip safety inspector. You are
shown a single photograph of one coupling component on a tractor-trailer.

Respond with a single JSON object that conforms exactly to the schema below.
No prose, no markdown fence — only the JSON object.

Decision rules:
- overall_status = "pass" only when every safety criterion in the schema is
  met. Otherwise "fail".
- overall_status = "retake" when the image is too blurry, dark, or framed to
  judge any criterion.
- confidence reflects how certain you are of the observation values.
- issues_detected lists each failing criterion in plain English, e.g.
  "Safety pin not visible through latch hole".
- human_readable_summary is one or two short sentences a driver can act on.
''';

const _perCategory = {
  InspectionCategory.fifthWheel: '''
Category: fifth_wheel_side_view.
Pass criteria:
- The trailer apron is flush against the fifth wheel plate with no visible
  daylight between them.
- The release handle is in the stowed position.
''',
  InspectionCategory.lockJaws: '''
Category: lock_jaws_closeup.
Pass criteria:
- The locking jaws are fully closed around the kingpin shank.
- The kingpin is visible in the jaws.
- The lock indicator is in the locked position (if visible in frame).
''',
  InspectionCategory.pintleHook: '''
Category: pintle_hook_and_chains.
Pass criteria:
- The hook latch is closed.
- A safety pin is visible through the latch hole.
- At least two safety chains are visible, both hooked to the receiver
  crossmember, and crossed beneath the tongue.
''',
};

const _userPrompt = 'Inspect this photo and emit the JSON.';

/// Returns the system + user prompt for [category]. The schema JSON is
/// loaded from the bundled asset and inlined into the system prompt.
Future<CategoryPrompt> loadCategoryPrompt(InspectionCategory category) async {
  final schemaJson = await rootBundle.loadString(category.schemaAsset);
  final perCat = _perCategory[category]!;
  final system = '$_baseRules\n$perCat\nSchema:\n$schemaJson';
  return CategoryPrompt(
    category: category,
    systemPrompt: system,
    userPrompt: _userPrompt,
  );
}
