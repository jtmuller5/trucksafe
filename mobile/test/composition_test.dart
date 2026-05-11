import 'package:flutter_test/flutter_test.dart';
import 'package:trucksafe/inference/inspections.dart';
import 'package:trucksafe/state/app_controller.dart';
import 'package:trucksafe/state/composition.dart';

EvidenceResult _r(EvidenceType t, String status, {String confidence = ''}) {
  return EvidenceResult(
    evidenceType: t,
    status: status,
    summary: '',
    confidence: confidence,
    issuesDetected: status == 'fail' ? const ['missing pin'] : const [],
    rawJson: '',
    capturedAt: DateTime(2026, 5, 11),
    imagePath: '',
  );
}

void main() {
  group('ComposedVerdict.compose', () {
    test('no photos yields incomplete', () {
      final v = ComposedVerdict.compose(Inspection.fifthWheelCoupling, []);
      expect(v.status, 'incomplete');
      expect(v.confidence, '');
    });

    test('single dominant pass = side_view_only confidence', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [_r(EvidenceType.sideView, 'pass')],
      );
      expect(v.status, 'pass');
      expect(v.confidence, 'side_view_only');
    });

    test('two evidence types pass = high confidence', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [
          _r(EvidenceType.sideView, 'pass'),
          _r(EvidenceType.lockJawsUnderneath, 'pass'),
        ],
      );
      expect(v.status, 'pass');
      expect(v.confidence, 'high');
    });

    test('non-dominant pass alone = low confidence', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [_r(EvidenceType.lockJawsUnderneath, 'pass')],
      );
      expect(v.status, 'pass');
      expect(v.confidence, 'low');
    });

    test('any fail overrides any pass', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [
          _r(EvidenceType.sideView, 'pass'),
          _r(EvidenceType.lockJawsUnderneath, 'fail'),
        ],
      );
      expect(v.status, 'fail');
      expect(v.issuesDetected, contains('missing pin'));
    });

    test('all retake/unclear = retake', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [
          _r(EvidenceType.sideView, 'retake'),
          _r(EvidenceType.lockJawsUnderneath, 'unclear'),
        ],
      );
      expect(v.status, 'retake');
      expect(v.confidence, 'low');
    });

    test('pass + unclear = pass with side_view_only', () {
      final v = ComposedVerdict.compose(
        Inspection.fifthWheelCoupling,
        [
          _r(EvidenceType.sideView, 'pass'),
          _r(EvidenceType.lockJawsUnderneath, 'unclear'),
        ],
      );
      expect(v.status, 'pass');
      expect(v.confidence, 'side_view_only');
    });
  });
}
