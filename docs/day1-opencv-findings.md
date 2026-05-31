# Day 1 — OpenCV Findings (DSV Spike)

## Summary

Day 1 implemented the **ChArUco / ArUco / magenta-band / OCR readout** pipeline on **synthetic worn-DSV images** with known ground truth, plus flat panel controls.

## Stack decisions

| Area | Decision |
|------|----------|
| Backend | **FastAPI (Python)** — wrap `pipeline.extract.extract_measurements` as HTTP in Week 1 |
| CV | **opencv-contrib-python** — ChArUco + ArUco |
| OCR (spike) | **Template digit matching** on readout ROIs (no Tesseract dep); swap to Tesseract/CNN if needed |
| Synthetic | **Tier A** — 2D homography warp of flat panels onto torso silhouette |
| 3D (note) | **License SMPL-X + Unity Obi** for Tier 1 try-on spike in Week 1–2; avoid building cloth solver in-house |
| LLM (note) | **Claude** for design assistant RAG; **CLIP** for inspiration tagging |

## Pipeline stages (go / no-go)

| Stage | Status | Notes |
|-------|--------|-------|
| ChArUco pose + scale | **Go** on flat panels; **partial** on worn synthetic when occluded |
| ArUco landmarks | **Go** when markers not occluded |
| Magenta bands | **Go** with HSV + morphology; fallback to fraction Y if peaks weak |
| OCR readouts | **Go** on flat side panel control; **partial** on worn JPEG (±1–2 cm) |
| Ellipse girth fallback | **Fallback only** — warn when OCR missing |

## Photo capture spec (app)

- **Photo 1:** Front — full vest, ChArUco MASTER visible, arms down.
- **Photo 2:** Back — ChArUco BACK visible.
- **Side readouts:** Numbers visible at side seam; if two-photo MVP only, add **guided side crop** from front (shoulder–hip strip) OR accept OCR on front/back with ellipse cross-check (lower confidence).

## Accuracy (Day 1 synthetic)

After `python run_day1.py`, inspect `Backend/cv_spike/spike_data/outputs/eval/eval_summary.json`.

**Validated on flat assets:**
- ChArUco + scale on flat front panel: **pass**
- Side readout OCR on flat side panel (86 / 74 / 68 cm): **pass** (shared `readout_render` templates)

**Worn synthetic (Tier A homography):**
- Front/back: scale + across-back landmarks; girth deferred to side readout per design
- Side: OCR succeeds on a subset; warped JPEG + overlap reduces readout SNR → many `partial` (no guessed values)
- Failure injection (`charuco_occlusion`, etc.) yields `partial`/`failed` as required

Targets for Week 1: raise side OCR success on worn synthetic (SMPL render or milder warp), then physical vest + 3 lightings.

## Open items → Week 1

- Caliper-verified print + 3 real lighting captures
- `pytest` in CI; synthetic suite expanded to 200 images
- FastAPI service + encrypted upload
- Disagreement policy: prefer OCR when confidence > 0.5, else warn

## Commands

```bash
cd Backend/cv_spike
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_day1.py
pytest tests/ -v
```
