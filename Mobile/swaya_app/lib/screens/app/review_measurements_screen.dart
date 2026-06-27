import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../models/blouse_measurements.dart';
import '../../providers/measurement_draft.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';
import 'save_measurements_sheet.dart';

/// Review Measurements — Figma frame 17. Confirm/edit each value before saving.
class ReviewMeasurementsScreen extends StatelessWidget {
  const ReviewMeasurementsScreen({super.key});

  Future<void> _edit(BuildContext context, MeasurementDraft draft,
      MeasurementField field) async {
    final controller =
        TextEditingController(text: draft.measurements[field.key]?.toString() ?? '');
    final value = await showDialog<double?>(
      context: context,
      builder: (ctx) => Theme(
        data: Theme.of(context),
        child: AlertDialog(
          backgroundColor: SwayaLight.canvas,
          title: Text(field.label),
          content: TextField(
            controller: controller,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[\d.]'))],
            decoration: const InputDecoration(suffixText: 'cm'),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            TextButton(
              onPressed: () =>
                  Navigator.pop(ctx, double.tryParse(controller.text)),
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (value != null) draft.setField(field.key, value);
  }

  @override
  Widget build(BuildContext context) {
    final draft = context.watch<MeasurementDraft>();
    final m = draft.measurements;

    return LightScaffold(
      title: 'Review Measurements',
      showBack: true,
      navIndex: 1,
      bottomBar: SizedBox(
        width: double.infinity,
        child: ElevatedButton(
          onPressed: () => showSaveMeasurementsSheet(context),
          child: const Text('Save Measurements'),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: SwayaLight.accent.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: const [
                Icon(Icons.fact_check_outlined,
                    color: SwayaLight.accent, size: 20),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Review carefully. Tap any value to edit before saving.',
                    style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          const SectionTitle('Body Measurements'),
          const SizedBox(height: 12),
          for (final field in kBlouseFields)
            _ReviewRow(
              label: field.label,
              value: m[field.key],
              onEdit: () => _edit(context, draft, field),
            ),
        ],
      ),
    );
  }
}

class _ReviewRow extends StatelessWidget {
  const _ReviewRow({
    required this.label,
    required this.value,
    required this.onEdit,
  });

  final String label;
  final double? value;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: onEdit,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: SwayaLight.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: SwayaLight.border),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(label,
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary, fontSize: 14)),
              ),
              Text(
                value != null ? '${value!.toStringAsFixed(1)} cm' : '—',
                style: TextStyle(
                    color: value != null
                        ? SwayaLight.inkPrimary
                        : SwayaLight.inkTertiary,
                    fontWeight: FontWeight.w600),
              ),
              const SizedBox(width: 8),
              const Icon(Icons.edit_outlined,
                  size: 16, color: SwayaLight.inkTertiary),
            ],
          ),
        ),
      ),
    );
  }
}
