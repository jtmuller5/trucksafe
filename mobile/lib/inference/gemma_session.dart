import 'dart:typed_data';

import 'package:flutter_gemma/flutter_gemma.dart';

/// Wraps flutter_gemma for the single-shot, multimodal use case we need:
/// load a `.litertlm` from a runtime file path, run inference with a fixed
/// system prompt + one user message containing a JPEG, return the raw text.
///
/// The class holds onto the [InferenceModel] across calls — opening it is
/// expensive (model file is ~4.8 GB). Sessions are created fresh per call
/// because reusing a session implicitly carries chat history we don't want.
class GemmaSession {
  GemmaSession();

  InferenceModel? _model;
  String? _loadedPath;

  bool get isLoaded => _model != null;
  String? get loadedPath => _loadedPath;

  /// Initializes flutter_gemma globals. Call once before opening any model.
  static Future<void> initializeRuntime() async {
    await FlutterGemma.initialize();
  }

  /// Installs the model from a local file path and creates an
  /// [InferenceModel] with multimodal vision enabled. Idempotent: if the
  /// already-loaded model points at the same path, this is a no-op.
  Future<void> openFromPath(String path) async {
    if (_model != null && _loadedPath == path) return;
    if (_model != null) await close();

    await FlutterGemma.installModel(
      modelType: ModelType.gemma4,
      fileType: ModelFileType.litertlm,
    ).fromFile(path).install();

    _model = await FlutterGemma.getActiveModel(
      maxTokens: 4096,
      supportImage: true,
      maxNumImages: 1,
    );
    _loadedPath = path;
  }

  /// Runs one inference. [systemPrompt] is set on the session; the user
  /// message carries [userPrompt] + the JPEG bytes. Returns the raw model
  /// text (the caller parses JSON).
  Future<String> generate({
    required String systemPrompt,
    required String userPrompt,
    required Uint8List imageJpeg,
    double temperature = 0.0,
  }) async {
    final model = _model;
    if (model == null) {
      throw StateError('GemmaSession not opened — call openFromPath first.');
    }
    final session = await model.createSession(
      temperature: temperature,
      topK: 1,
      enableVisionModality: true,
      systemInstruction: systemPrompt,
    );
    try {
      await session.addQueryChunk(Message.withImage(
        text: userPrompt,
        imageBytes: imageJpeg,
        isUser: true,
      ));
      return await session.getResponse();
    } finally {
      await session.close();
    }
  }

  Future<void> close() async {
    final m = _model;
    _model = null;
    _loadedPath = null;
    if (m != null) {
      await m.close();
    }
  }

  Future<void> dispose() => close();
}
