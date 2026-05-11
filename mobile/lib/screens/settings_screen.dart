import 'dart:io';

import 'package:flutter/material.dart';

import '../state/app_scope.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  static const route = '/settings';

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _pathField;

  @override
  void initState() {
    super.initState();
    _pathField = TextEditingController();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final current = AppScope.of(context).modelPath ?? '';
    if (_pathField.text.isEmpty && current.isNotEmpty) {
      _pathField.text = current;
    }
  }

  @override
  void dispose() {
    _pathField.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final path = _pathField.text.trim();
    final pathExists = path.isNotEmpty && File(path).existsSync();
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Model file path',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 6),
              Text(
                'Absolute path on this device to the .litertlm model file. '
                'Push it to the phone with adb (Android) or Xcode (iOS).',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.outline,
                    ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _pathField,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  hintText: '/sdcard/Download/gemma-4-E4B.litertlm',
                  border: OutlineInputBorder(),
                ),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
                maxLines: 2,
                minLines: 1,
              ),
              const SizedBox(height: 6),
              if (path.isNotEmpty)
                Row(
                  children: [
                    Icon(
                      pathExists ? Icons.check_circle : Icons.error_outline,
                      size: 16,
                      color: pathExists ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      pathExists ? 'File found' : 'File not found at this path',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () async {
                        await app.setModelPath(null);
                        if (!context.mounted) return;
                        _pathField.clear();
                        setState(() {});
                      },
                      child: const Text('Clear'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: path.isEmpty
                          ? null
                          : () async {
                              await app.setModelPath(path);
                              if (!context.mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Saved.'),
                                  duration: Duration(seconds: 2),
                                ),
                              );
                            },
                      child: const Text('Save'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 28),
              if (app.modelLoadError != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.errorContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    'Last load error: ${app.modelLoadError}',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onErrorContainer,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
