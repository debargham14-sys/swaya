import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../models/captured_photo.dart';
import '../../providers/measurement_draft.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Capture body images — Figma frames 15–16. Upload front / side / back photos,
/// then analyze. (Automated photo→measurement extraction is wired to the draft;
/// the review screen lets the user confirm/adjust values.)
class CaptureImagesScreen extends StatefulWidget {
  const CaptureImagesScreen({super.key});

  @override
  State<CaptureImagesScreen> createState() => _CaptureImagesScreenState();
}

class _CaptureImagesScreenState extends State<CaptureImagesScreen> {
  final _picker = ImagePicker();
  bool _analyzing = false;

  static const _views = [
    (key: 'front', label: 'Front Image'),
    (key: 'side', label: 'Side Image'),
    (key: 'back', label: 'Back Image'),
  ];

  Future<void> _pick(MeasurementDraft draft, String view) async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      backgroundColor: SwayaLight.canvas,
      // The sheet is rendered by the root navigator, OUTSIDE LightScaffold's
      // light-theme wrap, so it would otherwise inherit the global dark theme
      // (near-white text/icons on this white sheet = invisible). Re-apply light.
      builder: (ctx) => Theme(
        data: buildSwayaLightTheme(),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.photo_camera_outlined,
                    color: SwayaLight.inkPrimary),
                title: const Text('Take photo',
                    style: TextStyle(color: SwayaLight.inkPrimary)),
                onTap: () => Navigator.pop(ctx, ImageSource.camera),
              ),
              ListTile(
                leading: const Icon(Icons.photo_library_outlined,
                    color: SwayaLight.inkPrimary),
                title: const Text('Choose from gallery',
                    style: TextStyle(color: SwayaLight.inkPrimary)),
                onTap: () => Navigator.pop(ctx, ImageSource.gallery),
              ),
            ],
          ),
        ),
      ),
    );
    if (source == null) return;
    final file = await _picker.pickImage(source: source, imageQuality: 90);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    draft.setPhoto(view, CapturedPhoto(bytes: bytes, filename: file.name));
  }

  Future<void> _analyze(MeasurementDraft draft) async {
    setState(() => _analyzing = true);
    // Hook for backend photo analysis; for now move to review where the user
    // confirms/edits the measurement values.
    await Future<void>.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    setState(() => _analyzing = false);
    context.push('/measure/review');
  }

  @override
  Widget build(BuildContext context) {
    final draft = context.watch<MeasurementDraft>();
    final count = draft.photoCount;

    return LightScaffold(
      title: 'Measurements',
      showBack: true,
      navIndex: 3,
      bottomBar: SizedBox(
        width: double.infinity,
        child: ElevatedButton(
          onPressed: draft.hasAllPhotos && !_analyzing ? () => _analyze(draft) : null,
          child: _analyzing
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: SwayaLight.onCta))
              : const Text('Analyze Measurements'),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const Text('Capture body images',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Upload all 3 required angles before analysis.',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 14)),
          const SizedBox(height: 16),
          Row(
            children: [
              _Pill('$count of 3 uploaded',
                  active: count == 3),
              const SizedBox(width: 8),
              const _Pill('Good lighting required'),
            ],
          ),
          const SizedBox(height: 16),
          for (final v in _views)
            _UploadRow(
              label: v.label,
              photo: draft.photo(v.key),
              onTap: () => _pick(draft, v.key),
            ),
          const SizedBox(height: 8),
          AppCard(
            color: SwayaLight.surfaceAlt,
            child: Row(
              children: const [
                Icon(Icons.lightbulb_outline,
                    size: 18, color: SwayaLight.inkSecondary),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Capture tip: stand straight, keep arms slightly away, and fit your full body in frame.',
                    style: TextStyle(
                        color: SwayaLight.inkSecondary, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill(this.text, {this.active = false});
  final String text;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: active
            ? SwayaLight.success.withValues(alpha: 0.12)
            : SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (active) ...[
            const Icon(Icons.check_circle,
                size: 14, color: SwayaLight.success),
            const SizedBox(width: 4),
          ],
          Text(text,
              style: TextStyle(
                  color: active ? SwayaLight.success : SwayaLight.inkSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _UploadRow extends StatelessWidget {
  const _UploadRow({
    required this.label,
    required this.photo,
    required this.onTap,
  });

  final String label;
  final CapturedPhoto? photo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final done = photo != null;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: AppCard(
        onTap: onTap,
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox(
                width: 48,
                height: 48,
                child: done
                    ? Image.memory(photo!.bytes, fit: BoxFit.cover)
                    : Container(
                        color: SwayaLight.surfaceAlt,
                        child: const Icon(Icons.image_outlined,
                            color: SwayaLight.inkTertiary),
                      ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                      style: const TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(done ? 'Uploaded' : 'Tap to upload',
                      style: TextStyle(
                          color:
                              done ? SwayaLight.success : SwayaLight.inkTertiary,
                          fontSize: 12)),
                ],
              ),
            ),
            Icon(
              done ? Icons.check_circle : Icons.add_circle_outline,
              color: done ? SwayaLight.success : SwayaLight.inkTertiary,
            ),
          ],
        ),
      ),
    );
  }
}
