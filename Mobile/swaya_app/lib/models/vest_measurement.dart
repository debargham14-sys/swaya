/// Response model for POST /v1/vest (ChArUco vest measurement, beta).
class VestScanResult {
  const VestScanResult({
    required this.scanId,
    required this.beta,
    required this.stored,
    required this.measurement,
    this.groundTruthIn,
  });

  final String scanId;
  final bool beta;
  final bool stored;
  final VestMeasurement measurement;
  final Map<String, double>? groundTruthIn;

  factory VestScanResult.fromJson(Map<String, dynamic> json) {
    return VestScanResult(
      scanId: json['scan_id']?.toString() ?? '',
      beta: json['beta'] == true,
      stored: json['stored'] == true,
      measurement: VestMeasurement.fromJson(
        (json['measurement'] as Map?)?.cast<String, dynamic>() ?? const {},
      ),
      groundTruthIn: _numMap(json['ground_truth_in']),
    );
  }
}

class VestMeasurement {
  const VestMeasurement({
    required this.view,
    required this.confidence,
    required this.markersFound,
    required this.girthsCm,
    required this.girthsIn,
    required this.warnings,
    required this.reliable,
  });

  final String view;
  final double confidence;
  final List<String> markersFound;
  final Map<String, double> girthsCm;
  final Map<String, double> girthsIn;
  final List<String> warnings;
  final bool reliable;

  bool get hasGirths => girthsIn.isNotEmpty;

  factory VestMeasurement.fromJson(Map<String, dynamic> json) {
    return VestMeasurement(
      view: json['view']?.toString() ?? 'unknown',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      markersFound: (json['markers_found'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      girthsCm: _numMap(json['girths_cm']) ?? const {},
      girthsIn: _numMap(json['girths_in']) ?? const {},
      warnings: (json['warnings'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      reliable: json['measurements_reliable'] == true,
    );
  }
}

Map<String, double>? _numMap(dynamic raw) {
  if (raw is! Map) return null;
  final out = <String, double>{};
  raw.forEach((k, v) {
    if (v is num) out[k.toString()] = v.toDouble();
  });
  return out.isEmpty ? null : out;
}
