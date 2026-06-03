import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/captured_photo.dart';
import '../models/measurement_result.dart';

class MeasureApiException implements Exception {
  MeasureApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class MeasureApi {
  MeasureApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<bool> healthCheck() async {
    try {
      final res = await _client.get(_uri(AppConfig.healthPath)).timeout(const Duration(seconds: 90));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<MeasurementResult> measureWithHeight({
    required CapturedPhoto front,
    required CapturedPhoto back,
    required CapturedPhoto side,
    required double heightCm,
    double? weightKg,
  }) async {
    final request = http.MultipartRequest('POST', _uri(AppConfig.measureHeightPath));
    request.fields['height_cm'] = heightCm.toString();
    if (weightKg != null) {
      request.fields['weight_kg'] = weightKg.toString();
    }

    void attach(String name, CapturedPhoto photo) {
      request.files.add(
        http.MultipartFile.fromBytes(
          name,
          photo.bytes,
          filename: photo.filename,
        ),
      );
    }

    attach('front', front);
    attach('back', back);
    attach('side', side);

    final streamed = await _client.send(request).timeout(const Duration(minutes: 3));
    final body = await streamed.stream.bytesToString();

    if (streamed.statusCode >= 200 && streamed.statusCode < 300) {
      final json = jsonDecode(body) as Map<String, dynamic>;
      return MeasurementResult.fromJson(json);
    }

    String detail = body;
    try {
      final err = jsonDecode(body) as Map<String, dynamic>;
      detail = err['detail']?.toString() ?? body;
    } catch (_) {}

    throw MeasureApiException(
      detail.isEmpty ? 'Measurement failed (${streamed.statusCode})' : detail,
      statusCode: streamed.statusCode,
    );
  }
}
