import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../models/collab_session.dart';
import '../../services/collab_api.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// The user's collaboration inbox: active sessions and past history, with unread
/// badges. Tapping one re-opens the shared studio.
class CollaborationsScreen extends StatefulWidget {
  const CollaborationsScreen({super.key});

  @override
  State<CollaborationsScreen> createState() => _CollaborationsScreenState();
}

class _CollaborationsScreenState extends State<CollaborationsScreen> {
  late Future<List<CollabSession>> _future = CollabApi().listSessions('user');

  void _reload() =>
      setState(() => _future = CollabApi().listSessions('user'));

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: 'Collaborations',
      showBack: true,
      showNav: false,
      trailing: IconButton(
        icon: const Icon(Icons.add, size: 22),
        tooltip: 'Find a designer',
        onPressed: () => context.push('/designers'),
      ),
      body: FutureBuilder<List<CollabSession>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final sessions = snap.data ?? const [];
          if (sessions.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('No collaborations yet.',
                        style: TextStyle(color: SwayaLight.inkSecondary)),
                    const SizedBox(height: 16),
                    ElevatedButton.icon(
                      onPressed: () => context.push('/designers'),
                      icon: const Icon(Icons.search),
                      label: const Text('Find a designer'),
                    ),
                  ],
                ),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
              itemCount: sessions.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (_, i) => CollabSessionTile(
                session: sessions[i],
                role: 'user',
                onTap: () => context.push('/collab/${sessions[i].id}', extra: {
                  'role': 'user',
                  'seed': sessions[i].design,
                }),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Shared session row used by both the user inbox and the designer dashboard.
class CollabSessionTile extends StatelessWidget {
  const CollabSessionTile({
    super.key,
    required this.session,
    required this.role,
    required this.onTap,
  });

  final CollabSession session;
  final String role; // viewer's role
  final VoidCallback onTap;

  ({Color bg, Color fg, String label}) get _badge {
    switch (session.status) {
      case 'active':
        return (
          bg: SwayaLight.success.withValues(alpha: 0.14),
          fg: SwayaLight.success,
          label: 'Active'
        );
      case 'ended':
        return (
          bg: SwayaLight.surfaceAlt,
          fg: SwayaLight.inkTertiary,
          label: 'Ended'
        );
      default:
        return (
          bg: SwayaLight.accent.withValues(alpha: 0.14),
          fg: SwayaLight.accent,
          label: role == 'designer' ? 'New request' : 'Pending'
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final unread = session.unreadFor(role);
    final badge = _badge;
    return AppCard(
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: SwayaLight.accent.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            alignment: Alignment.center,
            child: const Icon(Icons.view_in_ar_outlined,
                color: SwayaLight.accent),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(session.otherName(role),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w700)),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: badge.bg,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(badge.label,
                          style: TextStyle(
                              color: badge.fg,
                              fontSize: 11,
                              fontWeight: FontWeight.w700)),
                    ),
                  ],
                ),
                const SizedBox(height: 3),
                Text(
                  session.lastMessage ?? 'Tap to open the shared design',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 12),
                ),
              ],
            ),
          ),
          if (unread > 0) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                color: SwayaLight.error,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text('$unread',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.w700)),
            ),
          ],
        ],
      ),
    );
  }
}
