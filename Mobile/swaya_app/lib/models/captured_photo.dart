import 'dart:typed_data';

/// In-memory photo — works on web, iOS, Android, and desktop.
class CapturedPhoto {
  const CapturedPhoto({
    required this.bytes,
    required this.filename,
  });

  final Uint8List bytes;
  final String filename;
}
