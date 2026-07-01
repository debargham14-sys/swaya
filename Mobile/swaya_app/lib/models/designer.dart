/// A designer/tailor profile from `/v1/designers`. Browseable in the directory;
/// the user picks one to start a collaboration.
class Designer {
  Designer({
    required this.id,
    required this.name,
    this.bio,
    this.specialties = const [],
    this.location,
    this.yearsExperience,
    this.priceRange,
    this.photoUrl,
    this.available = true,
    this.ratingAvg = 0,
    this.ratingCount = 0,
  });

  final String id;
  final String name;
  final String? bio;
  final List<String> specialties;
  final String? location;
  final int? yearsExperience;
  final String? priceRange;
  final String? photoUrl;
  final bool available;
  final double ratingAvg;
  final int ratingCount;

  Map<String, dynamic> toJson() => {
        'name': name,
        'bio': bio,
        'specialties': specialties,
        'location': location,
        'years_experience': yearsExperience,
        'price_range': priceRange,
        'photo_url': photoUrl,
        'available': available,
      };

  factory Designer.fromJson(Map<String, dynamic> json) => Designer(
        id: json['id'] as String,
        name: json['name'] as String? ?? 'Designer',
        bio: json['bio'] as String?,
        specialties: ((json['specialties'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        location: json['location'] as String?,
        yearsExperience: (json['years_experience'] as num?)?.toInt(),
        priceRange: json['price_range'] as String?,
        photoUrl: json['photo_url'] as String?,
        available: json['available'] as bool? ?? true,
        ratingAvg: (json['rating_avg'] as num?)?.toDouble() ?? 0,
        ratingCount: (json['rating_count'] as num?)?.toInt() ?? 0,
      );
}
