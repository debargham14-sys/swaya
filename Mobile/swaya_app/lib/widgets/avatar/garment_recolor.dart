// Live garment-recolour channel for the <model-viewer> avatar.
//
// One small API, two platform backends:
//   * web    — model-viewer lives in the SAME document as Flutter, so we reach
//     it with js_interop and edit material baseColorFactor directly.
//   * mobile — model-viewer runs inside a WebView; we drive it by running the
//     equivalent JS through the WebViewController handed to us by
//     ModelViewer.onWebViewCreated.
//
// Either way recolour / show / hide is a direct GPU material edit on the already
// loaded GLB — no reload, no per-frame Dart work.
export 'garment_recolor_stub.dart'
    if (dart.library.js_interop) 'garment_recolor_web.dart'
    if (dart.library.io) 'garment_recolor_mobile.dart';
