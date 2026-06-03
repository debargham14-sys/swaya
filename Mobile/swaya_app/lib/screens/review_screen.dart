import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../models/measurement_result.dart';
import '../providers/capture_session.dart';
import '../theme/swaya_theme.dart';
import '../widgets/captured_photo_image.dart';
import '../widgets/swaya_scaffold.dart';

class ReviewScreen extends StatelessWidget {
  const ReviewScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<CaptureSession>();

    return SwayaScaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Review',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Height ${session.heightCm?.toStringAsFixed(0) ?? '—'} cm · 3 photos ready',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: SwayaColors.inkSecondary,
                ),
          ),
          if (session.measureError != null && session.measureError!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              session.measureError!,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
            ),
          ],
          const SizedBox(height: 16),
          Row(
            children: CaptureView.values.map((view) {
              final photo = session.photoFor(view);
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Column(
                    children: [
                      AspectRatio(
                        aspectRatio: 3 / 4,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: photo != null
                              ? CapturedPhotoImage(photo: photo, fit: BoxFit.cover)
                              : Container(color: SwayaColors.elevated),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        view.label,
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: SwayaColors.inkSecondary,
                            ),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
          const Spacer(),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => context.go('/scan/capture/${CaptureView.front.routeName}'),
                  child: const Text('Edit'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 2,
                child: ElevatedButton(
                  onPressed: session.canSubmit
                      ? () => context.go('/scan/processing')
                      : null,
                  child: const Text('Get measurements'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
