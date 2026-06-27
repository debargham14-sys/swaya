// Web backend: drive the <model-viewer> custom element directly from Dart.
//
// model_viewer_plus (web) injects <model-viewer> into the SAME document as the
// Flutter app, so we reach it with document.querySelector and call its
// scene-graph API. Recolour / show / hide all go through one path: set a
// material's baseColorFactor (rgb + alpha). Parts that ship as alphaMode=BLEND
// are revealed by raising alpha to 1 and hidden by dropping it to 0 — in real
// time, no GLB reload.
import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:math' as math;

import 'package:web/web.dart' as web;

// glTF baseColorFactor is linear; swatches are sRGB -> convert so the rendered
// colour matches the swatch.
double _toLinear(int c) {
  final s = c / 255.0;
  return s <= 0.04045 ? s / 12.92 : math.pow((s + 0.055) / 1.055, 2.4).toDouble();
}

class GarmentRecolor {
  // Desired state per material: name -> [linR, linG, linB, alpha]. Kept so we can
  // re-apply once the model finishes loading (querySelector may run first).
  final Map<String, List<double>> _want = {};
  Timer? _poll;

  // Web has no WebViewController; the element is in the document.
  void attach(Object? controller) {}

  void setMaterial(String name, int r, int g, int b, double a) {
    _want[name] = [_toLinear(r), _toLinear(g), _toLinear(b), a];
    if (!_apply()) _startPoll();
  }

  void _startPoll() {
    _poll?.cancel();
    var tries = 0;
    _poll = Timer.periodic(const Duration(milliseconds: 120), (t) {
      if (_apply() || ++tries > 60) t.cancel();
    });
  }

  bool _apply() {
    final el = web.document.querySelector('model-viewer');
    if (el == null) return false;
    final mv = el as JSObject;
    final model = mv.getProperty('model'.toJS);
    if (model.isUndefinedOrNull) return false;
    final mats = (model as JSObject).getProperty('materials'.toJS);
    if (mats.isUndefinedOrNull) return false;
    for (final entry in (mats as JSArray).toDart) {
      final mat = entry as JSObject;
      final nm = (mat.getProperty('name'.toJS) as JSString?)?.toDart;
      final want = nm == null ? null : _want[nm];
      if (want == null) continue;
      final pbr = mat.getProperty('pbrMetallicRoughness'.toJS) as JSObject;
      final color =
          [want[0].toJS, want[1].toJS, want[2].toJS, want[3].toJS].toJS;
      pbr.callMethod('setBaseColorFactor'.toJS, color);
    }
    return true;
  }
}
