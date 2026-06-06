import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../services/assistant_api.dart';
import '../theme/swaya_theme.dart';

/// Bottom sheet with garment suggestions after calibration.
class FitSuggestionSheet extends StatelessWidget {
  const FitSuggestionSheet({
    super.key,
    required this.suggestion,
    this.onAskMore,
  });

  final FitSuggestion suggestion;
  final VoidCallback? onAskMore;

  static Future<void> show(
    BuildContext context, {
    required FitSuggestion suggestion,
    VoidCallback? onAskMore,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: SwayaColors.elevated,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: FitSuggestionSheet(suggestion: suggestion, onAskMore: onAskMore),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isLlm = suggestion.source == 'llm';

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: SwayaColors.borderSubtle,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                const Icon(Icons.checkroom_outlined, color: SwayaColors.accent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Fit suggestions',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
                if (isLlm)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: SwayaColors.accent.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Text(
                      'AI',
                      style: TextStyle(fontSize: 11, color: SwayaColors.accent),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Measurements were recalibrated — here are garment ideas based on your tape values.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: SwayaColors.inkSecondary,
                  ),
            ),
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: SwayaColors.base,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: SwayaColors.borderSubtle),
              ),
              child: Text(
                suggestion.suggestions,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      height: 1.45,
                    ),
              ),
            ),
            if (suggestion.garments.isNotEmpty) ...[
              const SizedBox(height: 12),
              Wrap(
                spacing: 6,
                children: suggestion.garments
                    .map(
                      (g) => Chip(
                        label: Text(g, style: const TextStyle(fontSize: 12)),
                        backgroundColor: SwayaColors.elevated,
                        side: const BorderSide(color: SwayaColors.borderSubtle),
                      ),
                    )
                    .toList(),
              ),
            ],
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Dismiss'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: ElevatedButton(
                    onPressed: () {
                      Navigator.of(context).pop();
                      if (onAskMore != null) {
                        onAskMore!();
                      } else {
                        context.go('/assistant');
                      }
                    },
                    child: const Text('Ask fit assistant'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
