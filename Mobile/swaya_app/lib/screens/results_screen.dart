import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../providers/capture_session.dart';
import '../theme/swaya_theme.dart';
import '../utils/bundle_launcher.dart';
import '../widgets/measurement_row.dart';
import '../widgets/swaya_scaffold.dart';

class ResultsScreen extends StatelessWidget {
  const ResultsScreen({super.key});

  static const _order = ['bust', 'underbust', 'waist', 'hip'];

  static String _label(String key) {
    if (key.isEmpty) return key;
    return key[0].toUpperCase() + key.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<CaptureSession>();
    final result = session.lastResult;
    final scan = session.lastScan;
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
          // Raw pipeline warnings are developer diagnostics (saved in the bundle),
          // not shown to testers. Surface only a friendly note for low confidence.
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
                'Lower confidence on this scan. For best results, retake with full '
                'body in frame, fitted clothing, and a plain background.',
                style: TextStyle(color: SwayaColors.warning, fontSize: 13),
              ),
            ),
          ],
          if (scan != null) ...[
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
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
                    'Beta bundle ready',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    scan.meshIncluded
                        ? 'ZIP includes body.obj, photos, and measurements.'
                        : 'ZIP includes photos and measurements (no mesh this run).',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: SwayaColors.inkSecondary,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'ID: ${scan.scanId}',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: SwayaColors.inkTertiary,
                        ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
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
              ],
            ),
          ),
          if (scan != null)
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
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
          if (scan != null) const SizedBox(height: 8),
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
                context.go('/scan/guide');
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
