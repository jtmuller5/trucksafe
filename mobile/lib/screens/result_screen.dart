import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../inference/inspections.dart';
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
    final color = _statusColor(context, record.overallStatus);
    final allIssues = <String>[
      for (final i in Inspection.values)
        ...?record.verdicts[i]?.issues.map((s) => '${i.label}: $s'),
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
              Icon(_statusIcon(record.overallStatus), color: color, size: 32),
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
        if (allIssues.isNotEmpty) ...[
          Text('Issues across all inspections',
              style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 6),
          for (final i in allIssues)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text('• $i'),
            ),
          const SizedBox(height: 20),
        ],
        for (final i in Inspection.values)
          _InspectionDetail(
            inspection: i,
            verdict: record.verdicts[i]!,
            evidence: record.evidence[i] ?? const [],
          ),
      ],
    );
  }

  static Color _statusColor(BuildContext context, String s) {
    return switch (s) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
  }

  static IconData _statusIcon(String s) {
    return switch (s) {
      'pass' => Icons.check_circle,
      'fail' => Icons.cancel,
      'retake' => Icons.refresh,
      _ => Icons.hourglass_empty,
    };
  }
}

class _InspectionDetail extends StatelessWidget {
  const _InspectionDetail({
    required this.inspection,
    required this.verdict,
    required this.evidence,
  });

  final Inspection inspection;
  final StoredVerdict verdict;
  final List<StoredEvidence> evidence;

  @override
  Widget build(BuildContext context) {
    final color = switch (verdict.status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
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
                    verdict.status.toUpperCase(),
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 12),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    inspection.label,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                ),
                if (verdict.confidence.isNotEmpty)
                  Text(
                    verdict.confidence,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.outline,
                        ),
                  ),
              ],
            ),
            if (evidence.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  'No photos captured.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            for (final e in evidence) ...[
              const SizedBox(height: 12),
              _EvidenceTile(evidence: e),
            ],
          ],
        ),
      ),
    );
  }
}

class _EvidenceTile extends StatelessWidget {
  const _EvidenceTile({required this.evidence});

  final StoredEvidence evidence;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (evidence.imagePath.isNotEmpty &&
            File(evidence.imagePath).existsSync())
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: Image.file(
              File(evidence.imagePath),
              width: 84,
              height: 84,
              fit: BoxFit.cover,
            ),
          )
        else
          Container(
            width: 84,
            height: 84,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Icon(Icons.image_not_supported_outlined),
          ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                evidence.evidenceType.label,
                style: Theme.of(context)
                    .textTheme
                    .bodyMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 2),
              Text(
                '${evidence.status.toUpperCase()} · ${evidence.summary}',
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
