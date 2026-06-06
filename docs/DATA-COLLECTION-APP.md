# Swaya data collection app — cloud setup

Hand the **Swaya** Flutter app to testers on **iPhone (TestFlight)** and **Android (APK)**. Each scan captures **front, back, and side** photos plus height/weight, runs the measurement pipeline, and stores **photos in AWS S3** with **metadata + ZIP bundles in MongoDB Atlas**.

---

## Architecture

```
iPhone / Android (Flutter swaya_app)
        │  HTTPS multipart POST /v1/scans
        ▼
Render / Railway (FastAPI + MediaPipe)
        ├── raw JPGs  → AWS S3  (dsv/scans/{scan_id}/photos/…)
        └── ZIP bundle → MongoDB GridFS
        ▼
MongoDB Atlas
  ├── collection: scans     (metadata, girths, S3 links per photo)
  └── bucket: scan_files    (ZIP bundle per scan)
```

---

## Step 1 — MongoDB Atlas (cloud database)

1. Create a free cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas).
2. **Database Access** → add a user with read/write on database `dsv`.
3. **Network Access** → **Allow access from anywhere** (`0.0.0.0/0`) so Render can connect. (Tighten later with VPC/peering if needed.)
4. **Connect** → Drivers → copy the connection string:
   ```
   mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

### What gets stored per scan

| Location | Content |
|----------|---------|
| `scans` collection | `scan_id`, `height_cm`, `weight_kg`, `measurements`, `photos` (S3 `s3_key` + `s3_url` per view), labels, timestamps |
| AWS S3 | Raw `front` / `back` / `side` JPEGs under `dsv/scans/{scan_id}/photos/` |
| GridFS `scan_files` | ZIP bundle (`manifest.json`, `measurements.json`, photos copy) |

Download later:

- Bundle: `GET /v1/scans/{scan_id}/bundle`
- Single photo: `GET /v1/scans/{scan_id}/photos/{front|back|side}` (proxied from S3), or use `photo_urls` from the scan JSON (direct S3 URL)
- List: `GET /v1/scans`

---

## Step 2 — Deploy API to Render

1. Push this repo to GitHub.
2. [render.com](https://render.com) → **New** → **Blueprint** → connect repo → path `Backend/cv_spike/render.yaml`.
3. Create an **S3 bucket** (e.g. `swaya-dsv-photos`) and an IAM user with `s3:PutObject` + `s3:GetObject` on that bucket.
4. In the service **Environment**, set (others are in `render.yaml`):
   - `MONGODB_URI` = your Atlas `mongodb+srv://...` string
   - `S3_BUCKET` = your bucket name
   - `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` = IAM credentials
   - Optionally `AWS_REGION` (default `us-east-1`) and `S3_PHOTO_PREFIX` (default `dsv/scans`)
5. Deploy. Note the public URL, e.g. `https://swaya-dsv-api.onrender.com`.
6. Verify: `curl https://YOUR-URL/health` → `"mongodb": true`, `"photo_storage": {"backend": "s3", "ready": true, ...}`.

**Local dev** (GridFS photos, no AWS):

```bash
cd Backend/cv_spike
docker compose up -d
cp .env.example .env
# In .env set PHOTO_STORAGE=gridfs for local dev without S3
source .venv/bin/activate && pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Step 3 — Build the mobile app

Install Flutter 3.22+, then:

```bash
cd Mobile/swaya_app
flutter pub get
```

Replace `YOUR_API_URL` with the Render HTTPS URL (no trailing slash).

### Android APK (share link)

```bash
flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR_API_URL
```

APK path: `build/app/outputs/flutter-apk/app-release.apk`  
Upload to Google Drive / Dropbox and share the link with testers.

### iOS TestFlight

1. Apple Developer account + App Store Connect app record.
2. Open `ios/` in Xcode, set signing team and bundle id.
3. Archive → Distribute → App Store Connect → TestFlight.
4. Or CI build with the same dart-define:

```bash
flutter build ipa --release \
  --dart-define=API_BASE_URL=https://YOUR_API_URL
```

Add internal/external testers in App Store Connect → TestFlight.

### Run on a device during development

```bash
# Use your machine's LAN IP if testing against local API
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

Physical phones cannot use `127.0.0.1` — they need LAN IP or the public Render URL.

---

## Step 4 — Tester workflow

1. Install app (TestFlight or APK).
2. **New scan** → enter participant ID, collector name, height, check **consent**.
3. Capture **front → back → side** (full body, arms slightly out, plain background).
4. Review → submit → wait for cloud processing (~30–90 s).
5. Results show girths; data is already in Atlas.

---

## Step 5 — Export data for ML / analysis

### MongoDB Compass or `mongosh`

Connect with the same Atlas URI → database `dsv` → collection `scans`.

### Python export script (example)

```python
from pymongo import MongoClient
from gridfs import GridFS

uri = "mongodb+srv://..."
db = MongoClient(uri)["dsv"]
fs = GridFS(db, collection="scan_files")

for doc in db.scans.find().sort("created_at", -1):
    sid = doc["scan_id"]
    for view in ("front", "back", "side"):
        meta = (doc.get("photos") or {}).get(view)
        if meta:
            out = f"export/{sid}_{view}.jpg"
            with open(out, "wb") as f:
                f.write(fs.get(meta["file_id"]).read())
    print(sid, doc.get("subject_label"), doc.get("measurements", {}).get("girths_cm"))
```

### API bulk download

```bash
curl https://YOUR_API_URL/v1/scans?limit=100
curl -O -J https://YOUR_API_URL/v1/scans/SCAN_ID/bundle
curl -o front.jpg https://YOUR_API_URL/v1/scans/SCAN_ID/photos/front
```

---

## Env reference

| Variable | Cloud (Render) | Local dev |
|----------|----------------|-----------|
| `MONGODB_URI` | `mongodb+srv://...` | `mongodb://localhost:27017` |
| `MONGODB_DB` | `dsv` | `dsv` |
| `SCAN_STORAGE_BACKEND` | `gridfs` | `gridfs` or `disk` |
| `BUNDLE_TRY_MESH` | `0` | `1` if 4D-Humans installed |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| App cannot connect | Use HTTPS Render URL, not localhost, on real devices |
| `mongodb: false` in `/health` | Check Atlas URI, user password URL-encoding, IP allowlist |
| Scan 503 MongoDB unavailable | Atlas cluster paused (free tier) or wrong URI |
| Slow first request on Render | Free tier cold start; retry after ~30 s |
| Large Atlas storage | GridFS stores 3 photos + ZIP per subject; monitor Atlas storage metrics |

---

## Related docs

- `docs/BETA-scan-storage.md` — local beta scan API
- `Mobile/swaya_app/README.md` — Flutter dev notes
- `Backend/cv_spike/README.md` — measurement API reference
