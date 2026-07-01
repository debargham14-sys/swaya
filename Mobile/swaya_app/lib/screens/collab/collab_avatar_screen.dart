import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';

import '../../models/avatar_design.dart';
import '../../models/collab_message.dart';
import '../../providers/collab_controller.dart';
import '../../services/designers_api.dart';
import '../../services/measure_api.dart' show MeasureApiException;
import '../../theme/swaya_light_theme.dart';
import '../../widgets/avatar/avatar_controls.dart';
import '../../widgets/avatar/garment_recolor.dart';

/// The collaborative 3D studio: a user and a designer share one avatar design
/// and a chat thread, synced via polling. Both sides use this same screen; the
/// [role] (`user` | `designer`) only changes a few affordances.
class CollabAvatarScreen extends StatefulWidget {
  const CollabAvatarScreen({
    super.key,
    required this.sessionId,
    required this.role,
    this.seed,
  });

  final String sessionId;
  final String role; // 'user' | 'designer'
  final AvatarDesign? seed;

  @override
  State<CollabAvatarScreen> createState() => _CollabAvatarScreenState();
}

class _CollabAvatarScreenState extends State<CollabAvatarScreen> {
  final CollabController _controller = CollabController();
  final GarmentRecolor _recolor = GarmentRecolor();
  final TextEditingController _input = TextEditingController();
  final ScrollController _chatScroll = ScrollController();

  late Widget _viewer = _buildViewer('female');
  String _lastGender = 'female';
  int _lastAppliedTick = -1;
  int _lastMessageCount = 0;
  int _tab = 0; // 0 = design, 1 = chat
  Timer? _primePoll;

  AvatarDesign get _design => _controller.design;

  @override
  void initState() {
    super.initState();
    _lastGender = widget.seed?.gender ?? 'female';
    _viewer = _buildViewer(_lastGender);
    _controller.addListener(_onChange);
    _controller.start(
      widget.sessionId,
      role: widget.role,
      seed: widget.seed,
    );
  }

  @override
  void dispose() {
    _primePoll?.cancel();
    _controller.removeListener(_onChange);
    _controller.dispose();
    _input.dispose();
    _chatScroll.dispose();
    super.dispose();
  }

  // React to controller changes: reload the GLB on gender change, otherwise
  // re-apply the shared design when its tick advances. Then rebuild the UI.
  void _onChange() {
    if (!mounted) return;
    if (_design.gender != _lastGender) {
      _lastGender = _design.gender;
      _viewer = _buildViewer(_lastGender); // reload, re-applies via onCreated
      _lastAppliedTick = _controller.designTick;
    } else if (_controller.designTick != _lastAppliedTick) {
      _lastAppliedTick = _controller.designTick;
      _design.applyTo(_recolor);
    }
    if (_controller.messages.length != _lastMessageCount) {
      _lastMessageCount = _controller.messages.length;
      WidgetsBinding.instance.addPostFrameCallback((_) => _scrollChatToEnd());
    }
    setState(() {});
  }

  Widget _buildViewer(String gender) => ModelViewer(
        key: ValueKey('collab-glb-$gender'),
        src: 'assets/models/body_shirt_$gender.glb',
        alt: 'Swaya SMPL-X avatar ($gender) — collaborative design',
        backgroundColor: SwayaLight.surface,
        cameraControls: true,
        interpolationDecay: 180,
        cameraOrbit: '20deg 82deg auto',
        cameraTarget: 'auto auto auto',
        fieldOfView: 'auto',
        autoRotate: false,
        shadowIntensity: 0.6,
        shadowSoftness: 1,
        exposure: 1.1,
        loading: Loading.eager,
        onWebViewCreated: (controller) {
          _recolor.attach(controller);
          _primeColours();
        },
      );

  // Re-push the design a handful of times after a (re)load until the
  // <model-viewer> element is actually present (same trick as AvatarScreen).
  void _primeColours() {
    _primePoll?.cancel();
    var tries = 0;
    _design.applyTo(_recolor);
    _primePoll = Timer.periodic(const Duration(milliseconds: 300), (t) {
      _design.applyTo(_recolor);
      if (++tries >= 8) t.cancel();
    });
  }

  void _scrollChatToEnd() {
    if (!_chatScroll.hasClients) return;
    _chatScroll.animateTo(
      _chatScroll.position.maxScrollExtent,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  void _edit(AvatarDesign next) => _controller.updateDesign(next);

  Future<void> _send() async {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    await _controller.sendMessage(text);
  }

  Future<void> _confirmEnd() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('End collaboration?'),
        content: const Text('Both of you will stop sharing this design.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('End')),
        ],
      ),
    );
    if (ok == true) {
      await _controller.end();
      if (mounted && widget.role == 'user') _maybeRate();
    }
  }

  Future<void> _maybeRate() async {
    final designerId = _controller.session?.designerId;
    if (designerId == null) return;
    final stars = await showDialog<int>(
      context: context,
      builder: (ctx) => _RatingDialog(),
    );
    if (stars == null) return;
    try {
      await DesignersApi().rate(designerId, stars.toDouble());
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Thanks for rating!')));
      }
    } on MeasureApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = _controller.session;
    final otherName = session?.otherName(widget.role) ?? 'Collaborator';
    final ended = _controller.status == 'ended';

    return Theme(
      data: buildSwayaLightTheme(),
      child: Scaffold(
        backgroundColor: SwayaLight.canvas,
        appBar: AppBar(
          backgroundColor: SwayaLight.canvas,
          elevation: 0,
          centerTitle: true,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new, size: 20),
            onPressed: () => context.canPop()
                ? context.pop()
                : context.go(widget.role == 'designer'
                    ? '/designer/home'
                    : '/home-v2'),
          ),
          title: Column(
            children: [
              const Text('Design studio',
                  style: TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontSize: 16,
                      fontWeight: FontWeight.w600)),
              Text('with $otherName',
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 12)),
            ],
          ),
          actions: [
            if (!ended)
              IconButton(
                tooltip: 'End',
                icon: const Icon(Icons.logout, size: 20),
                onPressed: _confirmEnd,
              ),
          ],
        ),
        body: Column(
          children: [
            _PresenceBar(controller: _controller, otherName: otherName),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(18),
                  child: Container(color: SwayaLight.surface, child: _viewer),
                ),
              ),
            ),
            _bottomPanel(ended),
          ],
        ),
      ),
    );
  }

  Widget _bottomPanel(bool ended) {
    return Container(
      decoration: const BoxDecoration(
        color: SwayaLight.canvas,
        border: Border(top: BorderSide(color: SwayaLight.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _TabToggle(
                index: _tab,
                unread: _unreadBadge(),
                onChanged: (i) => setState(() => _tab = i),
              ),
              const SizedBox(height: 12),
              SizedBox(
                height: 230,
                child: IndexedStack(
                  index: _tab,
                  children: [
                    _designTab(ended),
                    _chatTab(ended),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  int _unreadBadge() {
    final s = _controller.session;
    if (s == null || _tab == 1) return 0;
    return s.unreadFor(widget.role);
  }

  Widget _designTab(bool ended) {
    final d = _design;
    final controls = IgnorePointer(
      ignoring: ended,
      child: Opacity(
        opacity: ended ? 0.5 : 1,
        child: SingleChildScrollView(
          child: Column(
            children: [
              if (d.measurements != null &&
                  d.measurements!.values.isNotEmpty) ...[
                AvatarMeasurementSummary(measurements: d.measurements!),
                const SizedBox(height: 12),
              ],
              AvatarSegmented(
                selected: d.gender,
                onSelect: (g) => _edit(d.copyWith(gender: g)),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  AvatarToggleChip(
                    icon: Icons.checkroom,
                    label: 'Sleeves',
                    on: d.sleeves,
                    onTap: () => _edit(d.copyWith(sleeves: !d.sleeves)),
                  ),
                  AvatarToggleChip(
                    icon: Icons.dry_cleaning,
                    label: 'Pants',
                    on: d.pants,
                    onTap: () => _edit(d.copyWith(pants: !d.pants)),
                  ),
                  AvatarToggleChip(
                    icon: Icons.watch,
                    label: 'Watch',
                    on: d.watch,
                    onTap: () => _edit(d.copyWith(watch: !d.watch)),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              AvatarSwatchBar(
                selected: d.colorIndex,
                onPick: (i) => _edit(d.copyWith(colorIndex: i)),
              ),
            ],
          ),
        ),
      ),
    );
    return controls;
  }

  Widget _chatTab(bool ended) {
    final messages = _controller.messages;
    return Column(
      children: [
        Expanded(
          child: messages.isEmpty
              ? const Center(
                  child: Text('Say hello 👋',
                      style: TextStyle(color: SwayaLight.inkTertiary)))
              : ListView.builder(
                  controller: _chatScroll,
                  itemCount: messages.length,
                  itemBuilder: (_, i) => _ChatBubble(
                    message: messages[i],
                    mine: messages[i].senderRole == widget.role,
                  ),
                ),
        ),
        if (!ended)
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _input,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: const InputDecoration(
                    hintText: 'Message…',
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: _controller.sending ? null : _send,
                icon: const Icon(Icons.send, size: 20),
                style: IconButton.styleFrom(
                  backgroundColor: SwayaLight.cta,
                  foregroundColor: SwayaLight.onCta,
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class _TabToggle extends StatelessWidget {
  const _TabToggle({
    required this.index,
    required this.onChanged,
    this.unread = 0,
  });

  final int index;
  final ValueChanged<int> onChanged;
  final int unread;

  @override
  Widget build(BuildContext context) {
    Widget seg(int i, String label, {int badge = 0}) {
      final active = i == index;
      return Expanded(
        child: GestureDetector(
          onTap: () => onChanged(i),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            padding: const EdgeInsets.symmetric(vertical: 9),
            decoration: BoxDecoration(
              color: active ? SwayaLight.cta : Colors.transparent,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(label,
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color:
                            active ? SwayaLight.onCta : SwayaLight.inkSecondary)),
                if (badge > 0) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: SwayaLight.error,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text('$badge',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 11,
                            fontWeight: FontWeight.w700)),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Row(children: [seg(0, 'Design'), seg(1, 'Chat', badge: unread)]),
    );
  }
}

class _PresenceBar extends StatelessWidget {
  const _PresenceBar({required this.controller, required this.otherName});

  final CollabController controller;
  final String otherName;

  @override
  Widget build(BuildContext context) {
    final status = controller.status;
    String text;
    Color dot;
    if (status == 'pending') {
      text = controller.role == 'designer'
          ? 'Tap to accept this request'
          : 'Waiting for $otherName to join…';
      dot = SwayaLight.inkTertiary;
    } else if (status == 'ended') {
      text = 'Collaboration ended';
      dot = SwayaLight.inkTertiary;
    } else if (controller.editedByOther) {
      text = '$otherName just edited the design';
      dot = SwayaLight.accent;
    } else {
      text = '$otherName is in the studio';
      dot = SwayaLight.success;
    }

    final pending = status == 'pending' && controller.role == 'designer';
    return GestureDetector(
      onTap: pending ? controller.accept : null,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(16, 4, 16, 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: pending ? SwayaLight.cta : SwayaLight.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: SwayaLight.border),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(text,
                  style: TextStyle(
                      color: pending
                          ? SwayaLight.onCta
                          : SwayaLight.inkSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w600)),
            ),
            if (pending)
              const Text('Accept',
                  style: TextStyle(
                      color: SwayaLight.onCta,
                      fontSize: 12,
                      fontWeight: FontWeight.w700)),
          ],
        ),
      ),
    );
  }
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({required this.message, required this.mine});

  final CollabMessage message;
  final bool mine;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.7),
        decoration: BoxDecoration(
          color: mine ? SwayaLight.cta : SwayaLight.surface,
          borderRadius: BorderRadius.circular(14),
          border: mine ? null : Border.all(color: SwayaLight.border),
        ),
        child: Text(
          message.text,
          style: TextStyle(
            color: mine ? SwayaLight.onCta : SwayaLight.inkPrimary,
            fontSize: 14,
          ),
        ),
      ),
    );
  }
}

class _RatingDialog extends StatefulWidget {
  @override
  State<_RatingDialog> createState() => _RatingDialogState();
}

class _RatingDialogState extends State<_RatingDialog> {
  int _stars = 5;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Rate your designer'),
      content: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 1; i <= 5; i++)
            IconButton(
              onPressed: () => setState(() => _stars = i),
              icon: Icon(
                i <= _stars ? Icons.star : Icons.star_border,
                color: SwayaLight.accent,
              ),
            ),
        ],
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Skip')),
        TextButton(
            onPressed: () => Navigator.pop(context, _stars),
            child: const Text('Submit')),
      ],
    );
  }
}
