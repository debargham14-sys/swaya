import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:swaya_app/theme/swaya_theme.dart';

void main() {
  test('Swaya theme uses dark brightness', () {
    final theme = buildSwayaTheme();
    expect(theme.brightness, Brightness.dark);
    expect(theme.scaffoldBackgroundColor, isNotNull);
  });
}
