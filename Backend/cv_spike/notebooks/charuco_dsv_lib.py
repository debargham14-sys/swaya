"""
Generate and validate printable ChArUco / ArUco assets for the DSV sizing vest.

The vest panel carries:
  - a ChArUco calibration strip (sub-mm scale + perspective correction)
  - magenta horizontal bands at bust / underbust / waist / hip / shoulder
  - 18 mm shoulder ArUco markers (same spec as dsv_measurement_probe)
  - optional height ruler strip for stature without self-reported height

Detection helpers recover mm-per-px, measurement-line Y positions, and inferred
height from a calibrated photo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Anthropometric heights as fraction of stature measured from the floor (upward).
# Shared with pipeline.measure.markerless.LANDMARK_FROM_FLOOR.
LANDMARK_FROM_FLOOR: dict[str, float] = {
    "shoulder": 0.818,
    "bust": 0.720,
    "underbust": 0.685,
    "waist": 0.620,
    "hip": 0.530,
}

MEASUREMENT_LEVELS = ("shoulder", "bust", "underbust", "waist", "hip")
STENCIL_LEVELS = ("bust", "underbust", "waist", "hip", "hip2")

# Production stencil tape colours (BGR, sampled from dsv_front_panel_charuco.png)
STENCIL_TAPE_COLORS_BGR: dict[str, tuple[int, int, int]] = {
    "bust": (165, 54, 97),
    "underbust": (165, 54, 97),
    "waist": (104, 71, 142),
    "hip": (196, 160, 60),
    "hip2": (196, 160, 60),
}
STENCIL_TAPE_LABELS: dict[str, str] = {
    "bust": "BUST",
    "underbust": "UNDERBUST",
    "waist": "WAIST",
    "hip": "HIP",
    "hip2": "HIP-2",
}

MM_PER_IN = 25.4
TAPE_HEIGHT_MM = 14.0
TAPE_TICK_MAJOR_BGR = (255, 255, 255)
TAPE_TICK_MINOR_BGR = (235, 235, 235)
TAPE_NUMBER_BGR = (255, 255, 255)
TAPE_FOOT_MARK_BGR = (200, 220, 255)  # light highlight at 12", 24", 36"
TAPE_TICK_STEP_IN = 0.125             # 1/8 inch resolution

# Legacy single-marker slots on the production front-panel stencil
ID_STENCIL_F0 = 0
ID_STENCIL_F1 = 1

# BGR colours — all in the magenta HSV band detected by dsv_probe_lib / API
BAND_COLORS_BGR: dict[str, tuple[int, int, int]] = {
    "shoulder": (200, 40, 200),
    "bust": (180, 0, 180),
    "underbust": (160, 0, 150),
    "waist": (200, 0, 200),
    "hip": (140, 0, 170),
}

# Reserved ArUco IDs on the vest panel
ID_SHOULDER_L = 10
ID_SHOULDER_R = 11
ID_LEVEL_BASE = 20  # bust=20, underbust=21, waist=22, hip=23


@dataclass
class DSVVestSpec:
    """Physical layout for one printable DSV torso panel (shoulder anchor at top)."""

    panel_w_mm: float = 280.0
    panel_h_mm: float = 560.0
    reference_height_cm: float = 170.0
    charuco_cols: int = 4
    charuco_rows: int = 22
    charuco_square_mm: float = 20.0
    charuco_marker_mm: float = 14.0
    charuco_margin_mm: float = 8.0
    shoulder_aruco_mm: float = 18.0
    band_height_mm: float = 6.0
    fabric_bgr: tuple[int, int, int] = (245, 245, 240)
    dict_name: str = "DICT_4X4_250"  # 4×22 board needs ~88 ids (DICT_4X4_50 is too small)
    px_per_mm: float = 8.0  # render resolution (≈ 200 dpi at 8 px/mm)

    def level_offset_mm(self, level: str) -> float:
        """Signed mm from panel top (shoulder line); +y is downward."""
        h_mm = self.reference_height_cm * 10.0
        sh_frac = LANDMARK_FROM_FLOOR["shoulder"]
        if level == "shoulder":
            return 0.0
        if level not in LANDMARK_FROM_FLOOR:
            raise KeyError(level)
        return (sh_frac - LANDMARK_FROM_FLOOR[level]) * h_mm

    def level_y_mm(self, level: str) -> float:
        return self.level_offset_mm(level)

    def levels_mm(self) -> dict[str, float]:
        return {lv: self.level_y_mm(lv) for lv in MEASUREMENT_LEVELS}


@dataclass
class HeightRulerSpec:
    """Vertical wall chart for automatic stature (person stands beside it)."""

    height_cm: float = 200.0
    width_mm: float = 90.0
    charuco_cols: int = 3
    charuco_square_mm: float = 18.0
    charuco_marker_mm: float = 12.0
    tick_every_cm: float = 5.0
    dict_name: str = "DICT_4X4_50"
    px_per_mm: float = 8.0
    fabric_bgr: tuple[int, int, int] = (250, 250, 245)
    # Tile the 200 cm strip into short boards (3×12 = 36 ids each, fits DICT_4X4_50).
    max_rows_per_board: int = 12


@dataclass
class CharucoSlotSpec:
    """One ChArUco board replacing a legacy F0/F1 ArUco on the DSV stencil."""

    name: str  # "F0" | "F1"
    cols: int = 5
    rows: int = 4
    square_mm: float = 12.0
    marker_mm: float = 9.0
    dict_name: str = "DICT_4X4_50"
    legacy_aruco_id: int = 0
    # centre in panel-mm coords (filled by upgrade_stencil)
    center_x_mm: float | None = None
    center_y_mm: float | None = None
    # centre in image px (filled by auto-detect)
    center_px: tuple[float, float] | None = None
    legacy_side_px: float | None = None


@dataclass
class DSVStencilSpec:
    """
    Production DSV front-panel stencil (grid + coloured measurement lines).

    Set `panel_w_mm` to the real printed width between the outer grid edges.
    The image is scaled to that width; all ChArUco slots and measurement lines
    are stored in panel-mm coordinates for worn-photo calibration.
    """

    stencil_path: Path
    panel_w_mm: float = 340.0
    panel_h_mm: float | None = None  # derived from aspect ratio if None
    grid_mm: float = 5.0  # fine grid cell size on the stencil art
    shoulder_y_mm: float = 42.0  # SHL-L / SHL-R row from panel top
    slots: tuple[CharucoSlotSpec, CharucoSlotSpec] = (
        CharucoSlotSpec("F0", dict_name="DICT_4X4_50", legacy_aruco_id=ID_STENCIL_F0),
        CharucoSlotSpec("F1", dict_name="DICT_5X5_100", legacy_aruco_id=ID_STENCIL_F1),
    )
    # manual fallbacks (fraction of image w/h) when legacy ArUco is not detected
    fallback_center_frac: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {"F0": (0.50, 0.245), "F1": (0.50, 0.585)}
    )


@dataclass
class PanelAssets:
    spec: DSVVestSpec | DSVStencilSpec
    image_bgr: np.ndarray
    spec_json: dict[str, Any]
    output_paths: list[Path] = field(default_factory=list)


@dataclass
class CalibrationResult:
    mm_per_px: float | None
    H_px_to_mm: np.ndarray | None
    charuco_corners: int
    aruco_ids: list[int]
    method: str
    warnings: list[str] = field(default_factory=list)

    def px_to_mm(self, pts_px: np.ndarray) -> np.ndarray:
        if self.H_px_to_mm is None:
            raise ValueError("no homography")
        pts = np.asarray(pts_px, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(pts, self.H_px_to_mm)
        return out.reshape(-1, 2)


@dataclass
class VestDetection:
    calibration: CalibrationResult
    band_rows_px: dict[str, int]
    shoulder_aruco_cm_per_px: float | None
    inferred_height_cm: float | None
    level_heights_from_floor_mm: dict[str, float]


# ArUco predefined dictionaries and their marker-id capacity (ids 0 .. N-1).
_DICT_CAPACITIES: tuple[tuple[str, int], ...] = (
    ("DICT_4X4_50", 50),
    ("DICT_4X4_100", 100),
    ("DICT_4X4_250", 250),
    ("DICT_4X4_1000", 1000),
    ("DICT_5X5_50", 50),
    ("DICT_5X5_100", 100),
    ("DICT_5X5_250", 250),
    ("DICT_5X5_1000", 1000),
)


def _charuco_markers_required(cols: int, rows: int) -> int:
    """Upper-bound marker-id count for a cols×rows ChArUco board."""
    # OpenCV assigns sequential ids to marker slots; worst case ≈ half the cells.
    return max(1, (cols * rows + 1) // 2) + 4


def _resolve_dict_name(preferred: str, cols: int, rows: int, needed: int | None = None) -> str:
    """
    Pick a dictionary large enough for the board.

    A 200 cm height ruler at 18 mm squares needs ~3×112 = 336 ids — far more
    than DICT_4X4_50 (50). Upgrades automatically to DICT_4X4_1000 when needed.
    """
    needed = needed if needed is not None else _charuco_markers_required(cols, rows)
    caps = dict(_DICT_CAPACITIES)
    if preferred in caps and caps[preferred] >= needed:
        return preferred
    # Prefer 4x4 family, then 5x5, smallest dict that fits.
    for name, capacity in _DICT_CAPACITIES:
        if capacity >= needed:
            return name
    raise ValueError(
        f"ChArUco board {cols}×{rows} needs ≥{needed} marker ids; "
        f"increase charuco_square_mm or tile the ruler into shorter segments."
    )


def _dictionary(dict_name: str) -> cv2.aruco.Dictionary:
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))


def _mm_to_px(mm: float, px_per_mm: float) -> int:
    return int(round(mm * px_per_mm))


def _mm_to_in(mm: float, prec: int = 1) -> float:
    return round(mm / MM_PER_IN, prec)


def _format_in_label(inches: float) -> str:
    """Compact inch ruler label (whole numbers omit decimals)."""
    if abs(inches - round(inches)) < 0.05:
        return str(int(round(inches)))
    return f"{inches:.1f}"


def _tape_tick_profile(inch_val: float) -> tuple[float, bool, bool]:
    """Return (tick height fraction, show inch number, is major tick) for tape-measure marks."""
    eighth = int(round(inch_val * 8 + 1e-6)) % 8
    if eighth == 0:
        return 1.0, True, True
    if eighth == 4:
        return 0.68, False, True
    if eighth in (2, 6):
        return 0.46, False, False
    return 0.30, False, False


def _draw_hline(canvas: np.ndarray, y_px: int, color: tuple[int, int, int], thick: int) -> None:
    cv2.line(canvas, (0, y_px), (canvas.shape[1] - 1, y_px), color, thick, cv2.LINE_AA)


def _paste_aruco(
    canvas: np.ndarray,
    dictionary: cv2.aruco.Dictionary,
    marker_id: int,
    center_x_mm: float,
    center_y_mm: float,
    side_mm: float,
    px_per_mm: float,
) -> None:
    side_px = max(16, _mm_to_px(side_mm, px_per_mm))
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    cx = _mm_to_px(center_x_mm, px_per_mm)
    cy = _mm_to_px(center_y_mm, px_per_mm)
    x0, y0 = cx - side_px // 2, cy - side_px // 2
    x1, y1 = x0 + side_px, y0 + side_px
    h, w = canvas.shape[:2]
    x0c, y0c = max(0, x0), max(0, y0)
    x1c, y1c = min(w, x1), min(h, y1)
    if x1c <= x0c or y1c <= y0c:
        return
    mx0, my0 = x0c - x0, y0c - y0
    canvas[y0c:y1c, x0c:x1c] = marker_bgr[my0 : my0 + (y1c - y0c), mx0 : mx0 + (x1c - x0c)]


def _dict_candidates(preferred: str, needed: int) -> list[str]:
    """Ordered dictionary names to try, preferred first when it fits."""
    fitting = [name for name, cap in _DICT_CAPACITIES if cap >= needed]
    if not fitting:
        fitting = [name for name, _ in _DICT_CAPACITIES[-2:]]
    if preferred in fitting:
        return [preferred] + [n for n in fitting if n != preferred]
    return fitting


def _render_charuco_board_bgr(
    cols: int,
    rows: int,
    square_mm: float,
    marker_mm: float,
    dict_name: str,
    px_per_mm: float,
) -> tuple[np.ndarray, float, float, str]:
    """Render one ChArUco board; auto-upgrade dictionary when ids run out."""
    needed_est = _charuco_markers_required(cols, rows)
    square_m = square_mm / 1000.0
    marker_m = marker_mm / 1000.0
    strip_w_mm = cols * square_mm
    strip_h_mm = rows * square_mm
    out_w = max(8, _mm_to_px(strip_w_mm, px_per_mm))
    out_h = max(8, _mm_to_px(strip_h_mm, px_per_mm))

    last_exc: cv2.error | None = None
    for resolved in _dict_candidates(dict_name, needed_est):
        try:
            dictionary = _dictionary(resolved)
            board = cv2.aruco.CharucoBoard((cols, rows), square_m, marker_m, dictionary)
            ids = board.getIds()
            if ids is not None and len(ids) > 0:
                actual = int(np.max(ids)) + 1
                caps = dict(_DICT_CAPACITIES)
                if caps.get(resolved, 0) < actual:
                    continue
            strip = board.generateImage((out_w, out_h), marginSize=0, borderBits=1)
            strip_bgr = cv2.cvtColor(strip, cv2.COLOR_GRAY2BGR)
            return strip_bgr, strip_w_mm, strip_h_mm, resolved
        except cv2.error as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"could not render {cols}×{rows} ChArUco board")


def _render_charuco_strip(
    spec: DSVVestSpec | HeightRulerSpec,
    cols: int,
    rows: int,
    origin_x_mm: float,
    origin_y_mm: float,
) -> tuple[np.ndarray, float, float]:
    """Return (strip_bgr, strip_w_mm, strip_h_mm)."""
    strip_bgr, strip_w_mm, strip_h_mm, _ = _render_charuco_board_bgr(
        cols,
        rows,
        spec.charuco_square_mm,
        spec.charuco_marker_mm,
        spec.dict_name,
        spec.px_per_mm,
    )
    return strip_bgr, strip_w_mm, strip_h_mm


_RULER_TILE_DICTS = (
    "DICT_4X4_50",
    "DICT_5X5_50",
    "DICT_4X4_100",
    "DICT_5X5_100",
    "DICT_4X4_250",
    "DICT_5X5_250",
)


def _render_charuco_strip_tiled(
    spec: HeightRulerSpec,
    cols: int,
    total_rows: int,
    max_rows_per_board: int,
) -> tuple[np.ndarray, float, float, list[str]]:
    """Stack vertical ChArUco segments; rotate dictionary per segment to avoid duplicate ids."""
    segments: list[np.ndarray] = []
    dicts_used: list[str] = []
    y_mm = 0.0
    remaining = total_rows
    seg_idx = 0
    while remaining > 0:
        seg_rows = min(max_rows_per_board, remaining)
        seg_dict = _RULER_TILE_DICTS[seg_idx % len(_RULER_TILE_DICTS)]
        seg_bgr, _seg_w_mm, seg_h_mm, resolved = _render_charuco_board_bgr(
            cols,
            seg_rows,
            spec.charuco_square_mm,
            spec.charuco_marker_mm,
            seg_dict,
            spec.px_per_mm,
        )
        segments.append(seg_bgr)
        dicts_used.append(resolved)
        y_mm += seg_h_mm
        remaining -= seg_rows
        seg_idx += 1
    strip_bgr = np.vstack(segments)
    return strip_bgr, cols * spec.charuco_square_mm, y_mm, dicts_used


def generate_vest_panel(spec: DSVVestSpec | None = None) -> PanelAssets:
    """Render the full DSV torso panel at spec.px_per_mm."""
    spec = spec or DSVVestSpec()
    dictionary = _dictionary(spec.dict_name)
    w_px = _mm_to_px(spec.panel_w_mm, spec.px_per_mm)
    h_px = _mm_to_px(spec.panel_h_mm, spec.px_per_mm)
    canvas = np.full((h_px, w_px, 3), spec.fabric_bgr, np.uint8)

    # ChArUco strip along the left edge
    strip, strip_w_mm, _ = _render_charuco_strip(
        spec, spec.charuco_cols, spec.charuco_rows, 0.0, spec.charuco_margin_mm
    )
    sh_px = _mm_to_px(spec.charuco_margin_mm, spec.px_per_mm)
    sw_px = strip.shape[1]
    canvas[sh_px : sh_px + strip.shape[0], 0:sw_px] = strip

    fabric_x0_mm = strip_w_mm + 4.0
    band_x0 = _mm_to_px(fabric_x0_mm, spec.px_per_mm)
    band_x1 = w_px - 1
    band_thick = max(2, _mm_to_px(spec.band_height_mm, spec.px_per_mm))

    # Measurement bands + tiny level ArUco tags on the left of each band
    level_ids = {
        "bust": ID_LEVEL_BASE,
        "underbust": ID_LEVEL_BASE + 1,
        "waist": ID_LEVEL_BASE + 2,
        "hip": ID_LEVEL_BASE + 3,
    }
    for level in MEASUREMENT_LEVELS:
        y_mm = spec.level_y_mm(level)
        y_px = _mm_to_px(y_mm, spec.px_per_mm)
        color = BAND_COLORS_BGR[level]
        _draw_hline(canvas, y_px, color, band_thick)
        cv2.line(canvas, (band_x0, y_px), (band_x1, y_px), color, band_thick, cv2.LINE_AA)
        if level in level_ids:
            _paste_aruco(
                canvas,
                dictionary,
                level_ids[level],
                fabric_x0_mm + spec.shoulder_aruco_mm * 0.6,
                y_mm,
                spec.shoulder_aruco_mm * 0.55,
                spec.px_per_mm,
            )

    # Shoulder reference ArUco pair (18 mm — matches dsv_probe_lib)
    shoulder_y_mm = spec.level_y_mm("shoulder")
    inset = spec.shoulder_aruco_mm
    _paste_aruco(
        canvas, dictionary, ID_SHOULDER_L,
        fabric_x0_mm + inset, shoulder_y_mm + inset * 0.3,
        spec.shoulder_aruco_mm, spec.px_per_mm,
    )
    _paste_aruco(
        canvas, dictionary, ID_SHOULDER_R,
        spec.panel_w_mm - inset, shoulder_y_mm + inset * 0.3,
        spec.shoulder_aruco_mm, spec.px_per_mm,
    )

    # Panel border + labels
    cv2.rectangle(canvas, (0, 0), (w_px - 1, h_px - 1), (30, 30, 30), max(1, band_thick // 2))
    label = (
        f"DSV ChArUco panel  ref H={spec.reference_height_cm:.0f} cm  "
        f"top=shoulder  {spec.dict_name}"
    )
    cv2.putText(
        canvas, label, (band_x0, max(20, sh_px - 6)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1, cv2.LINE_AA,
    )

    meta = {
        "kind": "dsv_vest_panel",
        "spec": asdict(spec),
        "levels_mm_from_shoulder": spec.levels_mm(),
        "landmark_from_floor": LANDMARK_FROM_FLOOR,
        "marker_ids": {
            "shoulder_l": ID_SHOULDER_L,
            "shoulder_r": ID_SHOULDER_R,
            "levels": level_ids,
        },
        "print_note": (
            f"Print at 100% scale so the panel measures "
            f"{spec.panel_w_mm:.0f} x {spec.panel_h_mm:.0f} mm."
        ),
    }
    return PanelAssets(spec=spec, image_bgr=canvas, spec_json=meta)


def generate_height_ruler(spec: HeightRulerSpec | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Vertical stature chart with ChArUco strip and cm ticks (floor = bottom)."""
    spec = spec or HeightRulerSpec()
    dictionary = _dictionary(spec.dict_name)
    h_mm = spec.height_cm * 10.0
    w_px = _mm_to_px(spec.width_mm, spec.px_per_mm)
    h_px = _mm_to_px(h_mm, spec.px_per_mm)
    canvas = np.full((h_px, w_px, 3), spec.fabric_bgr, np.uint8)

    rows = max(4, int(np.ceil(h_mm / spec.charuco_square_mm)))
    seg_rows = spec.max_rows_per_board if spec.max_rows_per_board > 0 else 12
    try:
        strip, strip_w_mm, strip_h_mm, dicts_used = _render_charuco_strip_tiled(
            spec, spec.charuco_cols, rows, seg_rows
        )
    except cv2.error as exc:
        raise RuntimeError(
            f"ChArUco ruler failed ({exc}). "
            f"Full strip is {spec.charuco_cols}×{rows} — reduce max_rows_per_board "
            f"(current {seg_rows}) or increase charuco_square_mm."
        ) from exc
    use_h = min(strip.shape[0], h_px)
    canvas[0:use_h, 0 : strip.shape[1]] = strip[0:use_h]

    tick_x0 = _mm_to_px(strip_w_mm + 4.0, spec.px_per_mm)
    tick_x1 = w_px - _mm_to_px(6.0, spec.px_per_mm)
    for cm in np.arange(0.0, spec.height_cm + 0.1, spec.tick_every_cm):
        y_mm = h_mm - cm * 10.0  # floor at bottom
        y_px = _mm_to_px(y_mm, spec.px_per_mm)
        color = (0, 0, 200) if cm % 10 == 0 else (80, 80, 80)
        thick = 2 if cm % 10 == 0 else 1
        cv2.line(canvas, (tick_x0, y_px), (tick_x1, y_px), color, thick, cv2.LINE_AA)
        if cm % 10 == 0:
            cv2.putText(
                canvas, f"{int(cm)}", (tick_x1 + 2, y_px + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 160), 1, cv2.LINE_AA,
            )

    _paste_aruco(canvas, dictionary, 30, spec.width_mm / 2, 8.0, 16.0, spec.px_per_mm)
    _paste_aruco(canvas, dictionary, 31, spec.width_mm / 2, h_mm - 8.0, 16.0, spec.px_per_mm)

    meta = {
        "kind": "height_ruler",
        "spec": asdict(spec),
        "charuco_board": f"{spec.charuco_cols}x{rows} (tiled {seg_rows} rows/segment)",
        "charuco_dicts_used": dicts_used,
        "floor_marker_id": 31,
        "top_marker_id": 30,
        "print_note": f"Print at 100% scale so height = {spec.height_cm:.0f} cm.",
    }
    return canvas, meta


def tile_a4_pages(
    image_bgr: np.ndarray,
    px_per_mm: float,
    out_dir: Path,
    prefix: str = "tile",
    a4_w_mm: float = 210.0,
    a4_h_mm: float = 297.0,
    overlap_mm: float = 8.0,
) -> list[Path]:
    """Slice a large panel into landscape A4 tiles with overlap for home printing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tile_w = _mm_to_px(a4_w_mm, px_per_mm)
    tile_h = _mm_to_px(a4_h_mm, px_per_mm)
    step_x = _mm_to_px(a4_w_mm - overlap_mm, px_per_mm)
    step_y = _mm_to_px(a4_h_mm - overlap_mm, px_per_mm)
    h, w = image_bgr.shape[:2]
    paths: list[Path] = []
    row, col = 0, 0
    for y0 in range(0, h, step_y):
        for x0 in range(0, w, step_x):
            patch = image_bgr[y0 : min(y0 + tile_h, h), x0 : min(x0 + tile_w, w)]
            pad = np.full((tile_h, tile_w, 3), 255, np.uint8)
            pad[0 : patch.shape[0], 0 : patch.shape[1]] = patch
            tag = f"{prefix}_r{row:02d}_c{col:02d}.png"
            path = out_dir / tag
            cv2.imwrite(str(path), pad)
            paths.append(path)
            col += 1
        row += 1
        col = 0
    return paths


def _charuco_board_for_vest(spec: DSVVestSpec) -> cv2.aruco.CharucoBoard:
    dictionary = _dictionary(spec.dict_name)
    return cv2.aruco.CharucoBoard(
        (spec.charuco_cols, spec.charuco_rows),
        spec.charuco_square_mm / 1000.0,
        spec.charuco_marker_mm / 1000.0,
        dictionary,
    )


def calibrate_from_charuco(
    img_bgr: np.ndarray,
    spec: DSVVestSpec,
    origin_x_mm: float = 0.0,
    origin_y_mm: float | None = None,
) -> CalibrationResult:
    """Detect ChArUco corners and build px -> panel-mm homography."""
    origin_y_mm = spec.charuco_margin_mm if origin_y_mm is None else origin_y_mm
    board = _charuco_board_for_vest(spec)
    dictionary = _dictionary(spec.dict_name)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.CharucoDetector(board, detectorParams=params)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    charuco_corners, charuco_ids, marker_corners, marker_ids = detector.detectBoard(gray)

    warnings: list[str] = []
    n_corners = 0 if charuco_corners is None else len(charuco_corners)
    aruco_ids_list: list[int] = []
    if marker_ids is not None:
        aruco_ids_list = [int(i) for i in marker_ids.flatten()]

    if n_corners < 6:
        warnings.append(f"only_{n_corners}_charuco_corners")
        return CalibrationResult(None, None, n_corners, aruco_ids_list, "none", warnings)

    obj_pts = board.getChessboardCorners()[charuco_ids.flatten()]
    obj_mm = np.zeros((len(obj_pts), 2), dtype=np.float64)
    obj_mm[:, 0] = origin_x_mm + obj_pts[:, 0] * 1000.0
    obj_mm[:, 1] = origin_y_mm + obj_pts[:, 1] * 1000.0
    img_pts = charuco_corners.reshape(-1, 2).astype(np.float64)

    H, _ = cv2.findHomography(img_pts, obj_mm, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if H is None:
        warnings.append("homography_failed")
        return CalibrationResult(None, None, n_corners, aruco_ids_list, "none", warnings)

    # mm_per_px from median adjacent corner spacing
    ratios: list[float] = []
    for i in range(len(img_pts) - 1):
        d_px = float(np.linalg.norm(img_pts[i] - img_pts[i + 1]))
        d_mm = float(np.linalg.norm(obj_mm[i] - obj_mm[i + 1]))
        if d_px > 2.0 and d_mm > 1.0:
            ratios.append(d_mm / d_px)
    mm_per_px = float(np.median(ratios)) if ratios else None

    return CalibrationResult(mm_per_px, H, n_corners, aruco_ids_list, "charuco_homography", warnings)


def detect_magenta_bands(bgr: np.ndarray, min_width_frac: float = 0.12) -> list[int]:
    """Return centre-row of each horizontal magenta band (same logic as DSV probe)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([140, 60, 60], np.uint8), np.array([175, 255, 255], np.uint8))
    h, w = mask.shape
    row_frac = mask.sum(axis=1) / max(1, w) / 255.0
    on = np.where(row_frac >= min_width_frac)[0]
    if len(on) == 0:
        return []
    splits = np.where(np.diff(on) > 1)[0]
    groups = np.split(on, splits + 1)
    return [int((int(g[0]) + int(g[-1])) / 2) for g in groups]


def _aruco_scale_cm_per_px(bgr: np.ndarray, marker_mm: float, dict_name: str) -> float | None:
    dictionary = _dictionary(dict_name)
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return None
    target = {ID_SHOULDER_L, ID_SHOULDER_R}
    sides = []
    for c, mid in zip(corners, ids.flatten()):
        if int(mid) not in target:
            continue
        p = c[0]
        s = sum(float(np.linalg.norm(p[i] - p[(i + 1) % 4])) for i in range(4)) / 4.0
        sides.append(s)
    if not sides:
        return None
    px = float(np.median(sides))
    return (marker_mm / 10.0) / px


def map_bands_to_levels(band_rows: list[int], spec: DSVVestSpec) -> dict[str, int]:
    """Match detected magenta rows to named levels via expected Y order."""
    if not band_rows:
        return {}
    expected = sorted(
        ((lv, _mm_to_px(spec.level_y_mm(lv), spec.px_per_mm)) for lv in MEASUREMENT_LEVELS),
        key=lambda t: t[1],
    )
    levels_only = [lv for lv, _ in expected]
    bands = sorted(band_rows)
    if len(bands) != len(levels_only):
        # Greedy nearest-neighbour assignment
        out: dict[str, int] = {}
        used: set[int] = set()
        for lv, ey in expected:
            candidates = [(abs(b - ey), b) for b in bands if b not in used]
            if not candidates:
                break
            _, best = min(candidates)
            used.add(best)
            out[lv] = best
        return out
    return dict(zip(levels_only, bands))


def infer_height_cm(
    shoulder_y_px: float,
    image_bottom_px: float,
    mm_per_px: float | None,
    spec: DSVVestSpec,
) -> float | None:
    """
    Infer stature when the vest shoulder line is visible and scale is known.

    Uses the anthropometric model: shoulder sits at LANDMARK_FROM_FLOOR * H.
    Distance from shoulder (panel top) to feet ≈ (image_bottom - shoulder_y) in mm.
    """
    if not mm_per_px or mm_per_px <= 0:
        return None
    shoulder_from_floor_frac = LANDMARK_FROM_FLOOR["shoulder"]
    below_shoulder_mm = max(0.0, (image_bottom_px - shoulder_y_px) * mm_per_px)
    # feet are at floor; shoulder is at shoulder_frac * H above floor
    # below_shoulder_mm ≈ shoulder_frac * H  =>  H = below_shoulder_mm / shoulder_frac
    # More precisely: distance shoulder->floor = shoulder_frac * H
    if below_shoulder_mm < 50.0:
        return None
    return round(below_shoulder_mm / (shoulder_from_floor_frac * 10.0), 1)


def analyze_vest_photo(
    img_bgr: np.ndarray,
    spec: DSVVestSpec | None = None,
    silhouette_bottom_px: int | None = None,
) -> VestDetection:
    """Full decode: calibration, band levels, optional stature."""
    spec = spec or DSVVestSpec()
    calib = calibrate_from_charuco(img_bgr, spec)
    aruco_cpp = _aruco_scale_cm_per_px(img_bgr, spec.shoulder_aruco_mm, spec.dict_name)
    mm_per_px = calib.mm_per_px
    if mm_per_px is None and aruco_cpp:
        mm_per_px = aruco_cpp * 10.0

    bands = detect_magenta_bands(img_bgr)
    band_map = map_bands_to_levels(bands, spec)

    shoulder_y = _mm_to_px(spec.level_y_mm("shoulder"), spec.px_per_mm)
    if calib.H_px_to_mm is not None:
        # Re-project expected shoulder ArUco centres to refine shoulder row
        dictionary = _dictionary(spec.dict_name)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is not None:
            for c, mid in zip(corners, ids.flatten()):
                if int(mid) in (ID_SHOULDER_L, ID_SHOULDER_R):
                    cy = float(c[0][:, 1].mean())
                    shoulder_y = cy
                    break

    bottom = silhouette_bottom_px if silhouette_bottom_px is not None else img_bgr.shape[0] - 1
    height_cm = infer_height_cm(shoulder_y, bottom, mm_per_px, spec)

    floor_mm: dict[str, float] = {}
    if height_cm:
        h_mm = height_cm * 10.0
        for lv, frac in LANDMARK_FROM_FLOOR.items():
            floor_mm[lv] = frac * h_mm

    return VestDetection(
        calibration=calib,
        band_rows_px=band_map,
        shoulder_aruco_cm_per_px=aruco_cpp,
        inferred_height_cm=height_cm,
        level_heights_from_floor_mm=floor_mm,
    )


def _load_stencil_bgr(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"cannot read stencil: {path}")
    return img


def _px_per_mm_from_stencil(img: np.ndarray, panel_w_mm: float) -> float:
    return img.shape[1] / panel_w_mm


def _detect_legacy_aruco_slots(
    img_bgr: np.ndarray,
    spec: DSVStencilSpec,
) -> dict[str, dict[str, Any]]:
    """
    Find legacy F0/F1 ArUco markers on the stencil art.

    Tries every dictionary listed on the slot specs, then falls back to
    configured fractional centres.
    """
    h, w = img_bgr.shape[:2]
    px_per_mm = _px_per_mm_from_stencil(img_bgr, spec.panel_w_mm)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    found: dict[int, dict[str, Any]] = {}

    dicts = {slot.dict_name for slot in spec.slots}
    dicts.add("DICT_4X4_50")
    dicts.add("DICT_5X5_100")
    dicts.add("DICT_6X6_250")

    for dict_name in dicts:
        dictionary = _dictionary(dict_name)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is None:
            continue
        for c, mid in zip(corners, ids.flatten()):
            mid = int(mid)
            if mid in found:
                continue
            pts = c[0]
            cx = float(pts[:, 0].mean())
            cy = float(pts[:, 1].mean())
            side = float(
                sum(np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)) / 4.0
            )
            found[mid] = {"center_px": (cx, cy), "side_px": side, "dict": dict_name}

    out: dict[str, dict[str, Any]] = {}
    for slot in spec.slots:
        hit = found.get(slot.legacy_aruco_id)
        if hit:
            out[slot.name] = hit
            continue
        # pick the unused marker nearest the fallback centre
        fx, fy = spec.fallback_center_frac.get(slot.name, (0.5, 0.5))
        target = (fx * w, fy * h)
        if found:
            best_id = min(
                found,
                key=lambda i: np.hypot(
                    found[i]["center_px"][0] - target[0],
                    found[i]["center_px"][1] - target[1],
                ),
            )
            out[slot.name] = found[best_id]
        else:
            side_px = _mm_to_px(24.0, px_per_mm)
            out[slot.name] = {
                "center_px": target,
                "side_px": float(side_px),
                "dict": slot.dict_name,
                "synthetic": True,
            }
    return out


def _erase_square_patch(
    canvas: np.ndarray,
    center_px: tuple[float, float],
    side_px: float,
    pad_frac: float = 0.15,
) -> tuple[int, int, int, int]:
    """Inpaint a square region and return the cleared bounding box (x0,y0,x1,y1)."""
    cx, cy = center_px
    half = side_px * (0.5 + pad_frac)
    x0 = int(max(0, cx - half))
    y0 = int(max(0, cy - half))
    x1 = int(min(canvas.shape[1], cx + half))
    y1 = int(min(canvas.shape[0], cy + half))
    mask = np.zeros(canvas.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = 255
    canvas[:] = cv2.inpaint(canvas, mask, 3, cv2.INPAINT_TELEA)
    return x0, y0, x1, y1


def _render_slot_charuco_bgr(
    slot: CharucoSlotSpec,
    px_per_mm: float,
) -> tuple[np.ndarray, float, float]:
    board_bgr, w_mm, h_mm, _ = _render_charuco_board_bgr(
        slot.cols,
        slot.rows,
        slot.square_mm,
        slot.marker_mm,
        slot.dict_name,
        px_per_mm,
    )
    return board_bgr, w_mm, h_mm


def _paste_centered(
    canvas: np.ndarray,
    patch_bgr: np.ndarray,
    center_px: tuple[float, float],
) -> tuple[int, int, int, int]:
    cx, cy = center_px
    ph, pw = patch_bgr.shape[:2]
    x0 = int(round(cx - pw / 2))
    y0 = int(round(cy - ph / 2))
    x1, y1 = x0 + pw, y0 + ph
    h, w = canvas.shape[:2]
    x0c, y0c = max(0, x0), max(0, y0)
    x1c, y1c = min(w, x1), min(h, y1)
    if x1c <= x0c or y1c <= y0c:
        return x0, y0, x1, y1
    sx0, sy0 = x0c - x0, y0c - y0
    canvas[y0c:y1c, x0c:x1c] = patch_bgr[sy0 : sy0 + (y1c - y0c), sx0 : sx0 + (x1c - x0c)]
    return x0, y0, x1, y1


def detect_stencil_measurement_lines(
    img_bgr: np.ndarray,
    min_span_frac: float = 0.35,
) -> dict[str, int]:
    """
    Detect coloured horizontal measurement lines on the production stencil.

    Returns {level_name: centre_row_px} for bust, underbust, waist, hip, hip2.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, w = img_bgr.shape[:2]

    def _rows(mask: np.ndarray) -> list[int]:
        row_frac = mask.sum(axis=1) / max(1, w) / 255.0
        on = np.where(row_frac >= min_span_frac)[0]
        if len(on) == 0:
            return []
        splits = np.where(np.diff(on) > 2)[0]
        groups = np.split(on, splits + 1)
        return [int((int(g[0]) + int(g[-1])) / 2) for g in groups]

    pink = cv2.inRange(hsv, np.array([145, 40, 80], np.uint8), np.array([175, 255, 255], np.uint8))
    purple = cv2.inRange(hsv, np.array([125, 30, 60], np.uint8), np.array([155, 255, 255], np.uint8))
    teal = cv2.inRange(hsv, np.array([78, 35, 80], np.uint8), np.array([105, 255, 255], np.uint8))

    pink_rows = sorted(_rows(pink))
    purple_rows = sorted(_rows(purple))
    teal_rows = sorted(_rows(teal))

    out: dict[str, int] = {}
    if len(pink_rows) >= 2:
        out["bust"], out["underbust"] = pink_rows[0], pink_rows[1]
    elif len(pink_rows) == 1:
        out["bust"] = pink_rows[0]
    if purple_rows:
        out["waist"] = purple_rows[0]
    if len(teal_rows) >= 2:
        out["hip"], out["hip2"] = teal_rows[0], teal_rows[1]
    elif len(teal_rows) == 1:
        out["hip"] = teal_rows[0]
    return out


# HSV ranges for coloured measuring tapes (same as detect_stencil_measurement_lines).
_TAPE_HSV: dict[str, tuple[np.ndarray, np.ndarray]] = {
    "pink": (np.array([145, 40, 80], np.uint8), np.array([175, 255, 255], np.uint8)),
    "purple": (np.array([125, 30, 60], np.uint8), np.array([155, 255, 255], np.uint8)),
    "teal": (np.array([78, 35, 80], np.uint8), np.array([105, 255, 255], np.uint8)),
}
_LEVEL_TAPE_COLOR: dict[str, str] = {
    "bust": "pink",
    "underbust": "pink",
    "waist": "purple",
    "hip": "teal",
    "hip2": "teal",
}


@dataclass
class BandWidthResult:
    """Width read at a coloured measuring band (inch ticks + silhouette edges)."""

    level: str
    y_px: int
    left_x: int
    right_x: int
    width_cm: float
    width_in: float
    px_per_eighth_in: float | None = None
    scale_source: str = "tape_ticks"
    edge_source: str = "body_mask"
    warnings: list[str] = field(default_factory=list)


def _tape_hsv_for_level(level: str) -> tuple[np.ndarray, np.ndarray]:
    color = _LEVEL_TAPE_COLOR.get(level, "pink")
    return _TAPE_HSV[color]


def _tape_row_mask(
    bgr: np.ndarray,
    y: int,
    hsv_lo: np.ndarray,
    hsv_hi: np.ndarray,
    tape_half_h: int = 14,
) -> np.ndarray:
    h = bgr.shape[0]
    y = int(np.clip(y, 0, h - 1))
    y0, y1 = max(0, y - tape_half_h), min(h, y + tape_half_h)
    hsv = cv2.cvtColor(bgr[y0:y1], cv2.COLOR_BGR2HSV)
    return (cv2.inRange(hsv, hsv_lo, hsv_hi) > 0).any(axis=0)


def detect_tape_px_per_eighth_in(
    bgr: np.ndarray,
    y: int,
    level: str,
    tape_half_h: int = 14,
) -> tuple[float | None, tuple[int, int] | None]:
    """
    Median pixel spacing between 1/8-inch tick marks on a horizontal measuring band.

    Returns ``(px_per_eighth_in, (x0, x1))`` for the widest visible tape run.
    """
    lo, hi = _tape_hsv_for_level(level)
    col = _tape_row_mask(bgr, y, lo, hi, tape_half_h=tape_half_h)
    xs = np.where(col)[0]
    if len(xs) < 24:
        return None, None

    splits = np.where(np.diff(xs) > 12)[0]
    groups = np.split(xs, splits + 1)
    segs = [g for g in groups if len(g) >= 16]
    if not segs:
        return None, None
    best = max(segs, key=len)
    x0, x1 = int(best[0]), int(best[-1])

    h = bgr.shape[0]
    y0, y1 = max(0, y - tape_half_h), min(h, y + tape_half_h)
    gray = cv2.cvtColor(bgr[y0:y1, x0 : x1 + 1], cv2.COLOR_BGR2GRAY)
    gx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)).mean(axis=0).flatten()
    if gx.size < 8:
        return None, (x0, x1)

    thr = float(gx.mean() + 0.35 * gx.std())
    peaks: list[int] = []
    for i in range(2, len(gx) - 2):
        if gx[i] > thr and gx[i] >= gx[i - 1] and gx[i] >= gx[i + 1]:
            peaks.append(i + x0)
    if len(peaks) < 4:
        return None, (x0, x1)

    diffs = np.diff(peaks)
    diffs = diffs[(diffs > 1.5) & (diffs < 40.0)]
    if len(diffs) < 2:
        return None, (x0, x1)
    return float(np.median(diffs)), (x0, x1)


def _row_torso_edges(
    row: np.ndarray,
    margin_frac: float = 0.05,
    min_run_frac: float = 0.08,
) -> tuple[int, int] | None:
    """Left/right edges of the largest foreground run on a mask row."""
    w = row.shape[0]
    x_margin = int(w * margin_frac)
    seg = row[x_margin : w - x_margin]
    xs = np.where(seg > 128)[0]
    if len(xs) < 2:
        return None
    splits = np.where(np.diff(xs) > 3)[0]
    groups = np.split(xs, splits + 1)
    best = max(groups, key=len)
    if len(best) < max(8, int(w * min_run_frac)):
        return None
    return int(best[0] + x_margin), int(best[-1] + x_margin)


def _tape_wing_inner_edges(
    col: np.ndarray,
    min_seg_px: int = 8,
    min_gap_px: int = 30,
) -> tuple[int, int] | None:
    """Inner edges of left/right tape wings where the torso occludes the band."""
    w = col.shape[0]
    mid = w // 2
    left_x: int | None = None
    right_x: int | None = None

    for half, off, pick in (
        (col[:mid], 0, "right"),
        (col[mid:], mid, "left"),
    ):
        xs = np.where(half)[0]
        if len(xs) < min_seg_px:
            continue
        splits = np.where(np.diff(xs) > 10)[0]
        groups = np.split(xs, splits + 1)
        segs = [g for g in groups if len(g) >= min_seg_px]
        if not segs:
            continue
        if pick == "right":
            left_x = off + int(segs[-1][-1])
        else:
            right_x = off + int(segs[0][0])

    if left_x is None or right_x is None or (right_x - left_x) < min_gap_px:
        return None
    return left_x, right_x


def _tape_gap_inner_edges(col: np.ndarray, min_seg_px: int = 12, min_gap_px: int = 30) -> tuple[int, int] | None:
    """Gap between two tape segments when both shoulder wings are visible."""
    xs = np.where(col)[0]
    if len(xs) < min_seg_px * 2:
        return None
    splits = np.where(np.diff(xs) > 15)[0]
    groups = np.split(xs, splits + 1)
    segs = [(int(g[0]), int(g[-1])) for g in groups if len(g) >= min_seg_px]
    if len(segs) < 2:
        return None
    best_gap = 0
    best_pair: tuple[int, int] | None = None
    for i in range(len(segs) - 1):
        gap = segs[i + 1][0] - segs[i][1]
        if gap > best_gap:
            best_gap = gap
            best_pair = (segs[i][1], segs[i + 1][0])
    if best_pair is None or best_gap < min_gap_px:
        return None
    return best_pair


def measure_band_width_at_row(
    bgr: np.ndarray,
    y: int,
    level: str,
    body_mask: np.ndarray | None = None,
    mm_per_px: float | None = None,
    calibration: CalibrationResult | None = None,
    tape_half_h: int = 14,
) -> BandWidthResult | None:
    """
    Measure torso width at a coloured measuring band.

    Uses inch-tick spacing on the band for scale when ticks decode; edges come
    from the body mask row, falling back to tape-occlusion wings on the band.
    """
    h, w = bgr.shape[:2]
    y = int(np.clip(y, 0, h - 1))
    lo, hi = _tape_hsv_for_level(level)
    col = _tape_row_mask(bgr, y, lo, hi, tape_half_h=tape_half_h)
    px_eighth, _tape_span = detect_tape_px_per_eighth_in(bgr, y, level, tape_half_h=tape_half_h)

    edge_source = "body_mask"
    edges: tuple[int, int] | None = None
    if body_mask is not None and body_mask.shape[:2] == (h, w):
        edges = _row_torso_edges(body_mask[y])
    if edges is None:
        edges = _tape_gap_inner_edges(col)
        if edges:
            edge_source = "tape_gap"
    if edges is None:
        edges = _tape_wing_inner_edges(col)
        if edges:
            edge_source = "tape_wings"
    if edges is None:
        return None

    xl, xr = edges
    width_px = xr - xl
    if width_px < 8:
        return None

    warnings: list[str] = []
    scale_source = "tape_ticks"
    width_cm: float | None = None
    width_in: float | None = None

    if calibration is not None and calibration.H_px_to_mm is not None:
        pts = calibration.px_to_mm(
            np.array([[xl, y], [xr, y]], dtype=np.float64)
        )
        width_cm = round(abs(float(pts[1, 0] - pts[0, 0])) / 10.0, 2)
        width_in = round(width_cm / 2.54, 2)
        scale_source = "charuco_homography"
    elif mm_per_px and mm_per_px > 0:
        width_cm = round(width_px * mm_per_px / 10.0, 2)
        width_in = round(width_cm / 2.54, 2)
        scale_source = "charuco_mm_per_px"
    elif px_eighth and px_eighth > 0:
        width_in = round(width_px / (8.0 * px_eighth), 2)
        width_cm = round(width_in * 2.54, 2)
        scale_source = "tape_ticks"
    else:
        return None

    if px_eighth and px_eighth > 0 and scale_source != "tape_ticks":
        tick_in = width_px / (8.0 * px_eighth)
        if abs(tick_in - width_in) > max(1.5, 0.15 * width_in):
            warnings.append(
                f"tape_scale_mismatch:tick={tick_in:.1f}in vs {scale_source}={width_in:.1f}in"
            )

    return BandWidthResult(
        level=level,
        y_px=y,
        left_x=xl,
        right_x=xr,
        width_cm=width_cm,
        width_in=width_in,
        px_per_eighth_in=px_eighth,
        scale_source=scale_source,
        edge_source=edge_source,
        warnings=warnings,
    )


def measure_front_widths_from_bands(
    bgr: np.ndarray,
    band_rows: dict[str, int] | None = None,
    body_mask: np.ndarray | None = None,
    mm_per_px: float | None = None,
    calibration: CalibrationResult | None = None,
    min_span_frac: float = 0.08,
) -> dict[str, BandWidthResult]:
    """
    Extract front-panel widths at all detected coloured measuring bands.

    ``band_rows`` defaults to ``detect_stencil_measurement_lines`` on ``bgr``.
    """
    rows = band_rows or detect_stencil_measurement_lines(bgr, min_span_frac=min_span_frac)
    out: dict[str, BandWidthResult] = {}
    for level, y in rows.items():
        hit = measure_band_width_at_row(
            bgr,
            y,
            level,
            body_mask=body_mask,
            mm_per_px=mm_per_px,
            calibration=calibration,
        )
        if hit:
            out[level] = hit
    return out


def _rows_to_mm(
    rows: dict[str, int],
    px_per_mm: float,
    origin_y_mm: float = 0.0,
) -> dict[str, float]:
    return {lv: origin_y_mm + y / px_per_mm for lv, y in rows.items()}


def upgrade_stencil_with_charuco(spec: DSVStencilSpec) -> PanelAssets:
    """
    Load the production DSV stencil, erase legacy F0/F1 ArUco markers, and
    paste ChArUco boards in their place. Measurement-line geometry is recorded
    in panel-mm coordinates.
    """
    img = _load_stencil_bgr(spec.stencil_path)
    h_px, w_px = img.shape[:2]
    panel_h_mm = spec.panel_h_mm or (spec.panel_w_mm * h_px / w_px)
    px_per_mm = _px_per_mm_from_stencil(img, spec.panel_w_mm)

    legacy = _detect_legacy_aruco_slots(img, spec)
    canvas = img.copy()
    slot_meta: dict[str, Any] = {}

    for slot in spec.slots:
        hit = legacy[slot.name]
        cx, cy = hit["center_px"]
        slot.center_px = (cx, cy)
        slot.center_x_mm = cx / px_per_mm
        slot.center_y_mm = cy / px_per_mm
        slot.legacy_side_px = hit["side_px"]

        _erase_square_patch(canvas, (cx, cy), hit["side_px"])
        board_bgr, bw_mm, bh_mm = _render_slot_charuco_bgr(slot, px_per_mm)
        bbox = _paste_centered(canvas, board_bgr, (cx, cy))
        slot_meta[slot.name] = {
            "legacy": {k: v for k, v in hit.items() if k != "center_px"},
            "legacy_center_px": [round(cx, 1), round(cy, 1)],
            "center_mm": [round(slot.center_x_mm, 2), round(slot.center_y_mm, 2)],
            "board_mm": [round(bw_mm, 2), round(bh_mm, 2)],
            "paste_bbox_px": list(bbox),
            "charuco": asdict(slot),
        }
        cv2.putText(
            canvas,
            slot.name,
            (bbox[0], max(14, bbox[1] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )

    line_rows = detect_stencil_measurement_lines(canvas)
    line_mm = _rows_to_mm(line_rows, px_per_mm)

    meta = {
        "kind": "dsv_stencil_front_panel",
        "spec": {
            "stencil_path": str(spec.stencil_path),
            "panel_w_mm": spec.panel_w_mm,
            "panel_h_mm": panel_h_mm,
            "grid_mm": spec.grid_mm,
            "shoulder_y_mm": spec.shoulder_y_mm,
            "px_per_mm_render": px_per_mm,
        },
        "charuco_slots": slot_meta,
        "measurement_lines_px": line_rows,
        "measurement_lines_mm": {k: round(v, 2) for k, v in line_mm.items()},
        "landmark_from_floor": LANDMARK_FROM_FLOOR,
        "print_note": (
            f"Print at 100% scale so the stencil grid width = {spec.panel_w_mm:.0f} mm. "
            "Align SHL-L / SHL-R with the wearer's shoulder line."
        ),
        "capture_note": (
            "Front/back/side photos with the vest worn. ChArUco F0+F1 give per-panel "
            "homography; coloured lines give bust/underbust/waist/hip row anchors."
        ),
    }
    return PanelAssets(spec=spec, image_bgr=canvas, spec_json=meta)


def calibrate_stencil_charuco_roi(
    img_bgr: np.ndarray,
    slot: CharucoSlotSpec,
    px_per_mm: float,
    roi_pad_mm: float = 25.0,
) -> CalibrationResult:
    """Detect one ChArUco board in a padded ROI (safe when F0 and F1 share a photo)."""
    if slot.center_px is None:
        return CalibrationResult(None, None, 0, [], "none", ["slot_center_unknown"])
    cx, cy = slot.center_px
    pad_px = _mm_to_px(roi_pad_mm, px_per_mm)
    h, w = img_bgr.shape[:2]
    x0 = max(0, int(cx - pad_px))
    y0 = max(0, int(cy - pad_px))
    x1 = min(w, int(cx + pad_px))
    y1 = min(h, int(cy + pad_px))
    roi = img_bgr[y0:y1, x0:x1]

    dictionary = _dictionary(slot.dict_name)
    board = cv2.aruco.CharucoBoard(
        (slot.cols, slot.rows),
        slot.square_mm / 1000.0,
        slot.marker_mm / 1000.0,
        dictionary,
    )
    detector = cv2.aruco.CharucoDetector(board, detectorParams=cv2.aruco.DetectorParameters())
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    charuco_corners, charuco_ids, _, marker_ids = detector.detectBoard(gray)

    warnings: list[str] = []
    n = 0 if charuco_corners is None else len(charuco_corners)
    ids_list: list[int] = []
    if marker_ids is not None:
        ids_list = [int(i) for i in marker_ids.flatten()]
    if n < 4:
        warnings.append(f"{slot.name}:only_{n}_corners")
        return CalibrationResult(None, None, n, ids_list, "none", warnings)

    obj_pts = board.getChessboardCorners()[charuco_ids.flatten()]
    origin_x = (slot.center_x_mm or 0.0) - (slot.cols * slot.square_mm) / 2.0
    origin_y = (slot.center_y_mm or 0.0) - (slot.rows * slot.square_mm) / 2.0
    obj_mm = np.zeros((len(obj_pts), 2), dtype=np.float64)
    obj_mm[:, 0] = origin_x + obj_pts[:, 0] * 1000.0
    obj_mm[:, 1] = origin_y + obj_pts[:, 1] * 1000.0
    img_pts = charuco_corners.reshape(-1, 2).astype(np.float64)
    img_pts[:, 0] += x0
    img_pts[:, 1] += y0

    H, _ = cv2.findHomography(img_pts, obj_mm, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if H is None:
        warnings.append(f"{slot.name}:homography_failed")
        return CalibrationResult(None, None, n, ids_list, "none", warnings)

    cx_roi = float(np.mean(img_pts[:, 0]))
    cy_roi = float(np.mean(img_pts[:, 1]))
    mm_per_px = _mm_per_px_from_homography(H, cx_roi, cy_roi)
    return CalibrationResult(mm_per_px, H, n, ids_list, f"{slot.name}_charuco", warnings)


def _mm_per_px_from_homography(H: np.ndarray, cx: float, cy: float) -> float:
    """Local mm/px from a px→mm homography (mean of x- and y-axis unit steps)."""
    pts = np.array([[cx, cy], [cx + 1.0, cy], [cx, cy + 1.0]], dtype=np.float64)
    hom = np.hstack([pts, np.ones((3, 1), dtype=np.float64)])
    mm = (H @ hom.T).T
    mm_xy = mm[:, :2] / mm[:, 2:3]
    scale_x = float(np.linalg.norm(mm_xy[1] - mm_xy[0]))
    scale_y = float(np.linalg.norm(mm_xy[2] - mm_xy[0]))
    return (scale_x + scale_y) / 2.0


@dataclass
class CharucoRectifySpec:
    """Settings for perspective-flattening a tilted / curved DSV photo region."""

    px_per_mm: float = 3.0  # output canvas resolution
    margin_mm: float = 50.0  # pad around the detected board in the output
    upscale_for_detect: float = 3.0  # detect on upscaled image, warp original
    detect_pad_mm: float = 85.0
    fill_bgr: tuple[int, int, int] = (245, 245, 240)
    preprocess_clahe: bool = False


@dataclass
class RectifiedView:
    """A perspective-corrected crop where the ChArUco board is axis-aligned."""

    image_bgr: np.ndarray
    calibration: CalibrationResult
    slot_name: str
    slot_center_px: tuple[float, float]
    board_mm: tuple[float, float]
    mm_per_px_out: float
    H_img_to_mm: np.ndarray
    warnings: list[str] = field(default_factory=list)


def preprocess_for_charuco_detect(
    img_bgr: np.ndarray,
    upscale: float = 1.0,
    clahe: bool = True,
) -> np.ndarray:
    """
    Mild denoise + contrast boost before ChArUco detection.

    Does not modify geometry — safe to use only for finding corners, then map
    homography back to the original-resolution image for rectification.
    """
    out = img_bgr
    if upscale > 1.0:
        out = cv2.resize(out, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LANCZOS4)
    if clahe:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return cv2.bilateralFilter(out, d=5, sigmaColor=40, sigmaSpace=40)


def find_charuco_slot_in_image(
    img_bgr: np.ndarray,
    slot: CharucoSlotSpec,
    px_per_mm_hint: float | None = None,
    spec: CharucoRectifySpec | None = None,
    center_fracs: list[tuple[float, float]] | None = None,
) -> tuple[CalibrationResult, tuple[float, float], float]:
    """
    Auto-locate one ChArUco board and return calibration on the **native** image.

    Returns ``(calibration, center_px_native, detect_upscale)``.
    """
    spec = spec or CharucoRectifySpec()
    h, w = img_bgr.shape[:2]
    ppm_hint = px_per_mm_hint or (h / 900.0)

    if center_fracs is None:
        center_fracs = []
        defaults = {
            "F0": [(0.52, 0.30), (0.50, 0.28)],
            "F1": [(0.50, 0.58), (0.50, 0.55)],
            "F2": [(0.35, 0.30), (0.38, 0.28)],
            "F3": [(0.65, 0.30), (0.62, 0.28)],
        }
        center_fracs.extend(defaults.get(slot.name, []))
        for cy in np.linspace(0.12, 0.72, 14):
            for cx in (0.5, 0.45, 0.55, 0.35, 0.65, 0.4, 0.6):
                center_fracs.append((float(cx), float(cy)))

    detect_scales = [3.0, 4.0, 2.0, 1.0]
    if spec.upscale_for_detect not in detect_scales:
        detect_scales.insert(0, max(1.0, spec.upscale_for_detect))

    best_n = 0
    best_cal: CalibrationResult | None = None
    best_center = (w * 0.5, h * 0.4)
    best_detect_scale = 1.0

    for detect_scale in detect_scales:
        for use_preprocess in (False, spec.preprocess_clahe):
            if use_preprocess and not spec.preprocess_clahe:
                continue
            detect_img = (
                preprocess_for_charuco_detect(img_bgr, detect_scale, True)
                if use_preprocess
                else (
                    cv2.resize(img_bgr, None, fx=detect_scale, fy=detect_scale, interpolation=cv2.INTER_LANCZOS4)
                    if detect_scale > 1.0
                    else img_bgr
                )
            )
            dh, dw = detect_img.shape[:2]
            ppm_detect = ppm_hint * detect_scale

            for cx_frac, cy_frac in center_fracs:
                slot_probe = CharucoSlotSpec(
                    name=slot.name,
                    cols=slot.cols,
                    rows=slot.rows,
                    square_mm=slot.square_mm,
                    marker_mm=slot.marker_mm,
                    dict_name=slot.dict_name,
                    legacy_aruco_id=slot.legacy_aruco_id,
                    center_px=(dw * cx_frac, dh * cy_frac),
                )
                cal = calibrate_stencil_charuco_roi(
                    detect_img, slot_probe, ppm_detect, roi_pad_mm=spec.detect_pad_mm
                )
                if cal.charuco_corners > best_n:
                    best_n = cal.charuco_corners
                    best_cal = cal
                    best_center = (w * cx_frac, h * cy_frac)
                    best_detect_scale = detect_scale

    if best_cal is None or best_n < 4 or best_cal.H_px_to_mm is None:
        return (
            CalibrationResult(None, None, best_n, [], "none", ["charuco_not_found"]),
            best_center,
            best_detect_scale,
        )

    # Map homography from detect-scale pixels → native image pixels.
    S_detect_to_native = np.array(
        [[1.0 / best_detect_scale, 0, 0], [0, 1.0 / best_detect_scale, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    # p_detect = detect_scale * p_native  →  H_native = H_detect @ diag(scale, scale, 1)
    S_native_to_detect = np.array(
        [[best_detect_scale, 0, 0], [0, best_detect_scale, 0], [0, 0, 1]],
        dtype=np.float64,
    )
    H_native = best_cal.H_px_to_mm @ S_native_to_detect
    mm_per_px_native = _mm_per_px_from_homography(H_native, best_center[0], best_center[1])
    cal_native = CalibrationResult(
        mm_per_px_native,
        H_native,
        best_n,
        best_cal.aruco_ids,
        best_cal.method,
        list(best_cal.warnings),
    )
    return cal_native, best_center, best_detect_scale


def _board_extent_mm(slot: CharucoSlotSpec, margin_mm: float) -> tuple[float, float, float, float]:
    """Return (x0, y0, x1, y1) panel-mm bounds for the board + margin."""
    board_w = slot.cols * slot.square_mm
    board_h = slot.rows * slot.square_mm
    cx = slot.center_x_mm or 0.0
    cy = slot.center_y_mm or 0.0
    return (
        cx - board_w / 2.0 - margin_mm,
        cy - board_h / 2.0 - margin_mm,
        cx + board_w / 2.0 + margin_mm,
        cy + board_h / 2.0 + margin_mm,
    )


def rectify_image_by_charuco(
    img_bgr: np.ndarray,
    calibration: CalibrationResult,
    slot: CharucoSlotSpec,
    spec: CharucoRectifySpec | None = None,
    panel_mm_bounds: tuple[float, float, float, float] | None = None,
) -> RectifiedView:
    """
    Perspective-flatten a tilted photo using a ChArUco homography.

    The output image is a fronto-parallel view: the board appears square and
    axis-aligned, and distances in the output are proportional to real mm
    (``mm_per_px_out = 1 / spec.px_per_mm``).

    Use this to undo camera tilt and mild fabric skew around a detected marker
    before width / band measurements.
    """
    spec = spec or CharucoRectifySpec()
    warnings: list[str] = []
    H = calibration.H_px_to_mm
    if H is None or calibration.charuco_corners < 4:
        raise ValueError("calibration has no usable homography (need >=4 ChArUco corners)")

    if panel_mm_bounds is None:
        x0, y0, x1, y1 = _board_extent_mm(slot, spec.margin_mm)
    else:
        x0, y0, x1, y1 = panel_mm_bounds

    ppm = spec.px_per_mm
    out_w = max(8, _mm_to_px(x1 - x0, ppm))
    out_h = max(8, _mm_to_px(y1 - y0, ppm))

    # img_px -> mm via H, then mm -> out_px with origin at (x0, y0).
    T = np.array(
        [[ppm, 0, -x0 * ppm], [0, ppm, -y0 * ppm], [0, 0, 1]],
        dtype=np.float64,
    )
    M_img_to_out = T @ H
    M_out_to_img = np.linalg.inv(M_img_to_out)

    rectified = cv2.warpPerspective(
        img_bgr,
        M_out_to_img,
        (out_w, out_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=spec.fill_bgr,
    )

    board_w = slot.cols * slot.square_mm
    board_h = slot.rows * slot.square_mm
    return RectifiedView(
        image_bgr=rectified,
        calibration=calibration,
        slot_name=slot.name,
        slot_center_px=slot.center_px or (0.0, 0.0),
        board_mm=(board_w, board_h),
        mm_per_px_out=1.0 / ppm,
        H_img_to_mm=H,
        warnings=warnings,
    )


def rectify_panel_between_slots(
    img_bgr: np.ndarray,
    slot_top: CharucoSlotSpec,
    cal_top: CalibrationResult,
    slot_bottom: CharucoSlotSpec,
    cal_bottom: CalibrationResult,
    spec: CharucoRectifySpec | None = None,
    side_margin_mm: float = 120.0,
) -> RectifiedView:
    """
    Flatten the torso strip between two decoded markers (e.g. F0 + F1).

    Interpolates scale between the upper and lower homographies row-by-row so
    the output accounts for perspective change down the panel.
    """
    spec = spec or CharucoRectifySpec()
    if cal_top.H_px_to_mm is None or cal_bottom.H_px_to_mm is None:
        raise ValueError("both slots need valid homographies")

    # Panel-mm column span from both boards.
    boards = (slot_top, slot_bottom)
    cals = (cal_top, cal_bottom)
    x_vals: list[float] = []
    y_vals: list[float] = []
    for slot, _cal in zip(boards, cals):
        bw = slot.cols * slot.square_mm
        bh = slot.rows * slot.square_mm
        cx = slot.center_x_mm or 0.0
        cy = slot.center_y_mm or 0.0
        x_vals.extend([cx - bw / 2, cx + bw / 2])
        y_vals.extend([cy - bh / 2, cy + bh / 2])

    x0 = min(x_vals) - side_margin_mm
    x1 = max(x_vals) + side_margin_mm
    y0 = min(y_vals) - spec.margin_mm
    y1 = max(y_vals) + spec.margin_mm

    ppm = spec.px_per_mm
    out_w = max(8, _mm_to_px(x1 - x0, ppm))
    out_h = max(8, _mm_to_px(y1 - y0, ppm))
    rectified = np.full((out_h, out_w, 3), spec.fill_bgr, np.uint8)

    y_top_mm = slot_top.center_y_mm or 0.0
    y_bot_mm = slot_bottom.center_y_mm or 0.0
    denom = max(1e-6, y_bot_mm - y_top_mm)

    for out_y in range(out_h):
        mm_y = y0 + out_y / ppm
        t = float(np.clip((mm_y - y_top_mm) / denom, 0.0, 1.0))
        H = (1.0 - t) * cal_top.H_px_to_mm + t * cal_bottom.H_px_to_mm
        T = np.array(
            [[ppm, 0, -x0 * ppm], [0, 1, -y0 * ppm], [0, 0, 1]],
            dtype=np.float64,
        )
        M_out_to_img = np.linalg.inv(T @ H)
        src_y = np.full((out_w, 1), out_y, dtype=np.float32)
        src_x = np.arange(out_w, dtype=np.float32).reshape(-1, 1)
        src = np.concatenate([src_x, src_y], axis=1).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(src, M_out_to_img).reshape(-1, 2)
        xs = np.round(dst[:, 0]).astype(np.int32)
        ys = np.round(dst[:, 1]).astype(np.int32)
        for out_x in range(out_w):
            x, y = int(xs[out_x]), int(ys[out_x])
            if 0 <= x < img_bgr.shape[1] and 0 <= y < img_bgr.shape[0]:
                rectified[out_y, out_x] = img_bgr[y, x]

    merged_corners = cal_top.charuco_corners + cal_bottom.charuco_corners
    mm_vals = [v for v in (cal_top.mm_per_px, cal_bottom.mm_per_px) if v]
    cal_merged = CalibrationResult(
        float(np.median(mm_vals)) if mm_vals else None,
        cal_top.H_px_to_mm,
        merged_corners,
        cal_top.aruco_ids + cal_bottom.aruco_ids,
        f"{slot_top.name}+{slot_bottom.name}_blend",
    )
    return RectifiedView(
        image_bgr=rectified,
        calibration=cal_merged,
        slot_name=f"{slot_top.name}+{slot_bottom.name}",
        slot_center_px=(0.0, 0.0),
        board_mm=(x1 - x0, y1 - y0),
        mm_per_px_out=1.0 / ppm,
        H_img_to_mm=cal_top.H_px_to_mm,
        warnings=["row_blend_homography"],
    )


def auto_rectify_dsv_photo(
    img_bgr: np.ndarray,
    slot_name: str,
    stencil_spec_path: Path | None = None,
    spec: CharucoRectifySpec | None = None,
    center_fracs: list[tuple[float, float]] | None = None,
) -> RectifiedView:
    """
    One-shot: find a DSV ChArUco sticker (F0–F3) and return a flattened view.

    Example::

        view = auto_rectify_dsv_photo(front_bgr, \"F1\")
        cv2.imwrite(\"front_F1_flat.png\", view.image_bgr)
    """
    spec = spec or CharucoRectifySpec()
    slots = default_dsv_marker_slots(stencil_spec_path)
    if slot_name not in slots:
        raise KeyError(f"unknown slot {slot_name!r}")
    slot = slots[slot_name]

    cal, center_px, _ = find_charuco_slot_in_image(
        img_bgr, slot, spec=spec, center_fracs=center_fracs
    )
    slot.center_px = center_px
    if cal.H_px_to_mm is None:
        raise ValueError(
            f"{slot_name}: only {cal.charuco_corners} corners — need >=4 for rectification"
        )

    # Estimate slot centre in panel-mm from the homography.
    cx, cy = center_px
    pt_mm = cal.px_to_mm(np.array([[cx, cy]], dtype=np.float64))[0]
    slot.center_x_mm = float(pt_mm[0])
    slot.center_y_mm = float(pt_mm[1])

    return rectify_image_by_charuco(img_bgr, cal, slot, spec)


def analyze_stencil_photo(
    img_bgr: np.ndarray,
    assets: PanelAssets,
    silhouette_bottom_px: int | None = None,
) -> dict[str, Any]:
    """
    Decode a photo of the upgraded stencil (flat or worn).

    Merges both ChArUco ROIs, stencil measurement-line rows, and optional height.
    """
    if not isinstance(assets.spec, DSVStencilSpec):
        raise TypeError("assets.spec must be DSVStencilSpec")
    spec: DSVStencilSpec = assets.spec
    px_per_mm = assets.spec_json["spec"]["px_per_mm_render"]

    calibs: dict[str, CalibrationResult] = {}
    for slot in spec.slots:
        calibs[slot.name] = calibrate_stencil_charuco_roi(img_bgr, slot, px_per_mm)

    mm_vals = [c.mm_per_px for c in calibs.values() if c.mm_per_px]
    mm_per_px = float(np.median(mm_vals)) if mm_vals else None

    lines_px = detect_stencil_measurement_lines(img_bgr, min_span_frac=0.18)
    lines_mm = _rows_to_mm(lines_px, px_per_mm)

    shoulder_y_px = _mm_to_px(spec.shoulder_y_mm, px_per_mm)
    bottom = silhouette_bottom_px if silhouette_bottom_px is not None else img_bgr.shape[0] - 1
    height_cm = None
    if mm_per_px:
        below_shoulder_mm = max(0.0, (bottom - shoulder_y_px) * mm_per_px)
        if below_shoulder_mm >= 50.0:
            height_cm = round(
                below_shoulder_mm / (LANDMARK_FROM_FLOOR["shoulder"] * 10.0), 1
            )

    def _summarize(c: CalibrationResult) -> dict[str, Any]:
        return {
            "mm_per_px": c.mm_per_px,
            "charuco_corners": c.charuco_corners,
            "aruco_ids": c.aruco_ids,
            "method": c.method,
            "warnings": c.warnings,
        }

    return {
        "mm_per_px": mm_per_px,
        "calibrations": {k: _summarize(v) for k, v in calibs.items()},
        "measurement_lines_px": lines_px,
        "measurement_lines_mm": lines_mm,
        "inferred_height_cm": height_cm,
        "warnings": [w for c in calibs.values() for w in c.warnings],
    }


def save_assets(
    assets: PanelAssets,
    out_dir: Path,
    basename: str = "dsv_vest_panel",
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    png = out_dir / f"{basename}.png"
    cv2.imwrite(str(png), assets.image_bgr)
    paths.append(png)
    json_path = out_dir / f"{basename}_spec.json"
    json_path.write_text(json.dumps(assets.spec_json, indent=2), encoding="utf-8")
    paths.append(json_path)
    assets.output_paths = paths
    return paths


# ---------------------------------------------------------------------------
# PDF spec (swaya_charuco_functionalities.pdf) — print master for 45 GSM DSV
# ---------------------------------------------------------------------------

PDF_PANEL_W_MM = 1000.0   # 100 cm
PDF_PANEL_H_MM = 1500.0   # 150 cm
PDF_GRID_MM = 50.0        # 5 cm squares
PDF_MARKER_MM = 60.0      # 6 cm (PDF table); ChArUco board fits this footprint
PDF_MARKER_COORDS: dict[str, tuple[float, float]] = {
    # PDF grid coords interpreted as (x%, y%) of panel
    "F0": (0.47, 0.17),
    "F1": (0.47, 0.60),
    "F2": (0.47, 0.18),
    "F3": (0.47, 0.60),
}
PDF_DICT = "DICT_4X4_50"


@dataclass
class DSVPrintSpec:
    """High-resolution print master aligned to swaya_charuco_functionalities.pdf."""

    panel_w_mm: float = PDF_PANEL_W_MM
    panel_h_mm: float = PDF_PANEL_H_MM
    grid_mm: float = PDF_GRID_MM
    dpi: float = 300.0  # PDF minimum 600; 300 default keeps file < ~200 MB
    gsm: int = 45
    stencil_path: Path | None = None
    charuco_stencil_path: Path | None = None  # upgraded PNG with F0/F1 (preferred)
    render_mode: str = "vector"  # "vector" = crisp redraw; "raster" = upscale stencil bitmap
    use_charuco: bool = True  # PDF lists 6 cm ArUco; we ship ChArUco upgrade
    charuco_cols: int = 5
    charuco_rows: int = 5
    charuco_square_mm: float = 12.0
    charuco_marker_mm: float = 9.0

    @property
    def px_per_mm(self) -> float:
        return self.dpi / 25.4


def pdf_coverage_audit() -> dict[str, Any]:
    """
    Map PDF functions (01–34) to current codebase implementation status.
    """
    items = [
        ("01", "Scale calibration (px/cm)", "partial", "charuco_dsv_lib calibrate_stencil_charuco_roi; dsv_probe_lib calibrate_scale"),
        ("02", "Perspective correction", "partial", "auto_rectify_dsv_photo / rectify_image_by_charuco; not wired in probe"),
        ("03", "Camera distance estimation", "missing", "needs focal length + solvePnP"),
        ("04", "Panel identification (F0–F3)", "partial", "view routing only; no F2/F3 back detection"),
        ("05", "Panel orientation", "missing", "marker corner order check not implemented"),
        ("06", "Photo quality validation", "partial", "probe warnings; no unified pass/fail gate"),
        ("07", "Linear distance", "partial", "dsv_probe_lib line measures"),
        ("08", "Circumference", "partial", "markerless + probe ellipse girth"),
        ("09", "Shoulder length", "partial", "dsv_probe_lib compute_shoulder_measurements"),
        ("10", "Body width at arbitrary height", "partial", "slice sweep in markerless"),
        ("11", "Body proportions / ratios", "partial", "body_profile.py torso_fracs"),
        ("12", "Shoulder slope angle", "partial", "ShoulderMeasure.shoulder_slope_deg_l/r"),
        ("13", "Body symmetry", "missing", "not implemented"),
        ("14", "Silhouette extraction", "yes", "MediaPipe in dsv_probe_lib / markerless"),
        ("15", "Posture detection", "missing", "grid deformation analysis not implemented"),
        ("16", "Side body curvature", "partial", "side depth in probe"),
        ("17", "Bust projection (side)", "missing", "not implemented"),
        ("18", "DSV wear validation", "missing", "not implemented"),
        ("19", "Velcro position detection", "missing", "not implemented"),
        ("20", "Fabric drape quality", "missing", "not implemented"),
        ("21", "Landmark sticker verification", "missing", "SHL-L/R vs marker check not implemented"),
        ("22", "Customer vs CV comparison", "partial", "calibration.py tape anchors"),
        ("23", "Front-back consistency", "missing", "not implemented"),
        ("24", "Multi-photo consistency", "missing", "not implemented"),
        ("25", "Photo sequence verification", "partial", "manual front/back/side in probe"),
        ("26", "Required photo coverage", "partial", "API expects views; no completeness dict"),
        ("27", "Marker occlusion (redundant F0+F1)", "partial", "two slots; ROI detect only"),
        ("28", "Partial 3D reconstruction", "partial", "SMPL / 4D-Humans mesh path"),
        ("29", "Virtual garment overlay", "missing", "not implemented"),
        ("30", "Long-term tracking", "missing", "not implemented"),
        ("31", "Authenticity verification", "missing", "F0–F3 ID check not enforced"),
        ("32", "Print QC (manufacturing)", "partial", "notebook validation cells"),
        ("33", "Batch tracking (IDs 4–49)", "missing", "not implemented"),
        ("34", "Customer session logging", "yes", "API scans + MongoDB"),
    ]
    phase1 = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "14", "25", "26", "27", "32", "34"}
    counts = {"yes": 0, "partial": 0, "missing": 0}
    for _, _, status, _ in items:
        counts[status] = counts.get(status, 0) + 1
    p1_ok = sum(1 for fid, _, st, _ in items if fid in phase1 and st == "yes")
    p1_partial = sum(1 for fid, _, st, _ in items if fid in phase1 and st == "partial")
    return {
        "source_pdf": "assets/swaya_charuco_functionalities.pdf",
        "functions": [
            {"id": fid, "name": name, "status": st, "notes": note}
            for fid, name, st, note in items
        ],
        "summary": counts,
        "phase1_launch": {
            "total": len(phase1),
            "yes": p1_ok,
            "partial": p1_partial,
            "missing": len(phase1) - p1_ok - p1_partial,
            "launch_ready": p1_ok >= 8,
        },
        "pdf_config_gaps": [
            "Panel size PDF 100×150 cm vs stencil upgrade 34 cm wide (scale-up now in DSVPrintSpec)",
            "PDF 6 cm ArUco F0–F3 vs ChArUco 5×5 boards (upgrade path; panel ID uses board ROI)",
            "Back panel F2/F3 not in stencil art — generated programmatically",
            "Print 600 DPI — export defaults 300 DPI (set DSVPrintSpec.dpi=600 for print house)",
            "Grid 5 cm PDF vs 5 mm in early stencil spec — print master uses 5 cm",
        ],
    }


def _resolve_stencil_cut_source(
    charuco_meta: dict[str, Any],
    charuco_png: Path | None,
) -> np.ndarray:
    """Prefer the production stencil JPEG for cut-line artwork (unchanged geometry)."""
    raw = charuco_meta.get("spec", {}).get("stencil_path")
    if raw:
        src = Path(str(raw))
        if src.is_file():
            return _load_stencil_bgr(src)
    if charuco_png and Path(charuco_png).is_file():
        return _load_stencil_bgr(charuco_png)
    raise FileNotFoundError("no stencil source for cut-line overlay")


CUT_LINE_BGR = STENCIL_TAPE_COLORS_BGR["bust"]


def _filter_band_like_blobs(mask: np.ndarray) -> np.ndarray:
    """Drop wide horizontal blobs (old tape bands / end labels), keep thin cut guides."""
    h, w = mask.shape[:2]
    out = mask.copy()
    n, labels, stats, _ = cv2.connectedComponentsWithStats(out, connectivity=8)
    for i in range(1, n):
        cw = int(stats[i, cv2.CC_STAT_WIDTH])
        ch = int(stats[i, cv2.CC_STAT_HEIGHT])
        if cw > max(40, int(0.32 * w)) and ch < max(12, int(0.05 * h)):
            out[labels == i] = 0
        if cw > max(60, int(0.55 * w)):
            out[labels == i] = 0
    return out


def _build_cut_art_mask_native(
    stencil_bgr: np.ndarray,
    charuco_meta: dict[str, Any],
    side: str = "front",
) -> np.ndarray:
    """Binary mask of dashed cut guides at stencil resolution (excludes measurement bands)."""
    h, w = stencil_bgr.shape[:2]
    hsv = cv2.cvtColor(stencil_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([148, 55, 110], np.uint8), np.array([172, 255, 255], np.uint8))
    mask = _filter_band_like_blobs(mask)

    mask[: max(20, int(0.075 * h)), :] = 0

    band_half = max(18, int(0.028 * h))
    for row in charuco_meta.get("measurement_lines_px", {}).values():
        y = int(row)
        mask[max(0, y - band_half) : min(h, y + band_half), :] = 0

    for slot in charuco_meta.get("charuco_slots", {}).values():
        bbox = slot.get("paste_bbox_px")
        if bbox and len(bbox) == 4:
            x0, y0, x1, y1 = [int(v) for v in bbox]
            pad = max(8, int(0.012 * w))
            mask[max(0, y0 - pad) : min(h, y1 + pad), max(0, x0 - pad) : min(w, x1 + pad)] = 0

    rows = list(charuco_meta.get("measurement_lines_px", {}).values())
    first_band = min(rows) if rows else int(0.40 * h)
    cut_bottom = max(int(0.34 * h), first_band - max(30, int(0.04 * h)))
    keep = np.zeros_like(mask)
    keep[:cut_bottom, :] = 255
    keep[int(0.05 * h) : int(0.33 * h), : int(0.24 * w)] = 255
    keep[int(0.05 * h) : int(0.33 * h), int(0.76 * w) :] = 255
    mask[keep == 0] = 0

    if side == "back":
        neck_mask = np.zeros((h, w), np.uint8)
        pts = np.array(
            [
                [int(0.30 * w), 0],
                [int(0.70 * w), 0],
                [int(0.56 * w), int(0.16 * h)],
                [int(0.44 * w), int(0.16 * h)],
            ],
            np.int32,
        )
        cv2.fillPoly(neck_mask, [pts], 255)
        mask[neck_mask > 0] = 0
        side_w = int(0.24 * w)
        mask[int(0.06 * h) : int(0.34 * h), :side_w] = 0
        mask[int(0.06 * h) : int(0.34 * h), w - side_w :] = 0

    return mask


def _scale_binary_mask_to_panel(
    mask: np.ndarray,
    panel_w_mm: float,
    panel_h_mm: float,
    px_per_mm: float,
) -> np.ndarray:
    """Scale a stencil-resolution mask to the print panel (nearest-neighbour)."""
    tw = _mm_to_px(panel_w_mm, px_per_mm)
    th = _mm_to_px(panel_h_mm, px_per_mm)
    sh, sw = mask.shape[:2]
    scale = tw / sw
    interim = cv2.resize(mask, (tw, max(1, int(round(sh * scale)))), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((th, tw), np.uint8)
    ih = interim.shape[0]
    if ih >= th:
        y0 = (ih - th) // 2
        canvas[:] = interim[y0 : y0 + th]
    else:
        y0 = (th - ih) // 2
        canvas[y0 : y0 + ih] = interim
    return canvas


def _overlay_stencil_cut_art(
    canvas: np.ndarray,
    stencil_bgr: np.ndarray,
    charuco_meta: dict[str, Any],
    panel_w_mm: float,
    panel_h_mm: float,
    px_per_mm: float,
    side: str = "front",
) -> None:
    """Paint cut guides from a strict stencil mask (solid colour, no JPEG bleed)."""
    mask_native = _build_cut_art_mask_native(stencil_bgr, charuco_meta, side=side)
    mask = _scale_binary_mask_to_panel(mask_native, panel_w_mm, panel_h_mm, px_per_mm)
    h, w = canvas.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    geom = _scaled_stencil_geometry(charuco_meta, panel_w_mm, panel_h_mm)
    band_half_px = max(14, _mm_to_px(TAPE_HEIGHT_MM * 2.0, px_per_mm))
    for y_mm in geom["measurement_lines_mm"].values():
        y = _mm_to_px(y_mm, px_per_mm)
        mask[max(0, y - band_half_px) : min(h, y + band_half_px), :] = 0

    dilate = max(1, _stroke_px(px_per_mm, 0.12))
    if dilate > 1:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate, dilate))
        mask = cv2.dilate(mask, k, iterations=1)

    canvas[mask > 0] = CUT_LINE_BGR


def _scale_stencil_to_panel(
    stencil_bgr: np.ndarray,
    panel_w_mm: float,
    panel_h_mm: float,
    px_per_mm: float,
) -> np.ndarray:
    """Resize stencil art to PDF panel dimensions (width-locked, vertical fit)."""
    tw = _mm_to_px(panel_w_mm, px_per_mm)
    th = _mm_to_px(panel_h_mm, px_per_mm)
    sh, sw = stencil_bgr.shape[:2]
    scale = tw / sw
    interim = cv2.resize(stencil_bgr, (tw, max(1, int(round(sh * scale)))), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((th, tw, 3), 252, np.uint8)
    ih = interim.shape[0]
    if ih >= th:
        y0 = (ih - th) // 2
        canvas[:] = interim[y0 : y0 + th]
    else:
        y0 = (th - ih) // 2
        canvas[y0 : y0 + ih] = interim
    return canvas


def _draw_pdf_grid(canvas: np.ndarray, grid_mm: float, px_per_mm: float) -> None:
    """Overlay 5 cm grid (PDF spec) for print QC."""
    h, w = canvas.shape[:2]
    step = max(1, _mm_to_px(grid_mm, px_per_mm))
    color = (210, 210, 210)
    for x in range(0, w, step):
        cv2.line(canvas, (x, 0), (x, h - 1), color, 1, cv2.LINE_AA)
    for y in range(0, h, step):
        cv2.line(canvas, (0, y), (w - 1, y), color, 1, cv2.LINE_AA)


def _stroke_px(px_per_mm: float, mm: float = 0.3) -> int:
    return max(1, int(round(mm * px_per_mm)))


def _font_scale(px_per_mm: float, ref: float = 12.0) -> float:
    return max(0.4, px_per_mm / ref)


def _scaled_stencil_geometry(
    charuco_meta: dict[str, Any],
    panel_w_mm: float,
    panel_h_mm: float,
) -> dict[str, Any]:
    """Map stencil-mm geometry to the print panel size."""
    src = charuco_meta["spec"]
    src_h = float(src.get("panel_h_mm") or panel_h_mm)
    sx = panel_w_mm / float(src["panel_w_mm"])
    sy = panel_h_mm / src_h
    lines_mm = {
        k: round(float(v) * sy, 2)
        for k, v in charuco_meta.get("measurement_lines_mm", {}).items()
    }
    return {
        "sx": sx,
        "sy": sy,
        "grid_mm": float(src.get("grid_mm", 5.0)) * sx,
        "shoulder_y_mm": float(src.get("shoulder_y_mm", 42.0)) * sy,
        "measurement_lines_mm": lines_mm,
    }


def _draw_fine_grid(
    canvas: np.ndarray,
    panel_w_mm: float,
    panel_h_mm: float,
    grid_mm: float,
    px_per_mm: float,
    major_mm: float = 50.0,
    label_major: bool = True,
) -> None:
    """Crisp coordinate grid with major lines and optional cm labels."""
    h, w = canvas.shape[:2]
    fine = max(1, _mm_to_px(grid_mm, px_per_mm))
    major = max(fine, _mm_to_px(major_mm, px_per_mm))
    fine_color = (205, 205, 205)
    major_color = (125, 125, 125)
    fs = _font_scale(px_per_mm, 14.0)
    thick_fine = _stroke_px(px_per_mm, 0.15)
    thick_major = _stroke_px(px_per_mm, 0.28)

    for x in range(0, w, fine):
        color = major_color if x % major == 0 else fine_color
        thick = thick_major if x % major == 0 else thick_fine
        cv2.line(canvas, (x, 0), (x, h - 1), color, thick, cv2.LINE_AA)
    for y in range(0, h, fine):
        color = major_color if y % major == 0 else fine_color
        thick = thick_major if y % major == 0 else thick_fine
        cv2.line(canvas, (0, y), (w - 1, y), color, thick, cv2.LINE_AA)

    if not label_major:
        return
    for xmm in np.arange(0.0, panel_w_mm + 0.1, major_mm):
        for ymm in np.arange(0.0, panel_h_mm + 0.1, major_mm):
            x_px = _mm_to_px(xmm, px_per_mm)
            y_px = _mm_to_px(ymm, px_per_mm)
            if x_px >= w - 2 or y_px >= h - 14:
                continue
            label = f"{int(round(xmm / 10))},{int(round(ymm / 10))}"
            cv2.putText(
                canvas,
                label,
                (x_px + 2, y_px + max(10, int(9 * fs))),
                cv2.FONT_HERSHEY_SIMPLEX,
                fs * 0.42,
                (70, 70, 70),
                max(1, _stroke_px(px_per_mm, 0.12)),
                cv2.LINE_AA,
            )


def _draw_tape_label_box(
    canvas: np.ndarray,
    label: str,
    x_anchor: int,
    y_px: int,
    color: tuple[int, int, int],
    px_per_mm: float,
    align_left: bool,
    subtitle: str | None = None,
    transparent_bg: bool = False,
) -> None:
    fs = _font_scale(px_per_mm, 10.0)
    sub_fs = fs * 0.78
    thick = max(1, _stroke_px(px_per_mm, 0.14))
    lines = [label]
    if subtitle:
        lines.append(subtitle)
    sizes = [cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, fs if i == 0 else sub_fs, thick)[0] for i, line in enumerate(lines)]
    baselines = [
        cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, fs if i == 0 else sub_fs, thick)[1]
        for i, line in enumerate(lines)
    ]
    tw = max(s[0] for s in sizes)
    line_gap = max(2, _mm_to_px(0.6, px_per_mm))
    text_h = sum(s[1] for s in sizes) + line_gap * max(0, len(lines) - 1)
    baseline = max(baselines)
    pad_x = max(3, _mm_to_px(1.8, px_per_mm))
    pad_y = max(2, _mm_to_px(1.0, px_per_mm))
    box_w = tw + 2 * pad_x
    box_h = text_h + baseline + 2 * pad_y
    if align_left:
        x0, x1 = x_anchor, x_anchor + box_w
    else:
        x0, x1 = x_anchor - box_w, x_anchor
    y0 = y_px - box_h // 2
    y1 = y0 + box_h
    if not transparent_bg:
        cv2.rectangle(canvas, (x0, y0), (x1, y1), color, -1, cv2.LINE_AA)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (30, 30, 30), max(1, thick - 1), cv2.LINE_AA)
    ty = y0 + pad_y
    for i, line in enumerate(lines):
        line_fs = fs if i == 0 else sub_fs
        (_, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, line_fs, thick)
        ty += th
        cv2.putText(
            canvas,
            line,
            (x0 + pad_x, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            line_fs,
            (255, 255, 255),
            thick,
            cv2.LINE_AA,
        )
        ty += line_gap


def _draw_measurement_tape(
    canvas: np.ndarray,
    y_mm: float,
    level: str,
    panel_w_mm: float,
    px_per_mm: float,
) -> None:
    """Full-width coloured measuring tape (stencil colours) with inch ticks and labels."""
    color = STENCIL_TAPE_COLORS_BGR[level]
    label = STENCIL_TAPE_LABELS[level]
    height_sub = f'{_format_in_label(_mm_to_in(y_mm))}" from top'
    y_px = _mm_to_px(y_mm, px_per_mm)
    x0 = 0
    x1 = _mm_to_px(panel_w_mm, px_per_mm) - 1
    tape_h = max(12, _mm_to_px(TAPE_HEIGHT_MM, px_per_mm))
    band_y0 = y_px - tape_h // 2
    band_y1 = y_px + tape_h // 2

    cv2.rectangle(canvas, (x0, band_y0), (x1, band_y1), color, -1, cv2.LINE_AA)

    panel_w_in = panel_w_mm / MM_PER_IN
    tick_thick = max(1, _stroke_px(px_per_mm, 0.10))
    num_fs = _font_scale(px_per_mm, 12.0) * 0.78
    num_thick = max(1, _stroke_px(px_per_mm, 0.12))
    tick_top = band_y0
    num_baseline = band_y1 - max(3, _mm_to_px(1.2, px_per_mm))

    for inch_val in np.arange(0.0, panel_w_in + 0.001, TAPE_TICK_STEP_IN):
        xmm = inch_val * MM_PER_IN
        x = _mm_to_px(xmm, px_per_mm)
        tick_frac, show_number, is_major = _tape_tick_profile(inch_val)
        tick_len = max(2, int(tape_h * tick_frac * 0.82))
        tick_bot = min(band_y1 - 1, tick_top + tick_len)
        is_foot = show_number and int(round(inch_val)) > 0 and int(round(inch_val)) % 12 == 0
        tick_col = TAPE_FOOT_MARK_BGR if is_foot else (TAPE_TICK_MAJOR_BGR if is_major else TAPE_TICK_MINOR_BGR)
        cv2.line(canvas, (x, tick_top), (x, tick_bot), tick_col, tick_thick, cv2.LINE_AA)

        if show_number:
            num_txt = _format_in_label(inch_val)
            num_col = TAPE_FOOT_MARK_BGR if is_foot else TAPE_NUMBER_BGR
            (tw, _), _ = cv2.getTextSize(num_txt, cv2.FONT_HERSHEY_SIMPLEX, num_fs, num_thick)
            tx = max(x0 + 1, x - tw // 2)
            if tx + tw > x1:
                tx = x1 - tw
            cv2.putText(
                canvas,
                num_txt,
                (tx, num_baseline),
                cv2.FONT_HERSHEY_SIMPLEX,
                num_fs,
                num_col,
                num_thick,
                cv2.LINE_AA,
            )

    unit_fs = num_fs * 0.65
    (_, unit_th), _ = cv2.getTextSize("IN", cv2.FONT_HERSHEY_SIMPLEX, unit_fs, num_thick)
    cv2.putText(
        canvas,
        "IN",
        (x0 + max(3, _mm_to_px(1.0, px_per_mm)), num_baseline - max(2, unit_th // 3)),
        cv2.FONT_HERSHEY_SIMPLEX,
        unit_fs,
        TAPE_NUMBER_BGR,
        max(1, num_thick - 1),
        cv2.LINE_AA,
    )

    flag_w = max(_mm_to_px(24.0, px_per_mm), int(0.05 * (x1 - x0)))
    flag_h = max(_mm_to_px(9.0, px_per_mm), tape_h // 2)
    flag_y0 = band_y0 - flag_h
    cv2.rectangle(canvas, (x0, flag_y0), (x0 + flag_w, band_y0), color, -1, cv2.LINE_AA)
    cv2.rectangle(canvas, (x0, flag_y0), (x0 + flag_w, band_y0), (30, 30, 30), max(1, tick_thick), cv2.LINE_AA)
    _draw_tape_label_box(
        canvas,
        label,
        x0 + flag_w // 2,
        flag_y0 + flag_h // 2,
        color,
        px_per_mm,
        align_left=False,
        subtitle=height_sub,
        transparent_bg=True,
    )

    _draw_tape_label_box(canvas, label, x1, y_px, color, px_per_mm, align_left=False, subtitle=height_sub)


def _draw_dashed_line(
    canvas: np.ndarray,
    p0: tuple[int, int],
    p1: tuple[int, int],
    color: tuple[int, int, int],
    thick: int,
    dash_mm: float,
    px_per_mm: float,
) -> None:
    dash = max(4, _mm_to_px(dash_mm, px_per_mm))
    x0, y0 = p0
    x1, y1 = p1
    length = float(np.hypot(x1 - x0, y1 - y0))
    if length < 1:
        return
    dx, dy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    draw = True
    while pos < length:
        seg = min(dash, length - pos)
        sx = int(round(x0 + dx * pos))
        sy = int(round(y0 + dy * pos))
        ex = int(round(x0 + dx * (pos + seg)))
        ey = int(round(y0 + dy * (pos + seg)))
        if draw:
            cv2.line(canvas, (sx, sy), (ex, ey), color, thick, cv2.LINE_AA)
        pos += seg
        draw = not draw


def _draw_shoulder_marks(
    canvas: np.ndarray,
    shoulder_y_mm: float,
    panel_w_mm: float,
    px_per_mm: float,
) -> None:
    pink = (165, 54, 97)
    y_px = _mm_to_px(shoulder_y_mm, px_per_mm)
    thick = max(2, _stroke_px(px_per_mm, 0.35))
    fs = _font_scale(px_per_mm, 10.0)
    for frac, tag in ((0.15, "SHL-L"), (0.85, "SHL-R")):
        cx = _mm_to_px(panel_w_mm * frac, px_per_mm)
        radius = max(8, _mm_to_px(6.0, px_per_mm))
        cv2.circle(canvas, (cx, y_px), radius, pink, thick, cv2.LINE_AA)
        cv2.putText(
            canvas,
            tag,
            (cx - _mm_to_px(11.0, px_per_mm), y_px - radius - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            fs * 0.75,
            pink,
            max(1, thick - 1),
            cv2.LINE_AA,
        )


def _draw_front_neckline(canvas: np.ndarray, panel_w_mm: float, panel_h_mm: float, px_per_mm: float) -> None:
    pink = (165, 54, 97)
    thick = max(2, _stroke_px(px_per_mm, 0.35))
    fs = _font_scale(px_per_mm, 10.0)
    w_px = _mm_to_px(panel_w_mm, px_per_mm)
    top_y = _mm_to_px(panel_h_mm * 0.055, px_per_mm)
    bot_y = _mm_to_px(panel_h_mm * 0.13, px_per_mm)
    lx, rx = int(0.34 * w_px), int(0.66 * w_px)
    mx = w_px // 2
    _draw_dashed_line(canvas, (lx, top_y), (mx, bot_y), pink, thick, 4.0, px_per_mm)
    _draw_dashed_line(canvas, (rx, top_y), (mx, bot_y), pink, thick, 4.0, px_per_mm)
    cv2.putText(
        canvas,
        "CUT V-NECKLINE",
        (mx - _mm_to_px(22.0, px_per_mm), max(18, top_y - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs * 0.7,
        pink,
        max(1, thick - 1),
        cv2.LINE_AA,
    )


def _draw_armhole_guides(
    canvas: np.ndarray,
    shoulder_y_mm: float,
    panel_h_mm: float,
    px_per_mm: float,
) -> None:
    pink = (165, 54, 97)
    thick = max(2, _stroke_px(px_per_mm, 0.3))
    fs = _font_scale(px_per_mm, 10.0) * 0.65
    y0 = _mm_to_px(shoulder_y_mm, px_per_mm)
    y1 = _mm_to_px(panel_h_mm * 0.28, px_per_mm)
    for x in (0, canvas.shape[1] - 1):
        _draw_dashed_line(canvas, (x, y0), (x, y1), pink, thick, 5.0, px_per_mm)
        cv2.putText(canvas, "CUT", (x + (6 if x == 0 else -34), y0 + 18), cv2.FONT_HERSHEY_SIMPLEX, fs, pink, 1, cv2.LINE_AA)


def _draw_straight_back_neckline(canvas: np.ndarray, panel_w_mm: float, px_per_mm: float) -> None:
    pink = (165, 54, 97)
    neck_y = _mm_to_px(80.0 * panel_w_mm / PDF_PANEL_W_MM, px_per_mm)
    thick = max(2, _stroke_px(px_per_mm, 0.35))
    fs = _font_scale(px_per_mm, 10.0)
    x0 = _mm_to_px(panel_w_mm * 0.30, px_per_mm)
    x1 = _mm_to_px(panel_w_mm * 0.70, px_per_mm)
    cv2.line(canvas, (x0, neck_y), (x1, neck_y), pink, thick, cv2.LINE_AA)
    step = max(6, _mm_to_px(10.0, px_per_mm))
    for x in range(x0, x1, step):
        cv2.line(canvas, (x, neck_y - 6), (x, neck_y + 6), pink, max(1, thick - 1), cv2.LINE_AA)
    cv2.putText(
        canvas,
        "BACK NECKLINE",
        (x0, max(24, neck_y - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs * 0.75,
        pink,
        max(1, thick - 1),
        cv2.LINE_AA,
    )


def _render_vector_print_panel(
    panel_w_mm: float,
    panel_h_mm: float,
    px_per_mm: float,
    charuco_meta: dict[str, Any],
    side: str,
    cut_stencil_bgr: np.ndarray | None = None,
) -> np.ndarray:
    """Redraw the DSV panel at full print resolution (no bitmap upscale)."""
    w_px = _mm_to_px(panel_w_mm, px_per_mm)
    h_px = _mm_to_px(panel_h_mm, px_per_mm)
    canvas = np.full((h_px, w_px, 3), 252, np.uint8)
    geom = _scaled_stencil_geometry(charuco_meta, panel_w_mm, panel_h_mm)

    _draw_fine_grid(canvas, panel_w_mm, panel_h_mm, geom["grid_mm"], px_per_mm, major_mm=PDF_GRID_MM)

    if cut_stencil_bgr is not None:
        _overlay_stencil_cut_art(
            canvas, cut_stencil_bgr, charuco_meta, panel_w_mm, panel_h_mm, px_per_mm, side=side
        )

    for level in STENCIL_LEVELS:
        y_mm = geom["measurement_lines_mm"].get(level)
        if y_mm is not None:
            _draw_measurement_tape(canvas, y_mm, level, panel_w_mm, px_per_mm)

    if cut_stencil_bgr is None:
        if side == "front":
            _draw_shoulder_marks(canvas, geom["shoulder_y_mm"], panel_w_mm, px_per_mm)
            _draw_front_neckline(canvas, panel_w_mm, panel_h_mm, px_per_mm)
            _draw_armhole_guides(canvas, geom["shoulder_y_mm"], panel_h_mm, px_per_mm)
        else:
            _draw_shoulder_marks(canvas, geom["shoulder_y_mm"], panel_w_mm, px_per_mm)

    if side == "back":
        _draw_straight_back_neckline(canvas, panel_w_mm, px_per_mm)

    border = _stroke_px(px_per_mm, 0.25)
    cv2.rectangle(canvas, (0, 0), (w_px - 1, h_px - 1), (90, 90, 90), border, cv2.LINE_AA)
    return canvas


def _slot_at_pdf_coord(
    name: str,
    legacy_id: int,
    panel_w_mm: float,
    panel_h_mm: float,
    dict_name: str = PDF_DICT,
) -> CharucoSlotSpec:
    fx, fy = PDF_MARKER_COORDS[name]
    return CharucoSlotSpec(
        name=name,
        cols=5,
        rows=5,
        square_mm=12.0,
        marker_mm=9.0,
        dict_name=dict_name,
        legacy_aruco_id=legacy_id,
        center_x_mm=fx * panel_w_mm,
        center_y_mm=fy * panel_h_mm,
        center_px=None,
    )


def _paste_marker_at_slot(
    canvas: np.ndarray,
    slot: CharucoSlotSpec,
    px_per_mm: float,
    use_charuco: bool,
) -> dict[str, Any]:
    cx = _mm_to_px(slot.center_x_mm or 0.0, px_per_mm)
    cy = _mm_to_px(slot.center_y_mm or 0.0, px_per_mm)
    slot.center_px = (float(cx), float(cy))
    meta: dict[str, Any] = {"name": slot.name, "center_mm": [slot.center_x_mm, slot.center_y_mm]}

    if use_charuco:
        board_bgr, bw, bh, d_used = _render_charuco_board_bgr(
            slot.cols, slot.rows, slot.square_mm, slot.marker_mm, slot.dict_name, px_per_mm
        )
        bbox = _paste_centered(canvas, board_bgr, (cx, cy))
        meta.update({"kind": "charuco", "board_mm": [bw, bh], "dict": d_used, "bbox_px": list(bbox)})
    else:
        side_px = max(32, _mm_to_px(PDF_MARKER_MM, px_per_mm))
        dictionary = _dictionary(PDF_DICT)
        marker = cv2.aruco.generateImageMarker(dictionary, slot.legacy_aruco_id, side_px)
        patch = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        bbox = _paste_centered(canvas, patch, (cx, cy))
        meta.update({"kind": "aruco", "side_mm": PDF_MARKER_MM, "id": slot.legacy_aruco_id, "bbox_px": list(bbox)})

    fs = _font_scale(px_per_mm, 11.0) * 0.85
    thick = max(1, _stroke_px(px_per_mm, 0.18))
    cv2.putText(
        canvas,
        slot.name,
        (bbox[0], max(18, bbox[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs,
        (10, 10, 10),
        thick,
        cv2.LINE_AA,
    )
    return meta


def _relabel_panel_header(canvas: np.ndarray, side: str, px_per_mm: float | None = None) -> None:
    """Overwrite stencil header strip with FRONT or BACK panel label."""
    h, w = canvas.shape[:2]
    ppm = px_per_mm or (w / PDF_PANEL_W_MM)
    band_h = max(_mm_to_px(28.0, ppm), int(0.07 * h))
    cv2.rectangle(canvas, (0, 0), (w - 1, band_h), (20, 20, 20), -1)
    title = f"TOP / SHOULDERS -- {side.upper()} PANEL"
    fs_title = _font_scale(ppm, 9.0)
    fs_sub = _font_scale(ppm, 14.0) * 0.7
    thick = max(1, _stroke_px(ppm, 0.2))
    (tw, _), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, fs_title, thick)
    cv2.putText(
        canvas,
        title,
        (max(12, (w - tw) // 2), int(band_h * 0.62)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs_title,
        (255, 255, 255),
        thick,
        cv2.LINE_AA,
    )
    sub = "F0+F1 ChArUco" if side == "front" else "F2+F3 ChArUco"
    (sw, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, fs_sub, 1)
    cv2.putText(
        canvas,
        sub,
        (max(12, (w - sw) // 2), int(band_h * 0.9)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs_sub,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )


def _draw_back_neckline(canvas: np.ndarray, px_per_mm: float) -> None:
    """Replace front V-neck art with a straight back neckline (proper back panel)."""
    h, w = canvas.shape[:2]
    neck_y = _mm_to_px(80.0, px_per_mm)
    mask = np.zeros(canvas.shape[:2], np.uint8)
    # Mask the V-neck triangle + upper chest zone
    pts = np.array(
        [
            [int(0.32 * w), 0],
            [int(0.68 * w), 0],
            [int(0.56 * w), int(0.14 * h)],
            [int(0.44 * w), int(0.14 * h)],
        ],
        np.int32,
    )
    cv2.fillPoly(mask, [pts], 255)
    canvas[:] = cv2.inpaint(canvas, mask, 5, cv2.INPAINT_TELEA)
    pink = (180, 80, 200)
    thick = max(2, _mm_to_px(2.5, px_per_mm))
    x0, x1 = int(0.30 * w), int(0.70 * w)
    cv2.line(canvas, (x0, neck_y), (x1, neck_y), pink, thick, cv2.LINE_AA)
    for x in range(x0, x1, max(8, _mm_to_px(10.0, px_per_mm))):
        cv2.line(canvas, (x, neck_y - 6), (x, neck_y + 6), pink, 1, cv2.LINE_AA)
    cv2.putText(
        canvas, "BACK NECKLINE", (x0, max(24, neck_y - 12)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, pink, 2, cv2.LINE_AA,
    )


def _wrap_with_crop_marks(
    panel: np.ndarray,
    px_per_mm: float,
    margin_mm: float = 12.0,
) -> np.ndarray:
    """Add print crop marks outside the panel (panel size unchanged inside marks)."""
    m = _mm_to_px(margin_mm, px_per_mm)
    h, w = panel.shape[:2]
    out = np.full((h + 2 * m, w + 2 * m, 3), 255, np.uint8)
    out[m : m + h, m : m + w] = panel
    mark = (30, 30, 30)
    tick = max(4, _mm_to_px(5.0, px_per_mm))
    corners = ((m, m), (m + w, m), (m, m + h), (m + w, m + h))
    for cx, cy in corners:
        cv2.line(out, (cx - tick, cy), (cx + tick, cy), mark, 2, cv2.LINE_AA)
        cv2.line(out, (cx, cy - tick), (cx, cy + tick), mark, 2, cv2.LINE_AA)
    cv2.putText(
        out,
        f"PANEL {w / px_per_mm / 10:.0f}x{h / px_per_mm / 10:.0f} cm inside marks",
        (m, m - 8 if m > 8 else 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        mark,
        1,
        cv2.LINE_AA,
    )
    return out


def _all_marker_slots(panel_w_mm: float, panel_h_mm: float) -> dict[str, CharucoSlotSpec]:
    return {
        s.name: s
        for s in (
            _slot_at_pdf_coord("F0", 0, panel_w_mm, panel_h_mm, PDF_DICT),
            _slot_at_pdf_coord("F1", 1, panel_w_mm, panel_h_mm, "DICT_5X5_50"),
            _slot_at_pdf_coord("F2", 2, panel_w_mm, panel_h_mm, PDF_DICT),
            _slot_at_pdf_coord("F3", 3, panel_w_mm, panel_h_mm, "DICT_5X5_50"),
        )
    }


def _resolve_charuco_stencil_assets(
    spec: DSVPrintSpec,
    out_dir: Path,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Locate upgraded stencil PNG + spec JSON (F0/F1 positions from real stencil art)."""
    candidates = [
        spec.charuco_stencil_path,
        out_dir.parent / "stencils" / "dsv_front_panel_charuco.png",
    ]
    png_path = next((p for p in candidates if p and p.is_file()), None)
    if png_path is None:
        return None, None
    spec_path = png_path.with_name("dsv_front_panel_charuco_spec.json")
    if not spec_path.is_file():
        return png_path, None
    return png_path, json.loads(spec_path.read_text(encoding="utf-8"))


def _slots_from_charuco_spec(
    charuco_meta: dict[str, Any],
    panel_w_mm: float,
    panel_h_mm: float,
) -> dict[str, CharucoSlotSpec]:
    """Scale detected F0/F1 centres to print panel size; F2/F3 share those positions."""
    src = charuco_meta["spec"]
    src_h = src.get("panel_h_mm") or panel_h_mm
    sx = panel_w_mm / src["panel_w_mm"]
    sy = panel_h_mm / src_h

    def _scaled(name: str, legacy_id: int, dict_name: str, slot_info: dict[str, Any]) -> CharucoSlotSpec:
        ch = slot_info["charuco"]
        return CharucoSlotSpec(
            name=name,
            cols=ch["cols"],
            rows=ch["rows"],
            square_mm=ch["square_mm"],
            marker_mm=ch["marker_mm"],
            dict_name=dict_name,
            legacy_aruco_id=legacy_id,
            center_x_mm=ch["center_x_mm"] * sx,
            center_y_mm=ch["center_y_mm"] * sy,
        )

    f0 = charuco_meta["charuco_slots"]["F0"]
    f1 = charuco_meta["charuco_slots"]["F1"]
    return {
        "F0": _scaled("F0", 0, f0["charuco"]["dict_name"], f0),
        "F1": _scaled("F1", 1, f1["charuco"]["dict_name"], f1),
        "F2": _scaled("F2", 2, PDF_DICT, f0),
        "F3": _scaled("F3", 3, "DICT_5X5_50", f1),
    }


def _build_panel(
    stencil_base: np.ndarray,
    side: str,
    marker_names: tuple[str, ...],
    slots: dict[str, CharucoSlotSpec],
    px_per_mm: float,
    use_charuco: bool,
    draw_neckline: bool = True,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """One print-ready panel: correct neckline, only its markers (F0/F1 or F2/F3)."""
    canvas = stencil_base.copy()
    _relabel_panel_header(canvas, side, px_per_mm)
    if draw_neckline and side == "back":
        _draw_back_neckline(canvas, px_per_mm)

    _erase_marker_slots(canvas, list(slots.values()), px_per_mm)

    markers: list[dict[str, Any]] = []
    for name in marker_names:
        meta = _paste_marker_at_slot(canvas, slots[name], px_per_mm, use_charuco)
        markers.append(meta)
    return canvas, markers


def _erase_marker_slots(canvas: np.ndarray, slots: list[CharucoSlotSpec], px_per_mm: float) -> None:
    """Clear regions before pasting new ChArUco boards."""
    pad_mm = PDF_MARKER_MM * 0.65
    for slot in slots:
        cx = _mm_to_px(slot.center_x_mm or 0.0, px_per_mm)
        cy = _mm_to_px(slot.center_y_mm or 0.0, px_per_mm)
        side_px = _mm_to_px(pad_mm, px_per_mm)
        _erase_square_patch(canvas, (float(cx), float(cy)), float(side_px))


@dataclass
class CharucoStickerSheetSpec:
    """
    Printable ChArUco stickers to cut out and tape onto a worn DSV vest.

    Default geometry matches the production print master (5×4 board, 12 mm squares,
    60×48 mm footprint). Print at 100% scale — do not use “fit to page”.
    """

    dpi: float = 300.0
    cols: int = 5
    rows: int = 4
    square_mm: float = 12.0
    marker_mm: float = 9.0
    margin_mm: float = 15.0  # white border around each board for tape / trimming
    sheet_w_mm: float = 210.0  # A4
    sheet_h_mm: float = 297.0
    slots: tuple[str, ...] = ("F0", "F1", "F2", "F3")
    slot_labels: dict[str, str] = field(
        default_factory=lambda: {
            "F0": "F0 — FRONT upper chest",
            "F1": "F1 — FRONT lower abdomen",
            "F2": "F2 — BACK upper back",
            "F3": "F3 — BACK lower back",
        }
    )

    @property
    def px_per_mm(self) -> float:
        return self.dpi / MM_PER_IN

    @property
    def board_w_mm(self) -> float:
        return self.cols * self.square_mm

    @property
    def board_h_mm(self) -> float:
        return self.rows * self.square_mm


def default_dsv_marker_slots(
    stencil_spec_path: Path | None = None,
) -> dict[str, CharucoSlotSpec]:
    """
    Return F0–F3 ``CharucoSlotSpec`` matching the production DSV print master.

    Loads ``dsv_front_panel_charuco_spec.json`` when present; otherwise uses
    the built-in PDF / stencil defaults.
    """
    root = Path(__file__).resolve().parents[1]
    candidates = [
        stencil_spec_path,
        root / "assets/dsv_charuco/stencils/dsv_front_panel_charuco_spec.json",
    ]
    spec_path = next((p for p in candidates if p and p.is_file()), None)
    if spec_path is not None:
        meta = json.loads(spec_path.read_text(encoding="utf-8"))
        return _slots_from_charuco_spec(meta, 1000.0, 1500.0)

    return {
        "F0": CharucoSlotSpec("F0", dict_name=PDF_DICT, legacy_aruco_id=0),
        "F1": CharucoSlotSpec("F1", dict_name="DICT_5X5_100", legacy_aruco_id=1),
        "F2": CharucoSlotSpec("F2", dict_name=PDF_DICT, legacy_aruco_id=2),
        "F3": CharucoSlotSpec("F3", dict_name="DICT_5X5_50", legacy_aruco_id=3),
    }


def render_charuco_sticker(
    slot: CharucoSlotSpec,
    sheet_spec: CharucoStickerSheetSpec | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Render one labelled sticker (board + white margin) ready to print."""
    sheet_spec = sheet_spec or CharucoStickerSheetSpec()
    ppm = sheet_spec.px_per_mm
    board_bgr, bw_mm, bh_mm, dict_used = _render_charuco_board_bgr(
        sheet_spec.cols,
        sheet_spec.rows,
        sheet_spec.square_mm,
        sheet_spec.marker_mm,
        slot.dict_name,
        ppm,
    )
    pad = _mm_to_px(sheet_spec.margin_mm, ppm)
    sticker = np.full(
        (board_bgr.shape[0] + 2 * pad, board_bgr.shape[1] + 2 * pad, 3),
        255,
        np.uint8,
    )
    sticker[pad : pad + board_bgr.shape[0], pad : pad + board_bgr.shape[1]] = board_bgr

    label = sheet_spec.slot_labels.get(slot.name, slot.name)
    sub = f"{sheet_spec.cols}x{sheet_spec.rows}  {sheet_spec.square_mm:.0f}mm sq  {dict_used}"
    fs = max(0.35, _font_scale(ppm, 9.0) * 0.55)
    thick = max(1, _stroke_px(ppm, 0.15))
    cv2.putText(
        sticker,
        label,
        (pad, max(14, pad - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs,
        (30, 30, 30),
        thick,
        cv2.LINE_AA,
    )
    cv2.putText(
        sticker,
        sub,
        (pad, sticker.shape[0] - max(6, pad // 3)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs * 0.75,
        (80, 80, 80),
        thick,
        cv2.LINE_AA,
    )

    corners = _validate_charuco_sticker(board_bgr, sheet_spec, dict_used)
    meta = {
        "name": slot.name,
        "dict": dict_used,
        "board_mm": [round(bw_mm, 2), round(bh_mm, 2)],
        "sticker_mm": [
            round(bw_mm + 2 * sheet_spec.margin_mm, 2),
            round(bh_mm + 2 * sheet_spec.margin_mm, 2),
        ],
        "corners_detected": corners,
        "corners_expected": (sheet_spec.cols - 1) * (sheet_spec.rows - 1),
    }
    return sticker, meta


def _validate_charuco_sticker(
    board_bgr: np.ndarray,
    sheet_spec: CharucoStickerSheetSpec,
    dict_name: str,
) -> int:
    """Self-check: OpenCV should recover all inner corners on a fresh render."""
    dictionary = _dictionary(dict_name)
    board = cv2.aruco.CharucoBoard(
        (sheet_spec.cols, sheet_spec.rows),
        sheet_spec.square_mm / 1000.0,
        sheet_spec.marker_mm / 1000.0,
        dictionary,
    )
    detector = cv2.aruco.CharucoDetector(board, detectorParams=cv2.aruco.DetectorParameters())
    gray = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY)
    charuco_corners, _, _, _ = detector.detectBoard(gray)
    return 0 if charuco_corners is None else len(charuco_corners)


def _layout_charuco_sticker_sheet(
    stickers: list[tuple[str, np.ndarray]],
    sheet_spec: CharucoStickerSheetSpec,
) -> np.ndarray:
    """Place stickers in a 2×2 grid on an A4 canvas."""
    ppm = sheet_spec.px_per_mm
    sheet = np.full(
        (_mm_to_px(sheet_spec.sheet_h_mm, ppm), _mm_to_px(sheet_spec.sheet_w_mm, ppm), 3),
        255,
        np.uint8,
    )
    if not stickers:
        return sheet

    cols_n = 2
    rows_n = int(np.ceil(len(stickers) / cols_n))
    label_mm = 12.0
    gap_mm = 8.0
    cell_w_mm = sheet_spec.board_w_mm + 2 * sheet_spec.margin_mm + gap_mm
    cell_h_mm = sheet_spec.board_h_mm + 2 * sheet_spec.margin_mm + label_mm + gap_mm
    grid_w_mm = cols_n * cell_w_mm - gap_mm
    grid_h_mm = rows_n * cell_h_mm - gap_mm
    x0_mm = max(4.0, (sheet_spec.sheet_w_mm - grid_w_mm) / 2.0)
    y0_mm = max(14.0, (sheet_spec.sheet_h_mm - grid_h_mm) / 2.0)

    for idx, (_, sticker) in enumerate(stickers):
        row, col = divmod(idx, cols_n)
        x_mm = x0_mm + col * cell_w_mm
        y_mm = y0_mm + row * cell_h_mm
        x_px = max(0, _mm_to_px(x_mm, ppm))
        y_px = max(0, _mm_to_px(y_mm, ppm))
        sh, sw = sticker.shape[:2]
        x1 = min(sheet.shape[1], x_px + sw)
        y1 = min(sheet.shape[0], y_px + sh)
        if x1 <= x_px or y1 <= y_px:
            continue
        sheet[y_px:y1, x_px:x1] = sticker[: y1 - y_px, : x1 - x_px]

    # cut guides
    guide = (200, 200, 200)
    thick = max(1, _stroke_px(ppm, 0.12))
    for idx in range(len(stickers)):
        row, col = divmod(idx, cols_n)
        x_mm = x0_mm + col * cell_w_mm
        y_mm = y0_mm + row * cell_h_mm
        x_px = _mm_to_px(x_mm, ppm)
        y_px = _mm_to_px(y_mm, ppm)
        cw = _mm_to_px(cell_w_mm, ppm)
        ch = _mm_to_px(cell_h_mm, ppm)
        cv2.rectangle(sheet, (x_px, y_px), (x_px + cw - 1, y_px + ch - 1), guide, thick, cv2.LINE_AA)

    title = "DSV ChArUco stickers — print 100% scale, cut on grey lines, tape flat onto vest"
    fs = max(0.4, _font_scale(ppm, 10.0) * 0.5)
    cv2.putText(
        sheet,
        title,
        (_mm_to_px(8, ppm), _mm_to_px(10, ppm)),
        cv2.FONT_HERSHEY_SIMPLEX,
        fs,
        (40, 40, 40),
        max(1, thick),
        cv2.LINE_AA,
    )
    return sheet


def generate_charuco_sticker_sheet(
    sheet_spec: CharucoStickerSheetSpec | None = None,
    out_dir: Path | None = None,
    stencil_spec_path: Path | None = None,
) -> dict[str, Any]:
    """
    Generate printable ChArUco stickers (F0–F3) for sticking onto a worn DSV.

    Writes:
      - ``charuco_sticker_<name>.png`` — individual stickers
      - ``charuco_stickers_a4_<dpi>dpi.png`` + ``.pdf`` — 2×2 A4 sheet

    Returns metadata including per-board corner validation counts.
    """
    sheet_spec = sheet_spec or CharucoStickerSheetSpec()
    out_dir = out_dir or Path("assets/dsv_charuco/stickers")
    out_dir.mkdir(parents=True, exist_ok=True)

    slots = default_dsv_marker_slots(stencil_spec_path)
    stickers: list[tuple[str, np.ndarray]] = []
    board_meta: dict[str, Any] = {}

    for name in sheet_spec.slots:
        if name not in slots:
            raise KeyError(f"unknown slot {name!r}; expected one of {sorted(slots)}")
        slot = slots[name]
        slot.cols = sheet_spec.cols
        slot.rows = sheet_spec.rows
        slot.square_mm = sheet_spec.square_mm
        slot.marker_mm = sheet_spec.marker_mm
        sticker, meta = render_charuco_sticker(slot, sheet_spec)
        stickers.append((name, sticker))
        board_meta[name] = meta
        out_png = out_dir / f"charuco_sticker_{name}.png"
        cv2.imwrite(str(out_png), sticker, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        meta["png"] = str(out_png)

    sheet_bgr = _layout_charuco_sticker_sheet(stickers, sheet_spec)
    dpi_tag = int(sheet_spec.dpi)
    sheet_png = out_dir / f"charuco_stickers_a4_{dpi_tag}dpi.png"
    sheet_pdf = out_dir / f"charuco_stickers_a4_{dpi_tag}dpi.pdf"
    cv2.imwrite(str(sheet_png), sheet_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    export_panel_pdf(sheet_bgr, sheet_pdf, sheet_spec.dpi)

    expected = (sheet_spec.cols - 1) * (sheet_spec.rows - 1)
    all_ok = all(m["corners_detected"] >= expected for m in board_meta.values())
    meta = {
        "kind": "dsv_charuco_sticker_sheet",
        "spec": asdict(sheet_spec),
        "boards": board_meta,
        "outputs": {
            "sheet_png": str(sheet_png),
            "sheet_pdf": str(sheet_pdf),
        },
        "validation_ok": all_ok,
        "print_instructions": (
            f"Print charuco_stickers_a4_{dpi_tag}dpi.pdf at 100% scale (NO fit-to-page).\n"
            f"Each board must measure {sheet_spec.board_w_mm:.0f} mm × {sheet_spec.board_h_mm:.0f} mm "
            f"({sheet_spec.cols}×{sheet_spec.rows} squares @ {sheet_spec.square_mm:.0f} mm).\n"
            "Cut on grey lines, tape flat over the matching printed marker on the vest (F0–F3).\n"
            "Smooth the fabric — wrinkles break ChArUco detection."
        ),
    }
    meta_path = out_dir / f"charuco_stickers_{dpi_tag}dpi_spec.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["spec_json"] = str(meta_path)
    return meta


def export_panel_pdf(panel_bgr: np.ndarray, out_path: Path, dpi: float) -> Path:
    """Single-panel PDF with embedded DPI (one physical DSV piece per file)."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("pip install Pillow for PDF export") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(panel_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.save(str(out_path), "PDF", resolution=float(dpi))
    return out_path


def export_duplex_print_pdf(
    front_bgr: np.ndarray,
    back_bgr: np.ndarray,
    out_path: Path,
    dpi: float = 300.0,
) -> Path:
    """Optional 2-page reference PDF — prefer separate front/back PDFs for two fabric pieces."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("pip install Pillow for duplex PDF export") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img_front = Image.fromarray(cv2.cvtColor(front_bgr, cv2.COLOR_BGR2RGB))
    img_back = Image.fromarray(cv2.cvtColor(back_bgr, cv2.COLOR_BGR2RGB))
    img_front.save(
        str(out_path),
        "PDF",
        resolution=float(dpi),
        save_all=True,
        append_images=[img_back],
    )
    return out_path


def _export_print_panels(
    front_bgr: np.ndarray,
    back_bgr: np.ndarray,
    out_dir: Path,
    dpi: float,
) -> dict[str, Path]:
    """Write only the final front/back panel PNG + PDF (no tiles, cropmarks, or duplex)."""
    dpi_tag = int(dpi)
    front_path = out_dir / f"dsv_front_45gsm_{dpi_tag}dpi.png"
    back_path = out_dir / f"dsv_back_45gsm_{dpi_tag}dpi.png"
    front_pdf = out_dir / f"dsv_front_45gsm_{dpi_tag}dpi.pdf"
    back_pdf = out_dir / f"dsv_back_45gsm_{dpi_tag}dpi.pdf"
    png_q = [cv2.IMWRITE_PNG_COMPRESSION, 1]
    cv2.imwrite(str(front_path), front_bgr, png_q)
    cv2.imwrite(str(back_path), back_bgr, png_q)
    export_panel_pdf(front_bgr, front_pdf, dpi)
    export_panel_pdf(back_bgr, back_pdf, dpi)
    return {
        "front_png": front_path,
        "back_png": back_path,
        "front_pdf": front_pdf,
        "back_pdf": back_pdf,
    }


def generate_dsv_print_master(
    spec: DSVPrintSpec | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Generate high-resolution front + back DSV panels for 45 GSM print.

    Prefers the upgraded ChArUco stencil (``stencils/dsv_front_panel_charuco.png``)
    and places F0–F3 at detected stencil positions scaled to the print panel.
    Falls back to PDF coordinate table only when the upgraded stencil is missing.
    """
    spec = spec or DSVPrintSpec()
    out_dir = out_dir or Path("assets/dsv_charuco/print_master")
    out_dir.mkdir(parents=True, exist_ok=True)
    px_per_mm = spec.px_per_mm

    charuco_png, charuco_meta = _resolve_charuco_stencil_assets(spec, out_dir)
    marker_source = "stencil_charuco_spec"

    lines_mm: dict[str, float] = {}
    if charuco_png and charuco_meta:
        marker_slots = _slots_from_charuco_spec(charuco_meta, spec.panel_w_mm, spec.panel_h_mm)
        stencil_path = charuco_png
        geom = _scaled_stencil_geometry(charuco_meta, spec.panel_w_mm, spec.panel_h_mm)
        lines_mm = geom["measurement_lines_mm"]
        if spec.render_mode == "vector":
            marker_source = "stencil_charuco_spec_vector"
            cut_stencil = _resolve_stencil_cut_source(charuco_meta, charuco_png)
            front_base = _render_vector_print_panel(
                spec.panel_w_mm, spec.panel_h_mm, px_per_mm, charuco_meta, "front", cut_stencil
            )
            back_base = _render_vector_print_panel(
                spec.panel_w_mm, spec.panel_h_mm, px_per_mm, charuco_meta, "back", cut_stencil
            )
            base, front_markers = _build_panel(
                front_base, "front", ("F0", "F1"),
                marker_slots, px_per_mm, spec.use_charuco, draw_neckline=False,
            )
            back, back_markers = _build_panel(
                back_base, "back", ("F2", "F3"),
                marker_slots, px_per_mm, spec.use_charuco, draw_neckline=False,
            )
            outputs = _export_print_panels(base, back, out_dir, spec.dpi)
            dpi_tag = int(spec.dpi)
            spec_dict = asdict(spec)
            for key in ("stencil_path", "charuco_stencil_path"):
                if spec_dict.get(key) is not None:
                    spec_dict[key] = str(spec_dict[key])
            meta = {
                "kind": "dsv_print_master_45gsm",
                "spec": spec_dict,
                "marker_position_source": marker_source,
                "charuco_stencil_used": str(charuco_png),
                "physical_size_mm": [spec.panel_w_mm, spec.panel_h_mm],
                "dpi": spec.dpi,
                "px_per_mm": px_per_mm,
                "image_px": [base.shape[1], base.shape[0]],
                "markers_front": front_markers,
                "markers_back": back_markers,
                "measurement_lines_mm": lines_mm,
                "outputs": {k: str(v) for k, v in outputs.items()},
                "print_instructions": (
                    f"TWO SEPARATE 45 GSM fabric pieces:\n"
                    f"  1) Print dsv_front_45gsm_{dpi_tag}dpi.pdf on sheet 1 — V-neck, ChArUco F0+F1\n"
                    f"  2) Print dsv_back_45gsm_{dpi_tag}dpi.pdf on sheet 2 — back neckline, ChArUco F2+F3\n"
                    f"Settings: 100% scale, NO 'fit to page', media {spec.gsm} GSM.\n"
                    f"Verify each panel = {spec.panel_w_mm/10:.0f} cm × {spec.panel_h_mm/10:.0f} cm.\n"
                    f"Vector redraw at {spec.dpi:.0f} DPI ({px_per_mm:.2f} px/mm). "
                    "Set dpi=600 for print-house ChArUco sharpness."
                ),
            }
            meta_path = out_dir / f"dsv_print_master_{int(spec.dpi)}dpi_spec.json"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            return meta
        stencil_scaled = _scale_stencil_to_panel(
            _load_stencil_bgr(charuco_png), spec.panel_w_mm, spec.panel_h_mm, px_per_mm
        )
    else:
        marker_source = "pdf_coord_table"
        stencil_path = spec.stencil_path
        if stencil_path is None:
            default = Path(__file__).resolve().parents[1] / "assets/dsv_charuco/stencils/dsv_front_panel_stencil_original.jpg"
            stencil_path = default if default.is_file() else None

        if stencil_path and stencil_path.is_file():
            stencil_scaled = _scale_stencil_to_panel(
                _load_stencil_bgr(stencil_path), spec.panel_w_mm, spec.panel_h_mm, px_per_mm
            )
        else:
            tw = _mm_to_px(spec.panel_w_mm, px_per_mm)
            th = _mm_to_px(spec.panel_h_mm, px_per_mm)
            stencil_scaled = np.full((th, tw, 3), 252, np.uint8)

        _draw_pdf_grid(stencil_scaled, spec.grid_mm, px_per_mm)

        if stencil_path and stencil_path.is_file():
            st = _load_stencil_bgr(stencil_path)
            src_panel_w = charuco_meta["spec"]["panel_w_mm"] if charuco_meta else 340.0
            legacy_spec = DSVStencilSpec(stencil_path=stencil_path, panel_w_mm=src_panel_w)
            scaled_legacy = _detect_legacy_aruco_slots(
                cv2.resize(st, (stencil_scaled.shape[1], stencil_scaled.shape[0]), interpolation=cv2.INTER_LANCZOS4),
                legacy_spec,
            )
            scale_fix = stencil_scaled.shape[1] / max(1, st.shape[1])
            for name in ("F0", "F1"):
                if name in scaled_legacy:
                    hit = scaled_legacy[name]
                    _erase_square_patch(stencil_scaled, hit["center_px"], hit["side_px"] * scale_fix)

        marker_slots = _all_marker_slots(spec.panel_w_mm, spec.panel_h_mm)

    # --- Front panel (V-neck, F0 + F1 only) ---
    base, front_markers = _build_panel(
        stencil_scaled, "front", ("F0", "F1"),
        marker_slots, px_per_mm, spec.use_charuco, draw_neckline=True,
    )
    # --- Back panel (straight neckline, F2 + F3 only) ---
    back, back_markers = _build_panel(
        stencil_scaled, "back", ("F2", "F3"),
        marker_slots, px_per_mm, spec.use_charuco, draw_neckline=True,
    )

    if not lines_mm:
        lines_px = detect_stencil_measurement_lines(base, min_span_frac=0.08)
        if lines_px:
            lines_mm = {k: round(v / px_per_mm, 2) for k, v in lines_px.items()}
        else:
            spec_json = Path(__file__).resolve().parents[1] / "assets/dsv_charuco/stencils/dsv_front_panel_charuco_spec.json"
            if spec_json.is_file():
                prev = json.loads(spec_json.read_text())
                prev_h = prev["spec"].get("panel_h_mm") or spec.panel_h_mm
                scale_y = spec.panel_h_mm / prev_h
                lines_mm = {k: round(v * scale_y, 2) for k, v in prev.get("measurement_lines_mm", {}).items()}

    outputs = _export_print_panels(base, back, out_dir, spec.dpi)
    dpi_tag = int(spec.dpi)

    spec_dict = asdict(spec)
    for key in ("stencil_path", "charuco_stencil_path"):
        if spec_dict.get(key) is not None:
            spec_dict[key] = str(spec_dict[key])

    meta = {
        "kind": "dsv_print_master_45gsm",
        "spec": spec_dict,
        "marker_position_source": marker_source,
        "charuco_stencil_used": str(charuco_png) if charuco_png else None,
        "physical_size_mm": [spec.panel_w_mm, spec.panel_h_mm],
        "dpi": spec.dpi,
        "px_per_mm": px_per_mm,
        "image_px": [base.shape[1], base.shape[0]],
        "markers_front": front_markers,
        "markers_back": back_markers,
        "measurement_lines_mm": lines_mm,
        "outputs": {k: str(v) for k, v in outputs.items()},
        "print_instructions": (
            f"TWO SEPARATE 45 GSM fabric pieces:\n"
            f"  1) Print dsv_front_45gsm_{dpi_tag}dpi.pdf on sheet 1 — V-neck, ChArUco F0+F1\n"
            f"  2) Print dsv_back_45gsm_{dpi_tag}dpi.pdf on sheet 2 — back neckline, ChArUco F2+F3\n"
            f"Settings: 100% scale, NO 'fit to page', media {spec.gsm} GSM.\n"
            f"Verify each panel = {spec.panel_w_mm/10:.0f} cm × {spec.panel_h_mm/10:.0f} cm.\n"
            f"Exported at {spec.dpi:.0f} DPI ({px_per_mm:.2f} px/mm). "
            "Set dpi=600 for print-house ChArUco sharpness."
        ),
    }
    meta_path = out_dir / f"dsv_print_master_{int(spec.dpi)}dpi_spec.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


# ---------------------------------------------------------------------------
# DSV vest marker set — 13 uniquely-identifiable ChArUco boards
# ---------------------------------------------------------------------------
#
# The worn sizing vest carries 14 ChArUco markers, one per body landmark below.
# Each is a known-size board (a metric scale reference): printed at 100% it gives
# px<->mm scale at that body location, which feeds calibrate_from_charuco /
# infer_height_cm to recover real height + girths for custom-tailoring fit.
#
# All boards share ONE dictionary (DICT_4X4_250) but occupy NON-OVERLAPPING
# marker-id ranges, so a detector running the dictionary tells exactly which body
# position each board belongs to:  slot_index = detected_id // VEST_IDS_PER_BOARD.
#
# Geometry: 5x4 ChArUco @ 12 mm squares (60x48 mm), 10 marker ids per board.
# 14 boards -> ids 0..139, well within DICT_4X4_250 (250 ids).

VEST_MARKER_DICT = "DICT_4X4_250"
VEST_MARKER_COLS = 5
VEST_MARKER_ROWS = 4
VEST_MARKER_SQUARE_MM = 12.0
VEST_MARKER_MARKER_MM = 9.0
VEST_IDS_PER_BOARD = (VEST_MARKER_COLS * VEST_MARKER_ROWS) // 2  # 10


@dataclass
class VestMarkerSpec:
    """One uniquely-identifiable ChArUco marker placed on the worn DSV vest."""

    name: str            # short code, e.g. "FSH_L"
    region: str          # grouping: front / side / back
    description: str     # human-readable body position
    id_offset: int       # first marker id (block of VEST_IDS_PER_BOARD ids)
    cols: int = VEST_MARKER_COLS
    rows: int = VEST_MARKER_ROWS
    square_mm: float = VEST_MARKER_SQUARE_MM
    marker_mm: float = VEST_MARKER_MARKER_MM

    @property
    def n_markers(self) -> int:
        return (self.cols * self.rows) // 2

    @property
    def id_range(self) -> tuple[int, int]:
        return self.id_offset, self.id_offset + self.n_markers - 1


# (code, region, description) in placement order; id_offset assigned sequentially.
_VEST_MARKER_LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("FSH_L", "front", "Front shoulder - left"),
    ("FSH_R", "front", "Front shoulder - right"),
    ("FB", "front", "Front bust"),
    ("FW", "front", "Front waist"),
    ("FH", "front", "Front hip (widest)"),
    ("SR_U", "side", "Right side - upper"),
    ("SR_L", "side", "Right side - lower"),
    ("SL_U", "side", "Left side - upper"),
    ("SL_L", "side", "Left side - lower"),
    ("BSH_L", "back", "Back shoulder - left"),
    ("BSH_R", "back", "Back shoulder - right"),
    ("UB", "back", "Upper back"),
    ("MB", "back", "Mid back"),
    ("LB", "back", "Lower back"),
)


def dsv_vest_marker_set() -> list[VestMarkerSpec]:
    """The 13 DSV vest markers, each carved a non-overlapping id block."""
    return [
        VestMarkerSpec(name=code, region=region, description=desc, id_offset=i * VEST_IDS_PER_BOARD)
        for i, (code, region, desc) in enumerate(_VEST_MARKER_LAYOUT)
    ]


def _build_charuco_ids_board(
    cols: int,
    rows: int,
    square_mm: float,
    marker_mm: float,
    dict_name: str,
    id_offset: int,
) -> cv2.aruco.CharucoBoard:
    """ChArUco board whose marker ids start at id_offset (one shared dictionary)."""
    n_markers = (cols * rows) // 2
    cap = dict(_DICT_CAPACITIES).get(dict_name, 0)
    if id_offset + n_markers > cap:
        raise ValueError(
            f"{dict_name} holds {cap} ids; board needs {id_offset}..{id_offset + n_markers - 1}. "
            "Use a larger dictionary, or fewer/smaller boards."
        )
    dictionary = _dictionary(dict_name)
    ids = np.arange(id_offset, id_offset + n_markers, dtype=np.int32)
    return cv2.aruco.CharucoBoard(
        (cols, rows), square_mm / 1000.0, marker_mm / 1000.0, dictionary, ids
    )


def _render_charuco_ids_board_bgr(
    cols: int,
    rows: int,
    square_mm: float,
    marker_mm: float,
    dict_name: str,
    id_offset: int,
    px_per_mm: float,
) -> tuple[np.ndarray, float, float, list[int]]:
    """Render an offset-id ChArUco board; returns (bgr, w_mm, h_mm, marker_ids)."""
    board = _build_charuco_ids_board(cols, rows, square_mm, marker_mm, dict_name, id_offset)
    out_w = max(8, _mm_to_px(cols * square_mm, px_per_mm))
    out_h = max(8, _mm_to_px(rows * square_mm, px_per_mm))
    img = board.generateImage((out_w, out_h), marginSize=0, borderBits=1)
    ids = [int(i) for i in board.getIds().flatten()]
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), cols * square_mm, rows * square_mm, ids


def _validate_charuco_ids_board(
    board_bgr: np.ndarray,
    cols: int,
    rows: int,
    square_mm: float,
    marker_mm: float,
    dict_name: str,
    id_offset: int,
) -> int:
    """Self-check: detect the freshly rendered board back; returns inner-corner count."""
    board = _build_charuco_ids_board(cols, rows, square_mm, marker_mm, dict_name, id_offset)
    detector = cv2.aruco.CharucoDetector(board, detectorParams=cv2.aruco.DetectorParameters())
    corners, _, _, _ = detector.detectBoard(cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY))
    return 0 if corners is None else len(corners)


def render_vest_marker_sticker(
    spec: VestMarkerSpec,
    sheet: CharucoStickerSheetSpec | None = None,
    dict_name: str = VEST_MARKER_DICT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Render one labelled, print-ready vest marker (board + white margin + labels)."""
    sheet = sheet or CharucoStickerSheetSpec()
    ppm = sheet.px_per_mm
    board_bgr, bw_mm, bh_mm, ids = _render_charuco_ids_board_bgr(
        spec.cols, spec.rows, spec.square_mm, spec.marker_mm, dict_name, spec.id_offset, ppm
    )
    pad = _mm_to_px(sheet.margin_mm, ppm)
    sticker = np.full(
        (board_bgr.shape[0] + 2 * pad, board_bgr.shape[1] + 2 * pad, 3), 255, np.uint8
    )
    sticker[pad : pad + board_bgr.shape[0], pad : pad + board_bgr.shape[1]] = board_bgr

    fs = max(0.35, _font_scale(ppm, 9.0) * 0.55)
    thick = max(1, _stroke_px(ppm, 0.15))
    lo, hi = spec.id_range
    cv2.putText(
        sticker, f"{spec.name} - {spec.description}", (pad, max(14, pad - 6)),
        cv2.FONT_HERSHEY_SIMPLEX, fs, (30, 30, 30), thick, cv2.LINE_AA,
    )
    sub = f"{dict_name}  ids {lo}-{hi}  {spec.cols}x{spec.rows} @ {spec.square_mm:.0f}mm"
    cv2.putText(
        sticker, sub, (pad, sticker.shape[0] - max(6, pad // 3)),
        cv2.FONT_HERSHEY_SIMPLEX, fs * 0.72, (80, 80, 80), thick, cv2.LINE_AA,
    )

    corners = _validate_charuco_ids_board(
        board_bgr, spec.cols, spec.rows, spec.square_mm, spec.marker_mm, dict_name, spec.id_offset
    )
    meta = {
        "name": spec.name,
        "region": spec.region,
        "description": spec.description,
        "dict": dict_name,
        "id_offset": spec.id_offset,
        "id_range": [lo, hi],
        "marker_ids": ids,
        "board_mm": [round(bw_mm, 2), round(bh_mm, 2)],
        "sticker_mm": [
            round(bw_mm + 2 * sheet.margin_mm, 2),
            round(bh_mm + 2 * sheet.margin_mm, 2),
        ],
        "corners_detected": corners,
        "corners_expected": (spec.cols - 1) * (spec.rows - 1),
    }
    return sticker, meta


def _layout_vest_marker_pages(
    stickers: list[tuple[str, np.ndarray]],
    sheet: CharucoStickerSheetSpec,
    cols_n: int = 2,
    rows_n: int = 3,
) -> list[np.ndarray]:
    """Tile labelled stickers cols_n x rows_n per A4 page; one image per page."""
    ppm = sheet.px_per_mm
    per_page = cols_n * rows_n
    gap_mm = 8.0
    label_mm = 12.0
    cell_w_mm = sheet.board_w_mm + 2 * sheet.margin_mm + gap_mm
    cell_h_mm = sheet.board_h_mm + 2 * sheet.margin_mm + label_mm + gap_mm
    grid_w_mm = cols_n * cell_w_mm - gap_mm
    grid_h_mm = rows_n * cell_h_mm - gap_mm
    x0_mm = max(4.0, (sheet.sheet_w_mm - grid_w_mm) / 2.0)
    y0_mm = max(14.0, (sheet.sheet_h_mm - grid_h_mm) / 2.0)
    guide = (200, 200, 200)
    thick = max(1, _stroke_px(ppm, 0.12))
    title_fs = max(0.4, _font_scale(ppm, 10.0) * 0.5)

    n_pages = max(1, int(np.ceil(len(stickers) / per_page)))
    pages: list[np.ndarray] = []
    for p in range(n_pages):
        page = np.full(
            (_mm_to_px(sheet.sheet_h_mm, ppm), _mm_to_px(sheet.sheet_w_mm, ppm), 3), 255, np.uint8
        )
        chunk = stickers[p * per_page : (p + 1) * per_page]
        for idx, (_, st) in enumerate(chunk):
            row, col = divmod(idx, cols_n)
            x_px = max(0, _mm_to_px(x0_mm + col * cell_w_mm, ppm))
            y_px = max(0, _mm_to_px(y0_mm + row * cell_h_mm, ppm))
            sh, sw = st.shape[:2]
            x1 = min(page.shape[1], x_px + sw)
            y1 = min(page.shape[0], y_px + sh)
            if x1 > x_px and y1 > y_px:
                page[y_px:y1, x_px:x1] = st[: y1 - y_px, : x1 - x_px]
            cw = _mm_to_px(cell_w_mm, ppm)
            ch = _mm_to_px(cell_h_mm, ppm)
            cv2.rectangle(page, (x_px, y_px), (x_px + cw - 1, y_px + ch - 1), guide, thick, cv2.LINE_AA)
        cv2.putText(
            page,
            f"DSV vest ChArUco markers - page {p + 1}/{n_pages} - print 100% scale, cut on grey lines",
            (_mm_to_px(8, ppm), _mm_to_px(10, ppm)),
            cv2.FONT_HERSHEY_SIMPLEX, title_fs, (40, 40, 40), max(1, thick), cv2.LINE_AA,
        )
        pages.append(page)
    return pages


def _export_pages_pdf(pages: list[np.ndarray], out_path: Path, dpi: float) -> Path:
    """Write a multi-page PDF (one A4 page per image) with embedded DPI."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("pip install Pillow for PDF export") from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    imgs = [Image.fromarray(cv2.cvtColor(p, cv2.COLOR_BGR2RGB)) for p in pages]
    imgs[0].save(
        str(out_path), "PDF", resolution=float(dpi), save_all=True, append_images=imgs[1:]
    )
    return out_path


def generate_vest_marker_stickers(
    sheet: CharucoStickerSheetSpec | None = None,
    out_dir: Path | None = None,
    dict_name: str = VEST_MARKER_DICT,
) -> dict[str, Any]:
    """
    Generate the 13 uniquely-identifiable DSV vest ChArUco markers.

    Writes:
      - ``vest_marker_<NAME>.png`` — one labelled sticker per body position
      - ``vest_markers_a4_p<N>_<dpi>dpi.png`` — paginated A4 sheets (6 per page)
      - ``vest_markers_a4_<dpi>dpi.pdf`` — multi-page print PDF
      - ``vest_markers_<dpi>dpi_spec.json`` — name -> region -> id-range map

    Returns metadata with per-board corner validation + the id map used by
    detection to identify which body landmark each marker belongs to.
    """
    sheet = sheet or CharucoStickerSheetSpec()
    out_dir = out_dir or Path("assets/dsv_charuco/vest_markers")
    out_dir.mkdir(parents=True, exist_ok=True)

    markers = dsv_vest_marker_set()
    stickers: list[tuple[str, np.ndarray]] = []
    board_meta: dict[str, Any] = {}
    for spec in markers:
        sticker, meta = render_vest_marker_sticker(spec, sheet, dict_name)
        stickers.append((spec.name, sticker))
        out_png = out_dir / f"vest_marker_{spec.name}.png"
        cv2.imwrite(str(out_png), sticker, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        meta["png"] = str(out_png)
        board_meta[spec.name] = meta

    pages = _layout_vest_marker_pages(stickers, sheet)
    dpi_tag = int(sheet.dpi)
    page_pngs: list[str] = []
    for i, page in enumerate(pages, start=1):
        page_path = out_dir / f"vest_markers_a4_p{i}_{dpi_tag}dpi.png"
        cv2.imwrite(str(page_path), page, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        page_pngs.append(str(page_path))
    sheet_pdf = out_dir / f"vest_markers_a4_{dpi_tag}dpi.pdf"
    _export_pages_pdf(pages, sheet_pdf, sheet.dpi)

    all_ok = all(m["corners_detected"] >= m["corners_expected"] for m in board_meta.values())
    id_map = {
        name: {"region": m["region"], "description": m["description"], "id_range": m["id_range"]}
        for name, m in board_meta.items()
    }
    meta = {
        "kind": "dsv_vest_charuco_markers",
        "dict": dict_name,
        "ids_per_board": VEST_IDS_PER_BOARD,
        "marker_count": len(markers),
        "board_geometry": {
            "cols": sheet.cols,
            "rows": sheet.rows,
            "square_mm": sheet.square_mm,
            "marker_mm": sheet.marker_mm,
            "board_mm": [sheet.board_w_mm, sheet.board_h_mm],
        },
        "id_map": id_map,
        "boards": board_meta,
        "outputs": {"pages_png": page_pngs, "sheet_pdf": str(sheet_pdf)},
        "validation_ok": all_ok,
        "print_instructions": (
            f"Print vest_markers_a4_{dpi_tag}dpi.pdf at 100% scale (NO fit-to-page) over "
            f"{len(pages)} A4 page(s).\n"
            f"Each board MUST measure {sheet.board_w_mm:.0f} mm x {sheet.board_h_mm:.0f} mm "
            f"({sheet.cols}x{sheet.rows} squares @ {sheet.square_mm:.0f} mm) - verify with a ruler; "
            "the printed size is the scale reference.\n"
            "Cut on grey lines, tape each marker flat at its labelled body position on the vest.\n"
            "Smooth the fabric - wrinkles break ChArUco detection."
        ),
    }
    meta_path = out_dir / f"vest_markers_{dpi_tag}dpi_spec.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["spec_json"] = str(meta_path)
    return meta


def synthesize_worn_preview(
    panel_bgr: np.ndarray,
    background_bgr: np.ndarray,
    panel_origin: tuple[int, int],
    scale: float = 1.0,
    angle_deg: float = 0.0,
) -> np.ndarray:
    """Paste the panel onto a person photo for a quick detection smoke-test."""
    ph, pw = panel_bgr.shape[:2]
    new_w = max(32, int(pw * scale))
    new_h = max(32, int(ph * scale))
    resized = cv2.resize(panel_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    if abs(angle_deg) > 0.1:
        m = cv2.getRotationMatrix2D((new_w / 2, new_h / 2), angle_deg, 1.0)
        resized = cv2.warpAffine(resized, m, (new_w, new_h), borderValue=(245, 245, 240))
    out = background_bgr.copy()
    x0, y0 = panel_origin
    x1, y1 = min(out.shape[1], x0 + new_w), min(out.shape[0], y0 + new_h)
    roi = resized[0 : y1 - y0, 0 : x1 - x0]
    mask = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(mask, 250, 255, cv2.THRESH_BINARY_INV)
    mask3 = cv2.merge([mask, mask, mask])
    dst = out[y0:y1, x0:x1]
    np.copyto(dst, roi, where=mask3.astype(bool))
    return out
