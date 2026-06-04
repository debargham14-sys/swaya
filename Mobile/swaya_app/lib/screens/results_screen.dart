import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../models/ground_truth.dart';
import '../models/scan_record.dart';
import '../providers/capture_session.dart';
import '../services/measure_api.dart';
import '../services/scan_api.dart';
import '../theme/swaya_theme.dart';
import '../utils/bundle_launcher.dart';
import '../widgets/measurement_row.dart';
import '../widgets/swaya_scaffold.dart';

class ResultsScreen extends StatefulWidget {
  const ResultsScreen({super.key});

  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  static const _order = ['bust', 'underbust', 'waist', 'hip'];

  final _bustCtrl = TextEditingController();
  final _underbustCtrl = TextEditingController();
  final _waistCtrl = TextEditingController();
  final _hipCtrl = TextEditingController();
  bool _savingGt = false;

  @override
  void dispose() {
    _bustCtrl.dispose();
    _underbustCtrl.dispose();
    _waistCtrl.dispose();
    _hipCtrl.dispose();
    super.dispose();
  }

  void _loadGroundTruthFromScan(ScanRecord? scan) {
    if (scan == null) return;
    void set(TextEditingController c, String key) {
      final v = scan.groundTruthCm[key];
      c.text = v != null ? _formatNum(v) : '';
    }

    set(_bustCtrl, 'bust');
    set(_underbustCtrl, 'underbust');
    set(_waistCtrl, 'waist');
    set(_hipCtrl, 'hip');
  }

  static String _formatNum(double v) {
    return v == v.roundToDouble() ? v.round().toString() : v.toStringAsFixed(1);
  }

  double? _parse(TextEditingController c) {
    final v = double.tryParse(c.text.trim());
    if (v == null || v <= 0) return null;
    return v;
  }

  Future<void> _saveGroundTruth(ScanRecord scan) async {
    final bust = _parse(_bustCtrl);
    final underbust = _parse(_underbustCtrl);
    final waist = _parse(_waistCtrl);
    final hip = _parse(_hipCtrl);
    if (bust == null && underbust == null && waist == null && hip == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter at least one tape measurement (cm)')),
      );
      return;
    }
    setState(() => _savingGt = true);
    try {
      final updated = await ScanApi().saveGroundTruth(
        scanId: scan.scanId,
        bustCm: bust,
        underbustCm: underbust,
        waistCm: waist,
        hipCm: hip,
      );
      if (!mounted) return;
      context.read<CaptureSession>().setScan(updated);
      final calibrated = updated.result.isCalibrated;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            calibrated
                ? 'Saved — estimates updated; future scans use tape calibration'
                : 'Ground truth saved (add more levels to improve calibration)',
          ),
        ),
      );
    } on MeasureApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _savingGt = false);
    }
  }

  static String _label(String key) {
    if (key.isEmpty) return key;
    return key[0].toUpperCase() + key.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<CaptureSession>();
    final result = session.lastResult;
    final scan = session.lastScan;

    if (scan != null && _bustCtrl.text.isEmpty && scan.groundTruthCm.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _loadGroundTruthFromScan(scan);
      });
    }

    if (result == null) {
      return SwayaScaffold(
        body: Center(
          child: ElevatedButton(
            onPressed: () => context.go('/home'),
            child: const Text('Start over'),
          ),
        ),
      );
    }

    return SwayaScaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Your measurements',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
              if (result.confidence != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: SwayaColors.success.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    result.confidenceLabel(),
                    style: const TextStyle(
                      color: SwayaColors.success,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              if (result.bmi != null)
                _StatChip(label: 'BMI', value: result.bmi!.toStringAsFixed(1)),
              if (result.heightCm != null) ...[
                const SizedBox(width: 12),
                _StatChip(
                  label: 'Height',
                  value: '${result.heightCm!.toStringAsFixed(0)} cm',
                ),
              ],
            ],
          ),
          if (result.isCalibrated) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: SwayaColors.accent.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: SwayaColors.accent.withValues(alpha: 0.35)),
              ),
              child: Text(
                result.calibrationTrainingScans != null && result.calibrationTrainingScans! > 0
                    ? 'Calibrated from ${result.calibrationTrainingScans} prior tape '
                        'measurement${result.calibrationTrainingScans == 1 ? '' : 's'}. '
                        'Save tape values below to keep improving.'
                    : 'Calibrated using saved tape measurements. Save tape values below to keep improving.',
                style: const TextStyle(color: SwayaColors.accent, fontSize: 13),
              ),
            ),
          ],
          if (result.confidence != null && result.confidence! < 0.5) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: SwayaColors.warning.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: SwayaColors.warning.withValues(alpha: 0.4)),
              ),
              child: const Text(
                'For best accuracy: full body in frame, arms at sides, fitted clothing, '
                'plain background, good lighting.',
                style: TextStyle(color: SwayaColors.warning, fontSize: 13),
              ),
            ),
          ],
          Expanded(
            child: ListView(
              children: [
                for (final key in _order)
                  if (result.girthsCm[key] != null) ...[
                    MeasurementRow(
                      label: _label(key),
                      cm: result.girthsCm[key]!,
                      inches: result.girthsIn[key],
                    ),
                    const SizedBox(height: 8),
                  ],
                if (scan != null) ...[
                  const SizedBox(height: 16),
                  _GroundTruthCard(
                    bustCtrl: _bustCtrl,
                    underbustCtrl: _underbustCtrl,
                    waistCtrl: _waistCtrl,
                    hipCtrl: _hipCtrl,
                    saving: _savingGt,
                    comparison: scan.groundTruthComparison,
                    onSave: () => _saveGroundTruth(scan),
                  ),
                ],
                if (scan != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    'Scan ID: ${scan.scanId}',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: SwayaColors.inkTertiary,
                        ),
                  ),
                ],
                const SizedBox(height: 80),
              ],
            ),
          ),
          if (scan != null)
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () async {
                  final ok = await openBetaBundleDownload(scan);
                  if (!context.mounted) return;
                  if (!ok) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Could not open download link')),
                    );
                  }
                },
                child: const Text('Download beta bundle (ZIP)'),
              ),
            ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () => context.push('/scan/assistant'),
              child: const Text('Ask fit assistant'),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () {
                session.resetForNewScan();
                context.go('/scan/height');
              },
              child: const Text('New scan'),
            ),
          ),
        ],
      ),
    );
  }
}

class _GroundTruthCard extends StatelessWidget {
  const _GroundTruthCard({
    required this.bustCtrl,
    required this.underbustCtrl,
    required this.waistCtrl,
    required this.hipCtrl,
    required this.saving,
    required this.comparison,
    required this.onSave,
  });

  final TextEditingController bustCtrl;
  final TextEditingController underbustCtrl;
  final TextEditingController waistCtrl;
  final TextEditingController hipCtrl;
  final bool saving;
  final Map<String, GroundTruthComparison> comparison;
  final VoidCallback onSave;

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
            'Ground truth (tape measure)',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            'Enter real tape measurements in cm. Each save refits calibration so this scan '
            'and the next ones are closer to your tape.',
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
                  '${e.key}: tape ${c.tapeCm.toStringAsFixed(1)} cm, est ${c.predictedCm.toStringAsFixed(1)} cm ($sign${err.toStringAsFixed(1)} cm)',
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
    return Row(
      children: [
        SizedBox(
          width: 88,
          child: Text(
            label,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
        Expanded(
          child: TextField(
            controller: controller,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
            ],
            decoration: const InputDecoration(
              hintText: 'cm',
              isDense: true,
            ),
          ),
        ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: SwayaColors.elevated,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: SwayaColors.borderSubtle),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}
