import 'measurement_result.dart';

class ScanRecord {
  ScanRecord({
    required this.scanId,
    required this.result,
    required this.downloadUrl,
    this.meshIncluded = false,
    this.createdAt,
  });

  factory ScanRecord.fromJson(Map<String, dynamic> json) {
    final measurements = json['measurements'];
    final Map<String, dynamic> measureMap = measurements is Map<String, dynamic>
        ? measurements
        : json;
    return ScanRecord(
      scanId: json['scan_id'] as String? ?? '',
      result: MeasurementResult.fromJson(measureMap),
      downloadUrl: json['download_url'] as String? ?? '',
      meshIncluded: json['mesh_included'] as bool? ?? false,
      createdAt: json['created_at'] as String?,
    );
  }

  final String scanId;
  final MeasurementResult result;
  final String downloadUrl;
  final bool meshIncluded;
  final String? createdAt;

  String bundleAbsoluteUrl(String apiBase) {
    final base = apiBase.replaceAll(RegExp(r'/+$'), '');
    final path = downloadUrl.startsWith('/') ? downloadUrl : '/$downloadUrl';
    return '$base$path';
  }
}
