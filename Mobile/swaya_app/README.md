# DSV Mobile App

Flutter client for the DSV body-measurement flow (Figma: `DSV_APP`). Uses the Swaya measurement API in `Backend/cv_spike`.: capture front / back / side photos, submit height, view girths, and chat with a fit assistant.

## Prerequisites

- Flutter 3.22+ (this machine: `brew install --cask flutter` → `/opt/homebrew/bin/flutter`)
- Running API: `cd Backend/cv_spike && uvicorn api.main:app --host 0.0.0.0 --port 8000`

## Setup

```bash
cd Mobile/swaya_app
flutter pub get
```

Platform folders are already generated. Re-run only if you deleted `ios/` or `android/`:

```bash
flutter create . --org com.swaya --project-name swaya_app
```

### Camera permissions (after `flutter create`)

**iOS** — add to `ios/Runner/Info.plist`:

```xml
<key>NSCameraUsageDescription</key>
<string>Swaya needs the camera for body profile photos.</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>Swaya needs photo access to pick profile images.</string>
```

**Android** — `android/app/src/main/AndroidManifest.xml` should include:

```xml
<uses-permission android:name="android.permission.CAMERA"/>
```

## Authentication (Firebase)

Sign-in (phone OTP, email/password, Google, Apple) uses Firebase. The app ships
with a **placeholder** `lib/firebase_options.dart`, so it runs without auth until
you configure a project:

```bash
flutterfire configure --project=<your-firebase-project-id>
flutter pub get
```

Full walkthrough (providers, SHA keys, Apple capability, backend token
verification): **`docs/AUTH-firebase-setup.md`**.

## Run

```bash
# macOS desktop (no Xcode required)
flutter run -d macos --dart-define=API_BASE_URL=http://127.0.0.1:8000

# Chrome (quick UI test; camera may be limited)
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000

# iOS Simulator (requires full Xcode from App Store)
flutter run -d ios --dart-define=API_BASE_URL=http://127.0.0.1:8000

# Physical device — use your machine's LAN IP
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

If `flutter` is not found in a **new** terminal, ensure Homebrew is on your PATH:

```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
```

## App flow

1. Welcome → How it works (skippable after first launch)
2. Participant ID, collector name, height (required), weight (optional), consent
3. Capture tips → Camera: front → back → side
4. Review → POST `/v1/scans` (photos + measurements saved to MongoDB)
5. Results → girths + download bundle; **Scans** tab lists cloud history

**Cloud data collection (TestFlight + APK):** see `docs/DATA-COLLECTION-APP.md`.

## Configuration

| Dart define | Default | Purpose |
|-------------|---------|---------|
| `API_BASE_URL` | `http://127.0.0.1:8000` | Measurement API base URL |

Chat uses an on-device assistant that reads your measurement JSON. Replace `lib/services/chat_service.dart` with your LLM provider when ready.
