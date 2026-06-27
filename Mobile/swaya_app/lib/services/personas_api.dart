import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/persona.dart';
import 'auth_token.dart';
import 'measure_api.dart' show MeasureApiException;

/// Talks to the `/v1/personas` backend (DynamoDB-backed). Mirrors the other API
/// clients: base URL from [AppConfig], Firebase ID token attached as a Bearer
/// header, FastAPI `detail` surfaced via [MeasureApiException].
class PersonasApi {
  PersonasApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl)
            .replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  static const _timeout = Duration(seconds: 30);

  Future<List<Persona>> list() async {
    final res = await _client
        .get(_uri(AppConfig.personasPath), headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Load personas');
    final items = (json['personas'] as List?) ?? const [];
    return items
        .whereType<Map<String, dynamic>>()
        .map(Persona.fromJson)
        .toList();
  }

  Future<Persona> upsert(Persona persona) async {
    final res = await _client
        .put(
          _uri('${AppConfig.personasPath}/${persona.id}'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({
            'name': persona.name,
            'label': persona.label,
            'gender': persona.gender,
            'measurements': persona.measurements.toJson(),
          }),
        )
        .timeout(_timeout);
    return Persona.fromJson(_decode(res, 'Save persona'));
  }

  Future<void> delete(String id) async {
    final res = await _client
        .delete(_uri('${AppConfig.personasPath}/$id'),
            headers: await authHeaders())
        .timeout(_timeout);
    _decode(res, 'Delete persona');
  }

  Map<String, dynamic> _decode(http.Response res, String action) {
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.body.isEmpty) return {};
      return jsonDecode(res.body) as Map<String, dynamic>;
    }
    String message = '$action failed (${res.statusCode})';
    try {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      if (err['detail'] is String) message = err['detail'] as String;
    } catch (_) {/* keep fallback */}
    throw MeasureApiException(message, statusCode: res.statusCode);
  }
}
