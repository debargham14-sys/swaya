import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../models/avatar_design.dart';
import '../../models/designer.dart';
import '../../services/designers_api.dart';
import '../../services/measure_api.dart' show MeasureApiException;
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Browse designers/tailors and pick one to collaborate with. Reached from the
/// avatar screen ("Collaborate with a designer"); the current [seed] design is
/// carried through so the session opens on what the user was looking at.
class DesignerDirectoryScreen extends StatefulWidget {
  const DesignerDirectoryScreen({super.key, this.seed});

  final AvatarDesign? seed;

  @override
  State<DesignerDirectoryScreen> createState() =>
      _DesignerDirectoryScreenState();
}

class _DesignerDirectoryScreenState extends State<DesignerDirectoryScreen> {
  final DesignersApi _api = DesignersApi();
  late Future<List<Designer>> _future = _api.list();
  bool _seeding = false;

  void _reload() => setState(() => _future = _api.list());

  Future<void> _loadDemo() async {
    setState(() => _seeding = true);
    try {
      await _api.seedSamples();
      _reload();
    } on MeasureApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _seeding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: 'Find a designer',
      showBack: true,
      showNav: false,
      body: FutureBuilder<List<Designer>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return _Message(
              text: 'Couldn\'t load designers.\n${snap.error}',
              actionLabel: 'Retry',
              onAction: _reload,
            );
          }
          final designers = snap.data ?? const [];
          if (designers.isEmpty) {
            return _Message(
              text: 'No designers yet.',
              actionLabel: _seeding ? 'Loading…' : 'Load demo designers',
              onAction: _seeding ? null : _loadDemo,
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
              itemCount: designers.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (_, i) => _DesignerCard(
                designer: designers[i],
                onTap: () => context.push('/designers/${designers[i].id}',
                    extra: {'seed': widget.seed, 'designer': designers[i]}),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _DesignerCard extends StatelessWidget {
  const _DesignerCard({required this.designer, required this.onTap});

  final Designer designer;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      onTap: onTap,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _Avatar(name: designer.name, url: designer.photoUrl),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(designer.name,
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontSize: 15,
                              fontWeight: FontWeight.w700)),
                    ),
                    if (designer.ratingCount > 0) _Rating(designer: designer),
                  ],
                ),
                if (designer.location != null) ...[
                  const SizedBox(height: 2),
                  Text(designer.location!,
                      style: const TextStyle(
                          color: SwayaLight.inkSecondary, fontSize: 12)),
                ],
                if (designer.specialties.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final s in designer.specialties.take(3))
                        _Chip(label: s),
                    ],
                  ),
                ],
                const SizedBox(height: 8),
                Row(
                  children: [
                    Container(
                      width: 7,
                      height: 7,
                      decoration: BoxDecoration(
                        color: designer.available
                            ? SwayaLight.success
                            : SwayaLight.inkTertiary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(designer.available ? 'Available' : 'Busy',
                        style: const TextStyle(
                            color: SwayaLight.inkSecondary, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.name, this.url});
  final String name;
  final String? url;

  @override
  Widget build(BuildContext context) {
    final initial = name.isNotEmpty ? name[0].toUpperCase() : '?';
    return Container(
      width: 46,
      height: 46,
      decoration: BoxDecoration(
        color: SwayaLight.accent.withValues(alpha: 0.12),
        shape: BoxShape.circle,
        image: (url != null && url!.isNotEmpty)
            ? DecorationImage(image: NetworkImage(url!), fit: BoxFit.cover)
            : null,
      ),
      alignment: Alignment.center,
      child: (url == null || url!.isEmpty)
          ? Text(initial,
              style: const TextStyle(
                  color: SwayaLight.accent,
                  fontWeight: FontWeight.w700,
                  fontSize: 18))
          : null,
    );
  }
}

class _Rating extends StatelessWidget {
  const _Rating({required this.designer});
  final Designer designer;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.star, size: 14, color: SwayaLight.accent),
        const SizedBox(width: 2),
        Text(designer.ratingAvg.toStringAsFixed(1),
            style: const TextStyle(
                color: SwayaLight.inkPrimary,
                fontSize: 12,
                fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Text(label,
          style: const TextStyle(
              color: SwayaLight.inkSecondary, fontSize: 11)),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.text, this.actionLabel, this.onAction});
  final String text;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(text,
                textAlign: TextAlign.center,
                style: const TextStyle(color: SwayaLight.inkSecondary)),
            if (actionLabel != null) ...[
              const SizedBox(height: 16),
              OutlinedButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}
