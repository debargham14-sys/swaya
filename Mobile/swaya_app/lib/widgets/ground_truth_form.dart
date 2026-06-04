import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/ground_truth.dart';
import '../models/scan_record.dart';
import '../theme/swaya_theme.dart';
import '../utils/scan_display.dart';

/// Tape ground-truth fields (cm) with save action.
class GroundTruthFormCard extends StatelessWidget {
  const GroundTruthFormCard({
    super.key,
    required this.bustCtrl,
    required this.underbustCtrl,
    required this.waistCtrl,
    required this.hipCtrl,
    required this.saving,
    required this.comparison,
    required this.onSave,
    this.title = 'Ground truth (tape measure)',
  });

  final TextEditingController bustCtrl;
  final TextEditingController underbustCtrl;
  final TextEditingController waistCtrl;
  final TextEditingController hipCtrl;
  final bool saving;
  final Map<String, GroundTruthComparison> comparison;
  final VoidCallback onSave;
  final String title;

  static void loadFromScan(ScanRecord scan, {
    required TextEditingController bustCtrl,
    required TextEditingController underbustCtrl,
    required TextEditingController waistCtrl,
    required TextEditingController hipCtrl,
  }) {
    void set(TextEditingController c, String key) {
      final v = scan.groundTruthCm[key];
      c.text = v != null ? formatGroundTruthNum(v) : '';
    }

    set(bustCtrl, 'bust');
    set(underbustCtrl, 'underbust');
    set(waistCtrl, 'waist');
    set(hipCtrl, 'hip');
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SwayaColors.elevated,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: SwayaColors.accent.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            'Enter or edit tape measurements in cm. Saving updates this scan and refits calibration.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          const SizedBox(height: 16),
          _GtField(label: 'Bust', controller: bustCtrl),
          const SizedBox(height: 10),
          _GtField(label: 'Underbust', controller: underbustCtrl),
          const SizedBox(height: 10),
          _GtField(label: 'Waist', controller: waistCtrl),
          const SizedBox(height: 10),
          _GtField(label: 'Hip', controller: hipCtrl),
          if (comparison.isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(
              'Error vs estimate',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 6),
            ...comparison.entries.map((e) {
              final c = e.value;
              final err = c.errorCm;
              final sign = err >= 0 ? '+' : '';
              return Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  '${levelLabel(e.key)}: tape ${c.tapeCm.toStringAsFixed(1)} cm, '
                  'est ${c.predictedCm.toStringAsFixed(1)} cm ($sign${err.toStringAsFixed(1)} cm)',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: SwayaColors.inkSecondary,
                      ),
                ),
              );
            }),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: saving ? null : onSave,
              child: saving
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Save ground truth'),
            ),
          ),
        ],
      ),
    );
  }
}

class _GtField extends StatelessWidget {
  const _GtField({required this.label, required this.controller});

  final String label;
  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      inputFormatters: [
        FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
      ],
      decoration: InputDecoration(
        labelText: '$label (cm)',
        isDense: true,
      ),
    );
  }
}
