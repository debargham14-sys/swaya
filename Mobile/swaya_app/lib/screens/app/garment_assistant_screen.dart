import 'package:flutter/material.dart';

import '../../models/blouse_measurements.dart';
import '../../services/assistant_api.dart';
import '../../services/measure_api.dart' show MeasureApiException;
import '../../theme/swaya_light_theme.dart';
import '../../widgets/garment_suggestion_sheet.dart' show girthsForAssistant;
import 'app_chrome.dart';

/// Interactive clothing/design assistant. Seeds with gender-aware suggestions,
/// then lets the user chat back and forth. The backend layers in the caller's
/// orders + saved personas, so it can answer questions like "what did I order?"
/// or "suggest something to pair with my last order".
class GarmentAssistantScreen extends StatefulWidget {
  const GarmentAssistantScreen({
    super.key,
    required this.gender,
    required this.measurements,
    this.personaName,
    this.garment,
  });

  final String gender;
  final BlouseMeasurements measurements;
  final String? personaName;
  final String? garment;

  @override
  State<GarmentAssistantScreen> createState() => _GarmentAssistantScreenState();
}

class _Msg {
  _Msg(this.role, this.text);
  final String role; // 'user' | 'assistant'
  final String text;
}

class _GarmentAssistantScreenState extends State<GarmentAssistantScreen> {
  final _api = AssistantApi();
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  final List<_Msg> _messages = [];
  bool _loading = false;

  Map<String, double> get _girths => girthsForAssistant(widget.measurements);

  static const _suggestedPrompts = [
    'What should I order next?',
    'What have I ordered so far?',
    'Suggest a colour and fabric',
    'How much ease for a good fit?',
  ];

  @override
  void initState() {
    super.initState();
    _seed();
  }

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _seed() async {
    setState(() => _loading = true);
    try {
      final s = await _api.suggestForGarment(
        girthsCm: _girths,
        gender: widget.gender,
        garment: widget.garment,
      );
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg(
          'assistant',
          s.suggestions.trim().isNotEmpty
              ? s.suggestions
              : 'Hi! Ask me about garments, fit, fabrics, or your orders.',
        ));
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg('assistant',
            'Hi! Ask me about garments, fit, fabrics, or your orders.'));
        _loading = false;
      });
    }
    _scrollToEnd();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send([String? preset]) async {
    final text = (preset ?? _controller.text).trim();
    if (text.isEmpty || _loading) return;
    final history = [
      for (final m in _messages) {'role': m.role, 'text': m.text}
    ];
    setState(() {
      _messages.add(_Msg('user', text));
      _loading = true;
      _controller.clear();
    });
    _scrollToEnd();
    try {
      final reply = await _api.chatForGarment(
        girthsCm: _girths,
        message: text,
        history: history,
        gender: widget.gender,
        garment: widget.garment,
      );
      if (!mounted) return;
      setState(() {
        _messages.add(_Msg('assistant',
            reply.trim().isNotEmpty ? reply : '(no reply)'));
        _loading = false;
      });
      _scrollToEnd();
    } on MeasureApiException catch (e) {
      _fail(e.message);
    } catch (e) {
      _fail('$e');
    }
  }

  void _fail(String msg) {
    if (!mounted) return;
    setState(() => _loading = false);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('Could not get a reply: $msg')));
  }

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: 'Design assistant',
      showBack: true,
      showNav: false,
      body: Column(
        children: [
          // Quick prompts
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                for (final p in _suggestedPrompts)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ActionChip(
                      label: Text(p, style: const TextStyle(fontSize: 12)),
                      backgroundColor: SwayaLight.surface,
                      side: const BorderSide(color: SwayaLight.border),
                      onPressed: _loading ? null : () => _send(p),
                    ),
                  ),
              ],
            ),
          ),
          const Divider(height: 1, color: SwayaLight.border),
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              itemCount: _messages.length + (_loading ? 1 : 0),
              itemBuilder: (context, i) {
                if (_loading && i == _messages.length) {
                  return const Padding(
                    padding: EdgeInsets.all(10),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: SwayaLight.accent)),
                    ),
                  );
                }
                return _Bubble(message: _messages[i]);
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 14),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    minLines: 1,
                    maxLines: 4,
                    decoration: const InputDecoration(
                        hintText: 'Ask about garments, fit, or your orders…'),
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                Material(
                  color: SwayaLight.cta,
                  shape: const CircleBorder(),
                  child: IconButton(
                    onPressed: _loading ? null : () => _send(),
                    icon: const Icon(Icons.arrow_upward, color: SwayaLight.onCta),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message});
  final _Msg message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.78),
        decoration: BoxDecoration(
          color: isUser ? SwayaLight.cta : SwayaLight.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
              color: isUser ? SwayaLight.cta : SwayaLight.border),
        ),
        child: Text(
          message.text,
          style: TextStyle(
            color: isUser ? SwayaLight.onCta : SwayaLight.inkPrimary,
            fontSize: 14,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}
