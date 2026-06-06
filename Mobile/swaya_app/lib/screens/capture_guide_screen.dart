import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/measurement_result.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

class CaptureGuideScreen extends StatelessWidget {
  const CaptureGuideScreen({super.key});

  static const _tips = [
    'Step back — head and feet must both be in every photo',
    'Front: face the camera; Side: turn 90° (true profile)',
    'Arms slightly away from body (not tight at sides)',
    'Fitted clothing (loose kurta/saree often fails)',
    'Plain wall background, even lighting',
  ];

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Before you shoot',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Good photos improve bust, waist, and hip accuracy.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          const SizedBox(height: 20),
          ..._tips.map(
            (tip) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: const BoxDecoration(
                      color: SwayaColors.accentHighlight,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(child: Text(tip)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          Expanded(
            child: Container(
              width: double.infinity,
              decoration: BoxDecoration(
                color: SwayaColors.elevated,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: SwayaColors.borderSubtle),
              ),
              alignment: Alignment.center,
              child: Text(
                'Stand arm\'s length from camera',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: SwayaColors.inkTertiary,
                    ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => context.go('/scan/capture/${CaptureView.front.routeName}'),
              child: const Text('Open camera'),
            ),
          ),
        ],
      ),
    );
  }
}
