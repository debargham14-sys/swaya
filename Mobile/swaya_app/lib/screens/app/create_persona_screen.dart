import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/persona.dart';
import '../../providers/auth_controller.dart';
import '../../providers/measurement_draft.dart';
import '../../services/persona_store.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Create Persona — Figma frame 20. Name + quick label, with a summary of the
/// measurements being attached, then save.
class CreatePersonaScreen extends StatefulWidget {
  const CreatePersonaScreen({super.key});

  @override
  State<CreatePersonaScreen> createState() => _CreatePersonaScreenState();
}

class _CreatePersonaScreenState extends State<CreatePersonaScreen> {
  final _name = TextEditingController();
  String? _label;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim().isNotEmpty
        ? _name.text.trim()
        : (_label ?? '');
    if (name.isEmpty) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(
            content: Text('Enter a name or pick a quick label.')));
      return;
    }
    setState(() => _saving = true);
    final draft = context.read<MeasurementDraft>();
    final store = PersonaStore(userId: context.read<AuthController>().user?.uid);
    await store.upsert(Persona(
      id: PersonaStore.newId(),
      name: name,
      label: _label,
      measurements: draft.measurements.copy(),
    ));
    if (!mounted) return;
    context.go('/measure/saved', extra: name);
  }

  @override
  Widget build(BuildContext context) {
    final draft = context.watch<MeasurementDraft>();
    final filled = draft.measurements.filledCount;

    return LightScaffold(
      title: 'Create Persona',
      showBack: true,
      navIndex: 1,
      bottomBar: SizedBox(
        width: double.infinity,
        child: ElevatedButton(
          onPressed: _saving ? null : _save,
          child: _saving
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: SwayaLight.onCta))
              : const Text('Save Persona'),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const Text('Create new persona',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Give these measurements a recognisable name.',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 14)),
          const SizedBox(height: 24),
          const Text('Persona Name',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          TextField(
            controller: _name,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
              hintText: 'e.g. Mom, Sister, Friend',
              prefixIcon: Icon(Icons.badge_outlined, size: 20),
            ),
          ),
          const SizedBox(height: 20),
          const Text('Quick Labels',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final label in Persona.quickLabels)
                _LabelChip(
                  label: label,
                  selected: _label == label,
                  onTap: () => setState(() {
                    _label = _label == label ? null : label;
                    if (_label != null && _name.text.trim().isEmpty) {
                      _name.text = label;
                    }
                  }),
                ),
            ],
          ),
          const SizedBox(height: 24),
          AppCard(
            child: Row(
              children: [
                const Icon(Icons.straighten, color: SwayaLight.accent),
                const SizedBox(width: 12),
                Expanded(
                  child: Text('$filled measurements will be saved to this persona',
                      style: const TextStyle(
                          color: SwayaLight.inkSecondary, fontSize: 13)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LabelChip extends StatelessWidget {
  const _LabelChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? SwayaLight.cta : SwayaLight.surface,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
              color: selected ? SwayaLight.cta : SwayaLight.border),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? SwayaLight.onCta : SwayaLight.inkPrimary,
            fontWeight: FontWeight.w600,
            fontSize: 14,
          ),
        ),
      ),
    );
  }
}
