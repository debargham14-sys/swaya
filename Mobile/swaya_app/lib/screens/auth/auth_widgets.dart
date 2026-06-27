import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../theme/swaya_light_theme.dart';

/// Light-themed page shell for auth screens: white canvas, optional back button
/// and "Step x of n" pill, centered scrolling content.
class AuthShell extends StatelessWidget {
  const AuthShell({
    super.key,
    required this.children,
    this.showBack = false,
    this.stepLabel,
  });

  final List<Widget> children;
  final bool showBack;
  final String? stepLabel;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: buildSwayaLightTheme(),
      child: Scaffold(
        backgroundColor: SwayaLight.canvas,
        body: SafeArea(
          child: Column(
            children: [
              if (showBack)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
                    child: IconButton(
                      icon: const Icon(Icons.arrow_back_ios_new, size: 20),
                      color: SwayaLight.inkPrimary,
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                  ),
                ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (stepLabel != null) ...[
                        const SizedBox(height: 4),
                        Center(child: _StepPill(label: stepLabel!)),
                      ],
                      ...children,
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepPill extends StatelessWidget {
  const _StepPill({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: SwayaLight.inkSecondary,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// Brand mark (logo circle) + title + subtitle, centered — the top of every
/// auth frame.
class AuthHeader extends StatelessWidget {
  const AuthHeader({super.key, required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Column(
      children: [
        const SizedBox(height: 8),
        Container(
          width: 64,
          height: 64,
          decoration: const BoxDecoration(
            color: SwayaLight.surfaceAlt,
            shape: BoxShape.circle,
          ),
          alignment: Alignment.center,
          child: const Icon(Icons.straighten,
              color: SwayaLight.inkSecondary, size: 28),
        ),
        const SizedBox(height: 20),
        Text(
          title,
          textAlign: TextAlign.center,
          style: text.titleLarge?.copyWith(
            fontWeight: FontWeight.w700,
            color: SwayaLight.inkPrimary,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: text.bodyMedium?.copyWith(color: SwayaLight.inkSecondary),
        ),
        const SizedBox(height: 28),
      ],
    );
  }
}

/// Two-option segmented control (e.g. Password | OTP). Selected segment is the
/// dark CTA color, matching the Figma toggle.
class SegmentedToggle extends StatelessWidget {
  const SegmentedToggle({
    super.key,
    required this.labels,
    required this.selectedIndex,
    required this.onChanged,
  });

  final List<String> labels;
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++)
            Expanded(
              child: GestureDetector(
                onTap: () => onChanged(i),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: i == selectedIndex
                        ? SwayaLight.cta
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    labels[i],
                    style: TextStyle(
                      color: i == selectedIndex
                          ? SwayaLight.onCta
                          : SwayaLight.inkSecondary,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Field label shown above an input ("Email or Mobile Number").
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8, top: 4),
      child: Text(
        text,
        style: const TextStyle(
          color: SwayaLight.inkPrimary,
          fontSize: 13,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// Six-box OTP entry with auto-advance and paste support. Calls [onCompleted]
/// when all six digits are filled.
class OtpInput extends StatefulWidget {
  const OtpInput({
    super.key,
    required this.onChanged,
    this.onCompleted,
    this.length = 6,
  });

  final ValueChanged<String> onChanged;
  final ValueChanged<String>? onCompleted;
  final int length;

  @override
  State<OtpInput> createState() => _OtpInputState();
}

class _OtpInputState extends State<OtpInput> {
  late final List<TextEditingController> _controllers;
  late final List<FocusNode> _nodes;

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(widget.length, (_) => TextEditingController());
    _nodes = List.generate(widget.length, (_) => FocusNode());
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    for (final n in _nodes) {
      n.dispose();
    }
    super.dispose();
  }

  String get _value => _controllers.map((c) => c.text).join();

  void _emit() {
    final v = _value;
    widget.onChanged(v);
    if (v.length == widget.length) widget.onCompleted?.call(v);
  }

  void _onChanged(int i, String raw) {
    // Handle paste of the full code into one box.
    if (raw.length > 1) {
      final digits = raw.replaceAll(RegExp(r'\D'), '');
      for (var j = 0; j < widget.length; j++) {
        _controllers[j].text = j < digits.length ? digits[j] : '';
      }
      final next = digits.length.clamp(0, widget.length - 1);
      _nodes[next].requestFocus();
      _emit();
      return;
    }
    if (raw.isNotEmpty && i < widget.length - 1) {
      _nodes[i + 1].requestFocus();
    } else if (raw.isEmpty && i > 0) {
      _nodes[i - 1].requestFocus();
    }
    _emit();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        for (var i = 0; i < widget.length; i++)
          SizedBox(
            width: 46,
            height: 54,
            child: TextField(
              controller: _controllers[i],
              focusNode: _nodes[i],
              keyboardType: TextInputType.number,
              textAlign: TextAlign.center,
              maxLength: i == 0 ? widget.length : 1, // first box accepts paste
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w600,
                color: SwayaLight.inkPrimary,
              ),
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                counterText: '',
                contentPadding: EdgeInsets.zero,
              ),
              onChanged: (v) => _onChanged(i, v),
            ),
          ),
      ],
    );
  }
}

/// "or continue with" divider + circular social buttons.
class SocialRow extends StatelessWidget {
  const SocialRow({
    super.key,
    required this.onGoogle,
    this.onApple,
  });

  final VoidCallback onGoogle;
  final VoidCallback? onApple;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Row(
          children: [
            Expanded(child: Divider(color: SwayaLight.border)),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 12),
              child: Text(
                'or continue with',
                style: TextStyle(
                  color: SwayaLight.inkTertiary,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Expanded(child: Divider(color: SwayaLight.border)),
          ],
        ),
        const SizedBox(height: 20),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _SocialButton(icon: Icons.g_mobiledata_rounded, onTap: onGoogle),
            if (onApple != null) ...[
              const SizedBox(width: 16),
              _SocialButton(icon: Icons.apple, onTap: onApple!),
            ],
          ],
        ),
      ],
    );
  }
}

class _SocialButton extends StatelessWidget {
  const _SocialButton({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        width: 60,
        height: 52,
        decoration: BoxDecoration(
          color: SwayaLight.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: SwayaLight.border),
        ),
        child: Icon(icon, color: SwayaLight.inkPrimary, size: 28),
      ),
    );
  }
}

/// Footer prompt like "Don't have an account? Create Account".
class AuthFooterLink extends StatelessWidget {
  const AuthFooterLink({
    super.key,
    required this.prompt,
    required this.action,
    required this.onTap,
  });

  final String prompt;
  final String action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(prompt,
            style: const TextStyle(
                color: SwayaLight.inkSecondary, fontSize: 14)),
        TextButton(onPressed: onTap, child: Text(action)),
      ],
    );
  }
}
