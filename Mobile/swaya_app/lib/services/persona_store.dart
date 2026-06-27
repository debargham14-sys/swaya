import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/persona.dart';
import 'personas_api.dart';

/// Personas persistence (Figma frames 18–21).
///
/// Backed by the `/v1/personas` DynamoDB API (scoped to the signed-in user by
/// the Firebase token), with a per-user shared_preferences **cache** so the list
/// still renders offline. Writes go to the backend and mirror into the cache;
/// reads prefer the backend and fall back to the cache on network failure.
///
/// Public API (list/upsert/delete) is unchanged from the old local-only store.
class PersonaStore {
  PersonaStore({this.userId, PersonasApi? api}) : _api = api ?? PersonasApi();

  /// Namespaces the local cache to the current user (falls back to 'local').
  final String? userId;
  final PersonasApi _api;

  String get _key => 'personas_${userId ?? 'local'}';

  Future<List<Persona>> list() async {
    try {
      final personas = await _api.list();
      await _writeCache(personas);
      return personas;
    } catch (e) {
      debugPrint('PersonaStore.list: backend unavailable, using cache ($e)');
      return _readCache();
    }
  }

  /// Insert or update by id. Returns the saved persona.
  Future<Persona> upsert(Persona persona) async {
    final stamped = persona.copyWith(
      updatedAtIso: DateTime.now().toIso8601String(),
    );
    Persona saved = stamped;
    try {
      saved = await _api.upsert(stamped);
    } catch (e) {
      // Keep the flow alive offline — cache locally so it isn't lost.
      debugPrint('PersonaStore.upsert: backend failed, cached locally ($e)');
    }
    await _upsertCache(saved);
    return saved;
  }

  Future<void> delete(String id) async {
    try {
      await _api.delete(id);
    } catch (e) {
      debugPrint('PersonaStore.delete: backend failed ($e)');
    }
    final personas = await _readCache()
      ..removeWhere((p) => p.id == id);
    await _writeCache(personas);
  }

  // --- local cache ----------------------------------------------------------

  Future<List<Persona>> _readCache() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) return [];
    final decoded = jsonDecode(raw) as List<dynamic>;
    return decoded
        .whereType<Map<String, dynamic>>()
        .map(Persona.fromJson)
        .toList();
  }

  Future<void> _writeCache(List<Persona> personas) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _key,
      jsonEncode(personas.map((p) => p.toJson()).toList()),
    );
  }

  Future<void> _upsertCache(Persona persona) async {
    final personas = await _readCache();
    final idx = personas.indexWhere((p) => p.id == persona.id);
    if (idx >= 0) {
      personas[idx] = persona;
    } else {
      personas.add(persona);
    }
    await _writeCache(personas);
  }

  /// Generates a unique-enough persona id (used as the backend key).
  static String newId() =>
      'p_${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
}
