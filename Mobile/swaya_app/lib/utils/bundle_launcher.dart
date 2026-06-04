import 'package:url_launcher/url_launcher.dart';

import '../config/app_config.dart';
import '../models/scan_record.dart';

Future<bool> openBetaBundleDownload(ScanRecord scan) async {
  final url = Uri.parse(scan.bundleAbsoluteUrl(AppConfig.apiBaseUrl));
  if (await canLaunchUrl(url)) {
    return launchUrl(url, mode: LaunchMode.externalApplication);
  }
  return false;
}
