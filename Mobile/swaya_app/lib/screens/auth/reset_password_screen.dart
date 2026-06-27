import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../providers/auth_controller.dart';
import '../../services/auth_service.dart';
import '../../theme/swaya_light_theme.dart';
import 'auth_widgets.dart';

/// Reset password — Figma frame 5. Firebase sends a secure reset *link* by
/// email (its native flow), so we collect the email and send the link rather
/// than running the in-app OTP + new-password steps from frames 6–7 (those
/// would require a custom verification backend).
class ResetPasswordScreen extends StatefulWidget {
  const ResetPasswordScreen({super.key});

  @override
  State<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends State<ResetPasswordScreen> {
  final _email = TextEditingController();
  bool _busy = false;
  bool _sent = false;

  AuthService get _auth => context.read<AuthController>().service;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  void _snack(String m) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(m)));
  }

  Future<void> _send() async {
    if (!_email.text.contains('@')) {
      _snack('Enter your registered email address.');
      return;
    }
    setState(() => _busy = true);
    try {
      await _auth.sendPasswordReset(_email.text);
      if (mounted) setState(() => _sent = true);
    } on AuthFailure catch (e) {
      if (mounted) _snack(e.message);
    } catch (_) {
      if (mounted) _snack('Could not send the reset link. Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthShell(
      showBack: true,
      children: [
        AuthHeader(
          title: _sent ? 'Check your email' : 'Reset your Password',
          subtitle: _sent
              ? 'We sent a password reset link to\n${_email.text.trim()}'
              : "Enter your registered email. We'll send a secure reset link.",
        ),
        if (!_sent) ...[
          const FieldLabel('Email'),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            onSubmitted: (_) => _send(),
            decoration: const InputDecoration(
              hintText: 'Enter your Email',
              prefixIcon: Icon(Icons.mail_outline, size: 20),
            ),
          ),
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: _busy ? null : _send,
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: SwayaLight.onCta),
                  )
                : const Text('Send Reset Link'),
          ),
        ] else ...[
          const Icon(Icons.mark_email_read_outlined,
              size: 56, color: SwayaLight.success),
          const SizedBox(height: 24),
          OutlinedButton(
            onPressed: _busy ? null : _send,
            child: const Text('Resend link'),
          ),
        ],
        const SizedBox(height: 16),
        AuthFooterLink(
          prompt: 'Remember your password?',
          action: 'Login',
          onTap: () => context.pop(),
        ),
      ],
    );
  }
}
