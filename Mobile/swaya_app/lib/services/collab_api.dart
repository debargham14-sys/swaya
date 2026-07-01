import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/avatar_design.dart';
import '../models/collab_message.dart';
import '../models/collab_session.dart';
import 'auth_token.dart';
import 'measure_api.dart' show MeasureApiException;

/// Result of one polling `sync` round: the latest session/design + any messages
/// newer than the `since` cursor that was passed in.
class CollabSync {
  CollabSync({required this.session, required this.newMessages});
  final CollabSession session;
  final List<CollabMessage> newMessages;
}

/// Talks to `/v1/collab`. Membership-scoped server-side; the same Bearer-token
/// conventions as the other API clients.
class CollabApi {
  CollabApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl =
            (baseUrl ?? AppConfig.apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _baseUrl;

  String get _sessions => '${AppConfig.collabPath}/sessions';
  Uri _uri(String path) => Uri.parse('$_baseUrl$path');
  static const _timeout = Duration(seconds: 30);

  /// User starts a collaboration with [designerId], seeding the shared [design].
  Future<CollabSession> createSession(
      String designerId, AvatarDesign design) async {
    final res = await _client
        .post(
          _uri(_sessions),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({
            'designer_id': designerId,
            'design': design.toJson(),
          }),
        )
        .timeout(_timeout);
    return CollabSession.fromJson(_decode(res, 'Start collaboration'));
  }

  /// The caller's sessions for [role] (`user` | `designer`).
  Future<List<CollabSession>> listSessions(String role) async {
    final res = await _client
        .get(_uri('$_sessions?role=$role'), headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Load collaborations');
    return ((json['sessions'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(CollabSession.fromJson)
        .toList();
  }

  Future<CollabSession> getSession(String id) async {
    final res = await _client
        .get(_uri('$_sessions/$id'), headers: await authHeaders())
        .timeout(_timeout);
    return CollabSession.fromJson(_decode(res, 'Load session'));
  }

  /// The single polling endpoint: latest session + messages newer than [since].
  Future<CollabSync> sync(String id, {String? since}) async {
    final q = since == null ? '' : '?since=${Uri.encodeQueryComponent(since)}';
    final res = await _client
        .get(_uri('$_sessions/$id/sync$q'), headers: await authHeaders())
        .timeout(_timeout);
    final json = _decode(res, 'Sync');
    final session = CollabSession.fromJson(
        (json['session'] as Map).cast<String, dynamic>());
    final messages = ((json['messages'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(CollabMessage.fromJson)
        .toList();
    return CollabSync(session: session, newMessages: messages);
  }

  Future<CollabSession> accept(String id) async {
    final res = await _client
        .post(_uri('$_sessions/$id/accept'), headers: await authHeaders())
        .timeout(_timeout);
    return CollabSession.fromJson(_decode(res, 'Accept'));
  }

  Future<CollabSession> patchDesign(String id, AvatarDesign design) async {
    final res = await _client
        .patch(
          _uri('$_sessions/$id/design'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({'design': design.toJson()}),
        )
        .timeout(_timeout);
    return CollabSession.fromJson(_decode(res, 'Update design'));
  }

  Future<CollabMessage> sendMessage(String id, String text) async {
    final res = await _client
        .post(
          _uri('$_sessions/$id/messages'),
          headers: await authHeaders({'Content-Type': 'application/json'}),
          body: jsonEncode({'text': text}),
        )
        .timeout(_timeout);
    return CollabMessage.fromJson(_decode(res, 'Send message'));
  }

  Future<CollabSession> end(String id) async {
    final res = await _client
        .post(_uri('$_sessions/$id/end'), headers: await authHeaders())
        .timeout(_timeout);
    return CollabSession.fromJson(_decode(res, 'End session'));
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
