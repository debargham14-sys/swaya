import 'package:firebase_auth/firebase_auth.dart';

/// Returns the current Firebase ID token, or null when signed out / Firebase is
/// not configured. Safe to call from any API client.
Future<String?> currentIdToken({bool forceRefresh = false}) async {
  try {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) return null;
    return await user.getIdToken(forceRefresh);
  } catch (_) {
    // Firebase not initialized (placeholder config) — treat as signed out.
    return null;
  }
}

/// Builds request headers, adding `Authorization: Bearer <token>` when signed
/// in. Merges any [extra] headers (e.g. content-type).
Future<Map<String, String>> authHeaders([Map<String, String>? extra]) async {
  final headers = <String, String>{if (extra != null) ...extra};
  final token = await currentIdToken();
  if (token != null) headers['Authorization'] = 'Bearer $token';
  return headers;
}
