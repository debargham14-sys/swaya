import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../models/blouse_measurements.dart';
import '../../models/garment_catalog.dart';
import '../../models/persona.dart';
import '../../services/order_actions.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Persona detail — opens when a saved persona is tapped. Shows the persona's
/// measurements and gender-aware "Order garment" / "Suggest" / "View on avatar"
/// actions.
class PersonaDetailScreen extends StatelessWidget {
  const PersonaDetailScreen({super.key, required this.persona});

  final Persona persona;

  Future<void> _orderGarment(BuildContext context) async {
    final garment = await showGarmentPicker(context, persona.gender);
    if (garment == null || !context.mounted) return;
    await placeGarmentOrder(context,
        personaName: persona.name, garment: garment.label);
  }

  @override
  Widget build(BuildContext context) {
    final m = persona.measurements;
    // Show the persona's saved measurements, labelled from the gender's catalog.
    final allFields = {
      for (final g in garmentsForGender(persona.gender))
        for (final f in g.fields) f.key: f,
    };
    final filled = m.values.keys
        .map((k) => allFields[k])
        .whereType<MeasurementField>()
        .toList();

    return LightScaffold(
      title: persona.name,
      showBack: true,
      showNav: false,
      bottomBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/design-assistant', extra: {
                    'gender': persona.gender,
                    'measurements': persona.measurements,
                    'personaName': persona.name,
                  }),
                  icon: const Icon(Icons.auto_awesome, size: 18),
                  label: const Text('Assistant'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => context.push('/avatar', extra: {
                    'gender': persona.gender,
                    'measurements': persona.measurements,
                  }),
                  icon: const Icon(Icons.view_in_ar_outlined, size: 18),
                  label: const Text('Avatar'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: () => _orderGarment(context),
              icon: const Icon(Icons.shopping_bag_outlined, size: 20),
              label: const Text('Order garment'),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: [
          AppCard(
            child: Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundColor: SwayaLight.surfaceAlt,
                  child: Text(
                    persona.name.isNotEmpty ? persona.name[0].toUpperCase() : '?',
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary,
                        fontWeight: FontWeight.w700,
                        fontSize: 18),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(persona.name,
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w700,
                              fontSize: 16)),
                      const SizedBox(height: 2),
                      Text(
                        persona.label ?? '${m.filledCount} measurements saved',
                        style: const TextStyle(
                            color: SwayaLight.inkTertiary, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const SectionTitle('Measurements'),
          const SizedBox(height: 12),
          if (filled.isEmpty)
            const AppCard(
              child: Text('No measurements saved for this persona yet.',
                  style:
                      TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
            )
          else
            for (final f in filled)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  decoration: BoxDecoration(
                    color: SwayaLight.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: SwayaLight.border),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(f.label,
                            style: const TextStyle(
                                color: SwayaLight.inkPrimary, fontSize: 14)),
                      ),
                      Text('${m[f.key]!.toStringAsFixed(1)} cm',
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              ),
        ],
      ),
    );
  }
}
