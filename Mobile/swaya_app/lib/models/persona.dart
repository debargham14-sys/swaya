import 'blouse_measurements.dart';

/// A saved measurement profile (Figma frames 18–21). Each persona has a name,
/// an optional quick label (Me / Mom / Father / Sister / Friend), and a set of
/// blouse measurements.
class Persona {
  Persona({
    required this.id,
    required this.name,
    this.label,
    BlouseMeasurements? measurements,
    this.updatedAtIso,
  }) : measurements = measurements ?? BlouseMeasurements();

  final String id;
  final String name;
  final String? label;
  final BlouseMeasurements measurements;
  final String? updatedAtIso;

  static const quickLabels = ['Me', 'Mom', 'Father', 'Sister', 'Friend'];

  Persona copyWith({
    String? name,
    String? label,
    BlouseMeasurements? measurements,
    String? updatedAtIso,
  }) {
    return Persona(
      id: id,
      name: name ?? this.name,
      label: label ?? this.label,
      measurements: measurements ?? this.measurements,
      updatedAtIso: updatedAtIso ?? this.updatedAtIso,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        if (label != null) 'label': label,
        'measurements': measurements.toJson(),
        if (updatedAtIso != null) 'updated_at': updatedAtIso,
      };

  factory Persona.fromJson(Map<String, dynamic> json) => Persona(
        id: json['id'] as String,
        name: json['name'] as String? ?? 'Unnamed',
        label: json['label'] as String?,
        measurements: BlouseMeasurements.fromJson(
            (json['measurements'] as Map?)?.cast<String, dynamic>() ?? {}),
        updatedAtIso: json['updated_at'] as String?,
      );
}
