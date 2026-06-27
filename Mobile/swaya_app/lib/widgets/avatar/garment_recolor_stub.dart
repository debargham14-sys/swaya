// Fallback backend (desktop / unsupported): recolour is a no-op so the app still
// compiles and the avatar simply renders with its baked colours.
class GarmentRecolor {
  void attach(Object? controller) {}
  void setMaterial(String name, int r, int g, int b, double a) {}
}
