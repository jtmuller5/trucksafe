import 'package:flutter/material.dart';

import 'app.dart';
import 'inference/gemma_session.dart';
import 'state/app_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await GemmaSession.initializeRuntime();
  final controller = AppController();
  await controller.init();
  runApp(TruckSafeApp(controller: controller));
}
