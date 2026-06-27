import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_controller.dart';
import '../../services/auth_service.dart';
import '../../theme/swaya_light_theme.dart';
import 'auth_widgets.dart';

/// Login — Figma frames 2 (Password), 3 (OTP request) and 4 (OTP verify).
/// A Password/OTP toggle switches between email+password sign-in and
/// mobile-number OTP sign-in. Social + "create account" round it out.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  int _mode = 0; // 0 = Password, 1 = OTP
  bool _busy = false;
  bool _obscure = true;

  final _identifier = TextEditingController(); // email or mobile
  final _password = TextEditingController();

  // OTP sub-state
  bool _otpSent = false;
  String? _verificationId;
  int? _resendToken;
  String _otp = '';

  AuthService get _auth => context.read<AuthController>().service;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  bool get _looksLikeEmail => _identifier.text.contains('@');

  String get _phoneE164 {
    var v = _identifier.text.trim().replaceAll(RegExp(r'[\s-]'), '');
    if (!v.startsWith('+')) v = '+91$v'; // default to India dial code
    return v;
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
    } on AuthFailure catch (e) {
      if (e.code != 'cancelled' && mounted) _snack(e.message);
    } catch (_) {
      if (mounted) _snack('Something went wrong. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _snack(String m) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(m)));
  }

  Future<void> _passwordLogin() async {
    if (_looksLikeEmail == false) {
      _snack('Enter your email to sign in with a password, or use OTP.');
      return;
    }
    if (_password.text.isEmpty) {
      _snack('Enter your password.');
      return;
    }
    await _run(() => _auth.signInWithEmail(_identifier.text, _password.text));
  }

  Future<void> _sendOtp() async {
    if (_looksLikeEmail) {
      _snack('OTP sign-in is for mobile numbers. Use the Password tab for email.');
      return;
    }
    if (_identifier.text.replaceAll(RegExp(r'\D'), '').length < 6) {
      _snack('Enter a valid mobile number.');
      return;
    }
    await _run(() async {
      final res = await _auth.startPhoneVerification(_phoneE164,
          resendToken: _resendToken);
      if (res.autoCredential != null) {
        await _auth.signInWithPhoneCredential(res.autoCredential!);
        return;
      }
      setState(() {
        _verificationId = res.verificationId;
        _resendToken = res.resendToken;
        _otpSent = true;
      });
    });
  }

  Future<void> _verifyOtp() async {
    final id = _verificationId;
    if (id == null) return;
    if (_otp.length < 6) {
      _snack('Enter the 6-digit code.');
      return;
    }
    await _run(() => _auth.confirmSmsCode(id, _otp));
  }

  @override
  Widget build(BuildContext context) {
    final title = _otpSent ? 'Verify OTP' : 'Login to Your Account';
    final subtitle = _otpSent
        ? 'Enter the verification code sent to\n${_maskedTarget()}'
        : 'Access your Swaya orders, measurements and production updates.';

    return AuthShell(
      showBack: _otpSent,
      children: [
        AuthHeader(title: title, subtitle: subtitle),
        SegmentedToggle(
          labels: const ['Password', 'OTP'],
          selectedIndex: _mode,
          onChanged: _busy
              ? (_) {}
              : (i) => setState(() {
                    _mode = i;
                    _otpSent = false;
                  }),
        ),
        const SizedBox(height: 24),
        if (_mode == 0) ..._passwordForm() else ..._otpForm(),
        const SizedBox(height: 24),
        SocialRow(
          onGoogle: () => _run(_auth.signInWithGoogle),
        ),
        const SizedBox(height: 16),
        AuthFooterLink(
          prompt: "Don't have an account?",
          action: 'Create Account',
          onTap: () => context.push('/auth/register'),
        ),
      ],
    );
  }

  String _maskedTarget() {
    final t = _identifier.text.trim();
    if (t.length <= 4) return t;
    return '••• ${t.substring(t.length - 4)}';
  }

  List<Widget> _passwordForm() {
    return [
      const FieldLabel('Email or Mobile Number'),
      TextField(
        controller: _identifier,
        keyboardType: TextInputType.emailAddress,
        decoration: const InputDecoration(
          hintText: 'Enter your Email or Mobile Number',
          prefixIcon: Icon(Icons.mail_outline, size: 20),
        ),
      ),
      const SizedBox(height: 16),
      const FieldLabel('Password'),
      TextField(
        controller: _password,
        obscureText: _obscure,
        onSubmitted: (_) => _passwordLogin(),
        decoration: InputDecoration(
          hintText: 'Enter Password',
          prefixIcon: const Icon(Icons.lock_outline, size: 20),
          suffixIcon: IconButton(
            icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility,
                size: 20),
            onPressed: () => setState(() => _obscure = !_obscure),
          ),
        ),
      ),
      Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          onPressed: () => context.push('/auth/reset'),
          child: const Text('Forgot Password?'),
        ),
      ),
      const SizedBox(height: 8),
      _primary('Login', _passwordLogin),
    ];
  }

  List<Widget> _otpForm() {
    if (!_otpSent) {
      return [
        const FieldLabel('Email or Mobile Number'),
        TextField(
          controller: _identifier,
          keyboardType: TextInputType.phone,
          decoration: const InputDecoration(
            hintText: 'Enter your Mobile Number',
            prefixIcon: Icon(Icons.phone_iphone, size: 20),
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          "We'll send an OTP to this mobile number.",
          style: TextStyle(color: SwayaLight.inkTertiary, fontSize: 12),
        ),
        const SizedBox(height: 16),
        _primary('Send OTP', _sendOtp),
      ];
    }
    return [
      const FieldLabel('Enter OTP'),
      OtpInput(
        onChanged: (v) => _otp = v,
        onCompleted: (_) => _verifyOtp(),
      ),
      const SizedBox(height: 12),
      Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text('OTP sent to ${_maskedTarget()}',
              style: const TextStyle(
                  color: SwayaLight.inkTertiary, fontSize: 12)),
          TextButton(onPressed: _busy ? null : _sendOtp, child: const Text('Resend')),
        ],
      ),
      const SizedBox(height: 8),
      _primary('Verify & Login', _verifyOtp),
    ];
  }

  Widget _primary(String label, VoidCallback onTap) {
    return ElevatedButton(
      onPressed: _busy ? null : onTap,
      child: _busy
          ? const SizedBox(
              height: 20,
              width: 20,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: SwayaLight.onCta),
            )
          : Text(label),
    );
  }
}
