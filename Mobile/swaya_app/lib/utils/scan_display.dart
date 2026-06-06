/// Display helpers for scan list and detail screens.

String scanDisplayName({String? subjectLabel, required String scanId}) {
  final name = subjectLabel?.trim();
  if (name != null && name.isNotEmpty) return name;
  if (scanId.length >= 8) return 'Scan ${scanId.substring(0, 8)}';
  return 'Scan';
}

String formatScanDate(String? iso) {
  if (iso == null || iso.isEmpty) return '';
  final dt = DateTime.tryParse(iso);
  if (dt == null) return iso;
  final local = dt.toLocal();
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return '${months[local.month - 1]} ${local.day}, ${local.year} · '
      '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
}

String formatGroundTruthNum(double v) {
  return v == v.roundToDouble() ? v.round().toString() : v.toStringAsFixed(1);
}

String levelLabel(String key) {
  if (key.isEmpty) return key;
  return key[0].toUpperCase() + key.substring(1);
}

/// User-facing hint when the API returned no girths (quality gate rejected the scan).
String measurementRetakeHint(List<String> warnings) {
  final w = warnings.join(' ').toLowerCase();
  if (w.contains('pose_not_detected') || w.contains('pose_error')) {
    return 'Front pose was not detected. Step back until head and feet are in frame, '
        'stand straight facing the camera, arms slightly away from your body, good lighting.';
  }
  if (w.contains('measurements_unreliable') || w.contains('unreadable')) {
    return 'Body outline could not be measured (often loose or layered clothing). '
        'Wear a fitted top and trousers, plain background, then retake all three photos.';
  }
  return 'Could not measure this scan. Retake with full body in frame (head to feet), '
      'fitted clothing, arms slightly out, plain background — or enter tape measurements below.';
}
