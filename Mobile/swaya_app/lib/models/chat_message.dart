enum ChatRole { user, assistant }

class ChatMessage {
  ChatMessage({
    required this.role,
    required this.text,
    DateTime? createdAt,
  }) : createdAt = createdAt ?? DateTime.now();

  final ChatRole role;
  final String text;
  final DateTime createdAt;
}
