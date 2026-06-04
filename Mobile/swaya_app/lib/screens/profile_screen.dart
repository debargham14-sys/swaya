import 'package:flutter/material.dart';

import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

/// Placeholder — settings / profile branch from Figma.
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      title: 'Profile',
      body: Center(
        child: Text(
          'Account and settings (phase 2).',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: SwayaColors.inkSecondary,
              ),
        ),
      ),
    );
  }
}
