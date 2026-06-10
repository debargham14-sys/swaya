import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/captured_photo.dart';
import '../models/vest_measurement.dart';
import 'measure_api.dart' show MeasureApiException;

/// Client for the ChArUco vest measurement endpoints (POST /v1/vest, beta).
class VestApi {
  VestApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<VestScanResult> createVestScan({
    required CapturedPhoto front,
    CapturedPhoto? sideLeft,
    CapturedPhoto? sideRight,
    String? subjectLabel,
    String? collectorId,
    bool? consentGiven,
    String? notes,
    double? bustIn,
    double? waistIn,
    double? hipIn,
    double? heightCm,
  }) async {
    final request = http.MultipartRequest('POST', _uri(AppConfig.vestScanPath));

    void field(String name, String? value) {
      if (value != null && value.isNotEmpty) request.fields[name] = value;
    }

    field('subject_label', subjectLabel);
    field('collector_id', collectorId);
    if (consentGiven != null) request.fields['consent_given'] = consentGiven.toString();
    field('notes', notes);
    if (bustIn != null) request.fields['bust_in'] = bustIn.toString();
    if (waistIn != null) request.fields['waist_in'] = waistIn.toString();
    if (hipIn != null) request.fields['hip_in'] = hipIn.toString();
    if (heightCm != null) request.fields['height_cm'] = heightCm.toString();

    void attach(String name, CapturedPhoto? photo) {
      if (photo == null) return;
      request.files.add(
        http.MultipartFile.fromBytes(name, photo.bytes, filename: photo.filename),
      );
    }

    attach('front', front);
    attach('side_left', sideLeft);
    attach('side_right', sideRight);

    final streamed = await _client.send(request).timeout(const Duration(minutes: 3));
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode >= 200 && streamed.statusCode < 300) {
      return VestScanResult.fromJson(jsonDecode(body) as Map<String, dynamic>);
    }

    String detail = body;
    try {
      detail = (jsonDecode(body) as Map<String, dynamic>)['detail']?.toString() ?? body;
    } catch (_) {}
    throw MeasureApiException(
      detail.isEmpty ? 'Vest scan failed (${streamed.statusCode})' : detail,
      statusCode: streamed.statusCode,
    );
  }

  Future<VestScanResult> saveGroundTruth({
    required String scanId,
    double? bustIn,
    double? waistIn,
    double? hipIn,
    double? heightCm,
  }) async {
    final body = <String, dynamic>{};
    if (bustIn != null) body['bust_in'] = bustIn;
    if (waistIn != null) body['waist_in'] = waistIn;
    if (hipIn != null) body['hip_in'] = hipIn;
    if (heightCm != null) body['height_cm'] = heightCm;

    final res = await _client.patch(
      _uri('${AppConfig.vestScanPath}/$scanId/ground-truth'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (res.statusCode >= 200 && res.statusCode < 300) {
      return VestScanResult.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
    }
    throw MeasureApiException('Could not save ground truth (${res.statusCode})', statusCode: res.statusCode);
  }
}
