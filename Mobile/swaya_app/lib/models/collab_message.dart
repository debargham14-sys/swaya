/// A single chat message within a collaboration session.
class CollabMessage {
  CollabMessage({
    required this.id,
    required this.senderRole,
    required this.text,
    this.sessionId,
    this.senderId,
    this.createdAtIso,
  });

  final String id;

  /// `'user'` or `'designer'`.
  final String senderRole;
  final String text;
  final String? sessionId;
  final String? senderId;
  final String? createdAtIso;

  bool get fromUser => senderRole == 'user';

  DateTime? get createdAt =>
      createdAtIso == null ? null : DateTime.tryParse(createdAtIso!);

  factory CollabMessage.fromJson(Map<String, dynamic> json) => CollabMessage(
        id: json['id'] as String,
        senderRole: json['sender_role'] as String? ?? 'user',
        text: json['text'] as String? ?? '',
        sessionId: json['session_id'] as String?,
        senderId: json['sender_id'] as String?,
        createdAtIso: json['created_at'] as String?,
      );
}
