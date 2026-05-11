import 'package:flutter/services.dart' show rootBundle;

import 'inspections.dart';

/// Per-evidence-type system prompt + user prompt. The JSON Schema text
/// is loaded from the bundled asset and inlined into the system prompt so
/// Gemma 4's native structured-output behavior targets the right shape.
class EvidencePrompt {
  EvidencePrompt({
    required this.evidenceType,
    required this.systemPrompt,
    required this.userPrompt,
  });

  final EvidenceType evidenceType;
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

const _perEvidence = {
  EvidenceType.sideView: '''
This is the side view of the fifth wheel coupling.
Pass criteria:
- The trailer apron is flush against the fifth wheel plate with no visible
  daylight between them.
- The release handle is in the stowed position.
''',
  EvidenceType.lockJawsUnderneath: '''
This is the underneath view of the lock jaws.
Pass criteria:
- The locking jaws are fully closed around the kingpin shank.
- The kingpin is visible in the jaws.
- The lock indicator is in the locked position (if visible in frame).
''',
  EvidenceType.rearAssembly: '''
This is the rear pintle hook + safety chains assembly.
Pass criteria:
- The hook latch is closed.
- A safety pin is visible through the latch hole.
- At least two safety chains are visible, both hooked to the receiver
  crossmember, and crossed beneath the tongue.
''',
};

const _userPrompt = 'Inspect this photo and emit the JSON.';

Future<EvidencePrompt> loadEvidencePrompt(EvidenceType evidence) async {
  final schemaJson = await rootBundle.loadString(evidence.schemaAsset);
  final perCat = _perEvidence[evidence]!;
  final system = '$_baseRules\n$perCat\nSchema:\n$schemaJson';
  return EvidencePrompt(
    evidenceType: evidence,
    systemPrompt: system,
    userPrompt: _userPrompt,
  );
}
