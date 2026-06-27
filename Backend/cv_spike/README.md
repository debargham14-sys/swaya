# Swaya Body Measurement API

Markerless body girth estimation from **front**, **back**, and **side** profile photos.

## Setup

```bash
cd Backend/cv_spike
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r notebooks/requirements.txt   # optional: Jupyter probe
bash scripts/setup_4dhumans.sh   # optional, for height / 4D-Humans flow
```

### DSV line-probe notebook (OpenCV)

Interactive **front / back / side** viewer: draws neck, shoulder, bust, underbust,
waist, hip, and hem lines; detects magenta DSV bands + ArUco scale; exports JSON.

```bash
cd Backend/cv_spike
source .venv/bin/activate
jupyter notebook notebooks/dsv_measurement_probe.ipynb
```

Open the notebook and **run Cell 1 (Install)** first — it installs
`notebooks/requirements-probe.txt` (opencv, mediapipe, widgets) into the active
kernel, then downloads `models/pose_landmarker.task` if missing.

Default images: `spike_data/user_capture/{front,back,side}.jpg` — edit paths in the
notebook config cell. With a **printed DSV**, align sliders to magenta bands and
compare girths to side-panel OCR readouts.

Place the SMPL neutral model for 4D-Humans: see `models/smpl/README.md`.

## Run the API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open docs at http://localhost:8000/docs

---

## Flow A — Height + weight (recommended when height is known)

**Inputs:** front, back, side photos + **height (cm)** + optional weight (kg)  
**Default backend:** photo silhouettes (best with loose clothing like robes)  
**No ArUco marker required**

Use `prefer=four_d_humans` only in **fitted clothing**; loose layers break SMPL fitting.

### Capture

- Full body visible in all three views (front, back, side)
- Fitted clothing, arms relaxed at sides
- Plain background helps

### API

```bash
curl -X POST http://localhost:8000/v1/measure \
  -F "mode=height" \
  -F "front=@front.jpg" \
  -F "back=@back.jpg" \
  -F "side=@side.jpg" \
  -F "height_cm=170" \
  -F "weight_kg=70"
```

Or the dedicated shortcut endpoint:

```bash
curl -X POST http://localhost:8000/v1/measure/height \
  -F "front=@front.jpg" \
  -F "back=@back.jpg" \
  -F "side=@side.jpg" \
  -F "height_cm=170" \
  -F "weight_kg=70"
```

Photo fallback (silhouettes only):

```bash
curl -X POST http://localhost:8000/v1/measure \
  -F "mode=height" \
  -F "front=@front.jpg" -F "back=@back.jpg" -F "side=@side.jpg" \
  -F "height_cm=170" -F "prefer=photo"
```

### CLI

```bash
python scripts/measure_with_height.py \
  --front front.jpg --back back.jpg --side side.jpg \
  --height 170 --weight 70
```

### Example response

```json
{
  "mode": "height",
  "backend": "photo:silhouette+pose",
  "height_cm": 170,
  "weight_kg": 70,
  "bmi": 24.2,
  "confidence": 0.85,
  "girths_cm": {"bust": 92.1, "underbust": 78.4, "waist": 74.2, "hip": 98.5},
  "girths_in": {"bust": 36.3, "underbust": 30.9, "waist": 29.2, "hip": 38.8},
  "warnings": []
}
```

---

## Flow B — ArUco at chest (no height required)

**Inputs:** front, back, side photos + **50 mm ArUco marker at chest level**  
**Default backend:** photo silhouettes + MediaPipe pose

### Setup marker

```bash
python -m pipeline.measure.scale_reference --generate assets/aruco_50mm.png
```

Print at exactly **50 mm × 50 mm**.

### API

```bash
curl -X POST http://localhost:8000/v1/measure \
  -F "mode=aruco" \
  -F "front=@front.jpg" \
  -F "back=@back.jpg" \
  -F "side=@side.jpg" \
  -F "ref=aruco" \
  -F "ref_mm=50"
```

4D-Humans with inferred height from marker:

```bash
curl -X POST http://localhost:8000/v1/measure \
  -F "mode=aruco" \
  -F "front=@front.jpg" -F "back=@back.jpg" -F "side=@side.jpg" \
  -F "ref=aruco" -F "prefer=four_d_humans"
```

---

## API reference

| Field | Flow A (height) | Flow B (aruco) |
|-------|-----------------|----------------|
| `mode` | `height` | `aruco` |
| `height_cm` | **required** | optional |
| `weight_kg` | optional (BMI) | optional |
| `ref` | omit | `aruco` (default when mode=aruco) |
| `prefer` | `four_d_humans` (default) | `photo` (default) |
| `tape_in` / `tape_cm` | optional correction | optional correction |

`GET /health` — reports `backends.four_d_humans`, `backends.smpl_cached`, etc.

---

## QC engine — finished-blouse quality check

A separate, staged CV pipeline (`pipeline/qc/`) that inspects a finished blouse
photographed flat inside the **standardized QC framework** (the perimeter strip
torn from the A1 stencil) and compares it against the order's spec sheet.

The framework is the same for every order: four corner ArUco fiducials
(`DICT_4X4_50`, ids 0=TL, 1=TR, 2=BR, 3=BL) plus cm scales and magenta hem /
symmetry lines. The fiducials give a px ↔ mm homography used as ground truth.

### Pipeline stages

1. ChArUco/ArUco detection + px↔mm calibration (`charuco.py`)
2. Framework inner boundary → measurement zone (`framework.py`)
3. Blouse silhouette extraction (`silhouette.py`)
4. Direct dimensional measurement (`landmarks.py` + `dimensions.py`)
5. Comparison vs spec with tolerance tiers (`compare.py`, `spec.py`)
6. Symmetry analysis (`symmetry.py`)
7. 47-check checklist; feature/seam/surface/drape checks scaffolded (`checklist.py`)
8. QC report + annotated photo (`report.py`)

### Tolerance tiers (mm)

Per-dimension tolerances from the QC checklist, e.g. bust `(couture 3, bespoke 5,
express 8)`, shoulder width `3` all tiers; otherwise a per-tier default
`(couture 2, bespoke 3, express 5)`. Symmetry tolerance is `2 mm`.

### Order spec sheet

The spec carries target dimensions (mm), tier, variant, and expected features.
In production it is loaded by `order_id` (from the cutting-region QR code); here
it can be inline JSON or `pipeline/qc/specs/<order_id>.json`. See
[pipeline/qc/specs/sample_order.json](pipeline/qc/specs/sample_order.json).

### API

```bash
# inline spec
curl -X POST http://localhost:8000/v1/qc \
  -F "front=@qc_photo.jpg" \
  -F 'spec={"order_id":"SW-2026-04827","tier":"bespoke","variant":"sleeveless","target_dims_mm":{"bust":860,"shoulder_width":380,"total_length":600}}'

# or by order id (resolved via OrderRepository / specs folder)
curl -X POST http://localhost:8000/v1/qc \
  -F "front=@qc_photo.jpg" -F "order_id=sample_order"
```

Response: `overall_status` (pass/fail/needs_review), `score`, `calibration`,
`dimensions`, `comparisons`, `symmetry`, `category_summary`, and the full
47-item `checks` list.

### CLI

```bash
python -m pipeline.qc.qc_engine --photo qc_photo.jpg --order-id sample_order --debug-dir out/
python -m pipeline.qc.qc_engine --photo qc_photo.jpg --spec order.json --debug-dir out/
```

`--debug-dir` writes `qc_annotated.jpg`, `qc_silhouette.png`, and `qc_result.json`.

---

## Tests

```bash
pytest tests/ -v
```

## Layout

- `api/` — FastAPI service
- `pipeline/measure/` — body-measurement engine (photo silhouettes + SMPL mesh)
- `pipeline/qc/` — quality-check engine (framework calibration + spec comparison)
- `pipeline/common/` — shared CV helpers used by both engines
- `scripts/measure_with_height.py` — height flow CLI
- `scripts/try_4dhumans.py` — 4D-Humans smoke test
- `models/smpl/` — SMPL model for 4D-Humans
- `assets/aruco_50mm.png` — printable marker
