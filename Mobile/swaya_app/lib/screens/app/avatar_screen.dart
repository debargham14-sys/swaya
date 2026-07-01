import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';

import '../../models/avatar_design.dart';
import '../../models/blouse_measurements.dart';
import '../../theme/swaya_light_theme.dart';
import '../../widgets/avatar/garment_recolor.dart';
import 'app_chrome.dart';

/// 3D Try-On — a static SMPL-X avatar (female / male) with live garment
/// recolour + add-ons, rendered from a baked GLB inside `<model-viewer>`.
///
/// Reachable two ways: standalone from Home, or after entering/taking
/// measurements with [gender] + [measurements] passed in so the user can check
/// the result on an avatar. Today the body is a generic per-gender GLB; the
/// [_srcFor] seam is the single place to swap in a measurement-driven mesh
/// later (see the doc on that function).
///
/// Jitter-free by construction: the GLB loads ONCE and is never re-fetched while
/// you customise. Recolour / show / hide are direct GPU material edits on the
/// loaded model (see [GarmentRecolor]). Switching gender swaps to a different
/// baked GLB (a deliberate reload), then re-applies the current state.
class AvatarScreen extends StatefulWidget {
  const AvatarScreen({
    super.key,
    this.gender,
    this.measurements,
    this.garmentId,
  });

  /// Initial gender ('female' / 'male'); null falls back to female.
  final String? gender;

  /// Optional measurements to preview on the avatar (shown as a summary now;
  /// will drive mesh generation once a measurement-driven backend is wired).
  final BlouseMeasurements? measurements;

  /// Optional garment the avatar is being previewed for (reserved for the
  /// measurement-driven path).
  final String? garmentId;

  @override
  State<AvatarScreen> createState() => _AvatarScreenState();
}

// Garment swatches — brand-matched to the Swaya light wireframes (teal accent
// anchor + warm/cool complements that read on a light canvas).
class _Swatch {
  const _Swatch(this.name, this.color);
  final String name;
  final Color color;
}

const List<_Swatch> _palette = [
  _Swatch('Teal', Color(0xFF4A9B9B)), // brand accent
  _Swatch('Clay', Color(0xFFB5613B)),
  _Swatch('Indigo', Color(0xFF3C4A66)),
  _Swatch('Sand', Color(0xFFC9B79C)),
];

// Fixed (non-recoloured) part colours.
const int _watchR = 30, _watchG = 32, _watchB = 38; // dark metal
const int _pantsR = 58, _pantsG = 66, _pantsB = 96; // denim slate

/// The avatar's GLB source. **Swap-later seam:** today this returns a static
/// per-gender baked model. To make the avatar reflect the person's actual
/// measurements, return a generated/fetched GLB URL here (e.g. an SMPL/SMPL-X
/// mesh produced by the backend from [measurements]) — nothing else in this
/// screen needs to change.
String _srcFor(String gender, BlouseMeasurements? measurements) =>
    'assets/models/body_shirt_$gender.glb';

class _AvatarScreenState extends State<AvatarScreen> {
  final GarmentRecolor _recolor = GarmentRecolor();

  late String _gender = widget.gender ?? 'female';
  int _color = 0;
  bool _sleeves = false;
  bool _watch = false;
  bool _pants = false;

  Timer? _primePoll;

  // Rebuilt ONLY when gender changes (a deliberate reload). Colour/toggle changes
  // reuse the same widget instance, so model-viewer is never torn down.
  late Widget _viewer = _buildViewer();

  Widget _buildViewer() => ModelViewer(
        key: ValueKey('glb-$_gender'),
        src: _srcFor(_gender, widget.measurements),
        alt: 'Swaya SMPL-X avatar ($_gender) with customisable garments',
        backgroundColor: SwayaLight.surface,
        cameraControls: true,
        interpolationDecay: 180, // the "0 jitter / buttery" settle knob
        disableZoom: false,
        disablePan: false,
        cameraOrbit: '20deg 82deg auto', // auto-fit the whole avatar
        cameraTarget: 'auto auto auto',
        fieldOfView: 'auto',
        autoRotate: false, // static: no auto-spin (drag to orbit)
        shadowIntensity: 0.6,
        shadowSoftness: 1,
        exposure: 1.1,
        loading: Loading.eager,
        onWebViewCreated: (controller) {
          _recolor.attach(controller);
          _primeColours();
        },
      );

  // On web there is no WebView; push once the first frame is up.
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _primeColours());
  }

  @override
  void dispose() {
    _primePoll?.cancel();
    super.dispose();
  }

  // Re-push the full state a handful of times after a (re)load: the JS side binds
  // a one-time `load` listener, but only once the page DOM actually carries the
  // <model-viewer> element — so we retry briefly until that's true.
  void _primeColours() {
    _primePoll?.cancel();
    var tries = 0;
    _pushAll();
    _primePoll = Timer.periodic(const Duration(milliseconds: 300), (t) {
      _pushAll();
      if (++tries >= 8) t.cancel();
    });
  }

  Color get _current => _palette[_color].color;
  int get _r => (_current.r * 255).round();
  int get _g => (_current.g * 255).round();
  int get _b => (_current.b * 255).round();

  void _pushAll() {
    _recolor.setMaterial('shirt', _r, _g, _b, 1);
    _recolor.setMaterial('sleeve', _r, _g, _b, _sleeves ? 1 : 0);
    _recolor.setMaterial('watch', _watchR, _watchG, _watchB, _watch ? 1 : 0);
    _recolor.setMaterial('pants', _pantsR, _pantsG, _pantsB, _pants ? 1 : 0);
  }

  void _setGender(String g) {
    if (g == _gender) return;
    setState(() {
      _gender = g;
      _viewer = _buildViewer(); // new GLB -> reload, then re-apply (via onCreated)
    });
  }

  void _pickColor(int i) {
    setState(() => _color = i);
    _recolor.setMaterial('shirt', _r, _g, _b, 1);
    _recolor.setMaterial('sleeve', _r, _g, _b, _sleeves ? 1 : 0);
  }

  void _toggleSleeves() {
    setState(() => _sleeves = !_sleeves);
    _recolor.setMaterial('sleeve', _r, _g, _b, _sleeves ? 1 : 0);
  }

  void _toggleWatch() {
    setState(() => _watch = !_watch);
    _recolor.setMaterial('watch', _watchR, _watchG, _watchB, _watch ? 1 : 0);
  }

  void _togglePants() {
    setState(() => _pants = !_pants);
    _recolor.setMaterial('pants', _pantsR, _pantsG, _pantsB, _pants ? 1 : 0);
  }

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: '3D Try-On',
      showBack: true,
      showNav: false,
      trailing: IconButton(
        tooltip: 'Collaborate with a designer',
        icon: const Icon(Icons.handshake_outlined, size: 22),
        onPressed: () => context.push('/designers', extra: {
          'seed': AvatarDesign(
            gender: _gender,
            colorIndex: _color,
            sleeves: _sleeves,
            watch: _watch,
            pants: _pants,
            measurements: widget.measurements,
          ),
        }),
      ),
      body: Column(
        children: [
          // Avatar canvas — rounded, surface-filled, matches the AppCard idiom.
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Container(
                  color: SwayaLight.surface,
                  child: _viewer,
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
            child: Column(
              children: [
                if (widget.measurements != null &&
                    widget.measurements!.values.isNotEmpty) ...[
                  _MeasurementSummary(measurements: widget.measurements!),
                  const SizedBox(height: 14),
                ],
                _Segmented(
                  options: const ['female', 'male'],
                  labels: const ['Female', 'Male'],
                  selected: _gender,
                  onSelect: _setGender,
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  alignment: WrapAlignment.center,
                  children: [
                    _Toggle(
                      icon: Icons.checkroom,
                      label: 'Sleeves',
                      on: _sleeves,
                      onTap: _toggleSleeves,
                    ),
                    _Toggle(
                      icon: Icons.dry_cleaning,
                      label: 'Pants',
                      on: _pants,
                      onTap: _togglePants,
                    ),
                    _Toggle(
                      icon: Icons.watch,
                      label: 'Watch',
                      on: _watch,
                      onTap: _toggleWatch,
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _SwatchBar(
                  palette: _palette,
                  selected: _color,
                  onPick: _pickColor,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Compact read-out of the measurements being previewed on the avatar. Static
/// for now (the GLB is generic per gender); it documents what a future
/// measurement-driven mesh would be built from.
class _MeasurementSummary extends StatelessWidget {
  const _MeasurementSummary({required this.measurements});

  final BlouseMeasurements measurements;

  @override
  Widget build(BuildContext context) {
    final entries = measurements.values.entries.take(4).toList();
    final more = measurements.values.length - entries.length;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: SwayaLight.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.straighten, size: 16, color: SwayaLight.accent),
              SizedBox(width: 8),
              Text('Previewing your measurements',
                  style: TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 14,
            runSpacing: 4,
            children: [
              for (final e in entries)
                Text('${_pretty(e.key)} ${e.value.toStringAsFixed(0)}cm',
                    style: const TextStyle(
                        color: SwayaLight.inkSecondary, fontSize: 12)),
              if (more > 0)
                Text('+$more more',
                    style: const TextStyle(
                        color: SwayaLight.inkTertiary, fontSize: 12)),
            ],
          ),
        ],
      ),
    );
  }

  static String _pretty(String key) =>
      key.replaceAll('_', ' ').replaceAllMapped(
            RegExp(r'^\w'),
            (m) => m.group(0)!.toUpperCase(),
          );
}

class _Segmented extends StatelessWidget {
  const _Segmented({
    required this.options,
    required this.labels,
    required this.selected,
    required this.onSelect,
  });

  final List<String> options;
  final List<String> labels;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < options.length; i++)
            GestureDetector(
              onTap: () => onSelect(options[i]),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                padding:
                    const EdgeInsets.symmetric(horizontal: 26, vertical: 9),
                decoration: BoxDecoration(
                  color: options[i] == selected
                      ? SwayaLight.cta
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Text(
                  labels[i],
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: options[i] == selected
                        ? SwayaLight.onCta
                        : SwayaLight.inkSecondary,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Toggle extends StatelessWidget {
  const _Toggle({
    required this.icon,
    required this.label,
    required this.on,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: on
              ? SwayaLight.accent.withValues(alpha: 0.12)
              : SwayaLight.surface,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(
            color: on ? SwayaLight.accent : SwayaLight.border,
            width: 1.5,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                size: 18,
                color: on ? SwayaLight.accent : SwayaLight.inkSecondary),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: on ? SwayaLight.inkPrimary : SwayaLight.inkSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SwatchBar extends StatelessWidget {
  const _SwatchBar({
    required this.palette,
    required this.selected,
    required this.onPick,
  });

  final List<_Swatch> palette;
  final int selected;
  final ValueChanged<int> onPick;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: SwayaLight.surface,
          borderRadius: BorderRadius.circular(28),
          border: Border.all(color: SwayaLight.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < palette.length; i++) ...[
              if (i > 0) const SizedBox(width: 16),
              _SwatchDot(
                color: palette[i].color,
                selected: i == selected,
                onTap: () => onPick(i),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _SwatchDot extends StatelessWidget {
  const _SwatchDot({
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? SwayaLight.inkPrimary : SwayaLight.border,
            width: selected ? 3 : 1.5,
          ),
        ),
      ),
    );
  }
}
