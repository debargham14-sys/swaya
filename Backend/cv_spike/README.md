# Swaya Body Measurement API

Markerless body girth estimation from **front**, **back**, and **side** profile photos.

## Setup

```bash
cd Backend/cv_spike
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/setup_4dhumans.sh   # optional, for height / 4D-Humans flow
```

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
python -m pipeline.scale_reference --generate assets/aruco_50mm.png
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

## Tests

```bash
pytest tests/ -v
```

## Layout

- `api/` — FastAPI service
- `pipeline/` — measurement engine
- `scripts/measure_with_height.py` — height flow CLI
- `scripts/try_4dhumans.py` — 4D-Humans smoke test
- `models/smpl/` — SMPL model for 4D-Humans
- `assets/aruco_50mm.png` — printable marker
