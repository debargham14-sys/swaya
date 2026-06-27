import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_controller.dart';
import '../../theme/swaya_light_theme.dart';

/// Light page shell for the in-app screens (Figma frames 11–21): white canvas,
/// a top bar (menu / title / action), optional bottom nav, and a sticky bottom
/// action button.
class LightScaffold extends StatelessWidget {
  const LightScaffold({
    super.key,
    required this.title,
    required this.body,
    this.showBack = false,
    this.showMenu = false,
    this.trailing,
    this.bottomBar,
    this.showNav = true,
    this.navIndex = 2,
  });

  final String title;
  final Widget body;
  final bool showBack;
  final bool showMenu;
  final Widget? trailing;
  final Widget? bottomBar;
  final bool showNav;
  final int navIndex;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: buildSwayaLightTheme(),
      child: Scaffold(
        backgroundColor: SwayaLight.canvas,
        drawer: showMenu ? const _AppDrawer() : null,
        appBar: AppBar(
          backgroundColor: SwayaLight.canvas,
          surfaceTintColor: SwayaLight.canvas,
          elevation: 0,
          centerTitle: true,
          leading: showBack
              ? IconButton(
                  icon: const Icon(Icons.arrow_back_ios_new, size: 20),
                  // go_router-aware back: pop the pushed page, or fall back to
                  // Home if this screen was entered via a tab switch (no stack).
                  onPressed: () =>
                      context.canPop() ? context.pop() : context.go('/home-v2'),
                )
              : showMenu
                  // Builder gives a context *below* the Scaffold so openDrawer works.
                  ? Builder(
                      builder: (ctx) => IconButton(
                        icon: const Icon(Icons.menu, size: 22),
                        onPressed: () => Scaffold.of(ctx).openDrawer(),
                      ),
                    )
                  : null,
          title: Text(
            title,
            style: const TextStyle(
              color: SwayaLight.inkPrimary,
              fontSize: 17,
              fontWeight: FontWeight.w600,
            ),
          ),
          actions: trailing != null ? [trailing!] : null,
        ),
        // Tap anywhere on a blank area to dismiss the keyboard. translucent lets
        // this catch taps on gaps while interactive children still get theirs.
        body: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
          child: SafeArea(top: false, child: body),
        ),
        bottomNavigationBar: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (bottomBar != null)
              Container(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                decoration: const BoxDecoration(
                  color: SwayaLight.canvas,
                  border: Border(top: BorderSide(color: SwayaLight.border)),
                ),
                child: SafeArea(top: false, bottom: !showNav, child: bottomBar!),
              ),
            // Hide the tab bar while the keyboard is up so it doesn't float over
            // the keyboard and crowd form fields.
            if (showNav && MediaQuery.viewInsetsOf(context).bottom == 0)
              SwayaBottomNav(currentIndex: navIndex),
          ],
        ),
      ),
    );
  }
}

/// Side navigation opened by the top-bar hamburger. Reaches every top-level
/// destination from anywhere, plus sign-out.
class _AppDrawer extends StatelessWidget {
  const _AppDrawer();

  static const _items = [
    (icon: Icons.home_outlined, label: 'Home', route: '/home-v2'),
    (icon: Icons.straighten, label: 'Measure', route: '/measure'),
    (icon: Icons.shopping_bag_outlined, label: 'Orders', route: '/orders'),
    (icon: Icons.person_outline, label: 'Profile', route: '/profile-v2'),
  ];

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthController>();
    final user = auth.user;
    final label = user?.displayName?.trim().isNotEmpty == true
        ? user!.displayName!
        : (user?.email ?? 'Signed in');

    return Drawer(
      backgroundColor: SwayaLight.canvas,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('SWAYA',
                      style: TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontSize: 20,
                          fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Text(label,
                      style: const TextStyle(
                          color: SwayaLight.inkSecondary, fontSize: 13)),
                ],
              ),
            ),
            const Divider(height: 1, color: SwayaLight.border),
            for (final item in _items)
              ListTile(
                leading: Icon(item.icon, color: SwayaLight.inkSecondary),
                title: Text(item.label,
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary,
                        fontWeight: FontWeight.w600)),
                onTap: () {
                  Navigator.of(context).pop(); // close drawer
                  context.go(item.route);
                },
              ),
            const Spacer(),
            const Divider(height: 1, color: SwayaLight.border),
            ListTile(
              leading: const Icon(Icons.logout, color: SwayaLight.inkSecondary),
              title: const Text('Sign out',
                  style: TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontWeight: FontWeight.w600)),
              onTap: () {
                Navigator.of(context).pop();
                auth.signOut();
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}

/// The 5-item bottom navigation from the frames: Orders, Measure, Home,
/// Scan (center, raised), Profile.
class SwayaBottomNav extends StatelessWidget {
  const SwayaBottomNav({super.key, required this.currentIndex});

  final int currentIndex;

  static const _items = [
    (icon: Icons.shopping_bag_outlined, route: '/orders'),
    (icon: Icons.straighten, route: '/measure'),
    (icon: Icons.home_outlined, route: '/home-v2'),
    // Scan entry: route to the measure flow start (which sets up the draft +
    // photo source) rather than deep-linking into the mid-flow capture screen.
    (icon: Icons.center_focus_strong, route: '/measure'),
    (icon: Icons.person_outline, route: '/profile-v2'),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: SwayaLight.canvas,
        border: Border(top: BorderSide(color: SwayaLight.border)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 62,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              for (var i = 0; i < _items.length; i++)
                _NavItem(
                  icon: _items[i].icon,
                  active: i == currentIndex,
                  center: i == 3,
                  onTap: () => context.go(_items[i].route),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.active,
    required this.onTap,
    this.center = false,
  });

  final IconData icon;
  final bool active;
  final bool center;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    if (center) {
      return GestureDetector(
        onTap: onTap,
        child: Container(
          width: 52,
          height: 52,
          decoration: const BoxDecoration(
            color: SwayaLight.cta,
            shape: BoxShape.circle,
          ),
          child: const Icon(Icons.center_focus_strong,
              color: SwayaLight.onCta, size: 26),
        ),
      );
    }
    return IconButton(
      onPressed: onTap,
      icon: Icon(
        icon,
        size: 24,
        color: active ? SwayaLight.cta : SwayaLight.inkTertiary,
      ),
    );
  }
}

/// A tappable card used across the in-app screens (quick actions, method
/// choice, etc.).
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.all(16),
    this.color,
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsets padding;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: color ?? SwayaLight.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: SwayaLight.border),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Section heading like "Quick Actions" / "Choose Method".
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.subtitle});
  final String text;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          text,
          style: const TextStyle(
            color: SwayaLight.inkPrimary,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 4),
          Text(subtitle!,
              style: const TextStyle(
                  color: SwayaLight.inkSecondary, fontSize: 13)),
        ],
      ],
    );
  }
}
