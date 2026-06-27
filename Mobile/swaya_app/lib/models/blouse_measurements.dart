import 'dart:convert';

/// One blouse/tailoring measurement field shown in the manual-entry form
/// (Figma frames 13–14) and the review screen (frame 17).
class MeasurementField {
  const MeasurementField(this.key, this.label, {this.required = true});

  final String key;
  final String label;
  final bool required;
}

/// The blouse measurement schema, in display order. These are garment-fit
/// measurements (distinct from the body girths the photo API returns).
const List<MeasurementField> kBlouseFields = [
  MeasurementField('upper_chest', 'Upper Chest'),
  MeasurementField('chest', 'Chest'),
  MeasurementField('below_chest', 'Below Chest'),
  MeasurementField('waist', 'Waist'),
  MeasurementField('front_neck_deep', 'Front neck deep'),
  MeasurementField('back_neck_deep', 'Back neck deep'),
  MeasurementField('sleeve_length', 'Sleeve length'),
  MeasurementField('sleeve_round', 'Sleeve round'),
  MeasurementField('arm_hole', 'Arm hole'),
  MeasurementField('arm_length', 'Arm length'),
];

/// A set of blouse measurements in centimetres, keyed by [MeasurementField.key].
class BlouseMeasurements {
  BlouseMeasurements([Map<String, double>? values])
      : values = {...?values};

  final Map<String, double> values;

  double? operator [](String key) => values[key];

  void set(String key, double? cm) {
    if (cm == null) {
      values.remove(key);
    } else {
      values[key] = cm;
    }
  }

  int get filledCount =>
      kBlouseFields.where((f) => values[f.key] != null).length;

  int get requiredCount => kBlouseFields.where((f) => f.required).length;

  int get requiredFilledCount =>
      kBlouseFields.where((f) => f.required && values[f.key] != null).length;

  bool get isComplete => requiredFilledCount == requiredCount;

  List<MeasurementField> get missingRequired => kBlouseFields
      .where((f) => f.required && values[f.key] == null)
      .toList();

  Map<String, dynamic> toJson() => values;

  factory BlouseMeasurements.fromJson(Map<String, dynamic> json) =>
      BlouseMeasurements(json.map((k, v) => MapEntry(k, (v as num).toDouble())));

  String encode() => jsonEncode(values);

  factory BlouseMeasurements.decode(String s) =>
      BlouseMeasurements.fromJson(jsonDecode(s) as Map<String, dynamic>);

  BlouseMeasurements copy() => BlouseMeasurements(values);
}
