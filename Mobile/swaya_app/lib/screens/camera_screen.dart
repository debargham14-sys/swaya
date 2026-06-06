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
        imageQuality: 92,
        maxWidth: 1920,
        maxHeight: 2560,
      );
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      if (bytes.length < 8000) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Photo looks too small — try again with better lighting')),
        );
        return;
      }
      final name = picked.name.isNotEmpty ? picked.name : '${widget.view.name}.jpg';
      context.read<CaptureSession>().setPhoto(
            widget.view,
            CapturedPhoto(bytes: bytes, filename: name),
          );
      // Show the captured photo with the framed grid for review; user taps Next.
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
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                child: Center(
                  child: AspectRatio(
                    aspectRatio: 3 / 4,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          if (existing != null)
                            CapturedPhotoImage(photo: existing, fit: BoxFit.cover)
                          else
                            const ColoredBox(color: SwayaColors.elevated),
                          if (existing == null)
                            Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    Icons.person_outline,
                                    size: 64,
                                    color: SwayaColors.inkTertiary,
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Tap the shutter or pick from gallery',
                                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                          color: SwayaColors.inkTertiary,
                                        ),
                                  ),
                                ],
                              ),
                            ),
                          // Rule-of-thirds grid + body guide overlay.
                          const Positioned.fill(
                            child: IgnorePointer(
                              child: CustomPaint(painter: _CaptureGridPainter()),
                            ),
                          ),
                          Positioned(
                            top: 10,
                            left: 10,
                            right: 10,
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 10),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.45),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                existing == null
                                    ? 'Align your whole body inside the frame'
                                    : 'Looks good? Tap Next, or retake with the shutter',
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                      color: Colors.white,
                                    ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
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

/// Rule-of-thirds composition grid plus a soft body-alignment guide.
class _CaptureGridPainter extends CustomPainter {
  const _CaptureGridPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = Colors.white.withValues(alpha: 0.30)
      ..strokeWidth = 1;
    for (var i = 1; i < 3; i++) {
      final dx = size.width * i / 3;
      canvas.drawLine(Offset(dx, 0), Offset(dx, size.height), grid);
      final dy = size.height * i / 3;
      canvas.drawLine(Offset(0, dy), Offset(size.width, dy), grid);
    }

    final guide = Paint()
      ..color = SwayaColors.accentHighlight.withValues(alpha: 0.9)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final guideWidth = size.width * 0.42;
    final guideHeight = size.height * 0.82;
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: guideWidth,
      height: guideHeight,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(guideWidth / 2)),
      guide,
    );
  }

  @override
  bool shouldRepaint(covariant _CaptureGridPainter oldDelegate) => false;
}
