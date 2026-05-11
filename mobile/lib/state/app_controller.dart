import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../inference/gemma_session.dart';
import '../inference/inspections.dart';
import '../storage/inspection_repository.dart';
import 'composition.dart';

const _kModelPathKey = 'model_file_path';

/// Top-level vanilla state. Owns the model file path setting, the live
/// `GemmaSession` (lazy), the in-progress inspection (if any), and the
/// `InspectionRepository`. Widgets read it via `AppScope.of(context)`.
class AppController extends ChangeNotifier {
  AppController({InspectionRepository? repository, GemmaSession? session})
      : _repo = repository ?? InspectionRepository(),
        _session = session;

  final InspectionRepository _repo;
  GemmaSession? _session;
  String? _modelPath;
  String? _modelLoadError;
  bool _modelLoading = false;
  ActiveInspection? _active;

  InspectionRepository get repository => _repo;
  String? get modelPath => _modelPath;
  bool get hasModel => _modelPath != null && _modelPath!.isNotEmpty;
  bool get modelReady => _session?.isLoaded ?? false;
  bool get modelLoading => _modelLoading;
  String? get modelLoadError => _modelLoadError;
  ActiveInspection? get activeInspection => _active;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _modelPath = prefs.getString(_kModelPathKey);
    await _repo.init();
  }

  Future<void> setModelPath(String? path) async {
    final prefs = await SharedPreferences.getInstance();
    if (path == null || path.trim().isEmpty) {
      await prefs.remove(_kModelPathKey);
      _modelPath = null;
    } else {
      _modelPath = path.trim();
      await prefs.setString(_kModelPathKey, _modelPath!);
    }
    await _session?.dispose();
    _session = null;
    _modelLoadError = null;
    notifyListeners();
  }

  /// Loads the model if needed and returns a ready session. Throws on
  /// missing path or load failure. Callers should keep this off the build
  /// phase; call from a future / event handler.
  Future<GemmaSession> ensureSession() async {
    if (_session?.isLoaded ?? false) return _session!;
    final path = _modelPath;
    if (path == null || path.isEmpty) {
      throw StateError('No model file path configured. Set one in Settings.');
    }
    if (!await File(path).exists()) {
      throw StateError('Model file not found at: $path');
    }
    _modelLoading = true;
    _modelLoadError = null;
    notifyListeners();
    try {
      final session = _session ?? GemmaSession();
      await session.openFromPath(path);
      _session = session;
      return session;
    } catch (e) {
      _modelLoadError = e.toString();
      rethrow;
    } finally {
      _modelLoading = false;
      notifyListeners();
    }
  }

  void startInspection() {
    _active = ActiveInspection(startedAt: DateTime.now());
    notifyListeners();
  }

  /// Records (or replaces) the evidence photo result for a given evidence
  /// type. Re-shooting the same evidence type overwrites the prior
  /// result for that type within the active inspection.
  void recordEvidence(EvidenceResult result) {
    final a = _active;
    if (a == null) return;
    a.upsertEvidence(result);
    notifyListeners();
  }

  Future<int> finalizeInspection() async {
    final a = _active;
    if (a == null) throw StateError('No active inspection');
    final id = await _repo.save(a);
    _active = null;
    notifyListeners();
    return id;
  }

  void cancelInspection() {
    _active = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _session?.dispose();
    super.dispose();
  }
}

/// In-flight inspection: an ordered map of [Inspection] → recorded
/// evidence photos for that inspection.
class ActiveInspection {
  ActiveInspection({required this.startedAt});

  final DateTime startedAt;
  final Map<Inspection, List<EvidenceResult>> evidence = {
    for (final i in Inspection.values) i: <EvidenceResult>[],
  };

  void upsertEvidence(EvidenceResult r) {
    final list = evidence[r.evidenceType.inspection]!;
    list.removeWhere((e) => e.evidenceType == r.evidenceType);
    list.add(r);
  }

  List<EvidenceResult> photosFor(Inspection i) => List.unmodifiable(evidence[i]!);

  Set<EvidenceType> evidenceTypesPresent(Inspection i) =>
      evidence[i]!.map((e) => e.evidenceType).toSet();

  /// True when every inspection has at least its required evidence types
  /// captured. Optional evidence does not gate completion.
  bool get isReadyToFinalize =>
      Inspection.values.every(isInspectionReady);

  bool isInspectionReady(Inspection i) {
    final present = evidenceTypesPresent(i);
    return i.requiredEvidence.every(present.contains);
  }

  ComposedVerdict verdictFor(Inspection i) =>
      ComposedVerdict.compose(i, evidence[i]!);

  /// Overall status combines the per-inspection verdicts:
  /// - any inspection `fail` → overall `fail`
  /// - any inspection `retake` → overall `retake`
  /// - any inspection `incomplete` → overall `incomplete`
  /// - all `pass` → `pass`
  String get overallStatus {
    final verdicts =
        Inspection.values.map(verdictFor).map((v) => v.status).toList();
    if (verdicts.contains('fail')) return 'fail';
    if (verdicts.contains('retake')) return 'retake';
    if (verdicts.contains('incomplete')) return 'incomplete';
    return 'pass';
  }
}

/// Outcome of running one evidence photo through the model.
class EvidenceResult {
  EvidenceResult({
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

  /// Per-photo "pass" | "fail" | "retake" | "unclear" | "error".
  final String status;
  final String summary;

  /// Per-photo model confidence: "high" | "medium" | "low" | "" missing.
  final String confidence;
  final List<String> issuesDetected;
  final String rawJson;
  final DateTime capturedAt;

  /// Local file path to the captured image.
  final String imagePath;
}
