import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'orders_api.dart';

const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String _fmtDate(DateTime d) => '${d.day} ${_months[d.month - 1]} ${d.year}';

/// Places a blouse order for the given persona's measurements, shows feedback,
/// and routes to the Orders tab where the new active order appears.
Future<void> placeBlouseOrder(
  BuildContext context, {
  String? personaName,
  OrdersApi? api,
}) async {
  final messenger = ScaffoldMessenger.of(context);
  messenger.showSnackBar(const SnackBar(content: Text('Placing your order…')));
  try {
    final now = DateTime.now();
    await (api ?? OrdersApi()).createOrder(
      placedOn: _fmtDate(now),
      estimatedDate: _fmtDate(now.add(const Duration(days: 14))),
      noteTitle: personaName != null ? 'For $personaName' : 'Custom blouse',
      noteBody: 'Tailored from your saved measurements.',
    );
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      const SnackBar(content: Text('Order placed! Track it under Orders.')),
    );
    if (context.mounted) context.go('/orders');
  } catch (e) {
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text('Could not place order: $e')));
  }
}
