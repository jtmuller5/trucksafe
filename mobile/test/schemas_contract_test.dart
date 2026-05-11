import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:trucksafe/inference/categories.dart';

/// Each Dart-side category should know the same observation field enums
/// as the canonical JSON Schema. This test reads the schema files at
/// runtime and verifies the Dart-side category-id constant matches the
/// schema's `category.const`. Schema drift is a hard fail.
void main() {
  group('schemas contract', () {
    final schemaDir = Directory('assets/schemas');

    test('all schemas exist as assets', () {
      for (final cat in InspectionCategory.values) {
        final file = File('${schemaDir.path}/${cat.schemaId}.json');
        expect(file.existsSync(), isTrue,
            reason: 'missing schema asset: ${file.path}');
      }
    });

    test('category schema_id matches schema category.const', () {
      for (final cat in InspectionCategory.values) {
        final file = File('${schemaDir.path}/${cat.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final props = json['properties'] as Map<String, dynamic>;
        final category = (props['category'] as Map<String, dynamic>)['const'];
        expect(category, cat.schemaId,
            reason: 'Dart category.schemaId drifted from schema for $cat');
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
      for (final cat in InspectionCategory.values) {
        final file = File('${schemaDir.path}/${cat.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final required = (json['required'] as List).cast<String>().toSet();
        expect(required, expected,
            reason: 'required fields drifted for ${cat.schemaId}');
      }
    });

    test('overall_status enum is pass/fail/retake exactly', () {
      const expected = {'pass', 'fail', 'retake'};
      for (final cat in InspectionCategory.values) {
        final file = File('${schemaDir.path}/${cat.schemaId}.json');
        final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
        final props = json['properties'] as Map<String, dynamic>;
        final status = props['overall_status'] as Map<String, dynamic>;
        final actual = (status['enum'] as List).cast<String>().toSet();
        expect(actual, expected,
            reason: 'overall_status enum drifted for ${cat.schemaId}');
      }
    });
  });
}
