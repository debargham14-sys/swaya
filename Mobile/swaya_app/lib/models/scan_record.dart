import 'ground_truth.dart';
import 'measurement_result.dart';
import '../utils/scan_display.dart';

class ScanRecord {
  ScanRecord({
    required this.scanId,
    required this.result,
    required this.downloadUrl,
    this.meshIncluded = false,
    this.createdAt,
    this.subjectLabel,
    this.groundTruthCm = const {},
    this.groundTruthComparison = const {},
  });

  factory ScanRecord.fromJson(Map<String, dynamic> json) {
    final measurements = json['measurements'];
    final Map<String, dynamic> measureMap = measurements is Map<String, dynamic>
        ? measurements
        : json;

    final gtRaw = json['ground_truth_cm'];
    final groundTruthCm = <String, double>{};
    if (gtRaw is Map) {
      gtRaw.forEach((k, v) {
        if (v is num) groundTruthCm[k.toString()] = v.toDouble();
      });
    }

    final cmpRaw = json['ground_truth_comparison'];
    final comparison = <String, GroundTruthComparison>{};
    if (cmpRaw is Map) {
      cmpRaw.forEach((k, v) {
        if (v is Map<String, dynamic>) {
          comparison[k.toString()] = GroundTruthComparison.fromJson(v);
        }
      });
    }

    final subjectLabel = json['subject_label'] as String?;

    return ScanRecord(
      scanId: json['scan_id'] as String? ?? '',
      result: MeasurementResult.fromJson(measureMap),
      downloadUrl: json['download_url'] as String? ?? '',
      meshIncluded: json['mesh_included'] as bool? ?? false,
      createdAt: json['created_at'] as String?,
      subjectLabel: subjectLabel,
      groundTruthCm: groundTruthCm,
      groundTruthComparison: comparison,
    );
  }

  final String scanId;
  final MeasurementResult result;
  final String downloadUrl;
  final bool meshIncluded;
  final String? createdAt;
  final String? subjectLabel;

  String get displayName => scanDisplayName(subjectLabel: subjectLabel, scanId: scanId);
  final Map<String, double> groundTruthCm;
  final Map<String, GroundTruthComparison> groundTruthComparison;

  String bundleAbsoluteUrl(String apiBase) {
    final base = apiBase.replaceAll(RegExp(r'/+$'), '');
    final path = downloadUrl.startsWith('/') ? downloadUrl : '/$downloadUrl';
    return '$base$path';
  }
}
