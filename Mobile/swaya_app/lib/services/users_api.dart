import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'auth_token.dart';

/// Syncs the signed-in user's profile to the `/v1/users/me` backend (DynamoDB).
/// The backend also reads email/name/phone straight from the verified Firebase
/// token, so an empty body still creates a durable user record.
class UsersApi {
  UsersApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? AppConfig.apiBaseUrl)
            .replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  /// Best-effort upsert of the current user. Returns true on success; never
  /// throws (called fire-and-forget right after sign-in).
  Future<bool> syncMe({String? email, String? name, String? phone}) async {
    try {
      final res = await _client
          .post(
            Uri.parse('$_baseUrl${AppConfig.userSyncPath}'),
            headers: await authHeaders({'Content-Type': 'application/json'}),
            body: jsonEncode({
              if (email != null) 'email': email,
              if (name != null) 'name': name,
              if (phone != null) 'phone': phone,
            }),
          )
          .timeout(const Duration(seconds: 20));
      return res.statusCode >= 200 && res.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  /// Register this device's FCM token so the backend can push notifications
  /// (collab invites/messages). Best-effort; never throws.
  Future<bool> registerFcmToken(String token) async {
    try {
      final res = await _client
          .post(
            Uri.parse('$_baseUrl${AppConfig.userSyncPath}/fcm-token'),
            headers: await authHeaders({'Content-Type': 'application/json'}),
            body: jsonEncode({'token': token}),
          )
          .timeout(const Duration(seconds: 20));
      return res.statusCode >= 200 && res.statusCode < 300;
    } catch (_) {
      return false;
    }
  }
}
