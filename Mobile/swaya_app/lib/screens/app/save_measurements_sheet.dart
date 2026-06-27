import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/persona.dart';
import '../../providers/auth_controller.dart';
import '../../providers/measurement_draft.dart';
import '../../services/persona_store.dart';
import '../../theme/swaya_light_theme.dart';

/// Save Measurements — Figma frames 18–19. Bottom sheet to save the reviewed
/// measurements into an existing persona, or start a new one.
Future<void> showSaveMeasurementsSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: SwayaLight.canvas,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => const _SaveSheet(),
  );
}

class _SaveSheet extends StatefulWidget {
  const _SaveSheet();

  @override
  State<_SaveSheet> createState() => _SaveSheetState();
}

class _SaveSheetState extends State<_SaveSheet> {
  late final PersonaStore _store =
      PersonaStore(userId: context.read<AuthController>().user?.uid);
  List<Persona>? _personas;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _store.list().then((p) {
      if (mounted) setState(() => _personas = p);
    });
  }

  Future<void> _saveTo(Persona persona) async {
    setState(() => _saving = true);
    final draft = context.read<MeasurementDraft>();
    await _store.upsert(persona.copyWith(measurements: draft.measurements.copy()));
    if (!mounted) return;
    Navigator.pop(context);
    context.go('/measure/saved', extra: persona.name);
  }

  @override
  Widget build(BuildContext context) {
    final personas = _personas;
    return Theme(
      data: buildSwayaLightTheme(),
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: SwayaLight.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Save Measurements',
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 18,
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            const Text('Choose where to save these reviewed measurements.',
                style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
            const SizedBox(height: 20),
            if (personas == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              )
            else ...[
              if (personas.isNotEmpty) ...[
                const Text('Existing personas',
                    style: TextStyle(
                        color: SwayaLight.inkSecondary,
                        fontSize: 12,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                for (final p in personas)
                  _PersonaTile(
                    persona: p,
                    enabled: !_saving,
                    onTap: () => _saveTo(p),
                  ),
                const SizedBox(height: 12),
              ],
              OutlinedButton.icon(
                onPressed: _saving
                    ? null
                    : () {
                        Navigator.pop(context);
                        context.push('/measure/persona');
                      },
                icon: const Icon(Icons.add, size: 20),
                label: const Text('Create new Persona'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PersonaTile extends StatelessWidget {
  const _PersonaTile({
    required this.persona,
    required this.onTap,
    required this.enabled,
  });

  final Persona persona;
  final VoidCallback onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: SwayaLight.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: SwayaLight.border),
          ),
          child: Row(
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: SwayaLight.surfaceAlt,
                child: Text(
                  persona.name.isNotEmpty ? persona.name[0].toUpperCase() : '?',
                  style: const TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(persona.name,
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary,
                        fontWeight: FontWeight.w600)),
              ),
              if (persona.label != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: SwayaLight.surfaceAlt,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(persona.label!,
                      style: const TextStyle(
                          color: SwayaLight.inkSecondary, fontSize: 12)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
