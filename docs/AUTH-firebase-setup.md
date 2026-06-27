# Authentication — Firebase setup

DSV uses **Firebase Authentication** for sign-in (phone OTP, email/password,
Google, Apple). The Flutter app authenticates and sends the Firebase **ID token**
to the API as `Authorization: Bearer <token>`; the FastAPI backend verifies it
with the Firebase Admin SDK and scopes each user's scans to their `uid`.

Until a Firebase project is configured the app boots in **auth-unconfigured**
mode (sign-in is skipped) and the backend leaves routes open, so development
isn't blocked. The steps below make auth real.

---

## 1. Create the Firebase project (one-time, console)

1. <https://console.firebase.google.com> → **Add project** (e.g. `dsv-app`).
2. **Build → Authentication → Get started**, then enable providers under
   **Sign-in method**:
   - **Phone** — add test numbers under *Phone numbers for testing* for dev.
   - **Email/Password**.
   - **Google**.
   - **Apple** — needs an Apple Developer account + a Services ID (see step 4).

## 2. Wire up the Flutter app

Install the CLIs (one-time on this machine):

```bash
npm install -g firebase-tools
firebase login
dart pub global activate flutterfire_cli   # provides `flutterfire`
```

From the app dir, generate per-platform credentials. This **overwrites the
placeholder** `lib/firebase_options.dart` and drops the native config files:

```bash
cd Mobile/swaya_app
flutterfire configure --project=<your-firebase-project-id>
# select iOS + Android (+ macOS/web if you run those targets)
flutter pub get
```

It registers these app IDs (already set in the project):
- Android `applicationId`: `com.swaya.swaya_app`
- iOS bundle id: `com.swaya.swayaApp`

### Android — Google sign-in
Add your debug + release **SHA-1 / SHA-256** to the Firebase Android app
(Project settings → Your apps), then re-download `google-services.json`:

```bash
cd Mobile/swaya_app/android
./gradlew signingReport     # copy the SHA1/SHA256 under "Variant: debug"
```

### iOS — URL scheme & Apple
- `flutterfire configure` adds `GoogleService-Info.plist`. For Google sign-in,
  add the **reversed client ID** (from that plist) as a URL scheme in Xcode
  (Runner → Info → URL Types), or in `ios/Runner/Info.plist`.
- For **Apple sign-in**: in Xcode enable the *Sign in with Apple* capability on
  the Runner target, and configure the Apple provider (Services ID + key) in the
  Firebase console.

## 3. Configure the backend (token verification)

Generate a service account: Firebase console → **Project settings → Service
accounts → Generate new private key** (downloads a JSON file).

Set **one** of these (see `Backend/cv_spike/.env.example`):

```bash
# Option A — inline JSON (best for Render/Railway secret env vars)
FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account","project_id":"...",...}'

# Option B — file path + project id
GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json
FIREBASE_PROJECT_ID=<your-firebase-project-id>
```

Install deps and run:

```bash
cd Backend/cv_spike
pip install -r requirements.txt      # now includes firebase-admin
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

`GET /health` reports `"auth": {"firebase": true, "required": false}` when
verification is active.

- **Local dev without Firebase:** leave the vars unset. Auth is disabled; scans
  are attributed to a synthetic `dev-anonymous` user.
- **Shared/staging:** set `AUTH_REQUIRED=1` so missing/invalid tokens get 401s
  even before credentials are wired.

> Add the same `FIREBASE_*` vars to `render.yaml` / your host's dashboard for
> production. Never commit the service-account JSON.

## 4. How it fits together (code map)

**Mobile**
- `lib/services/auth_service.dart` — all four sign-in methods + ID token.
- `lib/providers/auth_controller.dart` — auth state; drives the router.
- `lib/screens/auth/` — landing (method picker), phone/OTP, email.
- `lib/router/app_router.dart` — `redirect` guard sends signed-out users to `/auth`.
- `lib/services/auth_token.dart` — `authHeaders()`; every API client attaches the token.

**Backend**
- `api/auth.py` — `require_user` / `current_uid` dependencies verify the token.
- `api/routes/scans.py` — protected; stamps `user_id` and scopes reads to the owner.
- `api/settings.py` — `FIREBASE_*`, `AUTH_REQUIRED`.

## Open follow-up
Onboarding (profile/height) currently isn't gated into the post-sign-in flow —
signed-in users land on `/home`. Wire onboarding into the redirect once the auth
mockups define the first-run sequence.
