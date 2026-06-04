class MeasurementResult {
  MeasurementResult({
    required this.mode,
    required this.backend,
    this.heightCm,
    this.weightKg,
    this.bmi,
    this.confidence,
    required this.girthsCm,
    required this.girthsIn,
    this.warnings = const [],
    this.calibrationProfile,
    this.calibrationTrainingScans,
    this.measurementsReliable = true,
  });

  factory MeasurementResult.fromJson(Map<String, dynamic> json) {
    final girthsCmRaw = json['girths_cm'];
    final girthsInRaw = json['girths_in'];
    return MeasurementResult(
      mode: json['mode'] as String? ?? 'height',
      backend: json['backend'] as String? ?? '',
      heightCm: (json['height_cm'] as num?)?.toDouble(),
      weightKg: (json['weight_kg'] as num?)?.toDouble(),
      bmi: (json['bmi'] as num?)?.toDouble(),
      confidence: (json['confidence'] as num?)?.toDouble(),
      girthsCm: girthsCmRaw is Map
          ? girthsCmRaw.map((k, v) => MapEntry(k.toString(), (v as num).toDouble()))
          : {},
      girthsIn: girthsInRaw is Map
          ? girthsInRaw.map((k, v) => MapEntry(k.toString(), (v as num).toDouble()))
          : {},
      warnings: (json['warnings'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      calibrationProfile: json['calibration_profile'] as String?,
      calibrationTrainingScans: json['calibration_training_scans'] as int?,
      measurementsReliable: json['measurements_reliable'] as bool? ??
          !_warningsUnreliable(json['warnings'] as List<dynamic>?),
    );
  }

  static bool _warningsUnreliable(List<dynamic>? warnings) {
    if (warnings == null) return false;
    final text = warnings.map((e) => e.toString()).join(' ').toLowerCase();
    return text.contains('measurements_unreliable') ||
        text.contains('pose_not_detected') ||
        text.contains('pose_error:');
  }

  final String mode;
  final String backend;
  final double? heightCm;
  final double? weightKg;
  final double? bmi;
  final double? confidence;
  final Map<String, double> girthsCm;
  final Map<String, double> girthsIn;
  final List<String> warnings;
  final String? calibrationProfile;
  final int? calibrationTrainingScans;

  final bool measurementsReliable;

  bool get isCalibrated => calibrationProfile != null && calibrationProfile!.isNotEmpty;

  bool get hasGirths => girthsCm.isNotEmpty;

  String confidenceLabel() {
    if (confidence == null) return '';
    return '${(confidence! * 100).round()}% conf.';
  }

  Map<String, dynamic> toContextJson() => {
        'mode': mode,
        'backend': backend,
        'height_cm': heightCm,
        'weight_kg': weightKg,
        'bmi': bmi,
        'confidence': confidence,
        'girths_cm': girthsCm,
        'girths_in': girthsIn,
        'warnings': warnings,
      };
}

enum CaptureView { front, back, side }

extension CaptureViewX on CaptureView {
  String get label {
    switch (this) {
      case CaptureView.front:
        return 'Front';
      case CaptureView.back:
        return 'Back';
      case CaptureView.side:
        return 'Side';
    }
  }

  String get routeName => name;

  CaptureView? get next {
    switch (this) {
      case CaptureView.front:
        return CaptureView.back;
      case CaptureView.back:
        return CaptureView.side;
      case CaptureView.side:
        return null;
    }
  }

  int get stepIndex {
    switch (this) {
      case CaptureView.front:
        return 1;
      case CaptureView.back:
        return 2;
      case CaptureView.side:
        return 3;
    }
  }
}
