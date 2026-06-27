import 'package:flutter/foundation.dart';

import '../models/blouse_measurements.dart';
import '../models/captured_photo.dart';

/// How the in-progress measurements were produced.
enum MeasurementSource { manual, photos }

/// Holds the in-progress measurement session that spans Add Measurements →
/// Manual Entry / Capture → Review → Save (Figma frames 12–21).
class MeasurementDraft extends ChangeNotifier {
  MeasurementSource source = MeasurementSource.manual;
  final BlouseMeasurements measurements = BlouseMeasurements();

  // Photo-capture path (frames 15–16).
  final Map<String, CapturedPhoto?> _photos = {
    'front': null,
    'side': null,
    'back': null,
  };

  CapturedPhoto? photo(String view) => _photos[view];
  bool get hasAllPhotos => _photos.values.every((p) => p != null);
  int get photoCount => _photos.values.where((p) => p != null).length;

  void setSource(MeasurementSource s) {
    source = s;
    notifyListeners();
  }

  void setField(String key, double? cm) {
    measurements.set(key, cm);
    notifyListeners();
  }

  void setPhoto(String view, CapturedPhoto? photo) {
    if (_photos.containsKey(view)) {
      _photos[view] = photo;
      notifyListeners();
    }
  }

  void reset() {
    measurements.values.clear();
    for (final k in _photos.keys) {
      _photos[k] = null;
    }
    source = MeasurementSource.manual;
    notifyListeners();
  }
}
