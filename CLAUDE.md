# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Swaya is a markerless **body-measurement** system. Two deployable pieces plus research notebooks:

- `Backend/cv_spike/` — Python/FastAPI CV service (the real backend; the `cv_spike` name is historical). All backend commands run from this directory.
- `Mobile/swaya_app/` — Flutter client (`DSV_APP` in Figma) that captures front/back/side photos and talks to the API.
- `docs/` — flow specs and data-collection notes (`DATA-COLLECTION-APP.md`, `BETA-scan-storage.md`, `DSV_APP-flow-implementation.md`).

The product estimates body girths (bust, underbust, waist, hip) from three photos. There is a *second, separate* CV pipeline (`pipeline/qc/`) that inspects a finished blouse against an order spec sheet — it shares CV helpers but is otherwise independent and gated off by default (`ENABLE_QC=0`).

## Backend commands (run from `Backend/cv_spike/`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # full local dev (includes optional mesh extras)
# requirements-deploy.txt is the slim cloud set: photo-only, NO torch/SMPL/4D-Humans

uvicorn api.main:app --host 0.0.0.0 --port 8000   # docs at /docs, health at /health

pytest tests/ -v                       # all tests
pytest tests/ -v -m "not slow"         # skip full-pipeline integration tests (slow marker)
pytest tests/test_charuco.py -v        # single file
pytest tests/test_api.py::test_name -v # single test
```

Docker mirrors the cloud deploy (Render blueprint in `render.yaml`): Python 3.11 slim, installs `requirements-deploy.txt`, downloads `pose_landmarker.task` at build time, runs the same uvicorn command.

## Mobile commands (run from `Mobile/swaya_app/`)

```bash
flutter pub get
flutter run -d macos  --dart-define=API_BASE_URL=http://127.0.0.1:8000   # desktop, no Xcode
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000   # quick UI check
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000          # device, use LAN IP
flutter test
```

`API_BASE_URL` is a compile-time `--dart-define` (read in `lib/config/app_config.dart`), not a runtime setting. Platform folders are committed; only re-run `flutter create` if you delete `ios/`/`android/` (then re-add camera permissions per `Mobile/swaya_app/README.md`).

## Backend architecture

### Measurement engine — the core path

`pipeline/measure/measure_engine.py::measure()` is the single entry point. It selects a backend by priority and returns one normalized `EngineResult` (`.to_dict()` is the API response shape):

1. **mesh** — 3D SMPL/SMPL-X body via 4D-Humans (`smpl_backend.py`, `mesh_measure.py`), sliced into cross-section girths. Most accurate, ties to the try-on avatar. Requires torch + models — **not present in the cloud image**.
2. **photo** — silhouette + MediaPipe pose ellipse estimator (`markerless.py`). The default cloud path. Works markerless or with a 50 mm ArUco scale reference (`scale_reference.py`).

`prefer` controls this: `photo` forces silhouettes; `four_d_humans`/`smplx`/`obj` force mesh; `auto` tries mesh then falls back. Mesh results with implausibly small bust girth are rejected (loose clothing breaks HMR2 fitting) — see `_mesh_girths_plausible`. **Use mesh only with fitted clothing; loose layers (robes) need the photo backend.**

Two API flows wrap the same engine (`api/forms.py::resolve_measure_request`): **height mode** (`height_cm` required, no marker) and **aruco mode** (50 mm marker at chest, height inferred).

**Calibration** (`calibration/`, `pipeline/measure/calibration.py`) maps raw girths to true measurements via per-garment affine profiles (`calibration/profiles/*.json`: `scale`/`offset_cm` + anchors). This corrects for clothing bulk. `body_profile.py`/`body_shape.py` carry shape priors.

### API layer (`api/`)

`api/main.py` builds the FastAPI app and mounts routers from `api/routes/` (`scans`, `calibration`, `assistant`, and `qc` only when `ENABLE_QC=1`). Pattern: **routes → services → db/storage**.

- `api/services/` — business logic (`scan_service`, `calibration_service`, `assistant_service`).
- `api/db/` — MongoDB access (`mongo.py` connection, `scans.py`, `calibration.py`). The service degrades gracefully when Mongo is unreachable (`mongo_available()`).
- `api/storage/photo_store.py` — raw JPGs to **S3** in prod (Mongo stores the `s3_key`/`s3_url`); GridFS for local dev without AWS.
- Stateless `POST /v1/measure` does the math only. `POST /v1/scans` (Beta) persists photos + measurements and returns a downloadable ZIP bundle (`pipeline/measure/bundle_export.py`: `manifest.json`, `measurements.json`, photos, optional `body.obj`).
- The fit **assistant** (`/v1/assistant`) uses Anthropic if `ANTHROPIC_API_KEY` is set, else rule-based fallback.

MediaPipe is warmed up in a background thread on startup so the first scan isn't a cold-start failure.

### QC engine (`pipeline/qc/`) — separate pipeline

Finished-blouse quality check, staged: ChArUco calibration (`charuco.py`) → framework boundary (`framework.py`) → silhouette (`silhouette.py`) → dimensions (`landmarks.py`/`dimensions.py`) → spec comparison with tolerance tiers (`compare.py`/`spec.py`) → symmetry (`symmetry.py`) → 47-item checklist (`checklist.py`) → annotated report (`report.py`). Uses four corner ArUco fiducials (`DICT_4X4_50`, ids 0=TL,1=TR,2=BR,3=BL) for a px↔mm homography. Run via `/v1/qc` or `python -m pipeline.qc.qc_engine`.

### Shared / research

- `pipeline/common/mask_ops.py` — CV helpers shared by measure + QC.
- `notebooks/` — DSV ChArUco/probe research (`dsv_measurement_probe.ipynb`, `charuco_dsv_*`). Have their own `requirements-probe.txt`; install via Cell 1 of the notebook.
- `vendor/4D-Humans/` — vendored upstream; don't edit. `scripts/setup_4dhumans.sh` installs it.
- `models/` — `pose_landmarker.task` (MediaPipe), `smpl.zip`/`smplx.zip` (LFS).

## Mobile architecture (`lib/`)

`go_router` (`router/app_router.dart`) + a single `CaptureSession` `ChangeNotifierProvider` (`providers/`) holding the in-progress scan. Flow: welcome → onboarding → profile (participant id, collector, height required, weight/consent optional) → capture guide → camera (front→back→side) → review → `POST /v1/scans` → results; a **Scans** tab lists cloud history.

- `services/` — one client per API surface (`measure_api`, `scan_api`, `assistant_api`) + `onboarding_store` (shared_preferences). `chat_service.dart` is on-device; swap for an LLM provider when ready.
- `screens/` one per flow step, `widgets/` reusable UI, `models/` JSON DTOs mirroring API payloads, `theme/swaya_theme.dart` (dark mode only).

## Conventions & gotchas

- Backend imports are package-rooted (`from pipeline.measure import ...`); `pytest.ini` sets `pythonpath = .`, and `api/main.py` inserts the repo root on `sys.path`. Run backend things from `Backend/cv_spike/`.
- `pipeline/measure_engine.py` (top of `pipeline/`) is a deprecated shim — import from `pipeline.measure.measure_engine`.
- Behavior is heavily env-tuned (see `render.yaml`/`Dockerfile`/`.env.example`): `SCAN_MAX_IMAGE_EDGE`, `POSE_*`, `GRABCUT_*` trade accuracy vs latency; defaults are accuracy-first. `BUNDLE_TRY_MESH=1` only where torch is installed (never the cloud image).
- The `slow` pytest marker = full CV pipeline integration tests; gate them out for fast iteration.
