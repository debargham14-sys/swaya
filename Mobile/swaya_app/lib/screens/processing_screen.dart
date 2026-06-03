import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../config/app_config.dart';
import '../models/measurement_result.dart';
import '../providers/capture_session.dart';
import '../services/measure_api.dart';
import '../services/scan_api.dart';
import '../theme/swaya_theme.dart';

class ProcessingScreen extends StatefulWidget {
  const ProcessingScreen({super.key});

  @override
  State<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends State<ProcessingScreen> {
  int _step = 0;
  static const _labels = [
    'Front photo',
    'Back photo',
    'Side photo',
    'Computing girths',
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _run() async {
    final session = context.read<CaptureSession>();
    final api = ScanApi();
    final photos = session.photos;

    try {
      for (var i = 0; i < 3; i++) {
        if (!mounted) return;
        setState(() => _step = i);
        await Future<void>.delayed(const Duration(milliseconds: 400));
      }

      if (!mounted) return;
      setState(() => _step = 3);
      session.isMeasuring = true;
      session.measureError = null;

      // Wake Render (free tier cold start) before the long multipart upload.
      final apiUp = await MeasureApi().healthCheck();
      if (!apiUp && mounted) {
        session.isMeasuring = false;
        session.measureError =
            'Cannot reach API at ${AppConfig.apiBaseUrl}. Check network or wait and retry.';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(session.measureError!)),
        );
        context.go('/scan/review');
        return;
      }

      final scan = await api.createScan(
        front: photos[CaptureView.front]!,
        back: photos[CaptureView.back]!,
        side: photos[CaptureView.side]!,
        heightCm: session.heightCm!,
        weightKg: session.weightKg,
        subjectLabel: session.subjectLabel,
        collectorId: session.collectorId,
        consentGiven: session.consentGiven,
      );

      session.setScan(scan);
      session.isMeasuring = false;
      if (mounted) context.go('/scan/results');
    } on MeasureApiException catch (e) {
      session.isMeasuring = false;
      session.measureError = e.message;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
        context.go('/scan/review');
      }
    } catch (e) {
      session.isMeasuring = false;
      session.measureError = e.toString();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Measurement failed: $e')),
        );
        context.go('/scan/review');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SwayaColors.base,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SizedBox(
                width: 48,
                height: 48,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
              const SizedBox(height: 24),
              Text(
                'Measuring your profile',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'Uploading photos and saving measurements to the cloud database. '
                'First scan after idle can take 1–2 minutes.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: SwayaColors.inkSecondary,
                    ),
              ),
              const SizedBox(height: 32),
              ...List.generate(_labels.length, (i) {
                final done = i <= _step;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: done
                              ? SwayaColors.accentHighlight
                              : SwayaColors.borderSubtle,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        _labels[i],
                        style: TextStyle(
                          color: done ? SwayaColors.inkPrimary : SwayaColors.inkTertiary,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                );
              }),
            ],
          ),
        ),
      ),
    );
  }
}
