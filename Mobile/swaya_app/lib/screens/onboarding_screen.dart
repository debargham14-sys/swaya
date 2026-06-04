import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../services/onboarding_store.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key});

  static const _steps = [
    (
      '1',
      'Three profile photos',
      'Front, back, and side — full body in frame',
    ),
    (
      '2',
      'Your height',
      'Used to scale measurements (cm)',
    ),
    (
      '3',
      'Talk to your fit assistant',
      'Ask about sizing, alterations, and what the numbers mean',
    ),
  ];

  Future<void> _continue(BuildContext context) async {
    await OnboardingStore().markComplete();
    if (context.mounted) context.go('/home');
  }

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 8),
          Text(
            'How it works',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 24),
          Expanded(
            child: ListView.separated(
              itemCount: _steps.length,
              separatorBuilder: (_, __) => const SizedBox(height: 16),
              itemBuilder: (context, i) {
                final (n, title, sub) = _steps[i];
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: SwayaColors.elevated,
                        shape: BoxShape.circle,
                      ),
                      alignment: Alignment.center,
                      child: Text(
                        n,
                        style: const TextStyle(
                          color: SwayaColors.accentHighlight,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            sub,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color: SwayaColors.inkSecondary,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => _continue(context),
              child: const Text('Continue'),
            ),
          ),
        ],
      ),
    );
  }
}
