import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import '../inference/categories.dart';
import '../state/app_controller.dart';

/// Persists completed inspections to a local SQLite db.
class InspectionRepository {
  Database? _db;

  Future<void> init() async {
    if (_db != null) return;
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'trucksafe.db');
    _db = await openDatabase(
      path,
      version: 1,
      onCreate: (db, _) async {
        await db.execute('''
          CREATE TABLE inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            overall_status TEXT NOT NULL,
            results_json TEXT NOT NULL
          )
        ''');
      },
    );
  }

  Future<int> save(ActiveInspection inspection) async {
    final db = _db!;
    final results = {
      for (final c in InspectionCategory.values)
        c.schemaId: _stepToMap(inspection.results[c]!),
    };
    return db.insert('inspections', {
      'started_at': inspection.startedAt.toIso8601String(),
      'overall_status': inspection.overallStatus,
      'results_json': jsonEncode(results),
    });
  }

  Future<List<InspectionRecord>> list({int limit = 50}) async {
    final db = _db!;
    final rows = await db.query(
      'inspections',
      orderBy: 'started_at DESC',
      limit: limit,
    );
    return rows.map(InspectionRecord.fromRow).toList();
  }

  Future<InspectionRecord> get(int id) async {
    final db = _db!;
    final rows = await db.query('inspections', where: 'id = ?', whereArgs: [id]);
    return InspectionRecord.fromRow(rows.single);
  }

  Map<String, dynamic> _stepToMap(StepResult r) => {
        'status': r.status,
        'summary': r.summary,
        'confidence': r.confidence,
        'issues_detected': r.issuesDetected,
        'raw_json': r.rawJson,
        'captured_at': r.capturedAt.toIso8601String(),
        'image_path': r.imagePath,
      };
}

class InspectionRecord {
  InspectionRecord({
    required this.id,
    required this.startedAt,
    required this.overallStatus,
    required this.steps,
  });

  final int id;
  final DateTime startedAt;
  final String overallStatus;
  final Map<InspectionCategory, StoredStep> steps;

  static InspectionRecord fromRow(Map<String, Object?> row) {
    final results = jsonDecode(row['results_json']! as String) as Map<String, dynamic>;
    final steps = <InspectionCategory, StoredStep>{};
    for (final c in InspectionCategory.values) {
      final m = results[c.schemaId];
      if (m is Map<String, dynamic>) {
        steps[c] = StoredStep.fromMap(c, m);
      }
    }
    return InspectionRecord(
      id: row['id']! as int,
      startedAt: DateTime.parse(row['started_at']! as String),
      overallStatus: row['overall_status']! as String,
      steps: steps,
    );
  }
}

class StoredStep {
  StoredStep({
    required this.category,
    required this.status,
    required this.summary,
    required this.confidence,
    required this.issuesDetected,
    required this.rawJson,
    required this.capturedAt,
    required this.imagePath,
  });

  final InspectionCategory category;
  final String status;
  final String summary;
  final String confidence;
  final List<String> issuesDetected;
  final String rawJson;
  final DateTime capturedAt;
  final String imagePath;

  static StoredStep fromMap(InspectionCategory c, Map<String, dynamic> m) {
    return StoredStep(
      category: c,
      status: (m['status'] ?? '') as String,
      summary: (m['summary'] ?? '') as String,
      confidence: (m['confidence'] ?? '') as String,
      issuesDetected:
          ((m['issues_detected'] as List?) ?? const []).cast<String>(),
      rawJson: (m['raw_json'] ?? '') as String,
      capturedAt: DateTime.parse(m['captured_at'] as String),
      imagePath: (m['image_path'] ?? '') as String,
    );
  }
}
