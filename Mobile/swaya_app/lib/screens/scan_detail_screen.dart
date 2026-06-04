import 'package:flutter/material.dart';
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

class ScanDetailScreen extends StatefulWidget {
  const ScanDetailScreen({
    super.key,
    required this.scanId,
    this.initialScan,
  });

  final String scanId;
  final ScanRecord? initialScan;

  @override
  State<ScanDetailScreen> createState() => _ScanDetailScreenState();
}

class _ScanDetailScreenState extends State<ScanDetailScreen> {
  static const _order = ['bust', 'underbust', 'waist', 'hip'];

  ScanRecord? _scan;
  bool _loading = false;
  String? _error;
  bool _savingGt = false;

  final _bustCtrl = TextEditingController();
  final _underbustCtrl = TextEditingController();
  final _waistCtrl = TextEditingController();
  final _hipCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _scan = widget.initialScan;
    if (_scan != null) {
      GroundTruthFormCard.loadFromScan(_scan!, bustCtrl: _bustCtrl, underbustCtrl: _underbustCtrl, waistCtrl: _waistCtrl, hipCtrl: _hipCtrl);
    } else {
      _fetch();
    }
  }

  @override
  void dispose() {
    _bustCtrl.dispose();
    _underbustCtrl.dispose();
    _waistCtrl.dispose();
    _hipCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final scan = await ScanApi().getScan(widget.scanId);
      if (!mounted) return;
      setState(() {
        _scan = scan;
        _loading = false;
      });
      GroundTruthFormCard.loadFromScan(scan, bustCtrl: _bustCtrl, underbustCtrl: _underbustCtrl, waistCtrl: _waistCtrl, hipCtrl: _hipCtrl);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  double? _parse(TextEditingController c) {
    final v = double.tryParse(c.text.trim());
    if (v == null || v <= 0) return null;
    return v;
  }

  Future<void> _saveGroundTruth() async {
    final scan = _scan;
    if (scan == null) return;
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
      setState(() => _scan = updated);
      GroundTruthFormCard.loadFromScan(updated, bustCtrl: _bustCtrl, underbustCtrl: _underbustCtrl, waistCtrl: _waistCtrl, hipCtrl: _hipCtrl);
      final session = context.read<CaptureSession>();
      if (session.lastScan?.scanId == updated.scanId) {
        session.setScan(updated);
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Ground truth saved')),
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
    if (_loading && _scan == null) {
      return const SwayaScaffold(
        title: 'Scan',
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null && _scan == null) {
      return SwayaScaffold(
        title: 'Scan',
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              OutlinedButton(onPressed: _fetch, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final scan = _scan;
    if (scan == null) {
      return const SwayaScaffold(
        title: 'Scan',
        body: Center(child: Text('Scan not found')),
      );
    }

    final result = scan.result;
    final title = scan.displayName;

    return SwayaScaffold(
      title: title,
      body: ListView(
        children: [
          if (scan.createdAt != null)
            Text(
              formatScanDate(scan.createdAt),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
          if (result.heightCm != null) ...[
            const SizedBox(height: 8),
            Text(
              'Height ${result.heightCm!.toStringAsFixed(0)} cm',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: SwayaColors.inkSecondary,
                  ),
            ),
          ],
          if (result.confidence != null) ...[
            const SizedBox(height: 8),
            Text(
              result.confidenceLabel(),
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.success,
                  ),
            ),
          ],
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
                'Measurements were not reliable for this scan. Edit tape values below or retake photos in fitted clothing.',
                style: TextStyle(color: SwayaColors.warning, fontSize: 13),
              ),
            ),
          ],
          const SizedBox(height: 20),
          Text(
            'Measurements',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 12),
          for (final key in _order)
            if (result.girthsCm[key] != null) ...[
              MeasurementRow(
                label: levelLabel(key),
                cm: result.girthsCm[key]!,
                inches: result.girthsIn[key],
              ),
              const SizedBox(height: 8),
            ],
          const SizedBox(height: 16),
          GroundTruthFormCard(
            bustCtrl: _bustCtrl,
            underbustCtrl: _underbustCtrl,
            waistCtrl: _waistCtrl,
            hipCtrl: _hipCtrl,
            saving: _savingGt,
            comparison: scan.groundTruthComparison,
            onSave: _saveGroundTruth,
            title: 'Edit ground truth (tape)',
          ),
          const SizedBox(height: 16),
          OutlinedButton(
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
          const SizedBox(height: 12),
          Text(
            'ID: ${scan.scanId}',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: SwayaColors.inkTertiary,
                ),
          ),
        ],
      ),
    );
  }
}
