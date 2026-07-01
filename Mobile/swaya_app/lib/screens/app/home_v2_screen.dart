import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_controller.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Home — Figma frame 11. Greeting, the DSV measurement call-to-action, a
/// quick-actions grid, and a "complete your profile" nudge.
class HomeV2Screen extends StatelessWidget {
  const HomeV2Screen({super.key});

  String _firstName(BuildContext context) {
    final user = context.read<AuthController>().user;
    final name = user?.displayName;
    if (name != null && name.trim().isNotEmpty) return name.split(' ').first;
    final email = user?.email;
    if (email != null && email.contains('@')) return email.split('@').first;
    return 'there';
  }

  @override
  Widget build(BuildContext context) {
    final name = _firstName(context);
    return LightScaffold(
      title: 'SWAYA',
      showMenu: true,
      navIndex: 2,
      trailing: IconButton(
        icon: const Icon(Icons.settings_outlined, size: 22),
        onPressed: () => context.go('/profile-v2'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text('Good Morning, $name',
              style: const TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Ready to create your custom Blouse?',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 14)),
          const SizedBox(height: 20),
          _DsvCard(onOrder: () => context.go('/measure')),
          const SizedBox(height: 12),
          AppCard(
            onTap: () => context.push('/avatar'),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: SwayaLight.accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.view_in_ar_outlined,
                      color: SwayaLight.accent, size: 22),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('3D Try-On',
                          style: TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w600)),
                      SizedBox(height: 2),
                      Text('Preview your blouse on a live avatar',
                          style: TextStyle(
                              color: SwayaLight.inkSecondary, fontSize: 12)),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, color: SwayaLight.inkTertiary),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            onTap: () => context.push('/collaborations'),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: SwayaLight.accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.handshake_outlined,
                      color: SwayaLight.accent, size: 22),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Collaborate with a designer',
                          style: TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w600)),
                      SizedBox(height: 2),
                      Text('Design your blouse together, live',
                          style: TextStyle(
                              color: SwayaLight.inkSecondary, fontSize: 12)),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, color: SwayaLight.inkTertiary),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionTitle('Quick Actions'),
          const SizedBox(height: 12),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.5,
            children: [
              _QuickAction(
                icon: Icons.design_services_outlined,
                title: 'Design',
                subtitle: 'Create',
                onTap: () => context.go('/measure'),
              ),
              _QuickAction(
                icon: Icons.straighten,
                title: 'Measure',
                subtitle: 'Add Measurements',
                onTap: () => context.go('/measure'),
              ),
              _QuickAction(
                icon: Icons.local_shipping_outlined,
                title: 'Orders',
                subtitle: 'Track Progress',
                onTap: () => context.go('/orders'),
              ),
              _QuickAction(
                icon: Icons.person_outline,
                title: 'Profile',
                subtitle: 'Saved Profile',
                onTap: () => context.go('/profile-v2'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          AppCard(
            onTap: () => context.go('/profile-v2'),
            child: Row(
              children: [
                const Icon(Icons.account_circle_outlined,
                    color: SwayaLight.inkSecondary),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text('Complete your Profile',
                      style: TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontWeight: FontWeight.w600)),
                ),
                const Icon(Icons.chevron_right, color: SwayaLight.inkTertiary),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DsvCard extends StatelessWidget {
  const _DsvCard({required this.onOrder});
  final VoidCallback onOrder;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SwayaLight.cta,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text('DSV for Measurements',
                    style: TextStyle(
                        color: SwayaLight.onCta,
                        fontSize: 17,
                        fontWeight: FontWeight.w700)),
              ),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.straighten,
                    color: SwayaLight.onCta, size: 22),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Start DSV ordering, add measurements and continue to design selection.',
            style: TextStyle(
                color: SwayaLight.onCta.withValues(alpha: 0.8), fontSize: 13),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: onOrder,
              style: ElevatedButton.styleFrom(
                backgroundColor: SwayaLight.onCta,
                foregroundColor: SwayaLight.cta,
              ),
              child: const Text('Order DSV'),
            ),
          ),
        ],
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: SwayaLight.accent, size: 26),
          const Spacer(),
          Text(title,
              style: const TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontWeight: FontWeight.w700,
                  fontSize: 15)),
          const SizedBox(height: 2),
          Text(subtitle,
              style: const TextStyle(
                  color: SwayaLight.inkSecondary, fontSize: 12)),
        ],
      ),
    );
  }
}
