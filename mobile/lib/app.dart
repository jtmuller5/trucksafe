import 'package:flutter/material.dart';

import 'screens/home_screen.dart';
import 'screens/inspection_screen.dart';
import 'screens/result_screen.dart';
import 'screens/settings_screen.dart';
import 'state/app_controller.dart';
import 'state/app_scope.dart';

class TruckSafeApp extends StatelessWidget {
  const TruckSafeApp({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      controller: controller,
      child: MaterialApp(
        title: 'TruckSafe',
        debugShowCheckedModeBanner: false,
        theme: _buildTheme(),
        initialRoute: HomeScreen.route,
        routes: {
          HomeScreen.route: (_) => const HomeScreen(),
          InspectionScreen.route: (_) => const InspectionScreen(),
          ResultScreen.route: (_) => const ResultScreen(),
          SettingsScreen.route: (_) => const SettingsScreen(),
        },
      ),
    );
  }
}

ThemeData _buildTheme() {
  const primary = Color(0xFF2E5363); // muted deep teal
  final colorScheme = ColorScheme.fromSeed(
    seedColor: primary,
    brightness: Brightness.light,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: const Color(0xFFF5F4F1),
    appBarTheme: AppBarTheme(
      backgroundColor: colorScheme.surface,
      foregroundColor: colorScheme.onSurface,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: colorScheme.onSurface,
        fontSize: 20,
        fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
  );
}
