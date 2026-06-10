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

/// One measured quantity (girth / width / length).
class MeasureEntry {
  const MeasureEntry({required this.name, required this.inches, required this.cm, required this.kind});

  final String name;
  final double inches;
  final double cm;
  final String kind; // girth | width | length

  /// "shoulder_width" -> "Shoulder width"
  String get label {
    final s = name.replaceAll('_', ' ');
    return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
  }
}

class VestMeasurement {
  const VestMeasurement({
    required this.views,
    required this.confidence,
    required this.markersFound,
    required this.entries,
    required this.warnings,
    required this.reliable,
  });

  final List<String> views;
  final double confidence;
  final List<String> markersFound;
  final List<MeasureEntry> entries;
  final List<String> warnings;
  final bool reliable;

  bool get hasMeasurements => entries.isNotEmpty;
  List<MeasureEntry> get girths => entries.where((e) => e.kind == 'girth').toList();
  List<MeasureEntry> get others => entries.where((e) => e.kind != 'girth').toList();

  factory VestMeasurement.fromJson(Map<String, dynamic> json) {
    final raw = (json['measurements'] as Map?)?.cast<String, dynamic>() ?? const {};
    final entries = <MeasureEntry>[];
    raw.forEach((name, v) {
      if (v is Map) {
        entries.add(MeasureEntry(
          name: name,
          inches: (v['in'] as num?)?.toDouble() ?? 0,
          cm: (v['cm'] as num?)?.toDouble() ?? 0,
          kind: v['kind']?.toString() ?? 'girth',
        ));
      }
    });
    return VestMeasurement(
      views: (json['views'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      markersFound: (json['markers_found'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      entries: entries,
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
