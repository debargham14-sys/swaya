import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/measurement_result.dart';
import '../services/assistant_api.dart';
import '../widgets/fit_suggestion_sheet.dart';

/// Fetch and show fit suggestions after ground-truth calibration.
Future<void> showFitSuggestionsAfterCalibration(
  BuildContext context, {
  required MeasurementResult measurements,
}) async {
  try {
    final suggestion = await AssistantApi().suggest(
      measurements: measurements,
      calibrated: true,
      context: 'ground_truth_saved',
    );
    if (!context.mounted) return;
    await FitSuggestionSheet.show(
      context,
      suggestion: suggestion,
      onAskMore: () => context.go('/assistant'),
    );
  } catch (_) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Could not load fit suggestions — try the Assistant tab'),
      ),
    );
  }
}
