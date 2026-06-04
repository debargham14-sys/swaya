import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Dark theme tokens from the Swaya design spec.
abstract final class SwayaColors {
  static const base = Color(0xFF121110);
  static const chrome = Color(0xFF0A0908);
  static const elevated = Color(0xFF1E1D1A);
  static const inkPrimary = Color(0xFFF5F2EB);
  static const inkSecondary = Color(0xFFA8A296);
  static const inkTertiary = Color(0xFF6B665C);
  static const accent = Color(0xFF4A9B9B);
  static const accentHighlight = Color(0xFF6BBFBF);
  static const onAccent = Color(0xFF0C1212);
  static const borderSubtle = Color(0x1FF5F2EB);
  static const success = Color(0xFF5CB88A);
  static const warning = Color(0xFFD4A84B);
  static const error = Color(0xFFE57373);
}

ThemeData buildSwayaTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: SwayaColors.base,
    colorScheme: const ColorScheme.dark(
      surface: SwayaColors.base,
      onSurface: SwayaColors.inkPrimary,
      primary: SwayaColors.accent,
      onPrimary: SwayaColors.onAccent,
      secondary: SwayaColors.accentHighlight,
      onSecondary: SwayaColors.onAccent,
      error: SwayaColors.error,
      outline: SwayaColors.borderSubtle,
    ),
  );

  final display = GoogleFonts.frauncesTextTheme(base.textTheme);
  final body = GoogleFonts.dmSansTextTheme(display);

  return base.copyWith(
    textTheme: body.apply(
      bodyColor: SwayaColors.inkPrimary,
      displayColor: SwayaColors.inkPrimary,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: SwayaColors.base,
      foregroundColor: SwayaColors.inkPrimary,
      elevation: 0,
      centerTitle: false,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: SwayaColors.accent,
        foregroundColor: SwayaColors.onAccent,
        minimumSize: const Size.fromHeight(52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: GoogleFonts.dmSans(
          fontSize: 16,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: SwayaColors.inkPrimary,
        minimumSize: const Size.fromHeight(52),
        side: const BorderSide(color: SwayaColors.borderSubtle),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: GoogleFonts.dmSans(fontSize: 16, fontWeight: FontWeight.w500),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SwayaColors.elevated,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: SwayaColors.borderSubtle),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: SwayaColors.borderSubtle),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: SwayaColors.accentHighlight, width: 1.5),
      ),
      hintStyle: const TextStyle(color: SwayaColors.inkTertiary),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    dividerTheme: const DividerThemeData(color: SwayaColors.borderSubtle),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: SwayaColors.elevated,
      contentTextStyle: TextStyle(color: SwayaColors.inkPrimary),
    ),
  );
}
