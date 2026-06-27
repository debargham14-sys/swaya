import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

import '../services/auth_service.dart';
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
  StreamSubscription<User?>? _sub;

  AuthStatus _status = AuthStatus.unknown;
  User? _user;

  AuthStatus get status => _status;
  User? get user => _user;
  bool get isSignedIn => _status == AuthStatus.signedIn;
  AuthService get service => _service;

  void _onUserChanged(User? user) {
    _user = user;
    _status = user == null ? AuthStatus.signedOut : AuthStatus.signedIn;
    notifyListeners();
    if (user != null) _syncUser(user);
  }

  /// Persist the signed-in user's profile to DynamoDB (best-effort, fire-and-forget).
  void _syncUser(User user) {
    UsersApi().syncMe(
      email: user.email,
      name: user.displayName,
      phone: user.phoneNumber,
    );
  }

  Future<void> signOut() async {
    await _service.signOut();
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}
