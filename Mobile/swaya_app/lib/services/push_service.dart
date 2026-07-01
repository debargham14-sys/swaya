import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import 'users_api.dart';

/// Messenger used to surface foreground push notifications as an in-app banner.
/// Wired onto [MaterialApp.router] in app.dart.
final GlobalKey<ScaffoldMessengerState> rootMessengerKey =
    GlobalKey<ScaffoldMessengerState>();

/// Background/terminated message handler. Must be a top-level function and
/// registered in main(). Notification-payload messages are shown by the OS
/// automatically; this exists so data-only messages don't get dropped.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // No-op: the OS renders the notification tray entry. Hook deep-linking here
  // later if needed.
}

/// Thin wrapper around [FirebaseMessaging]: requests permission, registers the
/// device token with the backend, and shows foreground notifications in-app.
/// All operations are best-effort — push must never block or crash the app.
class PushService {
  PushService._();
  static final PushService instance = PushService._();

  final FirebaseMessaging _fm = FirebaseMessaging.instance;
  bool _wired = false;
  String? _lastToken;

  /// Call once the user is signed in. Idempotent.
  Future<void> registerForUser() async {
    try {
      await _fm.requestPermission(alert: true, badge: true, sound: true);
      // iOS needs an APNs token resolved before an FCM token can be issued.
      await _fm.getAPNSToken();
      await _fm.setForegroundNotificationPresentationOptions(
          alert: true, badge: true, sound: true);

      final token = await _fm.getToken();
      if (token != null && token != _lastToken) {
        _lastToken = token;
        await UsersApi().registerFcmToken(token);
      }

      if (!_wired) {
        _wired = true;
        _fm.onTokenRefresh.listen((t) {
          _lastToken = t;
          UsersApi().registerFcmToken(t);
        });
        FirebaseMessaging.onMessage.listen(_showForeground);
      }
    } catch (_) {
      // Push is non-critical; swallow (missing APNs key, denied perms, etc.).
    }
  }

  void _showForeground(RemoteMessage message) {
    final n = message.notification;
    if (n == null) return;
    final messenger = rootMessengerKey.currentState;
    if (messenger == null) return;
    final text = [n.title, n.body].where((s) => (s ?? '').isNotEmpty).join(' — ');
    if (text.isEmpty) return;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(text),
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 4),
      ));
  }

  /// On sign-out, drop the token so a shared device doesn't keep receiving the
  /// previous user's pushes.
  Future<void> clearToken() async {
    try {
      _lastToken = null;
      await _fm.deleteToken();
    } catch (_) {}
  }
}
