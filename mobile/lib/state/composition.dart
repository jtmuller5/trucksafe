import '../inference/inspections.dart';
import 'app_controller.dart';

/// Composed verdict for one [Inspection], built from a list of per-photo
/// [EvidenceResult]s.
///
/// Rules (subject to v5 schema sharpening):
/// - Any evidence `fail` → inspection `fail`. An irrecoverable observation
///   overrides everything else.
/// - All evidence `pass` → `pass`. Confidence is `high` when at least two
///   evidence types contributed, `side_view_only` when only the dominant
///   evidence type is present, `low` otherwise.
/// - All evidence `retake`/`unclear` → `retake`. Driver should add another
///   photo.
/// - Mixed `pass` + `retake`/`unclear` → `pass` with `side_view_only` (or
///   `low`) confidence — the unclear photo is non-blocking, but the lower
///   evidence diversity caps the confidence.
class ComposedVerdict {
  ComposedVerdict({
    required this.inspection,
    required this.status,
    required this.confidence,
    required this.issuesDetected,
    required this.evidence,
  });

  final Inspection inspection;

  /// "pass" | "fail" | "retake" | "incomplete".
  final String status;

  /// "high" | "side_view_only" | "low" | "" — `side_view_only` means a
  /// confident pass that rested on the dominant evidence type alone (no
  /// confirmation from optional shots).
  final String confidence;

  final List<String> issuesDetected;
  final List<EvidenceResult> evidence;

  static ComposedVerdict compose(
    Inspection inspection,
    List<EvidenceResult> photos,
  ) {
    if (photos.isEmpty) {
      return ComposedVerdict(
        inspection: inspection,
        status: 'incomplete',
        confidence: '',
        issuesDetected: const [],
        evidence: const [],
      );
    }

    final fails = photos.where((p) => p.status == 'fail').toList();
    if (fails.isNotEmpty) {
      return ComposedVerdict(
        inspection: inspection,
        status: 'fail',
        confidence: _confidenceFor(photos),
        issuesDetected: [for (final p in fails) ...p.issuesDetected],
        evidence: photos,
      );
    }

    final allRetake = photos.every(
      (p) => p.status == 'retake' || p.status == 'unclear',
    );
    if (allRetake) {
      return ComposedVerdict(
        inspection: inspection,
        status: 'retake',
        confidence: 'low',
        issuesDetected: const [],
        evidence: photos,
      );
    }

    // At least one pass, no fails. Anything not-pass is treated as
    // non-blocking unclear evidence.
    return ComposedVerdict(
      inspection: inspection,
      status: 'pass',
      confidence: _confidenceFor(photos),
      issuesDetected: const [],
      evidence: photos,
    );
  }

  static String _confidenceFor(List<EvidenceResult> photos) {
    final passingTypes = photos
        .where((p) => p.status == 'pass')
        .map((p) => p.evidenceType)
        .toSet();
    if (passingTypes.length >= 2) return 'high';
    if (passingTypes.length == 1 && passingTypes.single.isDominant) {
      return 'side_view_only';
    }
    return 'low';
  }
}
