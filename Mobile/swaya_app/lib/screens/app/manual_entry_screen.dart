import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/blouse_measurements.dart';
import '../../providers/measurement_draft.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Manual Entry — Figma frames 13–14. Enter the blouse measurements with a
/// progress ring, per-field cm inputs, validation, and Continue to Design.
class ManualEntryScreen extends StatefulWidget {
  const ManualEntryScreen({super.key});

  @override
  State<ManualEntryScreen> createState() => _ManualEntryScreenState();
}

class _ManualEntryScreenState extends State<ManualEntryScreen> {
  bool _showErrors = false;

  void _continue(MeasurementDraft draft) {
    if (!draft.measurements.isComplete) {
      setState(() => _showErrors = true);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(
            content: Text('Fill all required measurements to continue.')));
      return;
    }
    context.push('/measure/review');
  }

  @override
  Widget build(BuildContext context) {
    final draft = context.watch<MeasurementDraft>();
    final m = draft.measurements;

    return LightScaffold(
      title: 'Manual Entry',
      showBack: true,
      navIndex: 1,
      bottomBar: SizedBox(
        width: double.infinity,
        child: ElevatedButton(
          onPressed: () => _continue(draft),
          child: const Text('Continue to Design'),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const Text('Enter Measurements',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Fill all required values in centimeters.',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 14)),
          const SizedBox(height: 16),
          if (_showErrors && !m.isComplete) _ErrorBanner(missing: m.missingRequired.length),
          _ProgressCard(filled: m.requiredFilledCount, total: m.requiredCount),
          const SizedBox(height: 20),
          const SectionTitle(
            'Body Measurements',
            subtitle: 'Use a soft measuring tape. Keep it level, not tight.',
          ),
          const SizedBox(height: 12),
          for (final field in kBlouseFields)
            _MeasurementRow(
              // Stable key: keyed reconciliation keeps each row's State (and its
              // focused TextField) alive when the error banner is inserted or
              // removed above — without it, focus and the keyboard drop mid-type.
              key: ValueKey(field.key),
              field: field,
              value: m[field.key],
              showError: _showErrors && field.required && m[field.key] == null,
              onChanged: (v) => draft.setField(field.key, v),
            ),
        ],
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.missing});
  final int missing;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SwayaLight.error.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: SwayaLight.error.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: SwayaLight.error, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              "$missing measurement${missing == 1 ? '' : 's'} still required before you can submit.",
              style: const TextStyle(color: SwayaLight.error, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  const _ProgressCard({required this.filled, required this.total});
  final int filled;
  final int total;

  @override
  Widget build(BuildContext context) {
    final pct = total == 0 ? 0.0 : filled / total;
    return AppCard(
      child: Row(
        children: [
          SizedBox(
            width: 48,
            height: 48,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: pct,
                  strokeWidth: 5,
                  backgroundColor: SwayaLight.surfaceAlt,
                  valueColor:
                      const AlwaysStoppedAnimation(SwayaLight.accent),
                ),
                Text('${(pct * 100).round()}%',
                    style: const TextStyle(
                        fontSize: 11, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Measurement Progress',
                  style: TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              Text('$filled of $total required completed',
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 13)),
            ],
          ),
        ],
      ),
    );
  }
}

class _MeasurementRow extends StatefulWidget {
  const _MeasurementRow({
    super.key,
    required this.field,
    required this.value,
    required this.onChanged,
    required this.showError,
  });

  final MeasurementField field;
  final double? value;
  final bool showError;
  final ValueChanged<double?> onChanged;

  @override
  State<_MeasurementRow> createState() => _MeasurementRowState();
}

class _MeasurementRowState extends State<_MeasurementRow> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.value?.toString() ?? '');

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Expanded(
            child: Text.rich(
              TextSpan(
                text: widget.field.label,
                style: const TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500),
                children: widget.field.required
                    ? const [
                        TextSpan(
                            text: ' *',
                            style: TextStyle(color: SwayaLight.error))
                      ]
                    : null,
              ),
            ),
          ),
          SizedBox(
            width: 120,
            child: TextField(
              controller: _controller,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              textAlign: TextAlign.center,
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
              ],
              decoration: InputDecoration(
                hintText: 'cm',
                isDense: true,
                enabledBorder: widget.showError
                    ? OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: SwayaLight.error),
                      )
                    : null,
                suffixText: 'cm',
                suffixStyle: const TextStyle(
                    color: SwayaLight.inkTertiary, fontSize: 12),
              ),
              onChanged: (v) => widget.onChanged(double.tryParse(v)),
            ),
          ),
        ],
      ),
    );
  }
}
