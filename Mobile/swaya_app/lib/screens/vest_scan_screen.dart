import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../models/captured_photo.dart';
import '../services/measure_api.dart' show MeasureApiException;
import '../services/vest_api.dart';
import '../theme/swaya_theme.dart';
import '../widgets/captured_photo_image.dart';
import '../widgets/swaya_scaffold.dart';

/// Beta ChArUco-vest data-collection flow: capture front (+ optional sides),
/// optional tape ground truth, submit to POST /v1/vest.
class VestScanScreen extends StatefulWidget {
  const VestScanScreen({super.key});

  @override
  State<VestScanScreen> createState() => _VestScanScreenState();
}

class _VestScanScreenState extends State<VestScanScreen> {
  final _picker = ImagePicker();
  final _vestApi = VestApi();

  CapturedPhoto? _front;
  CapturedPhoto? _sideLeft;
  CapturedPhoto? _sideRight;

  final _collector = TextEditingController();
  final _subject = TextEditingController();
  final _bust = TextEditingController();
  final _waist = TextEditingController();
  final _hip = TextEditingController();
  final _notes = TextEditingController();
  bool _consent = false;
  bool _submitting = false;

  @override
  void dispose() {
    for (final c in [_collector, _subject, _bust, _waist, _hip, _notes]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pick(String slot, ImageSource source) async {
    try {
      final picked = await _picker.pickImage(
        source: source,
        preferredCameraDevice: CameraDevice.rear,
        imageQuality: 95,
      );
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      if (bytes.length < 8000) {
        _snack('Photo looks too small — retake with better lighting');
        return;
      }
      final photo = CapturedPhoto(
        bytes: bytes,
        filename: picked.name.isNotEmpty ? picked.name : '$slot.jpg',
      );
      setState(() {
        if (slot == 'front') _front = photo;
        if (slot == 'side_left') _sideLeft = photo;
        if (slot == 'side_right') _sideRight = photo;
      });
    } catch (e) {
      _snack('Could not load photo: $e');
    }
  }

  void _snack(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  double? _num(TextEditingController c) {
    final t = c.text.trim();
    if (t.isEmpty) return null;
    return double.tryParse(t);
  }

  Future<void> _submit() async {
    if (_front == null) {
      _snack('A front photo is required');
      return;
    }
    setState(() => _submitting = true);
    try {
      final result = await _vestApi.createVestScan(
        front: _front!,
        sideLeft: _sideLeft,
        sideRight: _sideRight,
        subjectLabel: _subject.text.trim(),
        collectorId: _collector.text.trim(),
        consentGiven: _consent,
        notes: _notes.text.trim(),
        bustIn: _num(_bust),
        waistIn: _num(_waist),
        hipIn: _num(_hip),
      );
      if (!mounted) return;
      context.push('/vest/result', extra: result);
    } on MeasureApiException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Vest scan failed: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      title: 'Vest scan (beta)',
      leading: BackButton(onPressed: () => context.go('/home')),
      body: ListView(
        children: [
          const _BetaNote(),
          const SizedBox(height: 16),
          Text('Photos', style: _label(context)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: _PhotoSlot(label: 'Front *', photo: _front, onPick: (s) => _pick('front', s))),
              const SizedBox(width: 8),
              Expanded(child: _PhotoSlot(label: 'Side L', photo: _sideLeft, onPick: (s) => _pick('side_left', s))),
              const SizedBox(width: 8),
              Expanded(child: _PhotoSlot(label: 'Side R', photo: _sideRight, onPick: (s) => _pick('side_right', s))),
            ],
          ),
          const SizedBox(height: 24),
          Text('Collection', style: _label(context)),
          const SizedBox(height: 8),
          _text(_collector, 'Tailor / collector name'),
          const SizedBox(height: 10),
          _text(_subject, 'Subject ID or name'),
          const SizedBox(height: 24),
          Text('Tape measurements (inches, optional)', style: _label(context)),
          const SizedBox(height: 4),
          Text(
            'Enter what you measured by tape — used to validate and improve the estimate.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkSecondary),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: _numField(_bust, 'Bust')),
              const SizedBox(width: 8),
              Expanded(child: _numField(_waist, 'Waist')),
              const SizedBox(width: 8),
              Expanded(child: _numField(_hip, 'Hip')),
            ],
          ),
          const SizedBox(height: 16),
          _text(_notes, 'Notes', maxLines: 2),
          const SizedBox(height: 8),
          CheckboxListTile(
            value: _consent,
            onChanged: (v) => setState(() => _consent = v ?? false),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            title: Text(
              'Subject consents to photo storage',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _submitting || _front == null ? null : _submit,
            child: _submitting
                ? const SizedBox(
                    height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Measure & save'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  TextStyle? _label(BuildContext c) =>
      Theme.of(c).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600);

  Widget _text(TextEditingController c, String hint, {int maxLines = 1}) =>
      TextField(controller: c, maxLines: maxLines, decoration: InputDecoration(hintText: hint));

  Widget _numField(TextEditingController c, String hint) => TextField(
        controller: c,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
        decoration: InputDecoration(hintText: hint),
      );
}

class _PhotoSlot extends StatelessWidget {
  const _PhotoSlot({required this.label, required this.photo, required this.onPick});

  final String label;
  final CapturedPhoto? photo;
  final void Function(ImageSource) onPick;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AspectRatio(
          aspectRatio: 3 / 4,
          child: InkWell(
            onTap: () => _sheet(context),
            borderRadius: BorderRadius.circular(10),
            child: Container(
              decoration: BoxDecoration(
                color: SwayaColors.elevated,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: SwayaColors.borderSubtle),
              ),
              clipBehavior: Clip.antiAlias,
              child: photo != null
                  ? CapturedPhotoImage(photo: photo!, fit: BoxFit.cover)
                  : const Center(
                      child: Icon(Icons.add_a_photo_outlined, color: SwayaColors.inkTertiary)),
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(label, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkSecondary)),
      ],
    );
  }

  void _sheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: SwayaColors.elevated,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_outlined),
              title: const Text('Camera'),
              onTap: () {
                Navigator.pop(ctx);
                onPick(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Gallery'),
              onTap: () {
                Navigator.pop(ctx);
                onPick(ImageSource.gallery);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _BetaNote extends StatelessWidget {
  const _BetaNote();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: SwayaColors.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: SwayaColors.warning.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.science_outlined, color: SwayaColors.warning, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Beta: front bust/waist/hip from the ChArUco vest. Capture a square-on '
              'front photo with the vest markers flat and fully visible.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: SwayaColors.inkSecondary),
            ),
          ),
        ],
      ),
    );
  }
}
