import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:trucksafe/inference/inspections.dart';

/// Each Dart-side evidence type should know the same observation field
/// enums as the canonical JSON Schema. This test reads the schema files
/// at runtime and verifies the Dart-side schemaId constants match the
/// schema's `category.const`. Schema drift is a hard fail.
///
/// The v5 schema audit will sharpen field names; these tests will need
/// updating once it lands.
void main() {
  group('schemas contract', () {
    final schemaDir = Directory('assets/schemas');

    test('all schemas exist as assets', () {
      for (final e in EvidenceType.values) {
        final file = File('${schemaDir.path}/${e.schemaId}.json');
        expect(file.existsSync(), isTrue,
            reason: 'missing schema asset: ${file.path}');
      }
    });

    test('evidence schemaId matches schema category.const', () {
      for (final e in EvidenceType.values) {
        final file = File('${schemaDir.path}/${e.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final props = json['properties'] as Map<String, dynamic>;
        final category = (props['category'] as Map<String, dynamic>)['const'];
        expect(category, e.schemaId,
            reason: 'Dart schemaId drifted from schema for $e');
      }
    });

    test('schema declares the canonical required fields', () {
      const expected = {
        'category',
        'observations',
        'issues_detected',
        'overall_status',
        'confidence',
        'human_readable_summary',
      };
      for (final e in EvidenceType.values) {
        final file = File('${schemaDir.path}/${e.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final required = (json['required'] as List).cast<String>().toSet();
        expect(required, expected,
            reason: 'required fields drifted for ${e.schemaId}');
      }
    });

    test('overall_status enum is pass/fail/retake exactly', () {
      const expected = {'pass', 'fail', 'retake'};
      for (final e in EvidenceType.values) {
        final file = File('${schemaDir.path}/${e.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final props = json['properties'] as Map<String, dynamic>;
        final status = props['overall_status'] as Map<String, dynamic>;
        final actual = (status['enum'] as List).cast<String>().toSet();
        expect(actual, expected,
            reason: 'overall_status enum drifted for ${e.schemaId}');
      }
    });

    test('each evidence type maps to exactly one inspection', () {
      for (final e in EvidenceType.values) {
        expect(e.inspection.evidenceTypes, contains(e));
      }
    });

    test('each inspection has at least one required evidence type', () {
      for (final i in Inspection.values) {
        expect(i.requiredEvidence, isNotEmpty,
            reason: '$i has no required evidence types');
      }
    });
  });
}
