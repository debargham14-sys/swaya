import '../models/chat_message.dart';
import '../models/measurement_result.dart';

/// Local fit assistant until an LLM API key is wired in.
class ChatService {
  Future<String> reply({
    required MeasurementResult measurements,
    required List<ChatMessage> history,
    required String userMessage,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 600));

    final lower = userMessage.toLowerCase();
    final waist = measurements.girthsCm['waist'];
    final bust = measurements.girthsCm['bust'];
    final hip = measurements.girthsCm['hip'];

    if (lower.contains('blouse') || lower.contains('lehenga') || lower.contains('ease')) {
      if (bust != null) {
        final easeLow = (bust + 5).toStringAsFixed(0);
        final easeHigh = (bust + 8).toStringAsFixed(0);
        return 'For a fitted blouse, add about 5–8 cm ease at bust '
            '(your ${bust.toStringAsFixed(1)} cm → cut roughly $easeLow–$easeHigh cm). '
            'Share a reference photo if you want help with shoulder or armhole depth.';
      }
    }

    if (lower.contains('size') || lower.contains('brand')) {
      if (waist != null) {
        return 'With a waist of ${waist.toStringAsFixed(1)} cm '
            '(${measurements.girthsIn['waist']?.toStringAsFixed(1) ?? '—'} in), '
            'many ready-to-wear charts put you around a US M / EU 38, but labels vary. '
            'What garment type are you buying (dress, trousers, jacket)?';
      }
    }

    if (lower.contains('waist')) {
      if (waist != null) {
        return 'Your estimated waist is ${waist.toStringAsFixed(1)} cm '
            '(${measurements.girthsIn['waist']?.toStringAsFixed(1) ?? '—'} in). '
            'Tell me the garment and how fitted you want it.';
      }
    }

    if (lower.contains('hip')) {
      if (hip != null) {
        return 'Hip girth is ${hip.toStringAsFixed(1)} cm '
            '(${measurements.girthsIn['hip']?.toStringAsFixed(1) ?? '—'} in). '
            'Use this for skirts, trousers, and lehenga bottoms.';
      }
    }

    if (lower.contains('bust')) {
      if (bust != null) {
        return 'Bust is ${bust.toStringAsFixed(1)} cm '
            '(${measurements.girthsIn['bust']?.toStringAsFixed(1) ?? '—'} in). '
            'Underbust is ${measurements.girthsCm['underbust']?.toStringAsFixed(1) ?? '—'} cm if you need bra sizing context.';
      }
    }

    if (lower.contains('accurate') || lower.contains('confidence')) {
      final conf = measurements.confidence;
      if (conf != null) {
        return 'This scan reported ${(conf * 100).round()}% confidence. '
            'Retake photos in fitted clothing, arms at sides, and full body in frame to improve accuracy.';
      }
    }

    return 'I have your latest scan on file (bust ${bust?.toStringAsFixed(1) ?? '—'} cm, '
        'waist ${waist?.toStringAsFixed(1) ?? '—'} cm, hip ${hip?.toStringAsFixed(1) ?? '—'} cm). '
        'Ask about sizing, ease, or a specific garment and I will walk through it.';
  }

  String welcomeMessage(MeasurementResult m) {
    final waist = m.girthsCm['waist'];
    if (waist == null) {
      return 'Your measurements are ready. What would you like help sizing?';
    }
    return 'Your waist is ${waist.toStringAsFixed(1)} cm '
        '(${m.girthsIn['waist']?.toStringAsFixed(1) ?? '—'} in) — '
        'typically around a medium in many brands. What garment are you shopping for?';
  }
}
