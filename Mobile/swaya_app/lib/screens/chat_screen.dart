import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../models/chat_message.dart';
import '../providers/capture_session.dart';
import '../services/chat_service.dart';
import '../theme/swaya_theme.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _chat = ChatService();
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _messages = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadWelcome();
  }

  Future<void> _loadWelcome() async {
    final result = context.read<CaptureSession>().lastResult;
    if (result == null) return;
    setState(() => _loading = true);
    try {
      final text = await _chat.welcomeMessage(result);
      if (!mounted) return;
      setState(() {
        _messages.add(ChatMessage(role: ChatRole.assistant, text: text));
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _loading) return;

    final session = context.read<CaptureSession>();
    final result = session.lastResult;
    if (result == null) return;

    setState(() {
      _messages.add(ChatMessage(role: ChatRole.user, text: text));
      _loading = true;
      _controller.clear();
    });
    _scrollToEnd();

    try {
      final reply = await _chat.reply(
        measurements: result,
        history: _messages,
        userMessage: text,
      );
      if (!mounted) return;
      setState(() {
        _messages.add(ChatMessage(role: ChatRole.assistant, text: reply));
        _loading = false;
      });
      _scrollToEnd();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not get a reply: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = context.watch<CaptureSession>().lastResult;

    if (result == null) {
      return Scaffold(
        backgroundColor: SwayaColors.base,
        appBar: AppBar(title: const Text('Fit assistant')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'Complete a body scan first — then ask about blouse, kurta, or lehenga sizing.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: SwayaColors.inkSecondary,
                  ),
            ),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: SwayaColors.base,
      appBar: AppBar(
        title: const Text('Fit assistant'),
        leading: context.canPop()
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () => context.pop(),
              )
            : null,
      ),
      body: Column(
        children: [
          if (result != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final entry in ['waist', 'hip', 'bust'])
                    if (result.girthsCm[entry] != null)
                      ActionChip(
                        label: Text(
                          '${entry[0].toUpperCase()}${entry.substring(1)} '
                          '${result.girthsCm[entry]!.toStringAsFixed(0)} cm',
                          style: const TextStyle(fontSize: 12),
                        ),
                        backgroundColor: SwayaColors.elevated,
                        side: const BorderSide(color: SwayaColors.borderSubtle),
                        onPressed: () {
                          _controller.text = 'Tell me more about my $entry measurement';
                        },
                      ),
                ],
              ),
            ),
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: _messages.length + (_loading ? 1 : 0),
              itemBuilder: (context, i) {
                if (_loading && i == _messages.length) {
                  return const Padding(
                    padding: EdgeInsets.all(12),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    ),
                  );
                }
                return ChatBubble(message: _messages[i]);
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      hintText: 'Ask about fit or sizing…',
                    ),
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                Material(
                  color: SwayaColors.accent,
                  shape: const CircleBorder(),
                  child: IconButton(
                    onPressed: _loading ? null : _send,
                    icon: const Icon(Icons.arrow_upward, color: SwayaColors.onAccent),
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
