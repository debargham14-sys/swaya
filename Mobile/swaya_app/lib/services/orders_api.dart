import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/blouse_order.dart';
import 'auth_token.dart';
import 'measure_api.dart' show MeasureApiException;

/// Talks to the `/v1/orders` backend (DynamoDB-backed, scoped to the signed-in
/// user). Same conventions as the other clients: Bearer token, FastAPI `detail`
/// surfaced via [MeasureApiException].
class OrdersApi {
  OrdersApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl =
            (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');
  static const _timeout = Duration(seconds: 30);

  Future<List<BlouseOrder>> list() async {
    final res = await _client
        .get(_uri(AppConfig.ordersPath), headers: await authHeaders())
        .timeout(_timeout);
    return _orders(_decode(res, 'Load orders'));
  }

  /// Places a new active order (status Processing) and returns it.
  Future<BlouseOrder> createOrder({
    String? placedOn,
    String? estimatedDate,
    String? location,
    double subtotal = 0,
    double shipping = 0,
    double total = 0,
    String? noteTitle,
    String? noteBody,
  }) async {
    final res = await _client
        .post(
          _uri(AppConfig.ordersPath),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({
            'category': 'active',
            'status': 'processing',
            'placed_on': placedOn,
            'estimated_date': estimatedDate,
            'location': location,
            'subtotal': subtotal,
            'shipping': shipping,
            'total': total,
            'tracking': const [
              {'label': 'Ordered', 'done': true},
              {'label': 'Processing', 'done': true},
              {'label': 'Shipped', 'done': false},
              {'label': 'Delivered', 'done': false},
            ],
            'note_title': noteTitle,
            'note_body': noteBody,
          }),
        )
        .timeout(_timeout);
    return BlouseOrder.fromJson(_decode(res, 'Place order'));
  }

  /// Loads the demo order set for the user (only if they have none).
  Future<List<BlouseOrder>> seedSamples() async {
    final res = await _client
        .post(_uri('${AppConfig.ordersPath}/seed'), headers: await authHeaders())
        .timeout(_timeout);
    return _orders(_decode(res, 'Seed orders'));
  }

  Future<BlouseOrder> cancel(String id, String reason) async {
    final res = await _client
        .post(
          _uri('${AppConfig.ordersPath}/$id/cancel'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({'reason': reason}),
        )
        .timeout(_timeout);
    return BlouseOrder.fromJson(_decode(res, 'Cancel order'));
  }

  Future<BlouseOrder> requestAlteration(String id, String description) async {
    final res = await _client
        .post(
          _uri('${AppConfig.ordersPath}/$id/alteration'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({'description': description}),
        )
        .timeout(_timeout);
    return BlouseOrder.fromJson(_decode(res, 'Request alteration'));
  }

  List<BlouseOrder> _orders(Map<String, dynamic> json) {
    final items = (json['orders'] as List?) ?? const [];
    return items
        .whereType<Map<String, dynamic>>()
        .map(BlouseOrder.fromJson)
        .toList();
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
