import 'package:flutter/foundation.dart';

import '../models/captured_photo.dart';
import '../models/measurement_result.dart';
import '../models/scan_record.dart';

class CaptureSession extends ChangeNotifier {
  double? heightCm;
  double? weightKg;
  String? subjectLabel;
  String? collectorId;
  bool consentGiven = false;

  final Map<CaptureView, CapturedPhoto?> _photos = {
    CaptureView.front: null,
    CaptureView.back: null,
    CaptureView.side: null,
  };

  MeasurementResult? lastResult;
  ScanRecord? lastScan;
  bool isMeasuring = false;
  String? measureError;

  CapturedPhoto? photoFor(CaptureView view) => _photos[view];

  bool get hasAllPhotos => _photos.values.every((f) => f != null);

  bool get canSubmit =>
      heightCm != null && heightCm! > 0 && hasAllPhotos && consentGiven;

  void setHeight(double? cm) {
    heightCm = cm;
    notifyListeners();
  }

  void setWeight(double? kg) {
    weightKg = kg;
    notifyListeners();
  }

  void setSubjectLabel(String? label) {
    subjectLabel = label?.trim().isEmpty == true ? null : label?.trim();
    notifyListeners();
  }

  void setCollectorId(String? id) {
    collectorId = id?.trim().isEmpty == true ? null : id?.trim();
    notifyListeners();
  }

  void setConsent(bool value) {
    consentGiven = value;
    notifyListeners();
  }

  void setPhoto(CaptureView view, CapturedPhoto photo) {
    _photos[view] = photo;
    notifyListeners();
  }

  void clearPhoto(CaptureView view) {
    _photos[view] = null;
    notifyListeners();
  }

  void resetCapture() {
    heightCm = null;
    weightKg = null;
    subjectLabel = null;
    collectorId = null;
    consentGiven = false;
    _photos.updateAll((_, __) => null);
    lastResult = null;
    lastScan = null;
    isMeasuring = false;
    measureError = null;
    notifyListeners();
  }

  void setScan(ScanRecord scan) {
    lastScan = scan;
    lastResult = scan.result;
    notifyListeners();
  }

  /// Clears capture + results and participant fields for a fresh scan.
  void resetForNewScan() => resetCapture();

  Map<CaptureView, CapturedPhoto> get photos {
    return Map.fromEntries(
      _photos.entries
          .where((e) => e.value != null)
          .map((e) => MapEntry(e.key, e.value!)),
    );
  }
}
