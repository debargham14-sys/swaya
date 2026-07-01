import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/collab_session.dart';
import '../../providers/auth_controller.dart';
import '../../services/collab_api.dart';
import '../../theme/swaya_light_theme.dart';
import '../app/collaborations_screen.dart' show CollabSessionTile;

/// The designer console home (role-gated landing). Lists incoming requests and
/// ongoing/past collaborations; tapping one opens the shared studio. Polls so
/// new requests appear without a manual refresh.
class DesignerHomeScreen extends StatefulWidget {
  const DesignerHomeScreen({super.key});

  @override
  State<DesignerHomeScreen> createState() => _DesignerHomeScreenState();
}

class _DesignerHomeScreenState extends State<DesignerHomeScreen> {
  final CollabApi _api = CollabApi();
  List<CollabSession>? _sessions;
  bool _loading = true;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _reload();
    _poll = Timer.periodic(const Duration(seconds: 10), (_) => _reload());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      final list = await _api.listSessions('designer');
      if (mounted) setState(() => _sessions = list);
    } catch (_) {
      // Keep showing the last good list; a transient poll failure isn't fatal.
    } finally {
      if (mounted && _loading) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final name = auth.designerProfile?.name ?? 'Designer';

    return Theme(
      data: buildSwayaLightTheme(),
      child: Scaffold(
        backgroundColor: SwayaLight.canvas,
        appBar: AppBar(
          backgroundColor: SwayaLight.canvas,
          elevation: 0,
          title: const Text('Designer studio',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 17,
                  fontWeight: FontWeight.w700)),
          actions: [
            IconButton(
              tooltip: 'Switch to shopping',
              icon: const Icon(Icons.storefront_outlined, size: 20),
              onPressed: () => context.go('/home-v2'),
            ),
            IconButton(
              tooltip: 'Edit profile',
              icon: const Icon(Icons.edit_outlined, size: 20),
              onPressed: () => context.push('/designer/register'),
            ),
            IconButton(
              tooltip: 'Sign out',
              icon: const Icon(Icons.logout, size: 20),
              onPressed: auth.signOut,
            ),
          ],
        ),
        body: Builder(
          builder: (context) {
            if (_loading && _sessions == null) {
              return const Center(child: CircularProgressIndicator());
            }
            final all = _sessions ?? const <CollabSession>[];
            final pending = all.where((s) => s.isPending).toList();
            final ongoing = all.where((s) => !s.isPending).toList();

            return RefreshIndicator(
              onRefresh: _reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                children: [
                  Text('Welcome, $name',
                      style: const TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontSize: 20,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text(
                    pending.isEmpty
                        ? 'No new requests right now.'
                        : '${pending.length} client${pending.length == 1 ? '' : 's'} waiting to collaborate.',
                    style: const TextStyle(
                        color: SwayaLight.inkSecondary, fontSize: 14),
                  ),
                  const SizedBox(height: 20),
                  if (pending.isNotEmpty) ...[
                    const _Heading('Requests'),
                    const SizedBox(height: 10),
                    for (final s in pending) ...[
                      CollabSessionTile(
                        session: s,
                        role: 'designer',
                        onTap: () => _open(s),
                      ),
                      const SizedBox(height: 12),
                    ],
                    const SizedBox(height: 8),
                  ],
                  const _Heading('Collaborations'),
                  const SizedBox(height: 10),
                  if (ongoing.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text('Accepted sessions will show up here.',
                            style: TextStyle(color: SwayaLight.inkTertiary)),
                      ),
                    )
                  else
                    for (final s in ongoing) ...[
                      CollabSessionTile(
                        session: s,
                        role: 'designer',
                        onTap: () => _open(s),
                      ),
                      const SizedBox(height: 12),
                    ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  void _open(CollabSession s) {
    context.push('/collab/${s.id}', extra: {
      'role': 'designer',
      'seed': s.design,
    }).then((_) => _reload());
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text,
        style: const TextStyle(
            color: SwayaLight.inkPrimary,
            fontSize: 16,
            fontWeight: FontWeight.w700));
  }
}
