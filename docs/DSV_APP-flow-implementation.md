# DSV_APP — UI flow v2 (mockups + Flutter)

| Artifact | Location |
|----------|----------|
| **Interactive mockups (v2)** | [dsv-app-ui-flow-v2.canvas.tsx](/Users/debargha/.cursor/projects/Users-debargha-Desktop-swaya/canvases/dsv-app-ui-flow-v2.canvas.tsx) |
| v1 mockups (superseded) | `canvases/swaya-flutter-app-design.canvas.tsx` |
| Original Figma export | [figma/DSV_APP-flow-overview.png](figma/DSV_APP-flow-overview.png) |
| Flutter app | `Mobile/swaya_app/` |

## v2 changes (vs v1)

| Before (v1) | After (v2) |
|-------------|------------|
| Linear: Welcome → … → Chat | **Tab shell** after onboarding |
| Brand “Swaya” | **DSV** |
| Single stack, no hub | **Home hub** starts scan |
| Chat only at end | **Assistant** tab + post-results CTA |
| 11 screens | **13 screens** (+ Home, Scans, Profile, flow map) |
| Routes `/capture/*` | Routes `/scan/*` |

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────┐
│   Entry     │     │         App shell (tabs)          │
│ Welcome     │────▶│ Home │ Scans │ Assistant │ Profile│
│ Onboarding  │     └───────────┬──────────────────────┘
└─────────────┘                 │ "New body scan"
                                ▼
                    ┌───────────────────────┐
                    │  Scan stack (fullscreen) │
                    │  height → guide → cam×3 │
                    │  → review → API → results│
                    └───────────┬─────────────┘
                                ▼
                         Assistant / Home
```

## MVP user journey

1. **Welcome** → first launch **Onboarding** → **Home**
2. **Home** → **New body scan**
3. **Height** → **Tips** → **Front / Back / Side** → **Review**
4. **Processing** → `POST /v1/measure/height`
5. **Results** → **Assistant** tab or **New scan**

## Decision gates

| Gate | Behavior |
|------|----------|
| Onboarding complete? | Skip to `/home` |
| Height valid? | Block on `/scan/height` |
| 3 photos? | Block on `/scan/review` |
| API success? | `/scan/results`; else snackbar + `/scan/review` |

## Routes

| Path | Screen |
|------|--------|
| `/` | Welcome |
| `/onboarding` | How it works |
| `/home` | Home (tab 0) |
| `/history` | Scans (tab 1, phase 2) |
| `/assistant` | Fit assistant (tab 2) |
| `/profile` | Profile (tab 3, phase 2) |
| `/scan/height` | Height & weight |
| `/scan/guide` | Capture tips |
| `/scan/capture/:view` | Camera |
| `/scan/review` | Review |
| `/scan/processing` | Processing |
| `/scan/results` | Measurements |

## Beta storage (implemented)

- `POST /v1/scans` → MongoDB + ZIP bundle (`manifest.json`, `measurements.json`, photos, optional `body.obj`)
- Flutter **Scans** tab lists history; **Results** has **Download beta bundle**
- See [BETA-scan-storage.md](BETA-scan-storage.md)

## Phase 2 (Figma + Day 1)

- ChArUco vest capture (front/back)
- Side readout OCR
- Auth & profile

## Figma handoff

Export node `104-1331` at **2×** for per-screen typography and copy alignment.
