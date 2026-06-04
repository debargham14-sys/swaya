import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../models/captured_photo.dart';
import '../models/measurement_result.dart';
import '../providers/capture_session.dart';
import '../theme/swaya_theme.dart';
import '../widgets/captured_photo_image.dart';
import '../widgets/step_dots.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key, required this.view});

  final CaptureView view;

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  final _picker = ImagePicker();
  bool _busy = false;

  Future<void> _pick(ImageSource source) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final picked = await _picker.pickImage(
        source: source,
        preferredCameraDevice: CameraDevice.rear,
        imageQuality: 82,
        maxWidth: 1280,
        maxHeight: 1920,
      );
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      final name = picked.name.isNotEmpty ? picked.name : '${widget.view.name}.jpg';
      context.read<CaptureSession>().setPhoto(
            widget.view,
            CapturedPhoto(bytes: bytes, filename: name),
          );
      _advance();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _advance() {
    final next = widget.view.next;
    if (next != null) {
      context.go('/scan/capture/${next.routeName}');
    } else {
      context.go('/scan/review');
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<CaptureSession>();
    final existing = session.photoFor(widget.view);

    return Scaffold(
      backgroundColor: SwayaColors.chrome,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Stack(
                alignment: Alignment.center,
                children: [
                  if (existing != null)
                    Positioned.fill(
                      child: CapturedPhotoImage(photo: existing, fit: BoxFit.cover),
                    )
                  else
                    const ColoredBox(color: SwayaColors.chrome),
                  Container(
                    width: 120,
                    height: 300,
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: SwayaColors.accentHighlight,
                        width: 2,
                        strokeAlign: BorderSide.strokeAlignCenter,
                      ),
                      borderRadius: BorderRadius.circular(60),
                    ),
                  ),
                  Positioned(
                    top: 8,
                    left: 16,
                    right: 16,
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: SwayaColors.inkPrimary.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'Align your body inside the guide',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Container(
              color: SwayaColors.base,
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '${widget.view.stepIndex} of 3 · ${widget.view.label}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: SwayaColors.inkSecondary,
                            ),
                      ),
                      StepDots(current: widget.view.stepIndex),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      TextButton(
                        onPressed: _busy ? null : () => _pick(ImageSource.gallery),
                        child: const Text('Gallery'),
                      ),
                      GestureDetector(
                        onTap: _busy ? null : () => _pick(ImageSource.camera),
                        child: Container(
                          width: 64,
                          height: 64,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: SwayaColors.accentHighlight, width: 4),
                            color: SwayaColors.elevated,
                          ),
                          child: _busy
                              ? const Padding(
                                  padding: EdgeInsets.all(18),
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : null,
                        ),
                      ),
                      TextButton(
                        onPressed: existing != null && !_busy ? _advance : null,
                        child: const Text('Next'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
