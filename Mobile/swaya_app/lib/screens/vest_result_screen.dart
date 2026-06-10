import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../models/vest_measurement.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

/// Shows a vest measurement result (passed via GoRouter `extra`).
class VestResultScreen extends StatelessWidget {
  const VestResultScreen({super.key, required this.result});

  final VestScanResult result;

  @override
  Widget build(BuildContext context) {
    final m = result.measurement;
    final bands = ['bust', 'waist', 'hip'];

    return SwayaScaffold(
      title: 'Vest result (beta)',
      leading: BackButton(onPressed: () => context.go('/home')),
      body: ListView(
        children: [
          Row(
            children: [
              _Pill(
                label: result.stored ? 'Saved' : 'Not stored',
                color: result.stored ? SwayaColors.success : SwayaColors.warning,
                icon: result.stored ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
              ),
              const SizedBox(width: 8),
              _Pill(
                label: 'Confidence ${(m.confidence * 100).round()}%',
                color: m.confidence >= 0.7 ? SwayaColors.success : SwayaColors.warning,
                icon: Icons.speed_outlined,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Scan ${result.scanId}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkTertiary),
          ),
          const SizedBox(height: 20),
          if (!m.hasGirths)
            _Empty(warnings: m.warnings)
          else ...[
            for (final b in bands)
              if (m.girthsIn[b] != null)
                _GirthRow(
                  label: b[0].toUpperCase() + b.substring(1),
                  inches: m.girthsIn[b]!,
                  cm: m.girthsCm[b],
                  groundTruth: result.groundTruthIn?['${b}_in'],
                ),
            const SizedBox(height: 16),
            Text(
              'Markers: ${m.markersFound.join(', ')}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkTertiary),
            ),
          ],
          if (m.warnings.isNotEmpty && m.hasGirths) ...[
            const SizedBox(height: 12),
            _Warnings(warnings: m.warnings),
          ],
          const SizedBox(height: 28),
          ElevatedButton(
            onPressed: () => context.go('/vest'),
            child: const Text('New vest scan'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: () => context.go('/home'),
            child: const Text('Done'),
          ),
        ],
      ),
    );
  }
}

class _GirthRow extends StatelessWidget {
  const _GirthRow({required this.label, required this.inches, this.cm, this.groundTruth});

  final String label;
  final double inches;
  final double? cm;
  final double? groundTruth;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: SwayaColors.elevated,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: SwayaColors.borderSubtle),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: Theme.of(context).textTheme.titleMedium),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${inches.toStringAsFixed(1)} in',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: SwayaColors.accentHighlight,
                    ),
              ),
              if (cm != null)
                Text(
                  '${cm!.toStringAsFixed(1)} cm'
                  '${groundTruth != null ? '  ·  tape ${groundTruth!.toStringAsFixed(1)} in' : ''}',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkSecondary),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({required this.warnings});
  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.search_off_outlined, color: SwayaColors.warning, size: 40),
        const SizedBox(height: 8),
        Text('No measurement', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          'The vest markers (front bust/waist/hip) were not all found. Retake square-on '
          'with the markers flat and fully in frame.',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: SwayaColors.inkSecondary),
        ),
        const SizedBox(height: 12),
        _Warnings(warnings: warnings),
      ],
    );
  }
}

class _Warnings extends StatelessWidget {
  const _Warnings({required this.warnings});
  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    if (warnings.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: warnings
          .map((w) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('• ${w.replaceAll('_', ' ')}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.warning)),
              ))
          .toList(),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.color, required this.icon});
  final String label;
  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(label, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: color)),
        ],
      ),
    );
  }
}
