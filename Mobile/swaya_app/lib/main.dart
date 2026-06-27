import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app.dart';
import 'firebase_options.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarBrightness: Brightness.dark,
      statusBarIconBrightness: Brightness.light,
    ),
  );

  // Boot Firebase before the app. If credentials aren't configured yet
  // (placeholder firebase_options.dart), fall back to "auth-unconfigured" so
  // the rest of the app is still runnable during development.
  var firebaseReady = false;
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
    firebaseReady = true;
  } catch (e) {
    debugPrint(
      'Firebase not initialized — running without auth. '
      'Run `flutterfire configure` to enable sign-in. ($e)',
    );
  }

  runApp(SwayaApp(firebaseReady: firebaseReady));
}
