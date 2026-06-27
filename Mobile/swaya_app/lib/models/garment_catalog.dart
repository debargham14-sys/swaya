import 'package:flutter/material.dart';

import '../theme/swaya_light_theme.dart';
import 'blouse_measurements.dart';

/// A garment a persona can order, with the measurement fields a tailor needs
/// for it. The field sets are display-only definitions — the measurements
/// themselves are stored as an opaque {key -> cm} map on the persona/backend.
class GarmentType {
  const GarmentType(this.id, this.label, this.gender, this.fields);

  final String id;
  final String label;
  final String gender; // 'female' | 'male'
  final List<MeasurementField> fields;
}

// Shared field sets ----------------------------------------------------------

const List<MeasurementField> _kurtaFemaleFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('waist', 'Waist'),
  MeasurementField('hip', 'Hip'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('kurta_length', 'Kurta length'),
  MeasurementField('sleeve_length', 'Sleeve length'),
  MeasurementField('sleeve_round', 'Sleeve round'),
  MeasurementField('arm_hole', 'Arm hole'),
];

const List<MeasurementField> _lehengaFields = [
  MeasurementField('waist', 'Waist'),
  MeasurementField('hip', 'Hip'),
  MeasurementField('lehenga_length', 'Lehenga length'),
  MeasurementField('waist_band', 'Waist band'),
];

const List<MeasurementField> _salwarFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('waist', 'Waist'),
  MeasurementField('hip', 'Hip'),
  MeasurementField('kameez_length', 'Kameez length'),
  MeasurementField('salwar_length', 'Salwar length'),
  MeasurementField('bottom_round', 'Bottom round'),
];

const List<MeasurementField> _dressFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('waist', 'Waist'),
  MeasurementField('hip', 'Hip'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('dress_length', 'Dress length'),
  MeasurementField('sleeve_length', 'Sleeve length'),
];

const List<MeasurementField> _maleKurtaFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('kurta_length', 'Kurta length'),
  MeasurementField('sleeve_length', 'Sleeve length'),
  MeasurementField('sleeve_round', 'Sleeve round'),
  MeasurementField('neck', 'Neck'),
];

const List<MeasurementField> _shirtFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('shirt_length', 'Shirt length'),
  MeasurementField('sleeve_length', 'Sleeve length'),
  MeasurementField('collar', 'Collar'),
  MeasurementField('cuff', 'Cuff'),
];

const List<MeasurementField> _sherwaniFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('waist', 'Waist'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('sherwani_length', 'Sherwani length'),
  MeasurementField('sleeve_length', 'Sleeve length'),
  MeasurementField('neck', 'Neck'),
];

const List<MeasurementField> _nehruFields = [
  MeasurementField('chest', 'Chest'),
  MeasurementField('shoulder', 'Shoulder'),
  MeasurementField('jacket_length', 'Jacket length'),
];

const List<MeasurementField> _trouserFields = [
  MeasurementField('waist', 'Waist'),
  MeasurementField('hip', 'Hip'),
  MeasurementField('trouser_length', 'Trouser length'),
  MeasurementField('thigh', 'Thigh'),
  MeasurementField('bottom', 'Bottom'),
];

/// Gender-appropriate garment catalogs. Female keeps the original blouse-first
/// flow (Blouse uses [kBlouseFields]); male gets kurta/shirt/sherwani/etc.
const List<GarmentType> kFemaleGarments = [
  GarmentType('blouse', 'Blouse', 'female', kBlouseFields),
  GarmentType('saree_blouse', 'Saree blouse', 'female', kBlouseFields),
  GarmentType('kurta', 'Kurta', 'female', _kurtaFemaleFields),
  GarmentType('lehenga', 'Lehenga', 'female', _lehengaFields),
  GarmentType('salwar_suit', 'Salwar suit', 'female', _salwarFields),
  GarmentType('dress', 'Dress', 'female', _dressFields),
];

const List<GarmentType> kMaleGarments = [
  GarmentType('kurta', 'Kurta', 'male', _maleKurtaFields),
  GarmentType('shirt', 'Shirt', 'male', _shirtFields),
  GarmentType('sherwani', 'Sherwani', 'male', _sherwaniFields),
  GarmentType('nehru_jacket', 'Nehru jacket', 'male', _nehruFields),
  GarmentType('trousers', 'Trousers', 'male', _trouserFields),
];

List<GarmentType> garmentsForGender(String gender) =>
    gender.toLowerCase() == 'male' ? kMaleGarments : kFemaleGarments;

/// Bottom sheet that lets the user pick a garment from the catalog for [gender].
/// Returns the chosen [GarmentType], or null if dismissed.
Future<GarmentType?> showGarmentPicker(
  BuildContext context,
  String gender,
) {
  final garments = garmentsForGender(gender);
  return showModalBottomSheet<GarmentType>(
    context: context,
    backgroundColor: SwayaLight.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(20, 18, 20, 4),
            child: Text('Choose a garment',
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 18,
                    fontWeight: FontWeight.w700)),
          ),
          for (final g in garments)
            ListTile(
              leading: const Icon(Icons.checkroom_outlined,
                  color: SwayaLight.accent),
              title: Text(g.label,
                  style: const TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontWeight: FontWeight.w600)),
              trailing: const Icon(Icons.chevron_right,
                  color: SwayaLight.inkTertiary),
              onTap: () => Navigator.of(ctx).pop(g),
            ),
          const SizedBox(height: 8),
        ],
      ),
    ),
  );
}
