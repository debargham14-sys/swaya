import 'package:flutter/material.dart';

import '../models/blouse_measurements.dart';
import '../services/assistant_api.dart';
import '../services/measure_api.dart' show MeasureApiException;
import '../theme/swaya_light_theme.dart';

/// Builds the body-girth payload the assistant expects from a persona's saved
/// garment-fit measurements. We surface chest as both `chest` and `bust` so the
/// backend's gendered rules pick the right one.
Map<String, double> _girthsFrom(BlouseMeasurements m) {
  final v = m.values;
  final girths = <String, double>{};
  final chest = v['chest'] ?? v['upper_chest'] ?? v['below_chest'];
  if (chest != null) {
    girths['chest'] = chest;
    girths['bust'] = chest;
  }
  if (v['waist'] != null) girths['waist'] = v['waist']!;
  if (v['hip'] != null) girths['hip'] = v['hip']!;
  return girths;
}

/// Fetches gender/garment-aware clothing suggestions from the assistant and
/// shows them in a light-themed bottom sheet. Used from the design/order flow.
Future<void> showGarmentSuggestions(
  BuildContext context, {
  required String gender,
  required BlouseMeasurements measurements,
  String? garment,
  AssistantApi? api,
}) async {
  final girths = _girthsFrom(measurements);
  if (girths.isEmpty) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(const SnackBar(
          content: Text('Save chest/bust or waist to get suggestions.')));
    return;
  }

  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const Center(
        child: CircularProgressIndicator(color: SwayaLight.accent)),
  );

  FitSuggestion? result;
  String? error;
  try {
    result = await (api ?? AssistantApi()).suggestForGarment(
      girthsCm: girths,
      gender: gender,
      garment: garment,
    );
  } on MeasureApiException catch (e) {
    error = e.message;
  } catch (e) {
    error = '$e';
  }

  if (!context.mounted) return;
  Navigator.of(context).pop(); // dismiss the loader
  if (!context.mounted) return;

  if (result == null) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
          SnackBar(content: Text('Could not get suggestions: $error')));
    return;
  }

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: SwayaLight.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (ctx) => _GarmentSuggestionBody(suggestion: result!),
  );
}

class _GarmentSuggestionBody extends StatelessWidget {
  const _GarmentSuggestionBody({required this.suggestion});

  final FitSuggestion suggestion;

  @override
  Widget build(BuildContext context) {
    final isLlm = suggestion.source == 'llm';
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.auto_awesome, color: SwayaLight.accent),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text('Clothing suggestions',
                      style: TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontSize: 18,
                          fontWeight: FontWeight.w700)),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: SwayaLight.accent.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(isLlm ? 'AI' : 'Guide',
                      style: const TextStyle(
                          fontSize: 11, color: SwayaLight.accent)),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: SwayaLight.surfaceAlt,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: SwayaLight.border),
              ),
              child: Text(suggestion.suggestions,
                  style: const TextStyle(
                      color: SwayaLight.inkPrimary, height: 1.45, fontSize: 14)),
            ),
            if (suggestion.garments.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final g in suggestion.garments)
                    Chip(
                      label: Text(g, style: const TextStyle(fontSize: 12)),
                      backgroundColor: SwayaLight.surface,
                      side: const BorderSide(color: SwayaLight.border),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 18),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Done'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
