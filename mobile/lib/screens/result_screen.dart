import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../inference/categories.dart';
import '../state/app_scope.dart';
import '../storage/inspection_repository.dart';

class ResultArgs {
  ResultArgs({required this.inspectionId});

  factory ResultArgs.fromRecord(InspectionRecord r) =>
      ResultArgs(inspectionId: r.id);

  final int inspectionId;
}

class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key});

  static const route = '/result';

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  Future<InspectionRecord>? _record;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)!.settings.arguments as ResultArgs;
    _record ??= AppScope.of(context).repository.get(args.inspectionId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Inspection result')),
      body: SafeArea(
        child: FutureBuilder<InspectionRecord>(
          future: _record,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(child: Text('Error: ${snapshot.error}'));
            }
            final r = snapshot.data!;
            return _ResultBody(record: r);
          },
        ),
      ),
    );
  }
}

class _ResultBody extends StatelessWidget {
  const _ResultBody({required this.record});

  final InspectionRecord record;

  @override
  Widget build(BuildContext context) {
    final fmt = DateFormat('MMM d, y · h:mm a');
    final color = switch (record.overallStatus) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    final issues = <String>[
      for (final s in record.steps.values)
        ...s.issuesDetected.map((i) => '${s.category.label}: $i'),
    ];
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color),
          ),
          child: Row(
            children: [
              Icon(
                record.overallStatus == 'pass'
                    ? Icons.check_circle
                    : record.overallStatus == 'fail'
                        ? Icons.cancel
                        : Icons.refresh,
                color: color,
                size: 32,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Overall: ${record.overallStatus.toUpperCase()}',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: color,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                    Text(
                      fmt.format(record.startedAt),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        if (issues.isNotEmpty) ...[
          Text('Issues across all steps',
              style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 6),
          for (final i in issues)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text('• $i'),
            ),
          const SizedBox(height: 20),
        ],
        Text('Per-step detail',
            style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        for (final c in InspectionCategory.values)
          if (record.steps[c] != null) _StepCard(step: record.steps[c]!),
      ],
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({required this.step});

  final StoredStep step;

  @override
  Widget build(BuildContext context) {
    final color = switch (step.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    step.status.toUpperCase(),
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 12),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    step.category.label,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (step.summary.isNotEmpty) Text(step.summary),
            if (step.imagePath.isNotEmpty &&
                File(step.imagePath).existsSync()) ...[
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.file(
                  File(step.imagePath),
                  height: 140,
                  fit: BoxFit.cover,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
