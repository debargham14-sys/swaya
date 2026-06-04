import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../theme/swaya_theme.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const _tabs = [
    (Icons.home_outlined, Icons.home, 'Home', '/home'),
    (Icons.straighten_outlined, Icons.straighten, 'Scans', '/history'),
    (Icons.chat_bubble_outline, Icons.chat_bubble, 'Assistant', '/assistant'),
    (Icons.person_outline, Icons.person, 'Profile', '/profile'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SwayaColors.base,
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        backgroundColor: SwayaColors.chrome,
        indicatorColor: SwayaColors.accent.withValues(alpha: 0.25),
        onDestinationSelected: (index) {
          navigationShell.goBranch(
            index,
            initialLocation: index == navigationShell.currentIndex,
          );
        },
        destinations: [
          for (final t in _tabs)
            NavigationDestination(
              icon: Icon(t.$1, color: SwayaColors.inkTertiary),
              selectedIcon: Icon(t.$2, color: SwayaColors.accentHighlight),
              label: t.$3,
            ),
        ],
      ),
    );
  }
}
