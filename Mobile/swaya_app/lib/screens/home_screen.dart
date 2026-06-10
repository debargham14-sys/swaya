import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../providers/capture_session.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<CaptureSession>();
    final hasResults = session.lastResult != null;

    return SwayaScaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'DSV',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 4),
          Text(
            'Digital sizing & fit',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          const SizedBox(height: 32),
          _ActionCard(
            title: 'New body scan',
            subtitle: 'Front, back, and side photos + height',
            icon: Icons.camera_alt_outlined,
            onTap: () {
              session.resetForNewScan();
              context.go('/scan/height');
            },
          ),
          const SizedBox(height: 12),
          _ActionCard(
            title: 'Vest scan (beta)',
            subtitle: 'ChArUco vest → bust, waist, hip',
            icon: Icons.straighten_outlined,
            onTap: () => context.push('/vest'),
          ),
          const SizedBox(height: 12),
          if (hasResults) ...[
            _ActionCard(
              title: 'Last measurements',
              subtitle: 'View bust, waist, hip from your latest scan',
              icon: Icons.analytics_outlined,
              onTap: () => context.push('/scan/results'),
            ),
            const SizedBox(height: 12),
            _ActionCard(
              title: 'Fit assistant',
              subtitle: 'Ask about sizing and alterations',
              icon: Icons.chat_outlined,
              onTap: () => context.go('/assistant'),
            ),
          ],
          const Spacer(),
        ],
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: SwayaColors.elevated,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: SwayaColors.borderSubtle),
          ),
          child: Row(
            children: [
              Icon(icon, color: SwayaColors.accentHighlight, size: 28),
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
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: SwayaColors.inkSecondary,
                          ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: SwayaColors.inkTertiary),
            ],
          ),
        ),
      ),
    );
  }
}
