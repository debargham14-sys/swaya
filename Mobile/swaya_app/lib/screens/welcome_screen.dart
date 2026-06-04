import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../services/onboarding_store.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  Future<void> _start(BuildContext context) async {
    final done = await OnboardingStore().isComplete();
    if (!context.mounted) return;
    context.go(done ? '/home' : '/onboarding');
  }

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      body: Column(
        children: [
          const Spacer(flex: 2),
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: SwayaColors.accent,
              borderRadius: BorderRadius.circular(18),
            ),
            alignment: Alignment.center,
            child: Text(
              'D',
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: SwayaColors.onAccent,
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ),
          const SizedBox(height: 32),
          Text(
            'DSV',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Body measurements from photos — fit guidance in conversation.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          const Spacer(flex: 3),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () => _start(context),
              child: const Text('Get started'),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Photos stay on device until you submit',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: SwayaColors.inkTertiary,
                ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
