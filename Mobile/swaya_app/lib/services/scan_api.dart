import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/captured_photo.dart';
import '../models/scan_record.dart';
import 'measure_api.dart';

class ScanApi {
  ScanApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$_baseUrl$path').replace(queryParameters: query);

  Future<ScanRecord> createScan({
    required CapturedPhoto front,
    required CapturedPhoto back,
    required CapturedPhoto side,
    required double heightCm,
    double? weightKg,
    String? subjectLabel,
    String? collectorId,
    bool? consentGiven,
  }) async {
    final request = http.MultipartRequest('POST', _uri(AppConfig.scansPath));
    request.fields['mode'] = 'height';
    request.fields['height_cm'] = heightCm.toString();
    request.fields['prefer'] = 'photo';
    if (weightKg != null) {
      request.fields['weight_kg'] = weightKg.toString();
    }
    if (subjectLabel != null && subjectLabel.isNotEmpty) {
      request.fields['subject_label'] = subjectLabel;
    }
    if (collectorId != null && collectorId.isNotEmpty) {
      request.fields['collector_id'] = collectorId;
    }
    if (consentGiven != null) {
      request.fields['consent_given'] = consentGiven.toString();
    }

    void attach(String name, CapturedPhoto photo) {
      request.files.add(
        http.MultipartFile.fromBytes(name, photo.bytes, filename: photo.filename),
      );
    }

    attach('front', front);
    attach('back', back);
    attach('side', side);

    final streamed = await _client.send(request).timeout(const Duration(minutes: 5));
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode >= 200 && streamed.statusCode < 300) {
      final json = jsonDecode(body) as Map<String, dynamic>;
      return ScanRecord.fromJson(json);
    }

    String detail = body;
    try {
      final err = jsonDecode(body) as Map<String, dynamic>;
      detail = err['detail']?.toString() ?? body;
    } catch (_) {}

    throw MeasureApiException(
      detail.isEmpty ? 'Scan upload failed (${streamed.statusCode})' : detail,
      statusCode: streamed.statusCode,
    );
  }

  Future<List<ScanRecord>> listScans({int limit = 30}) async {
    final res = await _client.get(_uri(AppConfig.scansPath, {'limit': '$limit'}));
    if (res.statusCode != 200) {
      throw MeasureApiException('Failed to list scans (${res.statusCode})', statusCode: res.statusCode);
    }
    final json = jsonDecode(res.body) as Map<String, dynamic>;
    final list = json['scans'] as List<dynamic>? ?? [];
    return list
        .whereType<Map<String, dynamic>>()
        .map(ScanRecord.fromJson)
        .toList();
  }
}
