import 'package:flutter/material.dart';

import '../widgets/avatar/garment_recolor.dart';
import 'blouse_measurements.dart';

/// One garment swatch — brand-matched to the Swaya light wireframes.
class AvatarSwatch {
  const AvatarSwatch(this.name, this.color);
  final String name;
  final Color color;
}

/// The shared garment palette (teal accent anchor + warm/cool complements).
/// Lives here so both the solo [AvatarScreen] and the collaborative
/// [CollabAvatarScreen] index into the same colours.
const List<AvatarSwatch> kAvatarPalette = [
  AvatarSwatch('Teal', Color(0xFF4A9B9B)), // brand accent
  AvatarSwatch('Clay', Color(0xFFB5613B)),
  AvatarSwatch('Indigo', Color(0xFF3C4A66)),
  AvatarSwatch('Sand', Color(0xFFC9B79C)),
];

// Fixed (non-recoloured) part colours.
const _watchRgb = (30, 32, 38); // dark metal
const _pantsRgb = (58, 66, 96); // denim slate

/// The full customisable state of the 3D avatar: gender (which GLB), the chosen
/// garment colour, and which add-on parts are shown. This is the unit that the
/// collaboration session syncs between a user and a designer — both edit one
/// [AvatarDesign] and [applyTo] re-pushes it onto the shared `<model-viewer>`.
class AvatarDesign {
  const AvatarDesign({
    this.gender = 'female',
    this.colorIndex = 0,
    this.sleeves = false,
    this.watch = false,
    this.pants = false,
    this.garmentId,
    this.measurements,
  });

  /// `'female'` / `'male'` — selects the baked GLB.
  final String gender;

  /// Index into [kAvatarPalette] for the shirt/sleeve colour.
  final int colorIndex;
  final bool sleeves;
  final bool watch;
  final bool pants;

  /// Optional garment being designed (reserved; informs the LLM / catalog).
  final String? garmentId;

  /// Optional measurements being previewed (shown as a summary today).
  final BlouseMeasurements? measurements;

  AvatarSwatch get swatch =>
      kAvatarPalette[colorIndex.clamp(0, kAvatarPalette.length - 1)];

  AvatarDesign copyWith({
    String? gender,
    int? colorIndex,
    bool? sleeves,
    bool? watch,
    bool? pants,
    String? garmentId,
    BlouseMeasurements? measurements,
  }) {
    return AvatarDesign(
      gender: gender ?? this.gender,
      colorIndex: colorIndex ?? this.colorIndex,
      sleeves: sleeves ?? this.sleeves,
      watch: watch ?? this.watch,
      pants: pants ?? this.pants,
      garmentId: garmentId ?? this.garmentId,
      measurements: measurements ?? this.measurements,
    );
  }

  /// Push the full design onto the loaded avatar via [GarmentRecolor] — the same
  /// direct GPU material edits the solo screen uses (no reload).
  void applyTo(GarmentRecolor recolor) {
    final c = swatch.color;
    final r = (c.r * 255).round();
    final g = (c.g * 255).round();
    final b = (c.b * 255).round();
    recolor.setMaterial('shirt', r, g, b, 1);
    recolor.setMaterial('sleeve', r, g, b, sleeves ? 1 : 0);
    recolor.setMaterial('watch', _watchRgb.$1, _watchRgb.$2, _watchRgb.$3,
        watch ? 1 : 0);
    recolor.setMaterial('pants', _pantsRgb.$1, _pantsRgb.$2, _pantsRgb.$3,
        pants ? 1 : 0);
  }

  Map<String, dynamic> toJson() => {
        'gender': gender,
        'color_index': colorIndex,
        'sleeves': sleeves,
        'watch': watch,
        'pants': pants,
        if (garmentId != null) 'garment_id': garmentId,
        if (measurements != null && measurements!.values.isNotEmpty)
          'measurements': measurements!.toJson(),
      };

  factory AvatarDesign.fromJson(Map<String, dynamic> json) {
    final m = (json['measurements'] as Map?)?.cast<String, dynamic>();
    return AvatarDesign(
      gender: (json['gender'] as String?) ?? 'female',
      colorIndex: (json['color_index'] as num?)?.toInt() ?? 0,
      sleeves: json['sleeves'] as bool? ?? false,
      watch: json['watch'] as bool? ?? false,
      pants: json['pants'] as bool? ?? false,
      garmentId: json['garment_id'] as String?,
      measurements:
          m == null ? null : BlouseMeasurements.fromJson(m),
    );
  }
}
