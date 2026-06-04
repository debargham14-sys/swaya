import 'package:flutter/material.dart';

import '../models/captured_photo.dart';

class CapturedPhotoImage extends StatelessWidget {
  const CapturedPhotoImage({
    super.key,
    required this.photo,
    this.fit = BoxFit.cover,
  });

  final CapturedPhoto photo;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    return Image.memory(photo.bytes, fit: fit, gaplessPlayback: true);
  }
}
