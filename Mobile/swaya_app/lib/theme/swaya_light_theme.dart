import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Light theme tokens for the new Figma screens (auth, measurements, persona).
/// The app's existing screens stay on the dark [buildSwayaTheme]; new screens
/// wrap themselves in [buildSwayaLightTheme] during the phased migration.
///
/// Palette derived from the Figma auth frames (1–10): white canvas, warm-gray
/// cards/inputs, near-black CTA buttons, with the brand teal kept as the accent
/// for links and active states.
abstract final class SwayaLight {
  static const canvas = Color(0xFFFFFFFF);
  static const surface = Color(0xFFF5F4F2); // input / card fill
  static const surfaceAlt = Color(0xFFEFEDEA); // segmented track, chips
  static const inkPrimary = Color(0xFF1A1815); // headings, primary text
  static const inkSecondary = Color(0xFF6B665C); // subtitles, helper text
  static const inkTertiary = Color(0xFF9A958C); // hints, disabled
  static const border = Color(0xFFE6E3DD);
  static const cta = Color(0xFF1A1815); // dark primary button
  static const onCta = Color(0xFFFAF8F3);
  static const accent = Color(0xFF4A9B9B); // brand teal — links / active
  static const success = Color(0xFF3F9D6B);
  static const error = Color(0xFFC8503C);
}

// The light theme is context-free, so build it once and reuse it. LightScaffold
// wraps every page in Theme(data: buildSwayaLightTheme()) and rebuilds on each
// keystroke; constructing the GoogleFonts text themes per frame was needless
// work that could show up as input jank.
ThemeData? _cachedLightTheme;
ThemeData buildSwayaLightTheme() => _cachedLightTheme ??= _buildSwayaLightTheme();

ThemeData _buildSwayaLightTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: SwayaLight.canvas,
    colorScheme: const ColorScheme.light(
      surface: SwayaLight.canvas,
      onSurface: SwayaLight.inkPrimary,
      primary: SwayaLight.cta,
      onPrimary: SwayaLight.onCta,
      secondary: SwayaLight.accent,
      onSecondary: Colors.white,
      error: SwayaLight.error,
      outline: SwayaLight.border,
    ),
  );

  final display = GoogleFonts.frauncesTextTheme(base.textTheme);
  final body = GoogleFonts.dmSansTextTheme(display);

  return base.copyWith(
    textTheme: body.apply(
      bodyColor: SwayaLight.inkPrimary,
      displayColor: SwayaLight.inkPrimary,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: SwayaLight.canvas,
      foregroundColor: SwayaLight.inkPrimary,
      elevation: 0,
      centerTitle: true,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: SwayaLight.cta,
        foregroundColor: SwayaLight.onCta,
        disabledBackgroundColor: SwayaLight.inkTertiary,
        minimumSize: const Size.fromHeight(54),
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: GoogleFonts.dmSans(fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: SwayaLight.inkPrimary,
        minimumSize: const Size.fromHeight(54),
        side: const BorderSide(color: SwayaLight.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: GoogleFonts.dmSans(fontSize: 16, fontWeight: FontWeight.w500),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: SwayaLight.accent,
        textStyle: GoogleFonts.dmSans(fontSize: 14, fontWeight: FontWeight.w600),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SwayaLight.surface,
      hintStyle: const TextStyle(color: SwayaLight.inkTertiary),
      prefixIconColor: SwayaLight.inkSecondary,
      suffixIconColor: SwayaLight.inkSecondary,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: SwayaLight.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: SwayaLight.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: SwayaLight.accent, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: SwayaLight.error),
      ),
    ),
    dividerTheme: const DividerThemeData(color: SwayaLight.border, thickness: 1),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: SwayaLight.inkPrimary,
      contentTextStyle: const TextStyle(color: SwayaLight.onCta),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    ),
  );
}
