import 'package:flutter/material.dart';

import '../theme/swaya_theme.dart';

class SwayaScaffold extends StatelessWidget {
  const SwayaScaffold({
    super.key,
    required this.body,
    this.title,
    this.leading,
    this.bottomBar,
    this.padding = const EdgeInsets.symmetric(horizontal: 20),
  });

  final Widget body;
  final String? title;
  final Widget? leading;
  final Widget? bottomBar;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SwayaColors.base,
      appBar: title != null
          ? AppBar(
              leading: leading,
              title: Text(title!),
            )
          : null,
      body: SafeArea(
        child: Padding(
          padding: padding,
          child: body,
        ),
      ),
      bottomNavigationBar: bottomBar != null
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                child: bottomBar,
              ),
            )
          : null,
    );
  }
}
