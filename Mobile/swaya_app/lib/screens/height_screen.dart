import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../providers/capture_session.dart';
import '../theme/swaya_theme.dart';
import '../widgets/swaya_scaffold.dart';

class HeightScreen extends StatefulWidget {
  const HeightScreen({super.key});

  @override
  State<HeightScreen> createState() => _HeightScreenState();
}

class _HeightScreenState extends State<HeightScreen> {
  final _heightController = TextEditingController();
  final _weightController = TextEditingController();
  final _subjectController = TextEditingController();
  final _collectorController = TextEditingController();
  bool _consent = false;

  @override
  void dispose() {
    _heightController.dispose();
    _weightController.dispose();
    _subjectController.dispose();
    _collectorController.dispose();
    super.dispose();
  }

  static const _minHeightCm = 80.0;
  static const _maxHeightCm = 250.0;
  static const _maxWeightKg = 300.0;

  void _continue() {
    final session = context.read<CaptureSession>();
    final height = double.tryParse(_heightController.text.trim());
    if (height == null || height <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid height in cm')),
      );
      return;
    }
    if (height < _minHeightCm || height > _maxHeightCm) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Height must be between $_minHeightCm and $_maxHeightCm cm')),
      );
      return;
    }
    final weight = double.tryParse(_weightController.text.trim());
    if (weight != null && (weight <= 0 || weight > _maxWeightKg)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Weight must be between 1 and $_maxWeightKg kg, or leave blank')),
      );
      return;
    }
    if (!_consent) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Consent is required to continue')),
      );
      return;
    }
    session.setHeight(height);
    session.setWeight(weight);
    session.setSubjectLabel(_subjectController.text.trim());
    session.setCollectorId(_collectorController.text.trim());
    session.setConsent(_consent);
    context.go('/scan/guide');
  }

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      leading: IconButton(
        icon: const Icon(Icons.close),
        onPressed: () => context.go('/home'),
      ),
      title: 'New scan',
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'About you',
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),
            const SizedBox(height: 8),
            Text(
              'Height is required. Photos and measurements are saved to the cloud database.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: SwayaColors.inkSecondary,
                  ),
            ),
            const SizedBox(height: 24),
            Text(
              'Participant name or ID',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _subjectController,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(hintText: 'e.g. Priya S. or P-042'),
            ),
            const SizedBox(height: 16),
            Text(
              'Collector (your name)',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _collectorController,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(hintText: 'Who is running this scan'),
            ),
            const SizedBox(height: 20),
            Text(
              'Height',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _heightController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
                    ],
                    decoration: const InputDecoration(hintText: '170'),
                  ),
                ),
                const SizedBox(width: 8),
                Chip(
                  label: const Text('cm'),
                  backgroundColor: SwayaColors.accent.withValues(alpha: 0.2),
                  labelStyle: const TextStyle(color: SwayaColors.accentHighlight),
                  side: BorderSide.none,
                ),
              ],
            ),
            const SizedBox(height: 20),
            Text(
              'Weight (optional)',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: SwayaColors.inkTertiary,
                  ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _weightController,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
                    ],
                    decoration: const InputDecoration(hintText: '—'),
                  ),
                ),
                const SizedBox(width: 8),
                const Chip(
                  label: Text('kg'),
                  backgroundColor: SwayaColors.elevated,
                  side: BorderSide(color: SwayaColors.borderSubtle),
                ),
              ],
            ),
            const SizedBox(height: 20),
            CheckboxListTile(
              value: _consent,
              onChanged: (v) => setState(() => _consent = v ?? false),
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              title: Text(
                'I consent to storing my photos and body measurements for research and product development.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: SwayaColors.inkSecondary,
                    ),
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _continue,
                child: const Text('Continue to photos'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
