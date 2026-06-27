import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/measurement_draft.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Add Measurements — Figma frame 12. Instruction video + method choice
/// (manual entry vs. capture images).
class AddMeasurementsScreen extends StatelessWidget {
  const AddMeasurementsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final draft = context.read<MeasurementDraft>();
    return LightScaffold(
      title: 'Measurements',
      showMenu: true,
      navIndex: 1,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          const Text('Add Measurements',
              style: TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontSize: 22,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Choose how to add your body measurements.',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 14)),
          const SizedBox(height: 20),
          _VideoCard(),
          const SizedBox(height: 24),
          const SectionTitle('Choose Method'),
          const SizedBox(height: 12),
          AppCard(
            onTap: () {
              draft.setSource(MeasurementSource.manual);
              context.push('/measure/manual');
            },
            child: _MethodRow(
              icon: Icons.edit_outlined,
              title: 'Manual Entry',
              subtitle: 'Enter measurements yourself. Best if you already have values.',
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            onTap: () {
              draft.setSource(MeasurementSource.photos);
              context.push('/measure/capture');
            },
            child: _MethodRow(
              icon: Icons.photo_camera_outlined,
              title: 'Capture Images',
              subtitle: 'Upload front, back and side photos for automated measurement.',
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              const Icon(Icons.info_outline,
                  size: 16, color: SwayaLight.inkTertiary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Use good lighting, fitted clothing and full-body framing.',
                  style: TextStyle(
                      color: SwayaLight.inkTertiary, fontSize: 12),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _VideoCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 16 / 8,
            child: Container(
              decoration: const BoxDecoration(
                color: SwayaLight.surfaceAlt,
                borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
              ),
              child: const Center(
                child: CircleAvatar(
                  radius: 26,
                  backgroundColor: SwayaLight.cta,
                  child: Icon(Icons.play_arrow, color: SwayaLight.onCta, size: 30),
                ),
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'Instruction video — how to capture clear front, back and side images.',
              style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _MethodRow extends StatelessWidget {
  const _MethodRow({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: SwayaLight.surfaceAlt,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: SwayaLight.inkPrimary, size: 22),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: const TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontSize: 15,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              Text(subtitle,
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 12)),
            ],
          ),
        ),
        const Icon(Icons.chevron_right, color: SwayaLight.inkTertiary),
      ],
    );
  }
}
