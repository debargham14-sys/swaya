import 'package:flutter/material.dart';

import '../theme/swaya_light_theme.dart';

/// The four Orders tabs (Figma frames 22–31).
enum OrderTab { active, delivered, alterations, cancelled }

extension OrderTabX on OrderTab {
  IconData get icon => switch (this) {
        OrderTab.active => Icons.receipt_long_outlined,
        OrderTab.delivered => Icons.local_shipping_outlined,
        OrderTab.alterations => Icons.content_cut,
        OrderTab.cancelled => Icons.replay,
      };

  String get title => switch (this) {
        OrderTab.active => 'Active Orders',
        OrderTab.delivered => 'Delivered Orders',
        OrderTab.alterations => 'Alterations',
        OrderTab.cancelled => 'Cancelled Orders',
      };

  String get subtitle => switch (this) {
        OrderTab.active => 'Track active garment orders from design to delivery.',
        OrderTab.delivered => 'Completed garment orders appear here.',
        OrderTab.alterations =>
          'Track requested fit changes and completion status.',
        OrderTab.cancelled => 'Cancelled and refunded orders appear here.',
      };
}

enum OrderStatus { processing, shipped, delivered, cancelled }

extension OrderStatusX on OrderStatus {
  String get label => switch (this) {
        OrderStatus.processing => 'Processing',
        OrderStatus.shipped => 'Shipped',
        OrderStatus.delivered => 'Delivered',
        OrderStatus.cancelled => 'Cancelled',
      };

  Color get color => switch (this) {
        OrderStatus.processing => const Color(0xFFB7791F), // amber
        OrderStatus.shipped => SwayaLight.accent, // teal
        OrderStatus.delivered => SwayaLight.success, // green
        OrderStatus.cancelled => SwayaLight.error, // red
      };
}

OrderStatus orderStatusFromName(String? n) => OrderStatus.values
    .firstWhere((e) => e.name == n, orElse: () => OrderStatus.processing);

OrderTab orderTabFromName(String? n) => OrderTab.values
    .firstWhere((e) => e.name == n, orElse: () => OrderTab.active);

/// One node in the Ordered → Processing → Shipped → Delivered tracker.
class TrackingStep {
  const TrackingStep(this.label, {this.done = false});
  final String label;
  final bool done;

  Map<String, dynamic> toJson() => {'label': label, 'done': done};

  factory TrackingStep.fromJson(Map<String, dynamic> j) =>
      TrackingStep(j['label'] as String? ?? '', done: j['done'] as bool? ?? false);
}

class BlouseOrder {
  const BlouseOrder({
    required this.id,
    this.garment = 'Blouse',
    required this.tab,
    required this.placedOn,
    required this.status,
    required this.estimatedDate,
    required this.location,
    required this.subtotal,
    required this.shipping,
    required this.total,
    required this.tracking,
    this.deliveryPerson,
    this.deliveryPhone,
    this.noteTitle,
    this.noteBody,
  });

  final String id; // e.g. SW-2024-001
  final String garment; // garment-type label, e.g. Blouse / Sherwani
  final OrderTab tab; // which tab/category it shows under
  final String placedOn; // e.g. 1 Jun 2026
  final OrderStatus status;
  final String estimatedDate; // e.g. 15 Jun 2026
  final String location; // e.g. Bangalore, Karnataka, 560034
  final double subtotal;
  final double shipping;
  final double total;
  final List<TrackingStep> tracking;

  // Shipped orders carry a delivery contact.
  final String? deliveryPerson;
  final String? deliveryPhone;

  // Alteration / delivered / cancelled cards carry a highlighted note.
  final String? noteTitle; // e.g. Size Adjustment
  final String? noteBody; // e.g. Make it looser at the waist by 2 inches.

  BlouseOrder copyWith({
    String? garment,
    OrderTab? tab,
    OrderStatus? status,
    String? noteTitle,
    String? noteBody,
    List<TrackingStep>? tracking,
  }) {
    return BlouseOrder(
      id: id,
      garment: garment ?? this.garment,
      tab: tab ?? this.tab,
      placedOn: placedOn,
      status: status ?? this.status,
      estimatedDate: estimatedDate,
      location: location,
      subtotal: subtotal,
      shipping: shipping,
      total: total,
      tracking: tracking ?? this.tracking,
      deliveryPerson: deliveryPerson,
      deliveryPhone: deliveryPhone,
      noteTitle: noteTitle ?? this.noteTitle,
      noteBody: noteBody ?? this.noteBody,
    );
  }

  factory BlouseOrder.fromJson(Map<String, dynamic> j) => BlouseOrder(
        id: j['id'] as String? ?? '',
        garment: j['garment'] as String? ?? 'Blouse',
        tab: orderTabFromName(j['category'] as String?),
        status: orderStatusFromName(j['status'] as String?),
        placedOn: j['placed_on'] as String? ?? '',
        estimatedDate: j['estimated_date'] as String? ?? '',
        location: j['location'] as String? ?? '',
        subtotal: (j['subtotal'] as num?)?.toDouble() ?? 0,
        shipping: (j['shipping'] as num?)?.toDouble() ?? 0,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        tracking: ((j['tracking'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(TrackingStep.fromJson)
            .toList(),
        deliveryPerson: j['delivery_person'] as String?,
        deliveryPhone: j['delivery_phone'] as String?,
        noteTitle: j['note_title'] as String?,
        noteBody: j['note_body'] as String?,
      );
}

/// Reasons offered in the Cancel Order sheet (Figma frame 24).
const kCancelReasons = [
  'Found a better price elsewhere',
  'No longer need the product',
  'Ordered by mistake',
  'Delivery time is too long',
  'Others',
];
