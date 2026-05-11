import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../inference/image_prep.dart';
import '../inference/inspections.dart';
import '../inference/prompts.dart';
import '../inference/result_parser.dart';
import '../state/app_controller.dart';
import '../state/app_scope.dart';

class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key});

  static const route = '/capture';

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

enum _Phase { preview, captured, running, done, error }

class _CaptureScreenState extends State<CaptureScreen> {
  CameraController? _camera;
  Future<void>? _cameraInit;
  XFile? _captured;
  _Phase _phase = _Phase.preview;
  String? _errorMessage;
  EvidenceResult? _result;
  EvidenceType? _evidence;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _evidence ??=
        ModalRoute.of(context)!.settings.arguments as EvidenceType;
    _cameraInit ??= _initCamera();
  }

  Future<void> _initCamera() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) {
      setState(() {
        _phase = _Phase.error;
        _errorMessage = 'No camera available on this device.';
      });
      return;
    }
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    final controller = CameraController(
      back,
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );
    await controller.initialize();
    if (!mounted) return;
    setState(() => _camera = controller);
  }

  @override
  void dispose() {
    _camera?.dispose();
    super.dispose();
  }

  Future<void> _capture() async {
    final c = _camera;
    if (c == null || !c.value.isInitialized) return;
    final shot = await c.takePicture();
    if (!mounted) return;
    setState(() {
      _captured = shot;
      _phase = _Phase.captured;
    });
  }

  Future<void> _retake() async {
    setState(() {
      _captured = null;
      _phase = _Phase.preview;
      _result = null;
      _errorMessage = null;
    });
  }

  Future<void> _runInference() async {
    final shot = _captured;
    final evidence = _evidence;
    if (shot == null || evidence == null) return;

    setState(() => _phase = _Phase.running);
    final app = AppScope.read(context);

    try {
      final docs = await getApplicationDocumentsDirectory();
      final imagesDir = Directory(p.join(docs.path, 'inspections'));
      await imagesDir.create(recursive: true);
      final ts = DateTime.now().millisecondsSinceEpoch;
      final destPath = p.join(imagesDir.path, '${evidence.name}_$ts.jpg');
      await File(shot.path).copy(destPath);

      final jpegBytes = await preprocessJpeg(File(destPath));
      final session = await app.ensureSession();
      final prompt = await loadEvidencePrompt(evidence);
      final raw = await session.generate(
        systemPrompt: prompt.systemPrompt,
        userPrompt: prompt.userPrompt,
        imageJpeg: jpegBytes,
      );
      final result = parseEvidenceResult(
        evidenceType: evidence,
        rawText: raw,
        capturedAt: DateTime.now(),
        imagePath: destPath,
      );
      app.recordEvidence(result);
      if (!mounted) return;
      setState(() {
        _result = result;
        _phase = _Phase.done;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _phase = _Phase.error;
        _errorMessage = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final evidence = _evidence;
    if (evidence == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(title: Text(evidence.label)),
      body: SafeArea(child: _buildBody(evidence)),
    );
  }

  Widget _buildBody(EvidenceType evidence) {
    switch (_phase) {
      case _Phase.preview:
        return _buildPreview(evidence);
      case _Phase.captured:
        return _buildCaptured(evidence);
      case _Phase.running:
        return _buildRunning(evidence);
      case _Phase.done:
        return _buildDone(evidence);
      case _Phase.error:
        return _buildError();
    }
  }

  Widget _buildPreview(EvidenceType evidence) {
    return FutureBuilder<void>(
      future: _cameraInit,
      builder: (context, snapshot) {
        if (_camera == null ||
            snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        return Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: Text(
                evidence.instruction,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
            Expanded(
              child: AspectRatio(
                aspectRatio: _camera!.value.aspectRatio,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    CameraPreview(_camera!),
                    if (evidence.showsTargetOverlay)
                      _TargetOverlay(label: _overlayLabel(evidence)),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(20),
              child: FilledButton.icon(
                icon: const Icon(Icons.camera_alt),
                label: const Text('Capture'),
                onPressed: _capture,
              ),
            ),
          ],
        );
      },
    );
  }

  String _overlayLabel(EvidenceType evidence) {
    return switch (evidence) {
      EvidenceType.sideView => 'Frame the apron–plate seam',
      _ => '',
    };
  }

  Widget _buildCaptured(EvidenceType evidence) {
    return Column(
      children: [
        Expanded(child: Image.file(File(_captured!.path), fit: BoxFit.contain)),
        Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _retake,
                  child: const Text('Retake'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: _runInference,
                  child: const Text('Inspect'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildRunning(EvidenceType evidence) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (_captured != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 24),
              child: SizedBox(
                height: 220,
                child: Image.file(File(_captured!.path), fit: BoxFit.contain),
              ),
            ),
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(
            'Running on-device inspection…',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 4),
          Text(
            'This can take 20–60 seconds the first time the model loads.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.outline,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildDone(EvidenceType evidence) {
    final r = _result!;
    final color = switch (r.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  r.status.toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (r.confidence.isNotEmpty) ...[
                const SizedBox(width: 10),
                Text(
                  'confidence: ${r.confidence}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
          const SizedBox(height: 14),
          Text(r.summary, style: Theme.of(context).textTheme.bodyLarge),
          if (r.issuesDetected.isNotEmpty) ...[
            const SizedBox(height: 18),
            Text(
              'Issues detected',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 6),
            for (final issue in r.issuesDetected)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text('• $issue'),
              ),
          ],
          const Spacer(),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _retake,
                  child: const Text('Retake'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Continue'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.error_outline, size: 48),
          const SizedBox(height: 12),
          Text(
            _errorMessage ?? 'Something went wrong.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 20),
          OutlinedButton(
            onPressed: _retake,
            child: const Text('Try again'),
          ),
        ],
      ),
    );
  }
}

/// Translucent target rectangle drawn over the camera preview. Currently
/// used only on the side-view shot — the load-bearing photo for the front
/// coupling inspection, where framing the apron–plate seam matters most.
class _TargetOverlay extends StatelessWidget {
  const _TargetOverlay({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: LayoutBuilder(builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        // Centered rectangle: 70% wide, 30% tall — roughly the strip where
        // the apron meets the fifth wheel plate in a driver-eye side view.
        final boxW = w * 0.7;
        final boxH = h * 0.3;
        final left = (w - boxW) / 2;
        final top = (h - boxH) / 2;
        return Stack(
          children: [
            Container(color: Colors.black.withValues(alpha: 0.18)),
            Positioned(
              left: left,
              top: top,
              width: boxW,
              height: boxH,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.white, width: 2),
                  borderRadius: BorderRadius.circular(8),
                  color: Colors.transparent,
                ),
              ),
            ),
            if (label.isNotEmpty)
              Positioned(
                left: 0,
                right: 0,
                top: top - 28,
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.65),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      label,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      }),
    );
  }
}
