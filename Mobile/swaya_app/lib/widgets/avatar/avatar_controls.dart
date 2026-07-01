import 'package:flutter/material.dart';

import '../../models/avatar_design.dart';
import '../../models/blouse_measurements.dart';
import '../../theme/swaya_light_theme.dart';

/// Shared garment-customisation controls for the 3D avatar — used by both the
/// solo `AvatarScreen` and the collaborative `CollabAvatarScreen` so the two
/// stay visually identical and edit the same [AvatarDesign] shape.

/// Female / male segmented selector (swaps the baked GLB).
class AvatarSegmented extends StatelessWidget {
  const AvatarSegmented({
    super.key,
    required this.selected,
    required this.onSelect,
    this.enabled = true,
  });

  final String selected;
  final ValueChanged<String> onSelect;
  final bool enabled;

  static const _options = ['female', 'male'];
  static const _labels = ['Female', 'Male'];

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _options.length; i++)
            GestureDetector(
              onTap: enabled ? () => onSelect(_options[i]) : null,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                padding:
                    const EdgeInsets.symmetric(horizontal: 26, vertical: 9),
                decoration: BoxDecoration(
                  color: _options[i] == selected
                      ? SwayaLight.cta
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Text(
                  _labels[i],
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: _options[i] == selected
                        ? SwayaLight.onCta
                        : SwayaLight.inkSecondary,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// One on/off add-on chip (Sleeves / Pants / Watch).
class AvatarToggleChip extends StatelessWidget {
  const AvatarToggleChip({
    super.key,
    required this.icon,
    required this.label,
    required this.on,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: on
              ? SwayaLight.accent.withValues(alpha: 0.12)
              : SwayaLight.surface,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: on ? SwayaLight.accent : SwayaLight.border,
            width: 1.5,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                size: 18,
                color: on ? SwayaLight.accent : SwayaLight.inkSecondary),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: on ? SwayaLight.inkPrimary : SwayaLight.inkSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The colour swatch row (indexes into [kAvatarPalette]).
class AvatarSwatchBar extends StatelessWidget {
  const AvatarSwatchBar({
    super.key,
    required this.selected,
    required this.onPick,
  });

  final int selected;
  final ValueChanged<int> onPick;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: SwayaLight.surface,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: SwayaLight.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < kAvatarPalette.length; i++) ...[
              if (i > 0) const SizedBox(width: 16),
              _SwatchDot(
                color: kAvatarPalette[i].color,
                selected: i == selected,
                onTap: () => onPick(i),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SwatchDot extends StatelessWidget {
  const _SwatchDot({
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? SwayaLight.inkPrimary : SwayaLight.border,
            width: selected ? 3 : 1.5,
          ),
        ),
      ),
    );
  }
}

/// Compact read-out of the measurements being previewed on the avatar.
class AvatarMeasurementSummary extends StatelessWidget {
  const AvatarMeasurementSummary({super.key, required this.measurements});

  final BlouseMeasurements measurements;

  @override
  Widget build(BuildContext context) {
    final entries = measurements.values.entries.take(4).toList();
    final more = measurements.values.length - entries.length;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: SwayaLight.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.straighten, size: 16, color: SwayaLight.accent),
              SizedBox(width: 8),
              Text('Previewing measurements',
                  style: TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 14,
            runSpacing: 4,
            children: [
              for (final e in entries)
                Text('${_pretty(e.key)} ${e.value.toStringAsFixed(0)}cm',
                    style: const TextStyle(
                        color: SwayaLight.inkSecondary, fontSize: 12)),
              if (more > 0)
                Text('+$more more',
                    style: const TextStyle(
                        color: SwayaLight.inkTertiary, fontSize: 12)),
            ],
          ),
        ],
      ),
    );
  }

  static String _pretty(String key) =>
      key.replaceAll('_', ' ').replaceAllMapped(
            RegExp(r'^\w'),
            (m) => m.group(0)!.toUpperCase(),
          );
}
