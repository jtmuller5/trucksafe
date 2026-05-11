import 'dart:convert';

import '../state/app_controller.dart';
import 'inspections.dart';

/// Parses the model's raw text into an [EvidenceResult]. Tolerant of
/// common emit quirks: surrounding markdown fences, leading/trailing prose,
/// stray whitespace. Falls back to a "retake" status if the JSON can't be
/// recovered.
EvidenceResult parseEvidenceResult({
  required EvidenceType evidenceType,
  required String rawText,
  required DateTime capturedAt,
  required String imagePath,
}) {
  final json = _extractJson(rawText);
  if (json == null) {
    return EvidenceResult(
      evidenceType: evidenceType,
      status: 'retake',
      summary: 'Model did not return parseable JSON. Retake the photo.',
      confidence: 'low',
      issuesDetected: const [],
      rawJson: rawText,
      capturedAt: capturedAt,
      imagePath: imagePath,
    );
  }

  Map<String, dynamic> obj;
  try {
    obj = jsonDecode(json) as Map<String, dynamic>;
  } on FormatException {
    return EvidenceResult(
      evidenceType: evidenceType,
      status: 'retake',
      summary: 'Model returned malformed JSON. Retake the photo.',
      confidence: 'low',
      issuesDetected: const [],
      rawJson: rawText,
      capturedAt: capturedAt,
      imagePath: imagePath,
    );
  }

  final status = (obj['overall_status'] as String?)?.toLowerCase() ?? 'retake';
  final confidence = (obj['confidence'] as String?)?.toLowerCase() ?? '';
  final summary = (obj['human_readable_summary'] as String?) ?? '';
  final issuesRaw = obj['issues_detected'];
  final issues = issuesRaw is List
      ? issuesRaw.whereType<String>().toList()
      : const <String>[];

  return EvidenceResult(
    evidenceType: evidenceType,
    status: status,
    summary: summary,
    confidence: confidence,
    issuesDetected: issues,
    rawJson: const JsonEncoder.withIndent('  ').convert(obj),
    capturedAt: capturedAt,
    imagePath: imagePath,
  );
}

/// Pull the first `{ ... }` block out of arbitrary surrounding text.
String? _extractJson(String text) {
  final start = text.indexOf('{');
  final end = text.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  return text.substring(start, end + 1);
}
