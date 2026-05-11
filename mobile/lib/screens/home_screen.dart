import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../state/app_scope.dart';
import '../storage/inspection_repository.dart';
import 'inspection_screen.dart';
import 'result_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  static const route = '/';

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<InspectionRecord>> _records;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _records = AppScope.of(context).repository.list();
  }

  void _reload() {
    setState(() {
      _records = AppScope.of(context).repository.list();
    });
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('TruckSafe'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () async {
              await Navigator.pushNamed(context, SettingsScreen.route);
              _reload();
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 12),
              if (!app.hasModel)
                _ModelMissingBanner(onOpenSettings: () async {
                  await Navigator.pushNamed(context, SettingsScreen.route);
                  _reload();
                }),
              if (!app.hasModel) const SizedBox(height: 16),
              FilledButton.icon(
                icon: const Icon(Icons.add_road),
                label: const Text('Start new inspection'),
                onPressed: app.hasModel
                    ? () async {
                        app.startInspection();
                        await Navigator.pushNamed(
                            context, InspectionScreen.route);
                        _reload();
                      }
                    : null,
              ),
              const SizedBox(height: 28),
              Text(
                'Past inspections',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Expanded(
                child: FutureBuilder<List<InspectionRecord>>(
                  future: _records,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    final list = snapshot.data ?? const [];
                    if (list.isEmpty) {
                      return const _EmptyState();
                    }
                    return ListView.separated(
                      itemCount: list.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 8),
                      itemBuilder: (_, i) {
                        final r = list[i];
                        return _RecordTile(
                          record: r,
                          onTap: () {
                            Navigator.pushNamed(
                              context,
                              ResultScreen.route,
                              arguments: ResultArgs.fromRecord(r),
                            );
                          },
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModelMissingBanner extends StatelessWidget {
  const _ModelMissingBanner({required this.onOpenSettings});

  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.errorContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber, color: cs.onErrorContainer),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Set the on-device model file path before starting an inspection.',
              style: TextStyle(color: cs.onErrorContainer),
            ),
          ),
          TextButton(
            onPressed: onOpenSettings,
            style: TextButton.styleFrom(foregroundColor: cs.onErrorContainer),
            child: const Text('Open settings'),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'No inspections yet. Run your first pre-trip to see it logged here.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.outline,
              ),
        ),
      ),
    );
  }
}

class _RecordTile extends StatelessWidget {
  const _RecordTile({required this.record, required this.onTap});

  final InspectionRecord record;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fmt = DateFormat('MMM d, h:mm a');
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              _StatusDot(status: record.overallStatus),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      fmt.format(record.startedAt),
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Overall: ${record.overallStatus}',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
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

class _StatusDot extends StatelessWidget {
  const _StatusDot({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'pass' => Colors.green.shade600,
      'fail' => Colors.red.shade700,
      'retake' => Colors.amber.shade700,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Container(
      width: 12,
      height: 12,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}
