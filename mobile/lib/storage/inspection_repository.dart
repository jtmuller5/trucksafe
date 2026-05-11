import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import '../inference/inspections.dart';
import '../state/app_controller.dart';

/// Persists completed inspections to a local SQLite db.
///
/// `results_json` shape:
/// ```
/// {
///   "<inspection.name>": {
///     "verdict": { "status": ..., "confidence": ..., "issues": [...] },
///     "evidence": [
///       { "evidence_type": ..., "status": ..., "summary": ..., ... },
///       ...
///     ]
///   },
///   ...
/// }
/// ```
class InspectionRepository {
  Database? _db;

  Future<void> init() async {
    if (_db != null) return;
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'trucksafe.db');
    _db = await openDatabase(
      path,
      version: 2,
      onCreate: (db, _) => _createSchema(db),
      onUpgrade: (db, _, _) async {
        // v1 stored per-category results; the shape changed when the
        // data model shifted to "two inspections, multiple evidence
        // photos." No live users yet — drop and recreate.
        await db.execute('DROP TABLE IF EXISTS inspections');
        await _createSchema(db);
      },
    );
  }

  Future<void> _createSchema(Database db) async {
    await db.execute('''
      CREATE TABLE inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        overall_status TEXT NOT NULL,
        results_json TEXT NOT NULL
      )
    ''');
  }

  Future<int> save(ActiveInspection inspection) async {
    final db = _db!;
    final payload = <String, Object?>{};
    for (final i in Inspection.values) {
      final verdict = inspection.verdictFor(i);
      payload[i.name] = {
        'verdict': {
          'status': verdict.status,
          'confidence': verdict.confidence,
          'issues': verdict.issuesDetected,
        },
        'evidence': [
          for (final e in inspection.photosFor(i)) _evidenceToMap(e),
        ],
      };
    }
    return db.insert('inspections', {
      'started_at': inspection.startedAt.toIso8601String(),
      'overall_status': inspection.overallStatus,
      'results_json': jsonEncode(payload),
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

  Map<String, dynamic> _evidenceToMap(EvidenceResult r) => {
        'evidence_type': r.evidenceType.name,
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
    required this.verdicts,
    required this.evidence,
  });

  final int id;
  final DateTime startedAt;
  final String overallStatus;
  final Map<Inspection, StoredVerdict> verdicts;
  final Map<Inspection, List<StoredEvidence>> evidence;

  static InspectionRecord fromRow(Map<String, Object?> row) {
    final payload =
        jsonDecode(row['results_json']! as String) as Map<String, dynamic>;
    final verdicts = <Inspection, StoredVerdict>{};
    final evidence = <Inspection, List<StoredEvidence>>{};
    for (final i in Inspection.values) {
      final entry = payload[i.name];
      if (entry is! Map<String, dynamic>) {
        evidence[i] = const [];
        verdicts[i] = StoredVerdict.empty();
        continue;
      }
      final v = entry['verdict'] as Map<String, dynamic>? ?? const {};
      verdicts[i] = StoredVerdict(
        status: (v['status'] ?? '') as String,
        confidence: (v['confidence'] ?? '') as String,
        issues: ((v['issues'] as List?) ?? const []).cast<String>(),
      );
      final e = (entry['evidence'] as List?) ?? const [];
      evidence[i] = [
        for (final m in e) StoredEvidence.fromMap(m as Map<String, dynamic>),
      ];
    }
    return InspectionRecord(
      id: row['id']! as int,
      startedAt: DateTime.parse(row['started_at']! as String),
      overallStatus: row['overall_status']! as String,
      verdicts: verdicts,
      evidence: evidence,
    );
  }
}

class StoredVerdict {
  StoredVerdict({
    required this.status,
    required this.confidence,
    required this.issues,
  });

  StoredVerdict.empty()
      : status = 'incomplete',
        confidence = '',
        issues = const [];

  final String status;
  final String confidence;
  final List<String> issues;
}

class StoredEvidence {
  StoredEvidence({
    required this.evidenceType,
    required this.status,
    required this.summary,
    required this.confidence,
    required this.issuesDetected,
    required this.rawJson,
    required this.capturedAt,
    required this.imagePath,
  });

  final EvidenceType evidenceType;
  final String status;
  final String summary;
  final String confidence;
  final List<String> issuesDetected;
  final String rawJson;
  final DateTime capturedAt;
  final String imagePath;

  static StoredEvidence fromMap(Map<String, dynamic> m) {
    final name = (m['evidence_type'] ?? '') as String;
    final evidenceType = EvidenceType.values.firstWhere(
      (e) => e.name == name,
      orElse: () => EvidenceType.sideView,
    );
    return StoredEvidence(
      evidenceType: evidenceType,
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
