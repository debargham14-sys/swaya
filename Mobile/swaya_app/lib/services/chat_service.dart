import '../models/chat_message.dart';
import '../models/measurement_result.dart';
import 'assistant_api.dart';

/// Fit assistant backed by the API (LLM when configured, rules otherwise).
class ChatService {
  ChatService({AssistantApi? api}) : _api = api ?? AssistantApi();

  final AssistantApi _api;

  Future<String> reply({
    required MeasurementResult measurements,
    required List<ChatMessage> history,
    required String userMessage,
  }) async {
    final hist = history
        .where((m) => m.text.trim().isNotEmpty)
        .map((m) => {
              'role': m.role == ChatRole.user ? 'user' : 'assistant',
              'text': m.text,
            })
        .toList();

    return _api.chat(
      measurements: measurements,
      message: userMessage,
      history: hist,
    );
  }

  Future<String> welcomeMessage(MeasurementResult m) async {
    try {
      final suggestion = await _api.suggest(
        measurements: m,
        calibrated: m.isCalibrated,
      );
      if (suggestion.suggestions.trim().isNotEmpty) {
        return suggestion.suggestions;
      }
    } catch (_) {
      // Fall through to local default.
    }
    final waist = m.girthsCm['waist'];
    if (waist == null) {
      return 'Your measurements are ready. What garment would you like help sizing?';
    }
    return 'Your waist is ${waist.toStringAsFixed(1)} cm '
        '(${m.girthsIn['waist']?.toStringAsFixed(1) ?? '—'} in). '
        'Ask about blouse, kurta, lehenga, or ease for a specific fit.';
  }
}
