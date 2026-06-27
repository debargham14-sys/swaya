import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_controller.dart';
import '../../services/auth_service.dart';
import '../../theme/swaya_light_theme.dart';
import 'auth_widgets.dart';

/// Create account — Figma frames 8–9 (collect details + secure with a password)
/// and 10 (success). Firebase email sign-up doesn't use a 6-digit OTP step, so
/// the OTP box from frame 9 is replaced by email verification sent on sign-up.
class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();

  bool _busy = false;
  bool _obscure = true;
  bool _agreed = false;

  AuthService get _auth => context.read<AuthController>().service;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _snack(String m) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(m)));
  }

  bool get _passwordStrong {
    final p = _password.text;
    return p.length >= 8 &&
        p.contains(RegExp(r'\d')) &&
        p.contains(RegExp(r'[!@#$%^&*(),.?":{}|<>_\-]'));
  }

  Future<void> _create() async {
    if (_name.text.trim().isEmpty) return _snack('Enter your full name.');
    if (!_email.text.contains('@')) return _snack('Enter a valid email address.');
    if (!_passwordStrong) {
      return _snack('Use 8+ characters with a number and a symbol.');
    }
    if (!_agreed) return _snack('Please accept the Terms and Conditions.');

    setState(() => _busy = true);
    try {
      final user = await _auth.registerWithEmail(_email.text, _password.text);
      await user.updateDisplayName(_name.text.trim());
      try {
        await user.sendEmailVerification();
      } catch (_) {/* non-fatal */}
      // Land in the current (light) app flow, matching post-login.
      if (mounted) context.go('/home-v2');
    } on AuthFailure catch (e) {
      if (mounted) _snack(e.message);
    } catch (_) {
      if (mounted) _snack('Could not create your account. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthShell(
      showBack: true,
      stepLabel: 'Step 1 of 2',
      children: [
        const AuthHeader(
          title: 'Create New Account',
          subtitle: 'Track designs, measurements, orders and production updates.',
        ),
        const FieldLabel('Full Name'),
        TextField(
          controller: _name,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            hintText: 'Enter your full name',
            prefixIcon: Icon(Icons.person_outline, size: 20),
          ),
        ),
        const SizedBox(height: 16),
        const FieldLabel('Email'),
        TextField(
          controller: _email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            hintText: 'Enter your Email',
            prefixIcon: Icon(Icons.mail_outline, size: 20),
          ),
        ),
        const SizedBox(height: 16),
        const FieldLabel('Password'),
        TextField(
          controller: _password,
          obscureText: _obscure,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(
            hintText: 'Create a password',
            prefixIcon: const Icon(Icons.lock_outline, size: 20),
            suffixIcon: IconButton(
              icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility,
                  size: 20),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
          ),
        ),
        const SizedBox(height: 8),
        _Requirement(
          met: _passwordStrong,
          text: 'Use 8+ characters with a number & symbol',
        ),
        const SizedBox(height: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Checkbox(
              value: _agreed,
              onChanged: (v) => setState(() => _agreed = v ?? false),
              activeColor: SwayaLight.accent,
            ),
            const Expanded(
              child: Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text(
                  'I agree to the Terms and Conditions',
                  style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        ElevatedButton(
          onPressed: _busy ? null : _create,
          child: _busy
              ? const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: SwayaLight.onCta),
                )
              : const Text('Create Account'),
        ),
        const SizedBox(height: 12),
        AuthFooterLink(
          prompt: 'Already have an account?',
          action: 'Login',
          onTap: () => context.pop(),
        ),
      ],
    );
  }
}

class _Requirement extends StatelessWidget {
  const _Requirement({required this.met, required this.text});
  final bool met;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(
          met ? Icons.check_circle : Icons.circle_outlined,
          size: 16,
          color: met ? SwayaLight.success : SwayaLight.inkTertiary,
        ),
        const SizedBox(width: 8),
        Text(
          text,
          style: TextStyle(
            color: met ? SwayaLight.success : SwayaLight.inkTertiary,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}
