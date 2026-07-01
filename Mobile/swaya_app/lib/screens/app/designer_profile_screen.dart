import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../models/avatar_design.dart';
import '../../models/designer.dart';
import '../../services/collab_api.dart';
import '../../services/designers_api.dart';
import '../../services/measure_api.dart' show MeasureApiException;
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Full designer profile with the "Start collaboration" CTA, which creates a
/// session (seeded with the current avatar [seed]) and opens the shared studio.
class DesignerProfileScreen extends StatefulWidget {
  const DesignerProfileScreen({
    super.key,
    required this.designerId,
    this.initial,
    this.seed,
  });

  final String designerId;
  final Designer? initial;
  final AvatarDesign? seed;

  @override
  State<DesignerProfileScreen> createState() => _DesignerProfileScreenState();
}

class _DesignerProfileScreenState extends State<DesignerProfileScreen> {
  late final Future<Designer> _future =
      widget.initial != null ? Future.value(widget.initial) : _load();
  bool _starting = false;

  Future<Designer> _load() => DesignersApi().get(widget.designerId);

  Future<void> _start(Designer designer) async {
    setState(() => _starting = true);
    try {
      final session = await CollabApi()
          .createSession(widget.designerId, widget.seed ?? const AvatarDesign());
      if (!mounted) return;
      context.pushReplacement('/collab/${session.id}', extra: {
        'role': 'user',
        'seed': session.design,
      });
    } on MeasureApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
        setState(() => _starting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: 'Designer',
      showBack: true,
      showNav: false,
      body: FutureBuilder<Designer>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!snap.hasData) {
            return Center(
              child: Text('Couldn\'t load this designer.\n${snap.error ?? ''}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: SwayaLight.inkSecondary)),
            );
          }
          final d = snap.data!;
          return ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
            children: [
              Row(
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: SwayaLight.accent.withValues(alpha: 0.12),
                      shape: BoxShape.circle,
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      d.name.isNotEmpty ? d.name[0].toUpperCase() : '?',
                      style: const TextStyle(
                          color: SwayaLight.accent,
                          fontSize: 26,
                          fontWeight: FontWeight.w700),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(d.name,
                            style: const TextStyle(
                                color: SwayaLight.inkPrimary,
                                fontSize: 20,
                                fontWeight: FontWeight.w700)),
                        if (d.location != null)
                          Text(d.location!,
                              style: const TextStyle(
                                  color: SwayaLight.inkSecondary,
                                  fontSize: 13)),
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            if (d.ratingCount > 0) ...[
                              const Icon(Icons.star,
                                  size: 16, color: SwayaLight.accent),
                              const SizedBox(width: 4),
                              Text(
                                  '${d.ratingAvg.toStringAsFixed(1)} (${d.ratingCount})',
                                  style: const TextStyle(
                                      color: SwayaLight.inkPrimary,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600)),
                              const SizedBox(width: 12),
                            ],
                            if (d.yearsExperience != null)
                              Text('${d.yearsExperience}y exp',
                                  style: const TextStyle(
                                      color: SwayaLight.inkSecondary,
                                      fontSize: 13)),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (d.bio != null && d.bio!.isNotEmpty) ...[
                const SizedBox(height: 20),
                Text(d.bio!,
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary, fontSize: 14, height: 1.4)),
              ],
              if (d.specialties.isNotEmpty) ...[
                const SizedBox(height: 20),
                const SectionTitle('Specialties'),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final s in d.specialties)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: SwayaLight.surfaceAlt,
                          borderRadius: BorderRadius.circular(20),
                          border: Border.all(color: SwayaLight.border),
                        ),
                        child: Text(s,
                            style: const TextStyle(
                                color: SwayaLight.inkSecondary, fontSize: 13)),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 28),
              ElevatedButton.icon(
                onPressed: _starting ? null : () => _start(d),
                icon: _starting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: SwayaLight.onCta))
                    : const Icon(Icons.handshake_outlined),
                label: Text(_starting ? 'Starting…' : 'Start collaboration'),
              ),
            ],
          );
        },
      ),
    );
  }
}
