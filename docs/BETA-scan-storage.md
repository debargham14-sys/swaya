# DSV beta — MongoDB scans & downloadable bundles

## Overview

`POST /v1/scans` runs measurement, stores metadata in **MongoDB**, writes a **ZIP bundle** to disk, and returns `scan_id` + `download_url`.

### Bundle contents (`dsv-scan-{id}.zip`)

| File | Description |
|------|-------------|
| `manifest.json` | Scan id, version, mesh included flag |
| `measurements.json` | Girths, BMI, backend, warnings |
| `photos/front|back|side.*` | Uploaded captures |
| `body.obj` | SMPL mesh (only if 4D-Humans / mesh backend succeeds) |
| `README.txt` | Short beta notes |

## Quick start

```bash
# 1. MongoDB
cd Backend/cv_spike
docker compose up -d

# 2. API deps
source .venv/bin/activate
pip install -r requirements.txt

# 3. API
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 4. Flutter (Chrome)
cd ../../Mobile/swaya_app
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Check health: `curl http://127.0.0.1:8000/health` → `"mongodb": true`

## API

```bash
# Create scan (multipart, same fields as /v1/measure/height)
curl -X POST http://127.0.0.1:8000/v1/scans \
  -F "mode=height" -F "height_cm=170" -F "weight_kg=70" -F "prefer=photo" \
  -F "front=@front.jpg" -F "back=@back.jpg" -F "side=@side.jpg"

# Download bundle
curl -O -J http://127.0.0.1:8000/v1/scans/{scan_id}/bundle

# List scans
curl http://127.0.0.1:8000/v1/scans
```

## Env

Copy `Backend/cv_spike/.env.example`:

- `MONGODB_URI` — default `mongodb://localhost:27017`
- `MONGODB_DB` — default `dsv`
- `SCAN_STORAGE_DIR` — bundle files (default `./data/scans`)
- `BUNDLE_TRY_MESH=1` — attempt `body.obj` export via 4D-Humans

## Flutter v2 flow

1. **Home** → New body scan  
2. **Scan stack** → uploads via `POST /v1/scans`  
3. **Results** → **Download beta bundle (ZIP)**  
4. **Scans tab** → history from MongoDB  

## Tests

```bash
cd Backend/cv_spike
pytest tests/test_bundle_export.py -v
pytest tests/test_scans_api.py -v   # needs MongoDB running
```
