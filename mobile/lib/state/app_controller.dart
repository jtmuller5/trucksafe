import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../inference/categories.dart';
import '../inference/gemma_session.dart';
import '../storage/inspection_repository.dart';

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

  void recordStepResult(InspectionCategory category, StepResult result) {
    final a = _active;
    if (a == null) return;
    a.results[category] = result;
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

class ActiveInspection {
  ActiveInspection({required this.startedAt});

  final DateTime startedAt;
  final Map<InspectionCategory, StepResult> results = {};

  bool get isComplete =>
      InspectionCategory.values.every((c) => results.containsKey(c));

  /// Overall pass if every step's result is "pass". Any fail/retake yields
  /// that label as overall.
  String get overallStatus {
    if (results.values.any((r) => r.status == 'fail')) return 'fail';
    if (results.values.any((r) => r.status == 'retake')) return 'retake';
    if (results.values.every((r) => r.status == 'pass')) return 'pass';
    return 'incomplete';
  }
}

/// Outcome of running a single inspection step.
class StepResult {
  StepResult({
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

  /// "pass" | "fail" | "retake" | "error".
  final String status;
  final String summary;

  /// "high" | "medium" | "low" | "" when missing.
  final String confidence;
  final List<String> issuesDetected;
  final String rawJson;
  final DateTime capturedAt;

  /// Local file path to the captured image. Persisted; not deleted.
  final String imagePath;
}
