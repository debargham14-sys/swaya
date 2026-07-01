import 'package:flutter_test/flutter_test.dart';
import 'package:swaya_app/models/avatar_design.dart';
import 'package:swaya_app/models/blouse_measurements.dart';
import 'package:swaya_app/models/collab_message.dart';
import 'package:swaya_app/models/collab_session.dart';
import 'package:swaya_app/models/designer.dart';

void main() {
  group('AvatarDesign', () {
    test('round-trips through JSON, including measurements', () {
      final d = AvatarDesign(
        gender: 'male',
        colorIndex: 2,
        sleeves: true,
        watch: false,
        pants: true,
        garmentId: 'kurta',
        measurements: BlouseMeasurements({'chest': 92.0}),
      );
      final back = AvatarDesign.fromJson(d.toJson());
      expect(back.gender, 'male');
      expect(back.colorIndex, 2);
      expect(back.sleeves, true);
      expect(back.pants, true);
      expect(back.garmentId, 'kurta');
      expect(back.measurements!['chest'], 92.0);
    });

    test('defaults are sane and swatch index is clamped', () {
      const d = AvatarDesign();
      expect(d.gender, 'female');
      expect(d.colorIndex, 0);
      expect(d.measurements, isNull);
      // Out-of-range index clamps instead of throwing.
      const wild = AvatarDesign(colorIndex: 99);
      expect(wild.swatch, kAvatarPalette.last);
    });
  });

  test('Designer.fromJson reads rating + specialties', () {
    final d = Designer.fromJson({
      'id': 'd1',
      'name': 'Aanya',
      'specialties': ['Blouse', 'Lehenga'],
      'rating_avg': 4.5,
      'rating_count': 10,
      'available': true,
    });
    expect(d.id, 'd1');
    expect(d.specialties, ['Blouse', 'Lehenga']);
    expect(d.ratingAvg, 4.5);
    expect(d.ratingCount, 10);
  });

  test('CollabSession parses design + unread/other-name by role', () {
    final s = CollabSession.fromJson({
      'id': 'CS-1',
      'status': 'active',
      'design': {'gender': 'female', 'color_index': 1},
      'version': 3,
      'user_name': 'Priya',
      'designer_name': 'Aanya',
      'user_unread': 0,
      'designer_unread': 2,
      'updated_by': 'user',
    });
    expect(s.version, 3);
    expect(s.design.colorIndex, 1);
    expect(s.isActive, true);
    expect(s.unreadFor('designer'), 2);
    expect(s.otherName('designer'), 'Priya');
    expect(s.otherName('user'), 'Aanya');
  });

  test('CollabMessage exposes role + parsed time', () {
    final m = CollabMessage.fromJson({
      'id': 'CM-1',
      'sender_role': 'designer',
      'text': 'hi',
      'created_at': '2026-06-28T10:00:00+00:00',
    });
    expect(m.fromUser, false);
    expect(m.createdAt, isNotNull);
  });
}
