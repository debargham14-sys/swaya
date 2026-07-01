import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../models/designer.dart';
import '../../providers/auth_controller.dart';
import '../../services/designers_api.dart';
import '../../services/measure_api.dart' show MeasureApiException;
import '../../theme/swaya_light_theme.dart';
import '../app/app_chrome.dart';

/// Become a designer / edit the designer profile. Saving flips the account's
/// role to designer (server-side) and lands them in the designer console.
class DesignerRegisterScreen extends StatefulWidget {
  const DesignerRegisterScreen({super.key});

  @override
  State<DesignerRegisterScreen> createState() => _DesignerRegisterScreenState();
}

class _DesignerRegisterScreenState extends State<DesignerRegisterScreen> {
  final _name = TextEditingController();
  final _bio = TextEditingController();
  final _specialties = TextEditingController();
  final _location = TextEditingController();
  final _years = TextEditingController();
  final _price = TextEditingController();
  bool _available = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final existing = context.read<AuthController>().designerProfile;
    if (existing != null) {
      _name.text = existing.name;
      _bio.text = existing.bio ?? '';
      _specialties.text = existing.specialties.join(', ');
      _location.text = existing.location ?? '';
      _years.text = existing.yearsExperience?.toString() ?? '';
      _price.text = existing.priceRange ?? '';
      _available = existing.available;
    }
  }

  @override
  void dispose() {
    _name.dispose();
    _bio.dispose();
    _specialties.dispose();
    _location.dispose();
    _years.dispose();
    _price.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Please enter your name.')));
      return;
    }
    setState(() => _saving = true);
    final auth = context.read<AuthController>();
    final profile = Designer(
      id: 'me', // ignored by the API — keyed to the caller's uid
      name: _name.text.trim(),
      bio: _bio.text.trim().isEmpty ? null : _bio.text.trim(),
      specialties: _specialties.text
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList(),
      location: _location.text.trim().isEmpty ? null : _location.text.trim(),
      yearsExperience: int.tryParse(_years.text.trim()),
      priceRange: _price.text.trim().isEmpty ? null : _price.text.trim(),
      available: _available,
    );
    try {
      await DesignersApi().upsertMe(profile);
      await auth.refreshRole();
      if (mounted) context.go('/designer/home');
    } on MeasureApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
        setState(() => _saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEditing = context.read<AuthController>().designerProfile != null;
    return LightScaffold(
      title: isEditing ? 'Edit profile' : 'Become a designer',
      showBack: true,
      showNav: false,
      bottomBar: ElevatedButton(
        onPressed: _saving ? null : _save,
        child: Text(_saving
            ? 'Saving…'
            : (isEditing ? 'Save profile' : 'Create designer profile')),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        children: [
          const Text(
            'Set up your public profile. Clients will see this in the designer '
            'directory and can start a live design session with you.',
            style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13),
          ),
          const SizedBox(height: 20),
          _Field(label: 'Name', controller: _name, hint: 'e.g. Aanya Kapoor'),
          _Field(
              label: 'Bio',
              controller: _bio,
              hint: 'A line about your craft',
              maxLines: 3),
          _Field(
              label: 'Specialties',
              controller: _specialties,
              hint: 'Comma-separated, e.g. Blouse, Lehenga'),
          _Field(
              label: 'Location',
              controller: _location,
              hint: 'City, State'),
          Row(
            children: [
              Expanded(
                child: _Field(
                    label: 'Years of experience',
                    controller: _years,
                    hint: 'e.g. 8',
                    keyboardType: TextInputType.number),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _Field(
                    label: 'Price range',
                    controller: _price,
                    hint: 'e.g. ₹₹'),
              ),
            ],
          ),
          const SizedBox(height: 4),
          SwitchListTile(
            value: _available,
            onChanged: (v) => setState(() => _available = v),
            contentPadding: EdgeInsets.zero,
            activeThumbColor: SwayaLight.accent,
            title: const Text('Available for new collaborations',
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontWeight: FontWeight.w600,
                    fontSize: 14)),
          ),
        ],
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.label,
    required this.controller,
    this.hint,
    this.maxLines = 1,
    this.keyboardType,
  });

  final String label;
  final TextEditingController controller;
  final String? hint;
  final int maxLines;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(
                  color: SwayaLight.inkPrimary,
                  fontWeight: FontWeight.w600,
                  fontSize: 13)),
          const SizedBox(height: 8),
          TextField(
            controller: controller,
            maxLines: maxLines,
            keyboardType: keyboardType,
            decoration: InputDecoration(hintText: hint),
          ),
        ],
      ),
    );
  }
}
