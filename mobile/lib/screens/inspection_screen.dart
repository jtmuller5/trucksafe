import 'package:flutter/material.dart';

import '../inference/inspections.dart';
import '../state/app_controller.dart';
import '../state/app_scope.dart';
import '../state/composition.dart';
import 'capture_screen.dart';
import 'result_screen.dart';

class InspectionScreen extends StatelessWidget {
  const InspectionScreen({super.key});

  static const route = '/inspection';

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final active = app.activeInspection;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pre-trip inspection'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => _confirmCancel(context, app),
        ),
      ),
      body: SafeArea(
        child: active == null
            ? const Center(child: Text('No active inspection.'))
            : _InspectionsList(active: active),
      ),
      bottomNavigationBar: active == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: FilledButton(
                  onPressed: active.isReadyToFinalize
                      ? () => _finalize(context, app)
                      : null,
                  child: Text(active.isReadyToFinalize
                      ? 'See result'
                      : _completionLabel(active)),
                ),
              ),
            ),
    );
  }

  static String _completionLabel(ActiveInspection a) {
    final required = Inspection.values
        .expand((i) => i.requiredEvidence)
        .toList();
    final done = required
        .where(
          (e) => a.evidenceTypesPresent(e.inspection).contains(e),
        )
        .length;
    return '$done of ${required.length} required photos taken';
  }

  Future<void> _confirmCancel(BuildContext context, AppController app) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cancel inspection?'),
        content: const Text('All photos taken so far will be discarded.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep going'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      app.cancelInspection();
      if (context.mounted) Navigator.pop(context);
    }
  }

  Future<void> _finalize(BuildContext context, AppController app) async {
    final id = await app.finalizeInspection();
    if (!context.mounted) return;
    await Navigator.pushReplacementNamed(
      context,
      ResultScreen.route,
      arguments: ResultArgs(inspectionId: id),
    );
  }
}

class _InspectionsList extends StatelessWidget {
  const _InspectionsList({required this.active});

  final ActiveInspection active;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      itemCount: Inspection.values.length,
      separatorBuilder: (_, _) => const SizedBox(height: 14),
      itemBuilder: (context, i) {
        final inspection = Inspection.values[i];
        return _InspectionCard(
          index: i + 1,
          inspection: inspection,
          active: active,
        );
      },
    );
  }
}

class _InspectionCard extends StatelessWidget {
  const _InspectionCard({
    required this.index,
    required this.inspection,
    required this.active,
  });

  final int index;
  final Inspection inspection;
  final ActiveInspection active;

  @override
  Widget build(BuildContext context) {
    final ready = active.isInspectionReady(inspection);
    final verdict = active.verdictFor(inspection);
    final color = _statusColor(context, verdict);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: ready
                        ? color
                        : Theme.of(context).colorScheme.surfaceContainerHighest,
                    shape: BoxShape.circle,
                  ),
                  child: ready
                      ? Icon(_statusIcon(verdict),
                          color: Colors.white, size: 18)
                      : Text(
                          '$index',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        inspection.label,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        inspection.description,
                        style:
                            Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color:
                                      Theme.of(context).colorScheme.outline,
                                ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const Divider(height: 22),
            for (final e in inspection.requiredEvidence)
              _EvidenceRow(
                evidence: e,
                result: active.evidence[inspection]!
                    .where((r) => r.evidenceType == e)
                    .cast<EvidenceResult?>()
                    .firstOrNull,
                onTap: () => Navigator.pushNamed(
                  context,
                  CaptureScreen.route,
                  arguments: e,
                ),
              ),
            if (inspection.optionalEvidence.isNotEmpty) ...[
              Padding(
                padding: const EdgeInsets.only(top: 6, bottom: 2),
                child: Text(
                  'Optional confirmation',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.outline,
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
              for (final e in inspection.optionalEvidence)
                _EvidenceRow(
                  evidence: e,
                  result: active.evidence[inspection]!
                      .where((r) => r.evidenceType == e)
                      .cast<EvidenceResult?>()
                      .firstOrNull,
                  onTap: () => Navigator.pushNamed(
                    context,
                    CaptureScreen.route,
                    arguments: e,
                  ),
                ),
            ],
            if (ready) ...[
              const SizedBox(height: 8),
              _VerdictChip(verdict: verdict),
            ],
          ],
        ),
      ),
    );
  }

  static Color _statusColor(BuildContext context, ComposedVerdict v) {
    return switch (v.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
  }

  static IconData _statusIcon(ComposedVerdict v) {
    return switch (v.status) {
      'pass' => Icons.check,
      'fail' => Icons.close,
      'retake' => Icons.refresh,
      _ => Icons.hourglass_empty,
    };
  }
}

class _EvidenceRow extends StatelessWidget {
  const _EvidenceRow({
    required this.evidence,
    required this.result,
    required this.onTap,
  });

  final EvidenceType evidence;
  final EvidenceResult? result;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final done = result != null;
    final color = switch (result?.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Icon(
              done
                  ? (result!.status == 'pass'
                      ? Icons.check_circle
                      : result!.status == 'fail'
                          ? Icons.cancel
                          : Icons.refresh)
                  : Icons.add_a_photo_outlined,
              color: done ? color : Theme.of(context).colorScheme.outline,
              size: 20,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    evidence.label,
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                  if (done && result!.summary.isNotEmpty)
                    Text(
                      result!.summary,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.outline,
                          ),
                    ),
                ],
              ),
            ),
            Text(
              done ? 'Retake' : (evidence.isRequired ? 'Capture' : 'Add'),
              style: TextStyle(
                color: Theme.of(context).colorScheme.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(width: 2),
            const Icon(Icons.chevron_right, size: 20),
          ],
        ),
      ),
    );
  }
}

class _VerdictChip extends StatelessWidget {
  const _VerdictChip({required this.verdict});

  final ComposedVerdict verdict;

  @override
  Widget build(BuildContext context) {
    final color = switch (verdict.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    final hint = switch (verdict.confidence) {
      'high' => 'Confirmed by multiple photos',
      'side_view_only' => 'Based on side view alone — add an optional shot '
          'to strengthen confidence',
      'low' => 'Low-confidence — consider retaking',
      _ => '',
    };
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  verdict.status.toUpperCase(),
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 12),
                ),
              ),
              if (hint.isNotEmpty) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    hint,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ],
            ],
          ),
          if (verdict.issuesDetected.isNotEmpty) ...[
            const SizedBox(height: 6),
            for (final i in verdict.issuesDetected)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 1),
                child: Text('• $i',
                    style: Theme.of(context).textTheme.bodySmall),
              ),
          ],
        ],
      ),
    );
  }
}
