import 'avatar_design.dart';

/// A live collaboration between a user and a designer over one shared avatar
/// [design]. The [version] advances each time either party edits the design;
/// clients re-apply the design when it increases (see CollabController).
class CollabSession {
  CollabSession({
    required this.id,
    required this.status,
    required this.design,
    required this.version,
    this.userId,
    this.designerId,
    this.userName,
    this.designerName,
    this.updatedBy,
    this.lastMessage,
    this.userUnread = 0,
    this.designerUnread = 0,
    this.updatedAtIso,
  });

  final String id;

  /// `pending` | `active` | `ended`.
  final String status;
  final AvatarDesign design;
  final int version;
  final String? userId;
  final String? designerId;
  final String? userName;
  final String? designerName;

  /// Which side made the last design edit (`user` | `designer`).
  final String? updatedBy;
  final String? lastMessage;
  final int userUnread;
  final int designerUnread;
  final String? updatedAtIso;

  bool get isPending => status == 'pending';
  bool get isActive => status == 'active';
  bool get isEnded => status == 'ended';

  /// Unread count from the perspective of [role] (`user` | `designer`).
  int unreadFor(String role) => role == 'designer' ? designerUnread : userUnread;

  /// The other participant's display name, given the viewer's [role].
  String otherName(String role) =>
      (role == 'designer' ? userName : designerName) ?? 'Collaborator';

  factory CollabSession.fromJson(Map<String, dynamic> json) => CollabSession(
        id: json['id'] as String,
        status: json['status'] as String? ?? 'pending',
        design: AvatarDesign.fromJson(
            (json['design'] as Map?)?.cast<String, dynamic>() ?? const {}),
        version: (json['version'] as num?)?.toInt() ?? 1,
        userId: json['user_id'] as String?,
        designerId: json['designer_id'] as String?,
        userName: json['user_name'] as String?,
        designerName: json['designer_name'] as String?,
        updatedBy: json['updated_by'] as String?,
        lastMessage: json['last_message'] as String?,
        userUnread: (json['user_unread'] as num?)?.toInt() ?? 0,
        designerUnread: (json['designer_unread'] as num?)?.toInt() ?? 0,
        updatedAtIso: json['updated_at'] as String?,
      );
}
