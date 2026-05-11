import 'package:flutter/material.dart';

import '../inference/categories.dart';
import '../state/app_controller.dart';
import '../state/app_scope.dart';
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
            : _StepsList(active: active),
      ),
      bottomNavigationBar: active == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: FilledButton(
                  onPressed: active.isComplete
                      ? () => _finalize(context, app)
                      : null,
                  child: Text(active.isComplete
                      ? 'See result'
                      : '${active.results.length} of ${InspectionCategory.values.length} steps done'),
                ),
              ),
            ),
    );
  }

  Future<void> _confirmCancel(BuildContext context, AppController app) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cancel inspection?'),
        content: const Text('All step results so far will be discarded.'),
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

class _StepsList extends StatelessWidget {
  const _StepsList({required this.active});

  final ActiveInspection active;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      itemCount: InspectionCategory.values.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        final cat = InspectionCategory.values[i];
        final result = active.results[cat];
        return _StepTile(
          index: i + 1,
          category: cat,
          result: result,
          onTap: () async {
            await Navigator.pushNamed(
              context,
              CaptureScreen.route,
              arguments: cat,
            );
          },
        );
      },
    );
  }
}

class _StepTile extends StatelessWidget {
  const _StepTile({
    required this.index,
    required this.category,
    required this.result,
    required this.onTap,
  });

  final int index;
  final InspectionCategory category;
  final StepResult? result;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDone = result != null;
    final color = switch (result?.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: isDone ? color : Theme.of(context).colorScheme.surfaceContainerHighest,
                  shape: BoxShape.circle,
                ),
                child: isDone
                    ? Icon(
                        result!.status == 'pass'
                            ? Icons.check
                            : result!.status == 'fail'
                                ? Icons.close
                                : Icons.refresh,
                        color: Colors.white,
                        size: 20,
                      )
                    : Text(
                        '$index',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      category.label,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      isDone
                          ? '${result!.status.toUpperCase()} · ${result!.summary}'
                          : category.instruction,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: Theme.of(context).colorScheme.outline,
                          ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, size: 22),
            ],
          ),
        ),
      ),
    );
  }
}
