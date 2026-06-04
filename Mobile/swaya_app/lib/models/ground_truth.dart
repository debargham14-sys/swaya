class GroundTruthComparison {
  GroundTruthComparison({
    required this.predictedCm,
    required this.tapeCm,
    required this.errorCm,
  });

  factory GroundTruthComparison.fromJson(Map<String, dynamic> json) {
    return GroundTruthComparison(
      predictedCm: (json['predicted_cm'] as num?)?.toDouble() ?? 0,
      tapeCm: (json['tape_cm'] as num?)?.toDouble() ?? 0,
      errorCm: (json['error_cm'] as num?)?.toDouble() ?? 0,
    );
  }

  final double predictedCm;
  final double tapeCm;
  final double errorCm;
}
