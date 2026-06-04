import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/capture_session.dart';
import 'router/app_router.dart';
import 'theme/swaya_theme.dart';

class SwayaApp extends StatelessWidget {
  SwayaApp({super.key});

  final _router = createAppRouter();

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => CaptureSession(),
      child: MaterialApp.router(
        title: 'DSV',
        debugShowCheckedModeBanner: false,
        theme: buildSwayaTheme(),
        themeMode: ThemeMode.dark,
        routerConfig: _router,
      ),
    );
  }
}
