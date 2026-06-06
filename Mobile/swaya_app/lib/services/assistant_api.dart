import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/measurement_result.dart';
import 'measure_api.dart';

class FitSuggestion {
  FitSuggestion({
    required this.suggestions,
    required this.source,
    this.garments = const [],
  });

  factory FitSuggestion.fromJson(Map<String, dynamic> json) {
    return FitSuggestion(
      suggestions: json['suggestions'] as String? ?? '',
      source: json['source'] as String? ?? 'rules',
      garments: (json['garments'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
    );
  }

  final String suggestions;
  final String source;
  final List<String> garments;
}

class AssistantApi {
  AssistantApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, dynamic> _measurementsPayload(MeasurementResult m) => {
        'girths_cm': m.girthsCm,
        'girths_in': m.girthsIn,
        if (m.heightCm != null) 'height_cm': m.heightCm,
        if (m.weightKg != null) 'weight_kg': m.weightKg,
        if (m.confidence != null) 'confidence': m.confidence,
        if (m.calibrationProfile != null) 'calibration_profile': m.calibrationProfile,
      };

  Future<FitSuggestion> suggest({
    required MeasurementResult measurements,
    bool calibrated = false,
    String? context,
  }) async {
    final body = <String, dynamic>{
      'measurements': _measurementsPayload(measurements),
      'calibrated': calibrated,
      if (context != null) 'context': context,
    };

    final res = await _client
        .post(
          _uri(AppConfig.assistantSuggestPath),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 60));

    if (res.statusCode >= 200 && res.statusCode < 300) {
      return FitSuggestion.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
    }

    String detail = res.body;
    try {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      detail = err['detail']?.toString() ?? res.body;
    } catch (_) {}

    throw MeasureApiException(
      detail.isEmpty ? 'Assistant unavailable (${res.statusCode})' : detail,
      statusCode: res.statusCode,
    );
  }

  Future<String> chat({
    required MeasurementResult measurements,
    required String message,
    List<Map<String, String>> history = const [],
  }) async {
    final res = await _client
        .post(
          _uri(AppConfig.assistantChatPath),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'measurements': _measurementsPayload(measurements),
            'message': message,
            'history': history,
          }),
        )
        .timeout(const Duration(seconds: 60));

    if (res.statusCode >= 200 && res.statusCode < 300) {
      final json = jsonDecode(res.body) as Map<String, dynamic>;
      return json['reply'] as String? ?? '';
    }

    String detail = res.body;
    try {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      detail = err['detail']?.toString() ?? res.body;
    } catch (_) {}

    throw MeasureApiException(
      detail.isEmpty ? 'Chat failed (${res.statusCode})' : detail,
      statusCode: res.statusCode,
    );
  }
}
