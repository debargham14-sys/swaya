import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/garment_catalog.dart';
import '../../providers/measurement_draft.dart';
import '../../services/order_actions.dart';
import '../../theme/swaya_light_theme.dart';

/// Persona Saved — Figma frame 21. Success confirmation after saving a persona.
class PersonaSavedScreen extends StatelessWidget {
  const PersonaSavedScreen({
    super.key,
    this.personaName,
    this.gender = 'female',
  });

  final String? personaName;
  final String gender;

  Future<void> _orderGarment(BuildContext context) async {
    final garment = await showGarmentPicker(context, gender);
    if (garment == null || !context.mounted) return;
    context.read<MeasurementDraft>().reset();
    if (!context.mounted) return;
    await placeGarmentOrder(context,
        personaName: personaName, garment: garment.label);
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: buildSwayaLightTheme(),
      child: Scaffold(
        backgroundColor: SwayaLight.canvas,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: [
                const Spacer(flex: 2),
                Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(
                    color: SwayaLight.success.withValues(alpha: 0.12),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.check_rounded,
                      color: SwayaLight.success, size: 48),
                ),
                const SizedBox(height: 28),
                Text(
                  'Persona created successfully',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: SwayaLight.inkPrimary),
                ),
                const SizedBox(height: 10),
                Text(
                  personaName != null
                      ? 'Your measurements are saved under "$personaName".'
                      : 'Your measurements have been saved.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 14),
                ),
                const Spacer(flex: 3),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: () => _orderGarment(context),
                    icon: const Icon(Icons.shopping_bag_outlined, size: 20),
                    label: const Text('Order garment'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () => context.push('/avatar', extra: {
                      'gender': gender,
                      'measurements':
                          context.read<MeasurementDraft>().measurements.copy(),
                    }),
                    icon: const Icon(Icons.view_in_ar_outlined, size: 18),
                    label: const Text('View on avatar'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () {
                      context.read<MeasurementDraft>().reset();
                      context.go('/home-v2');
                    },
                    child: const Text('Go to Home'),
                  ),
                ),
                const SizedBox(height: 4),
                TextButton(
                  onPressed: () {
                    context.read<MeasurementDraft>().reset();
                    context.go('/measure');
                  },
                  child: const Text('Add another'),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
