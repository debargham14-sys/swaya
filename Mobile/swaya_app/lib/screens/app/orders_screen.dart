import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../models/blouse_order.dart';
import '../../services/orders_api.dart';
import '../../theme/swaya_light_theme.dart';
import 'app_chrome.dart';

/// Orders — Figma frames 22–31. Four tabs (Active / Delivered / Alterations /
/// Cancelled), each with an empty state and a populated list of order cards,
/// plus the Cancel Order and Request Alteration sheets.
///
/// Orders are loaded from the `/v1/orders` backend (DynamoDB, scoped to the
/// signed-in user). Cancel and Alteration call the backend, then reload. The
/// empty state offers a "Load sample orders" seed so the design is previewable.
class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key});

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen> {
  final OrdersApi _api = OrdersApi();
  OrderTab _tab = OrderTab.active;
  bool _showTip = true;
  bool _loading = true;
  bool _busy = false; // a mutation (cancel/alteration/seed) is in flight
  String? _error;

  Map<OrderTab, List<BlouseOrder>> _orders = {
    for (final t in OrderTab.values) t: <BlouseOrder>[],
  };

  List<BlouseOrder> get _current => _orders[_tab]!;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _snack(String msg) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _load() async {
    if (mounted) setState(() => _error = null);
    try {
      final all = await _api.list();
      final grouped = {for (final t in OrderTab.values) t: <BlouseOrder>[]};
      for (final o in all) {
        grouped[o.tab]!.add(o);
      }
      if (!mounted) return;
      setState(() {
        _orders = grouped;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _seed() async {
    setState(() => _busy = true);
    try {
      await _api.seedSamples();
    } catch (e) {
      _snack('Could not load samples: $e');
    }
    await _load();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _cancelOrder(BlouseOrder order) async {
    final reason = await _showCancelSheet(context);
    if (reason == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await _api.cancel(order.id, reason);
      _snack('Order ${order.id} cancelled.');
    } catch (e) {
      _snack('Cancel failed: $e');
    }
    await _load();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _requestAlteration(BlouseOrder order) async {
    final description = await _showAlterationSheet(context);
    if (description == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await _api.requestAlteration(order.id, description);
      _snack('Alteration requested for ${order.id}.');
    } catch (e) {
      _snack('Alteration failed: $e');
    }
    await _load();
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return LightScaffold(
      title: 'Orders',
      showMenu: true,
      navIndex: 0,
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
            child: _OrdersTabBar(
              selected: _tab,
              onSelect: (t) => setState(() => _tab = t),
            ),
          ),
          if (_busy) const LinearProgressIndicator(minHeight: 2),
          Expanded(child: _content()),
        ],
      ),
    );
  }

  Widget _content() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _current.isEmpty) {
      return _ErrorRetry(message: _error!, onRetry: _load);
    }
    if (_current.isEmpty) {
      return RefreshIndicator(
        onRefresh: _load,
        child: _EmptyState(tab: _tab, onSeed: _busy ? null : _seed),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: _OrderList(
        tab: _tab,
        orders: _current,
        showTip: _tab == OrderTab.active && _showTip,
        onDismissTip: () => setState(() => _showTip = false),
        onCancel: _cancelOrder,
        onAlteration: _requestAlteration,
        onViewDetails: (o) => _snack('Details for ${o.id} coming soon.'),
      ),
    );
  }
}

class _ErrorRetry extends StatelessWidget {
  const _ErrorRetry({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, color: SwayaLight.inkTertiary, size: 40),
            const SizedBox(height: 12),
            const Text("Couldn't load orders",
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 16,
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            Text(message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    color: SwayaLight.inkSecondary, fontSize: 12)),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab bar
// ─────────────────────────────────────────────────────────────────────────────

class _OrdersTabBar extends StatelessWidget {
  const _OrdersTabBar({required this.selected, required this.onSelect});
  final OrderTab selected;
  final ValueChanged<OrderTab> onSelect;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Row(
        children: [
          for (final t in OrderTab.values)
            Expanded(
              child: GestureDetector(
                onTap: () => onSelect(t),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  height: 40,
                  decoration: BoxDecoration(
                    color:
                        t == selected ? SwayaLight.canvas : Colors.transparent,
                    borderRadius: BorderRadius.circular(10),
                    border: t == selected
                        ? Border.all(color: SwayaLight.border)
                        : null,
                  ),
                  alignment: Alignment.center,
                  child: Icon(
                    t.icon,
                    size: 20,
                    color: t == selected
                        ? SwayaLight.inkPrimary
                        : SwayaLight.inkTertiary,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Populated list
// ─────────────────────────────────────────────────────────────────────────────

class _OrderList extends StatelessWidget {
  const _OrderList({
    required this.tab,
    required this.orders,
    required this.showTip,
    required this.onDismissTip,
    required this.onCancel,
    required this.onAlteration,
    required this.onViewDetails,
  });

  final OrderTab tab;
  final List<BlouseOrder> orders;
  final bool showTip;
  final VoidCallback onDismissTip;
  final ValueChanged<BlouseOrder> onCancel;
  final ValueChanged<BlouseOrder> onAlteration;
  final ValueChanged<BlouseOrder> onViewDetails;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Text(tab.title,
            style: const TextStyle(
                color: SwayaLight.inkPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text(_countLine(tab, orders.length),
            style:
                const TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
        const SizedBox(height: 16),
        if (showTip) ...[
          _TipBanner(onDismiss: onDismissTip),
          const SizedBox(height: 16),
        ],
        for (final o in orders) ...[
          _OrderCard(
            tab: tab,
            order: o,
            onCancel: () => onCancel(o),
            onAlteration: () => onAlteration(o),
            onViewDetails: () => onViewDetails(o),
          ),
          const SizedBox(height: 16),
        ],
        const SizedBox(height: 4),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => context.go('/home-v2'),
            child: const Text('Continue Shopping'),
          ),
        ),
      ],
    );
  }

  String _countLine(OrderTab tab, int n) => switch (tab) {
        OrderTab.active => 'You have $n active garment ${_plural(n, 'order')}.',
        OrderTab.delivered =>
          '$n ${_plural(n, 'order')} delivered successfully.',
        OrderTab.alterations =>
          '$n alteration ${_plural(n, 'request')} in progress.',
        OrderTab.cancelled =>
          '$n cancelled ${_plural(n, 'order')} ${n == 1 ? 'is' : 'are'} available.',
      };

  String _plural(int n, String word) => n == 1 ? word : '${word}s';
}

// ─────────────────────────────────────────────────────────────────────────────
// Order card
// ─────────────────────────────────────────────────────────────────────────────

class _OrderCard extends StatelessWidget {
  const _OrderCard({
    required this.tab,
    required this.order,
    required this.onCancel,
    required this.onAlteration,
    required this.onViewDetails,
  });

  final OrderTab tab;
  final BlouseOrder order;
  final VoidCallback onCancel;
  final VoidCallback onAlteration;
  final VoidCallback onViewDetails;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SwayaLight.canvas,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: SwayaLight.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: id + placed date / status badge
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Order ID: ${order.id}',
                        style: const TextStyle(
                            color: SwayaLight.inkPrimary,
                            fontSize: 14,
                            fontWeight: FontWeight.w700)),
                    const SizedBox(height: 2),
                    Text('Placed on ${order.placedOn}',
                        style: const TextStyle(
                            color: SwayaLight.inkTertiary, fontSize: 12)),
                  ],
                ),
              ),
              _StatusBadge(status: order.status),
            ],
          ),
          const SizedBox(height: 14),
          _GarmentThumb(garment: order.garment),
          if (order.noteTitle != null) ...[
            const SizedBox(height: 14),
            _NoteBox(title: order.noteTitle!, body: order.noteBody ?? ''),
          ],
          const SizedBox(height: 16),
          const _Label('Order Tracking'),
          const SizedBox(height: 12),
          _Tracker(steps: order.tracking),
          const SizedBox(height: 16),
          _MetaRow(
            icon: Icons.event_outlined,
            label: 'Estimated date',
            value: order.estimatedDate,
          ),
          const SizedBox(height: 8),
          _MetaRow(
            icon: Icons.location_on_outlined,
            label: 'Address',
            value: order.location,
          ),
          if (order.deliveryPerson != null) ...[
            const SizedBox(height: 8),
            _MetaRow(
              icon: Icons.person_outline,
              label: 'Delivery person',
              value: '${order.deliveryPerson}  ·  ${order.deliveryPhone}',
            ),
          ],
          const SizedBox(height: 16),
          const Divider(height: 1, color: SwayaLight.border),
          const SizedBox(height: 12),
          _PriceRow(order: order),
          const SizedBox(height: 8),
          const Divider(height: 1, color: SwayaLight.border),
          const SizedBox(height: 4),
          _ActionRow(
            tab: tab,
            onCancel: onCancel,
            onAlteration: onAlteration,
            onViewDetails: onViewDetails,
          ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final OrderStatus status;

  @override
  Widget build(BuildContext context) {
    final c = status.color;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: c.withValues(alpha: 0.4)),
      ),
      child: Text(status.label,
          style:
              TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class _GarmentThumb extends StatelessWidget {
  const _GarmentThumb({required this.garment});

  final String garment;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 96,
      decoration: BoxDecoration(
        color: SwayaLight.surfaceAlt,
        borderRadius: BorderRadius.circular(12),
      ),
      alignment: Alignment.center,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.checkroom, size: 18, color: SwayaLight.inkTertiary),
          const SizedBox(width: 8),
          Text('$garment Details',
              style: const TextStyle(
                  color: SwayaLight.inkSecondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _NoteBox extends StatelessWidget {
  const _NoteBox({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFBF4E6), // warm note tint
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFEAD9B0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  color: Color(0xFF8A6D1F),
                  fontSize: 12,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 2),
          Text(body,
              style: const TextStyle(color: Color(0xFF7A6526), fontSize: 12)),
        ],
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Text(text,
      style: const TextStyle(
          color: SwayaLight.inkPrimary,
          fontSize: 13,
          fontWeight: FontWeight.w700));
}

class _Tracker extends StatelessWidget {
  const _Tracker({required this.steps});
  final List<TrackingStep> steps;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var i = 0; i < steps.length; i++)
          Expanded(
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(child: _bar(i > 0 && steps[i].done)),
                    _dot(steps[i].done),
                    Expanded(
                        child:
                            _bar(i < steps.length - 1 && steps[i + 1].done)),
                  ],
                ),
                const SizedBox(height: 6),
                Text(steps[i].label,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: steps[i].done
                            ? SwayaLight.inkPrimary
                            : SwayaLight.inkTertiary,
                        fontSize: 10,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ),
      ],
    );
  }

  Widget _dot(bool done) => Container(
        width: 14,
        height: 14,
        decoration: BoxDecoration(
          color: done ? SwayaLight.accent : SwayaLight.canvas,
          shape: BoxShape.circle,
          border: Border.all(
              color: done ? SwayaLight.accent : SwayaLight.border, width: 2),
        ),
        child:
            done ? const Icon(Icons.check, size: 8, color: Colors.white) : null,
      );

  Widget _bar(bool active) => Container(
        height: 2,
        color: active ? SwayaLight.accent : SwayaLight.border,
      );
}

class _MetaRow extends StatelessWidget {
  const _MetaRow(
      {required this.icon, required this.label, required this.value});
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: SwayaLight.inkTertiary),
        const SizedBox(width: 8),
        Expanded(
          child: RichText(
            text: TextSpan(
              style:
                  const TextStyle(fontSize: 12, color: SwayaLight.inkPrimary),
              children: [
                TextSpan(
                    text: '$label:  ',
                    style: const TextStyle(color: SwayaLight.inkTertiary)),
                TextSpan(
                    text: value,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PriceRow extends StatelessWidget {
  const _PriceRow({required this.order});
  final BlouseOrder order;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _cell('Subtotal', order.subtotal),
        _cell('Shipping', order.shipping, free: order.shipping == 0),
        _cell('Total', order.total, bold: true),
      ],
    );
  }

  Widget _cell(String label, double amount,
          {bool bold = false, bool free = false}) =>
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: const TextStyle(
                    color: SwayaLight.inkTertiary, fontSize: 11)),
            const SizedBox(height: 2),
            Text(free ? 'Free' : '₹ ${amount.toStringAsFixed(0)}',
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 13,
                    fontWeight: bold ? FontWeight.w800 : FontWeight.w600)),
          ],
        ),
      );
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.tab,
    required this.onCancel,
    required this.onAlteration,
    required this.onViewDetails,
  });

  final OrderTab tab;
  final VoidCallback onCancel;
  final VoidCallback onAlteration;
  final VoidCallback onViewDetails;

  @override
  Widget build(BuildContext context) {
    // (label, color, callback) for the left-hand primary action per tab.
    final (String, Color, VoidCallback) primary = switch (tab) {
      OrderTab.active => ('Cancel Order', SwayaLight.error, onCancel),
      OrderTab.delivered =>
        ('Request Alteration', SwayaLight.accent, onAlteration),
      OrderTab.alterations => ('Cancel Alteration', SwayaLight.error, onCancel),
      OrderTab.cancelled => ('Order Again', SwayaLight.accent, onViewDetails),
    };

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        TextButton(
          onPressed: primary.$3,
          style: TextButton.styleFrom(
              foregroundColor: primary.$2,
              padding: const EdgeInsets.symmetric(horizontal: 4)),
          child: Text(primary.$1,
              style: const TextStyle(fontWeight: FontWeight.w700)),
        ),
        TextButton(
          onPressed: onViewDetails,
          style: TextButton.styleFrom(
              foregroundColor: SwayaLight.inkPrimary,
              padding: const EdgeInsets.symmetric(horizontal: 4)),
          child: const Text('View Details',
              style: TextStyle(fontWeight: FontWeight.w700)),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty states (frames 22 / 25 / 28 / 30)
// ─────────────────────────────────────────────────────────────────────────────

typedef _EmptyRow = ({IconData icon, String title, String sub});
typedef _EmptySpec = ({
  IconData icon,
  String title,
  String body,
  String cta,
  String route,
  List<_EmptyRow> rows,
});

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.tab, this.onSeed});
  final OrderTab tab;
  final VoidCallback? onSeed;

  _EmptySpec get _spec => switch (tab) {
        OrderTab.active => (
            icon: Icons.add,
            title: 'No active orders yet',
            body:
                'Place a garment order and track every step here — design, measurements, production and delivery.',
            cta: 'Design & Order',
            route: '/measure',
            rows: [
              (
                icon: Icons.bookmark_border,
                title: 'Continue a saved design',
                sub: 'Pick up a draft you started earlier.'
              ),
            ],
          ),
        OrderTab.delivered => (
            icon: Icons.local_shipping_outlined,
            title: 'No delivered orders yet',
            body:
                'Your completed garment orders will appear here after delivery.',
            cta: 'Design & Order',
            route: '/measure',
            rows: [
              (
                icon: Icons.history,
                title: 'Order history',
                sub: 'Deliveries, returns and alterations show up here.'
              ),
              (
                icon: Icons.add_circle_outline,
                title: 'Start a new design',
                sub: 'Create your next custom garment.'
              ),
            ],
          ),
        OrderTab.alterations => (
            icon: Icons.content_cut,
            title: 'No alteration request yet',
            body:
                'Requests from delivered orders will appear here with status, progress and delivery updates.',
            cta: 'View Delivered Orders',
            route: '/orders',
            rows: [
              (
                icon: Icons.check_circle_outline,
                title: 'Check delivered orders',
                sub: 'Open a delivered order and request fit changes.'
              ),
            ],
          ),
        OrderTab.cancelled => (
            icon: Icons.receipt_long_outlined,
            title: 'No cancelled orders yet',
            body:
                'Cancelled orders, refund updates and rejected cancellation requests will appear here.',
            cta: 'View Active Orders',
            route: '/orders',
            rows: [
              (
                icon: Icons.manage_history,
                title: 'Manage current orders',
                sub: 'Active orders you can still cancel show up here.'
              ),
            ],
          ),
      };

  @override
  Widget build(BuildContext context) {
    final s = _spec;
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      children: [
        Text(tab.title,
            style: const TextStyle(
                color: SwayaLight.inkPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text(tab.subtitle,
            style:
                const TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
          decoration: BoxDecoration(
            color: SwayaLight.canvas,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: SwayaLight.border),
          ),
          child: Column(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
                    color: SwayaLight.surfaceAlt, shape: BoxShape.circle),
                child: Icon(s.icon, color: SwayaLight.inkSecondary),
              ),
              const SizedBox(height: 16),
              Text(s.title,
                  style: const TextStyle(
                      color: SwayaLight.inkPrimary,
                      fontSize: 16,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              Text(s.body,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: SwayaLight.inkSecondary, fontSize: 13)),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => context.go(s.route),
                  child: Text(s.cta),
                ),
              ),
              if (onSeed != null) ...[
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: onSeed,
                    icon: const Icon(Icons.auto_awesome, size: 18),
                    label: const Text('Load sample orders'),
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 16),
        for (final r in s.rows) ...[
          AppCard(
            onTap: () => context.go('/measure'),
            child: Row(
              children: [
                Icon(r.icon, color: SwayaLight.inkSecondary, size: 22),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(r.title,
                          style: const TextStyle(
                              color: SwayaLight.inkPrimary,
                              fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text(r.sub,
                          style: const TextStyle(
                              color: SwayaLight.inkSecondary, fontSize: 12)),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, color: SwayaLight.inkTertiary),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

class _TipBanner extends StatelessWidget {
  const _TipBanner({required this.onDismiss});
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 4, 4, 4),
      decoration: BoxDecoration(
        color: const Color(0xFFFBF4E6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFEAD9B0)),
      ),
      child: Row(
        children: [
          const Icon(Icons.lightbulb_outline,
              size: 18, color: Color(0xFF8A6D1F)),
          const SizedBox(width: 10),
          const Expanded(
            child: Text('Tip: track new orders here after checkout.',
                style: TextStyle(color: Color(0xFF7A6526), fontSize: 12)),
          ),
          IconButton(
            onPressed: onDismiss,
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.close, size: 16, color: Color(0xFF8A6D1F)),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Cancel Order sheet (frame 24)
// ─────────────────────────────────────────────────────────────────────────────

Future<String?> _showCancelSheet(BuildContext context) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: SwayaLight.canvas,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    // Re-apply the light theme — the sheet renders outside LightScaffold's wrap.
    builder: (ctx) => Theme(
      data: buildSwayaLightTheme(),
      child: Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
        child: const _CancelSheetBody(),
      ),
    ),
  );
}

class _CancelSheetBody extends StatefulWidget {
  const _CancelSheetBody();
  @override
  State<_CancelSheetBody> createState() => _CancelSheetBodyState();
}

class _CancelSheetBodyState extends State<_CancelSheetBody> {
  String? _reason;
  final _other = TextEditingController();

  @override
  void dispose() {
    _other.dispose();
    super.dispose();
  }

  String? get _resolved {
    if (_reason == null) return null;
    if (_reason == 'Others') {
      return _other.text.trim().isEmpty ? 'Others' : _other.text.trim();
    }
    return _reason;
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.cancel_outlined,
                    color: SwayaLight.error, size: 20),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text('Cancel Order',
                      style: TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontSize: 18,
                          fontWeight: FontWeight.w700)),
                ),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close, size: 20),
                ),
              ],
            ),
            const Text('Please provide a reason for cancellation.',
                style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
            const SizedBox(height: 12),
            for (final r in kCancelReasons)
              RadioListTile<String>(
                value: r,
                groupValue: _reason,
                onChanged: (v) => setState(() => _reason = v),
                title: Text(r,
                    style: const TextStyle(
                        color: SwayaLight.inkPrimary, fontSize: 14)),
                activeColor: SwayaLight.accent,
                contentPadding: EdgeInsets.zero,
                dense: true,
                visualDensity: VisualDensity.compact,
              ),
            if (_reason == 'Others') ...[
              const SizedBox(height: 4),
              TextField(
                controller: _other,
                minLines: 2,
                maxLines: 3,
                onChanged: (_) => setState(() {}),
                decoration:
                    const InputDecoration(hintText: 'Enter your reason'),
              ),
            ],
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Keep Order'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _resolved == null
                        ? null
                        : () => Navigator.pop(context, _resolved),
                    style: ElevatedButton.styleFrom(
                        backgroundColor: SwayaLight.error),
                    child: const Text('Confirm Cancellation'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Request Alteration sheet (frame 27)
// ─────────────────────────────────────────────────────────────────────────────

Future<String?> _showAlterationSheet(BuildContext context) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: SwayaLight.canvas,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (ctx) => Theme(
      data: buildSwayaLightTheme(),
      child: Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
        child: const _AlterationSheetBody(),
      ),
    ),
  );
}

class _AlterationSheetBody extends StatefulWidget {
  const _AlterationSheetBody();
  @override
  State<_AlterationSheetBody> createState() => _AlterationSheetBodyState();
}

class _AlterationSheetBodyState extends State<_AlterationSheetBody> {
  final _desc = TextEditingController();
  final _picker = ImagePicker();
  bool _front = false;
  bool _back = false;

  @override
  void dispose() {
    _desc.dispose();
    super.dispose();
  }

  Future<void> _pick(bool front) async {
    final f =
        await _picker.pickImage(source: ImageSource.gallery, imageQuality: 90);
    if (f == null) return;
    setState(() => front ? _front = true : _back = true);
  }

  @override
  Widget build(BuildContext context) {
    final canSubmit = _desc.text.trim().isNotEmpty && _front;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.content_cut,
                    color: SwayaLight.accent, size: 20),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text('Request Alteration',
                      style: TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontSize: 18,
                          fontWeight: FontWeight.w700)),
                ),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close, size: 20),
                ),
              ],
            ),
            const Text('Get your delivered order altered.',
                style: TextStyle(color: SwayaLight.inkSecondary, fontSize: 13)),
            const SizedBox(height: 14),
            TextField(
              controller: _desc,
              minLines: 3,
              maxLines: 5,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                  hintText: 'Describe the alteration needed'),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFFBF4E6),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFEAD9B0)),
              ),
              child: const Text(
                  'Support team: before alteration begins, our team will confirm details with you.',
                  style: TextStyle(color: Color(0xFF7A6526), fontSize: 12)),
            ),
            const SizedBox(height: 16),
            const Text('Upload blouse images',
                style: TextStyle(
                    color: SwayaLight.inkPrimary,
                    fontSize: 13,
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            _UploadTile(
                label: 'Front image', done: _front, onTap: () => _pick(true)),
            const SizedBox(height: 10),
            _UploadTile(
                label: 'Back image', done: _back, onTap: () => _pick(false)),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: canSubmit
                        ? () => Navigator.pop(context, _desc.text.trim())
                        : null,
                    child: const Text('Request Alteration'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _UploadTile extends StatelessWidget {
  const _UploadTile(
      {required this.label, required this.done, required this.onTap});
  final String label;
  final bool done;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: done
              ? SwayaLight.success.withValues(alpha: 0.08)
              : SwayaLight.surface,
          borderRadius: BorderRadius.circular(12),
          border:
              Border.all(color: done ? SwayaLight.success : SwayaLight.border),
        ),
        child: Row(
          children: [
            Icon(done ? Icons.check_circle : Icons.upload_outlined,
                size: 20,
                color: done ? SwayaLight.success : SwayaLight.inkSecondary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label,
                      style: const TextStyle(
                          color: SwayaLight.inkPrimary,
                          fontWeight: FontWeight.w600,
                          fontSize: 14)),
                  Text(done ? 'Uploaded' : 'Tap to choose an image',
                      style: TextStyle(
                          color: done
                              ? SwayaLight.success
                              : SwayaLight.inkTertiary,
                          fontSize: 12)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
