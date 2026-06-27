import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/persona.dart';
import '../../providers/auth_controller.dart';
import '../../services/persona_store.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Profile — bottom-nav tab. Shows the signed-in identity, saved personas, and
/// sign-out.
class ProfileV2Screen extends StatefulWidget {
  const ProfileV2Screen({super.key});

  @override
  State<ProfileV2Screen> createState() => _ProfileV2ScreenState();
}

class _ProfileV2ScreenState extends State<ProfileV2Screen> {
  List<Persona>? _personas;

  @override
  void initState() {
    super.initState();
    final uid = context.read<AuthController>().user?.uid;
    PersonaStore(userId: uid).list().then((p) {
      if (mounted) setState(() => _personas = p);
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final user = auth.user;
    final identity = user?.displayName?.isNotEmpty == true
        ? user!.displayName!
        : user?.email ?? user?.phoneNumber ?? 'Signed in';
    final personas = _personas;

    return LightScaffold(
      title: 'Profile',
      showMenu: true,
      navIndex: 4,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: [
          AppCard(
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 24,
                  backgroundColor: SwayaLight.surfaceAlt,
                  child: Icon(Icons.person, color: SwayaLight.inkSecondary),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(identity,
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w700,
                              fontSize: 16)),
                      const SizedBox(height: 2),
                      const Text('Signed in',
                          style: TextStyle(
                              color: SwayaLight.inkTertiary, fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionTitle('Saved Personas'),
          const SizedBox(height: 12),
          if (personas == null)
            const Center(child: Padding(
              padding: EdgeInsets.all(16),
              child: CircularProgressIndicator(),
            ))
          else if (personas.isEmpty)
            AppCard(
              child: Row(
                children: const [
                  Icon(Icons.group_outlined, color: SwayaLight.inkTertiary),
                  SizedBox(width: 12),
                  Expanded(
                    child: Text('No personas yet. Add measurements to create one.',
                        style: TextStyle(
                            color: SwayaLight.inkSecondary, fontSize: 13)),
                  ),
                ],
              ),
            )
          else
            for (final p in personas)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: AppCard(
                  onTap: () => context.push('/persona', extra: p),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 18,
                        backgroundColor: SwayaLight.surfaceAlt,
                        child: Text(
                          p.name.isNotEmpty ? p.name[0].toUpperCase() : '?',
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w700),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(p.name,
                            style: const TextStyle(
                                color: SwayaLight.inkPrimary,
                                fontWeight: FontWeight.w600)),
                      ),
                      Text('${p.measurements.filledCount} values',
                          style: const TextStyle(
                              color: SwayaLight.inkTertiary, fontSize: 12)),
                      const SizedBox(width: 6),
                      const Icon(Icons.chevron_right,
                          color: SwayaLight.inkTertiary),
                    ],
                  ),
                ),
              ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: () async {
              await auth.signOut();
              // Router redirect returns to /auth automatically.
            },
            icon: const Icon(Icons.logout, size: 20),
            label: const Text('Sign out'),
          ),
        ],
      ),
    );
  }
}
