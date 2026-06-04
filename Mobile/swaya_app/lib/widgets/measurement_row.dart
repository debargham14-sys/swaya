import 'package:flutter/material.dart';

import '../theme/swaya_theme.dart';

class MeasurementRow extends StatelessWidget {
  const MeasurementRow({
    super.key,
    required this.label,
    required this.cm,
    this.inches,
  });

  final String label;
  final double cm;
  final double? inches;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: SwayaColors.elevated,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: SwayaColors.borderSubtle),
      ),
      child: Row(
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          const Spacer(),
          Text(
            '${cm.toStringAsFixed(1)} cm',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          if (inches != null) ...[
            const SizedBox(width: 8),
            Text(
              '${inches!.toStringAsFixed(1)} in',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
          ],
        ],
      ),
    );
  }
}
