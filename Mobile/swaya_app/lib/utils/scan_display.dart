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
