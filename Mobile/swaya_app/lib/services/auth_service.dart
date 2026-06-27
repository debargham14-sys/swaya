import 'dart:async';

import 'package:flutter/foundation.dart' show debugPrint, kIsWeb;
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';

/// A friendly, user-facing auth failure. Screens show [message] directly.
class AuthFailure implements Exception {
  AuthFailure(this.message, {this.code});
  final String message;
  final String? code;

  @override
  String toString() => message;
}

/// Result of starting a phone-number verification.
///
/// On Android the SMS code may be auto-retrieved, in which case
/// [autoCredential] is non-null and the caller can sign in without an OTP
/// screen. Otherwise the caller collects the code and calls
/// [AuthService.confirmSmsCode] with [verificationId].
class PhoneVerification {
  PhoneVerification({
    required this.verificationId,
    this.resendToken,
    this.autoCredential,
  });

  final String verificationId;
  final int? resendToken;
  final PhoneAuthCredential? autoCredential;
}

/// Thin wrapper over [FirebaseAuth] exposing every sign-in method the app
/// supports: phone OTP, email/password (+ reset), Google, and Apple.
///
/// All methods translate Firebase exceptions into [AuthFailure] with a
/// human-readable [AuthFailure.message] so the UI never has to interpret raw
/// Firebase error codes.
class AuthService {
  AuthService({FirebaseAuth? auth, GoogleSignIn? googleSignIn})
      : _authOverride = auth,
        _googleSignIn = googleSignIn ?? GoogleSignIn();

  // Accessed lazily so constructing AuthService never touches FirebaseAuth.instance
  // before Firebase.initializeApp() has run (which throws [core/no-app]).
  final FirebaseAuth? _authOverride;
  final GoogleSignIn _googleSignIn;

  FirebaseAuth get _auth => _authOverride ?? FirebaseAuth.instance;

  /// Emits on sign-in, sign-out, and token refresh.
  Stream<User?> authStateChanges() => _auth.authStateChanges();

  User? get currentUser => _auth.currentUser;

  /// Current Firebase ID token (a JWT) for authenticating API calls.
  /// Returns null when signed out. Pass [forceRefresh] to bypass the cache.
  Future<String?> idToken({bool forceRefresh = false}) async {
    final user = _auth.currentUser;
    if (user == null) return null;
    try {
      return await user.getIdToken(forceRefresh);
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  // --- Email / password -----------------------------------------------------

  Future<User> signInWithEmail(String email, String password) async {
    try {
      final cred = await _auth.signInWithEmailAndPassword(
        email: email.trim(),
        password: password,
      );
      return cred.user!;
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  Future<User> registerWithEmail(String email, String password) async {
    try {
      final cred = await _auth.createUserWithEmailAndPassword(
        email: email.trim(),
        password: password,
      );
      return cred.user!;
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  Future<void> sendPasswordReset(String email) async {
    try {
      await _auth.sendPasswordResetEmail(email: email.trim());
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  // --- Phone / OTP ----------------------------------------------------------

  /// Kicks off phone verification. Resolves once Firebase has either sent an
  /// SMS (returning a [verificationId]) or auto-resolved the credential.
  ///
  /// [phoneE164] must be in E.164 form, e.g. `+919876543210`.
  Future<PhoneVerification> startPhoneVerification(
    String phoneE164, {
    int? resendToken,
  }) async {
    final completer = _PhoneCompleter();
    await _auth.verifyPhoneNumber(
      phoneNumber: phoneE164.trim(),
      forceResendingToken: resendToken,
      verificationCompleted: (cred) =>
          completer.complete(autoCredential: cred, verificationId: ''),
      verificationFailed: (e) => completer.fail(_mapError(e)),
      codeSent: (verificationId, token) => completer.complete(
        verificationId: verificationId,
        resendToken: token,
      ),
      codeAutoRetrievalTimeout: (verificationId) =>
          completer.completeIfPending(verificationId: verificationId),
    );
    return completer.future;
  }

  /// Confirms an SMS code the user typed against a prior [verificationId].
  Future<User> confirmSmsCode(String verificationId, String smsCode) async {
    try {
      final cred = PhoneAuthProvider.credential(
        verificationId: verificationId,
        smsCode: smsCode.trim(),
      );
      final result = await _auth.signInWithCredential(cred);
      return result.user!;
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  /// Signs in directly with an auto-retrieved phone credential (Android).
  Future<User> signInWithPhoneCredential(PhoneAuthCredential cred) async {
    try {
      final result = await _auth.signInWithCredential(cred);
      return result.user!;
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  // --- Google ---------------------------------------------------------------

  Future<User> signInWithGoogle() async {
    try {
      // Web: use Firebase's popup flow (the google_sign_in plugin needs a GIS
      // client-id meta tag and asserts without it). Native: credential flow.
      if (kIsWeb) {
        final provider = GoogleAuthProvider();
        final result = await _auth.signInWithPopup(provider);
        return result.user!;
      }
      final account = await _googleSignIn.signIn();
      if (account == null) {
        throw AuthFailure('Sign-in cancelled.', code: 'cancelled');
      }
      final googleAuth = await account.authentication;
      final cred = GoogleAuthProvider.credential(
        accessToken: googleAuth.accessToken,
        idToken: googleAuth.idToken,
      );
      final result = await _auth.signInWithCredential(cred);
      return result.user!;
    } on FirebaseAuthException catch (e) {
      throw _mapError(e);
    }
  }

  // --- Apple ----------------------------------------------------------------
  // Apple sign-in is temporarily removed: the sign_in_with_apple framework can't
  // code-sign with a personal (free) Apple ID, and Apple sign-in requires the
  // paid Apple Developer Program regardless. Re-add the `sign_in_with_apple`
  // dependency + a signInWithApple() method once enrolled; until then the UI
  // hides the button via [isAppleAvailable].
  bool get isAppleAvailable => false;

  // --- Session --------------------------------------------------------------

  Future<void> signOut() async {
    await _googleSignIn.signOut();
    await _auth.signOut();
  }

  AuthFailure _mapError(FirebaseAuthException e) {
    debugPrint('[auth] FirebaseAuthException code=${e.code} message=${e.message}');
    // operation-not-allowed covers both "provider disabled" and "SMS region not
    // allowed" — disambiguate so the message is actionable.
    if (e.code == 'operation-not-allowed' &&
        (e.message?.toLowerCase().contains('region') ?? false)) {
      return AuthFailure(
        'SMS to this region is not enabled yet. In Firebase console → '
        'Authentication → Settings → SMS region policy, allow your region — '
        'or add a test phone number.',
        code: e.code,
      );
    }
    final message = switch (e.code) {
      'invalid-email' => 'That email address looks invalid.',
      'user-disabled' => 'This account has been disabled.',
      'user-not-found' ||
      'wrong-password' ||
      'invalid-credential' =>
        'Incorrect email or password.',
      'email-already-in-use' => 'An account already exists for that email.',
      'weak-password' => 'Choose a stronger password (at least 6 characters).',
      'invalid-verification-code' => 'That code is incorrect. Try again.',
      'invalid-phone-number' => 'That phone number looks invalid.',
      'too-many-requests' => 'Too many attempts. Please wait and try again.',
      'account-exists-with-different-credential' =>
        'You already signed up with a different method for this email.',
      'network-request-failed' => 'Network error. Check your connection.',
      'operation-not-allowed' =>
        'This sign-in method is not enabled for the project.',
      'configuration-not-found' =>
        'Sign-in is not set up yet. Enable Authentication in the Firebase console.',
      _ => 'Authentication failed. Please try again.',
    };
    return AuthFailure(message, code: e.code);
  }
}

/// Bridges Firebase's multi-callback [verifyPhoneNumber] into a single Future.
class _PhoneCompleter {
  final _completer = Completer<PhoneVerification>();

  Future<PhoneVerification> get future => _completer.future;

  void complete({
    required String verificationId,
    int? resendToken,
    PhoneAuthCredential? autoCredential,
  }) {
    if (_completer.isCompleted) return;
    _completer.complete(PhoneVerification(
      verificationId: verificationId,
      resendToken: resendToken,
      autoCredential: autoCredential,
    ));
  }

  void completeIfPending({required String verificationId}) {
    if (_completer.isCompleted) return;
    complete(verificationId: verificationId);
  }

  void fail(AuthFailure error) {
    if (_completer.isCompleted) return;
    _completer.completeError(error);
  }
}
