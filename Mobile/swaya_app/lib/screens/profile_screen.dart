import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_controller.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

/// Profile / settings. Shows the signed-in identity and a sign-out action.
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final user = auth.user;
    final text = Theme.of(context).textTheme;

    final identity = user?.email?.isNotEmpty == true
        ? user!.email!
        : user?.phoneNumber?.isNotEmpty == true
            ? user!.phoneNumber!
            : user?.displayName?.isNotEmpty == true
                ? user!.displayName!
                : 'Signed in';

    return SwayaScaffold(
      title: 'Profile',
      body: ListView(
        children: [
          const SizedBox(height: 8),
          if (user != null)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: SwayaColors.elevated,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: SwayaColors.borderSubtle),
              ),
              child: Row(
                children: [
                  const CircleAvatar(
                    backgroundColor: SwayaColors.accent,
                    child: Icon(Icons.person, color: SwayaColors.onAccent),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(identity,
                            style: text.bodyLarge
                                ?.copyWith(fontWeight: FontWeight.w600)),
                        const SizedBox(height: 2),
                        Text(
                          'Signed in',
                          style: text.bodySmall
                              ?.copyWith(color: SwayaColors.inkTertiary),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            )
          else
            Text(
              'Account and settings (phase 2).',
              style: text.bodyMedium?.copyWith(color: SwayaColors.inkSecondary),
            ),
          const SizedBox(height: 24),
          if (user != null)
            OutlinedButton.icon(
              onPressed: () => _confirmSignOut(context, auth),
              icon: const Icon(Icons.logout, size: 20),
              label: const Text('Sign out'),
            ),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, AuthController auth) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: SwayaColors.elevated,
        title: const Text('Sign out?'),
        content: const Text('You can sign back in anytime.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await auth.signOut();
      // Router redirect sends the user back to /auth automatically.
    }
  }
}
