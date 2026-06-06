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
      // Full resolution — server applies EXIF upright + downscale (iPhone uploads).
      final picked = await _picker.pickImage(
        source: source,
        preferredCameraDevice: CameraDevice.rear,
        imageQuality: 95,
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

  static String _captureHint(CaptureView view) {
    switch (view) {
      case CaptureView.front:
        return 'Step back — fit your whole body inside the box, face camera';
      case CaptureView.back:
        return 'Same distance — back to camera, whole body in the box';
      case CaptureView.side:
        return 'Turn 90° — full side profile, head and feet inside the box';
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
                padding: const EdgeInsets.fromLTRB(6, 4, 6, 4),
                child: Center(
                  child: AspectRatio(
                    // Tall portrait frame — matches phone camera; fits head-to-toe.
                    aspectRatio: 9 / 16,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          if (existing != null)
                            CapturedPhotoImage(photo: existing, fit: BoxFit.contain)
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
                                    ? _captureHint(widget.view)
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

/// Full-body alignment frame — tall box so users step back and include head + feet.
class _CaptureGridPainter extends CustomPainter {
  const _CaptureGridPainter();

  static const _marginH = 0.04;
  static const _marginV = 0.02;

  @override
  void paint(Canvas canvas, Size size) {
    final dim = Paint()
      ..color = Colors.black.withValues(alpha: 0.35)
      ..style = PaintingStyle.fill;

    final guideW = size.width * (1 - 2 * _marginH);
    final guideH = size.height * (1 - 2 * _marginV);
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: guideW,
      height: guideH,
    );
    final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(10));

    // Darken outside the capture box so the frame reads clearly.
    final outer = Path()..addRect(Rect.fromLTWH(0, 0, size.width, size.height));
    final inner = Path()..addRRect(rrect);
    canvas.drawPath(
      Path.combine(PathOperation.difference, outer, inner),
      dim,
    );

    final border = Paint()
      ..color = SwayaColors.accentHighlight.withValues(alpha: 0.95)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5;
    canvas.drawRRect(rrect, border);

    // Corner ticks (viewfinder style).
    final tick = Paint()
      ..color = Colors.white.withValues(alpha: 0.9)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    const tickLen = 22.0;
    final corners = [
      rect.topLeft,
      rect.topRight,
      rect.bottomLeft,
      rect.bottomRight,
    ];
    for (final c in corners) {
      final isLeft = c.dx < size.width / 2;
      final isTop = c.dy < size.height / 2;
      canvas.drawLine(
        c,
        c + Offset(isLeft ? tickLen : -tickLen, 0),
        tick,
      );
      canvas.drawLine(
        c,
        c + Offset(0, isTop ? tickLen : -tickLen),
        tick,
      );
    }

    final label = TextPainter(
      text: const TextSpan(
        text: 'HEAD',
        style: TextStyle(color: Colors.white70, fontSize: 10, letterSpacing: 1),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    label.paint(canvas, Offset(rect.center.dx - label.width / 2, rect.top + 6));

    final feet = TextPainter(
      text: const TextSpan(
        text: 'FEET',
        style: TextStyle(color: Colors.white70, fontSize: 10, letterSpacing: 1),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    feet.paint(canvas, Offset(rect.center.dx - feet.width / 2, rect.bottom - 18));
  }

  @override
  bool shouldRepaint(covariant _CaptureGridPainter oldDelegate) => false;
}
