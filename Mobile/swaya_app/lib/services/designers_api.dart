import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/designer.dart';
import 'auth_token.dart';
import 'measure_api.dart' show MeasureApiException;

/// Talks to `/v1/designers` (DynamoDB-backed). Browsing the directory is open to
/// any signed-in user; `me`/`register` manage the caller's own profile. Same
/// conventions as [OrdersApi]: Bearer token, FastAPI `detail` surfaced.
class DesignersApi {
  DesignersApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl =
            (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');
  static const _timeout = Duration(seconds: 30);

  /// The designer directory. [availableOnly] filters to available designers.
  Future<List<Designer>> list({bool availableOnly = false}) async {
    final path =
        '${AppConfig.designersPath}${availableOnly ? '?available=1' : ''}';
    final res = await _client
        .get(_uri(path), headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Load designers');
    return ((json['designers'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(Designer.fromJson)
        .toList();
  }

  Future<Designer> get(String id) async {
    final res = await _client
        .get(_uri('${AppConfig.designersPath}/$id'), headers: await authHeaders())
        .timeout(_timeout);
    return Designer.fromJson(_decode(res, 'Load designer'));
  }

  /// The caller's own designer profile, or null if they aren't a designer.
  /// Used by the router to decide whether to land them in the designer console.
  Future<Designer?> me() async {
    final res = await _client
        .get(_uri('${AppConfig.designersPath}/me'), headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Load profile');
    final d = json['designer'];
    return d is Map<String, dynamic> ? Designer.fromJson(d) : null;
  }

  /// Register as / update the caller's designer profile.
  Future<Designer> upsertMe(Designer profile) async {
    final res = await _client
        .post(
          _uri('${AppConfig.designersPath}/me'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode(profile.toJson()),
        )
        .timeout(_timeout);
    return Designer.fromJson(_decode(res, 'Save profile'));
  }

  Future<List<Designer>> seedSamples() async {
    final res = await _client
        .post(_uri('${AppConfig.designersPath}/seed'),
            headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Seed designers');
    return ((json['designers'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(Designer.fromJson)
        .toList();
  }

  Future<Designer> rate(String id, double stars) async {
    final res = await _client
        .post(
          _uri('${AppConfig.designersPath}/$id/rating'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({'stars': stars}),
        )
        .timeout(_timeout);
    return Designer.fromJson(_decode(res, 'Rate designer'));
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
