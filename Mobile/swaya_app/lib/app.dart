import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/auth_controller.dart';
import 'providers/capture_session.dart';
import 'providers/measurement_draft.dart';
import 'router/app_router.dart';
import 'services/push_service.dart';
import 'theme/swaya_theme.dart';

class SwayaApp extends StatefulWidget {
  const SwayaApp({super.key, this.firebaseReady = true});

  /// False when Firebase failed to initialize (e.g. before `flutterfire
  /// configure`). The AuthController then reports `unconfigured` and the router
  /// lets users through without forcing sign-in.
  final bool firebaseReady;

  @override
  State<SwayaApp> createState() => _SwayaAppState();
}

class _SwayaAppState extends State<SwayaApp> {
  late final AuthController _auth =
      AuthController(firebaseReady: widget.firebaseReady);
  late final _router = createAppRouter(_auth);

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: _auth),
        ChangeNotifierProvider(create: (_) => CaptureSession()),
        ChangeNotifierProvider(create: (_) => MeasurementDraft()),
      ],
      child: MaterialApp.router(
        title: 'DSV',
        debugShowCheckedModeBanner: false,
        scaffoldMessengerKey: rootMessengerKey,
        theme: buildSwayaTheme(),
        themeMode: ThemeMode.dark,
        routerConfig: _router,
      ),
    );
  }
}
