import 'package:flutter/material.dart';

import '../theme/swaya_theme.dart';

class StepDots extends StatelessWidget {
  const StepDots({super.key, required this.current, this.total = 3});

  final int current;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(total, (i) {
        final active = i < current;
        return Container(
          width: 8,
          height: 8,
          margin: const EdgeInsets.only(left: 6),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: active ? SwayaColors.accentHighlight : SwayaColors.borderSubtle,
          ),
        );
      }),
    );
  }
}
