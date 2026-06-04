class AppConfig {
  AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static const String measureHeightPath = '/v1/measure/height';
  static const String scansPath = '/v1/scans';
  static const String healthPath = '/health';
}
