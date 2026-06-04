import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../models/scan_record.dart';
import '../providers/capture_session.dart';
import '../services/measure_api.dart';
import '../services/scan_api.dart';
import '../theme/swaya_theme.dart';
import '../utils/bundle_launcher.dart';
import '../utils/scan_display.dart';
import '../widgets/ground_truth_form.dart';
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
    GroundTruthFormCard.loadFromScan(
      scan,
      bustCtrl: _bustCtrl,
      underbustCtrl: _underbustCtrl,
      waistCtrl: _waistCtrl,
      hipCtrl: _hipCtrl,
    );
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
          if (!result.measurementsReliable || !result.hasGirths) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: SwayaColors.warning.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: SwayaColors.warning.withValues(alpha: 0.5)),
              ),
              child: const Text(
                'Could not measure reliably (pose or clothing issue). '
                'Retake in fitted clothing with arms slightly out, or enter tape measurements below.',
                style: TextStyle(color: SwayaColors.warning, fontSize: 13),
              ),
            ),
          ],
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
                      label: levelLabel(key),
                      cm: result.girthsCm[key]!,
                      inches: result.girthsIn[key],
                    ),
                    const SizedBox(height: 8),
                  ],
                if (scan != null) ...[
                  const SizedBox(height: 16),
                  GroundTruthFormCard(
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
