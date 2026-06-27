// Mobile backend: <model-viewer> runs inside a WebView, so we recolour by
// running JS through the WebViewController that ModelViewer.onWebViewCreated
// hands us.
//
// The injected JS is self-contained and idempotent: it stores the desired
// colour for each material on `window.__sway`, applies it if the model is
// already loaded, and otherwise binds a one-time `load` listener so the colour
// lands the moment the GLB finishes loading. That makes the call order between
// "page ready" and "set colour" irrelevant — whichever happens last wins.
import 'dart:async';
import 'dart:math' as math;

import 'package:webview_flutter/webview_flutter.dart';

// glTF baseColorFactor is linear; swatches are sRGB -> convert so the rendered
// colour matches the swatch.
double _toLinear(int c) {
  final s = c / 255.0;
  return s <= 0.04045 ? s / 12.92 : math.pow((s + 0.055) / 1.055, 2.4).toDouble();
}

String _num(double v) => v.toStringAsFixed(5);

class GarmentRecolor {
  WebViewController? _controller;

  void attach(Object? controller) {
    if (controller is WebViewController) _controller = controller;
  }

  void setMaterial(String name, int r, int g, int b, double a) {
    final c = _controller;
    if (c == null) return;
    final lr = _num(_toLinear(r));
    final lg = _num(_toLinear(g));
    final lb = _num(_toLinear(b));
    final al = _num(a);
    final js = '''
(function(){
  var mv = document.querySelector('model-viewer');
  if (!mv) return;
  var S = window.__sway || (window.__sway = { want: {}, bound: false });
  S.want['$name'] = [$lr, $lg, $lb, $al];
  S.apply = function(){
    var m = mv.model;
    if (!m || !m.materials) return false;
    m.materials.forEach(function(x){
      var w = S.want[x.name];
      if (w) x.pbrMetallicRoughness.setBaseColorFactor(w);
    });
    return true;
  };
  if (!S.apply() && !S.bound){
    S.bound = true;
    mv.addEventListener('load', function(){ S.apply(); });
  }
})();
''';
    // Fire and forget; ignore the race where the page DOM isn't up on the very
    // first call (the periodic re-push from the screen covers it).
    unawaited(c.runJavaScript(js).catchError((_) {}));
  }
}
