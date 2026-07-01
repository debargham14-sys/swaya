import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import '../models/designer.dart';
import '../services/auth_service.dart';
import '../services/designers_api.dart';
import '../services/push_service.dart';
import '../services/users_api.dart';

/// App-wide authentication state. Listens to Firebase auth changes and exposes
/// the current [User]; the router redirects off [status].
///
/// When Firebase fails to initialize (e.g. `flutterfire configure` not yet run)
/// the controller lands in [AuthStatus.unconfigured] so the rest of the app can
/// still be developed without crashing.
enum AuthStatus { unknown, unconfigured, signedOut, signedIn }

class AuthController extends ChangeNotifier {
  AuthController({AuthService? service, bool firebaseReady = true})
      : _service = service ?? AuthService() {
    if (!firebaseReady) {
      _status = AuthStatus.unconfigured;
      return;
    }
    _sub = _service.authStateChanges().listen(_onUserChanged);
  }

  final AuthService _service;
  final DesignersApi _designersApi = DesignersApi();
  StreamSubscription<User?>? _sub;

  AuthStatus _status = AuthStatus.unknown;
  User? _user;
  Designer? _designerProfile;
  bool _roleResolved = false;

  AuthStatus get status => _status;
  User? get user => _user;
  bool get isSignedIn => _status == AuthStatus.signedIn;
  AuthService get service => _service;

  /// The caller's own designer profile, if they are a designer (else null).
  Designer? get designerProfile => _designerProfile;

  /// True once the role lookup has completed (drives the router's landing).
  bool get roleResolved => _roleResolved;
  bool get isDesigner => _designerProfile != null;

  void _onUserChanged(User? user) {
    _user = user;
    _status = user == null ? AuthStatus.signedOut : AuthStatus.signedIn;
    _designerProfile = null;
    _roleResolved = user == null; // nothing to resolve when signed out
    notifyListeners();
    if (user != null) {
      _syncUser(user);
      _resolveRole();
      // Register this device for push (collab invites/messages). Best-effort.
      PushService.instance.registerForUser();
    }
  }

  /// Persist the signed-in user's profile to DynamoDB (best-effort, fire-and-forget).
  void _syncUser(User user) {
    UsersApi().syncMe(
      email: user.email,
      name: user.displayName,
      phone: user.phoneNumber,
    );
  }

  /// Look up whether this account is a designer; the router redirects designers
  /// into their console once this resolves. Best-effort — failures land the user
  /// in the normal (consumer) experience.
  Future<void> _resolveRole() async {
    try {
      _designerProfile = await _designersApi.me();
    } catch (_) {
      _designerProfile = null;
    } finally {
      _roleResolved = true;
      notifyListeners();
    }
  }

  /// Re-fetch the designer role (e.g. right after a user registers as a designer).
  Future<void> refreshRole() => _resolveRole();

  Future<void> signOut() async {
    await PushService.instance.clearToken();
    await _service.signOut();
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}
