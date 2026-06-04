import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../models/scan_record.dart';
import '../services/scan_api.dart';
import '../theme/swaya_theme.dart';
import '../utils/scan_display.dart';
import '../widgets/swaya_scaffold.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<ScanRecord>? _scans;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final scans = await ScanApi().listScans();
      if (mounted) {
        setState(() {
          _scans = scans;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return SwayaScaffold(
      title: 'Scans',
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        _error!,
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: SwayaColors.inkSecondary,
                            ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Start MongoDB: docker compose up -d in Backend/cv_spike',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: SwayaColors.inkTertiary,
                            ),
                      ),
                      const SizedBox(height: 16),
                      OutlinedButton(onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                )
              : _scans == null || _scans!.isEmpty
                  ? Center(
                      child: Text(
                        'No scans yet. Start one from Home.',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: SwayaColors.inkSecondary,
                            ),
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.separated(
                        itemCount: _scans!.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, i) {
                          final scan = _scans![i];
                          final date = formatScanDate(scan.createdAt);
                          final hasTape = scan.groundTruthCm.isNotEmpty;
                          return Material(
                            color: SwayaColors.elevated,
                            borderRadius: BorderRadius.circular(10),
                            child: ListTile(
                              title: Text(
                                scan.displayName,
                                style: const TextStyle(fontWeight: FontWeight.w600),
                              ),
                              subtitle: Text(
                                [
                                  if (date.isNotEmpty) date,
                                  if (hasTape) 'Tape saved',
                                ].join(' · '),
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: SwayaColors.inkTertiary,
                                ),
                              ),
                              trailing: const Icon(
                                Icons.chevron_right,
                                color: SwayaColors.inkTertiary,
                              ),
                              onTap: () => context.push(
                                '/history/scan/${scan.scanId}',
                                extra: scan,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
