import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/avatar_design.dart';
import '../models/collab_message.dart';
import '../models/collab_session.dart';
import '../services/collab_api.dart';

/// Drives one collaboration session for the [CollabAvatarScreen]: polls the
/// backend `sync` endpoint on an interval, exposes the shared [design] +
/// [messages], and applies local edits optimistically before persisting.
///
/// There is no realtime transport — "live" is ~2.5s polling. The screen
/// re-applies the avatar materials whenever [designTick] advances (a local edit
/// or a remote one picked up by a poll).
class CollabController extends ChangeNotifier {
  CollabController({
    CollabApi? api,
    this.pollInterval = const Duration(milliseconds: 2500),
  }) : _api = api ?? CollabApi();

  final CollabApi _api;
  final Duration pollInterval;

  String? _sessionId;
  String _role = 'user';
  CollabSession? _session;
  AvatarDesign _design = const AvatarDesign();
  final List<CollabMessage> _messages = [];
  int _version = 1;
  int _designTick = 0;
  String? _since;
  Timer? _timer;
  bool _disposed = false;
  bool _sending = false;
  String? _error;

  CollabSession? get session => _session;
  AvatarDesign get design => _design;
  List<CollabMessage> get messages => List.unmodifiable(_messages);
  int get version => _version;

  /// Increments every time [design] is replaced; the screen re-applies the
  /// avatar materials when it sees this change.
  int get designTick => _designTick;
  String get role => _role;
  bool get sending => _sending;
  String? get error => _error;
  String get status => _session?.status ?? 'pending';

  /// Was the most recent design edit made by the *other* participant?
  bool get editedByOther =>
      _session?.updatedBy != null && _session!.updatedBy != _role;

  /// Begin a session: load it once, then start polling.
  Future<void> start(
    String sessionId, {
    required String role,
    AvatarDesign? seed,
  }) async {
    _sessionId = sessionId;
    _role = role;
    if (seed != null) {
      _design = seed;
      _designTick++;
    }
    await _refresh(initial: true);
    _timer?.cancel();
    _timer = Timer.periodic(pollInterval, (_) => _refresh());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _refresh({bool initial = false}) async {
    final id = _sessionId;
    if (id == null) return;
    try {
      final res = await _api.sync(id, since: _since);
      _error = null;
      var changed = initial;

      if (res.newMessages.isNotEmpty) {
        _messages.addAll(res.newMessages);
        _since = res.newMessages.last.createdAtIso ?? _since;
        changed = true;
      }

      final s = res.session;
      final statusOrBadgeChanged = _session == null ||
          s.status != _session!.status ||
          s.unreadFor(_role) != _session!.unreadFor(_role);
      _session = s;

      // A version bump means someone edited the shared design — adopt it and
      // signal a re-apply. (Our own edits already bumped _version locally, so
      // they won't double-apply.)
      if (s.version != _version || initial) {
        _version = s.version;
        _design = s.design;
        _designTick++;
        changed = true;
      } else if (statusOrBadgeChanged) {
        changed = true;
      }

      if (changed && !_disposed) notifyListeners();
    } catch (e) {
      _error = e.toString();
      if (!_disposed) notifyListeners();
    }
  }

  /// Apply a local design edit: update immediately (optimistic) then persist.
  Future<void> updateDesign(AvatarDesign design) async {
    _design = design;
    _designTick++;
    notifyListeners();
    final id = _sessionId;
    if (id == null) return;
    try {
      final updated = await _api.patchDesign(id, design);
      _version = updated.version;
      _session = updated;
      _error = null;
    } catch (e) {
      _error = e.toString();
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> sendMessage(String text) async {
    final id = _sessionId;
    final trimmed = text.trim();
    if (id == null || trimmed.isEmpty) return;
    _sending = true;
    notifyListeners();
    try {
      final msg = await _api.sendMessage(id, trimmed);
      _messages.add(msg);
      _since = msg.createdAtIso ?? _since;
      _error = null;
    } catch (e) {
      _error = e.toString();
    } finally {
      _sending = false;
      if (!_disposed) notifyListeners();
    }
  }

  /// Designer accepts a pending request (status -> active).
  Future<void> accept() async {
    final id = _sessionId;
    if (id == null) return;
    try {
      _session = await _api.accept(id);
      if (!_disposed) notifyListeners();
    } catch (e) {
      _error = e.toString();
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> end() async {
    final id = _sessionId;
    if (id == null) return;
    try {
      _session = await _api.end(id);
      if (!_disposed) notifyListeners();
    } catch (e) {
      _error = e.toString();
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
