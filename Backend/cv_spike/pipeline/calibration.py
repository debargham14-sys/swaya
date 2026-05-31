"""
Calibrate photo-estimated girths to tape-measured ground truth.

Fits a global affine on circumference (cm):
    calibrated = scale * raw + offset_cm

from two or more tape anchors (e.g. bust=44in, waist=38in). Shoulder width is
left unchanged (linear width, not girth).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CM_PER_IN = 2.54
GIRTH_LEVELS = ("bust", "underbust", "waist", "hip")
LEVEL_ALIASES = {"chest": "bust", "seat": "hip", "hips": "hip"}


@dataclass
class CalibrationProfile:
    name: str
    method: str = "affine_girth"
    scale: float = 1.0
    offset_cm: float = 0.0
    anchors_cm: dict[str, float] = field(default_factory=dict)
    raw_girths_cm: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationProfile":
        return cls(
            name=data.get("name", "unnamed"),
            method=data.get("method", "affine_girth"),
            scale=float(data["scale"]),
            offset_cm=float(data["offset_cm"]),
            anchors_cm={k: float(v) for k, v in data.get("anchors_cm", {}).items()},
            raw_girths_cm={k: float(v) for k, v in data.get("raw_girths_cm", {}).items()},
            notes=data.get("notes", ""),
            created_at=data.get("created_at", ""),
        )


def normalize_level(name: str) -> str:
    key = name.strip().lower().replace("-", "_")
    return LEVEL_ALIASES.get(key, key)


def parse_tape_spec(spec: str, unit: str = "in") -> dict[str, float]:
    """Parse ``bust=44,waist=38`` or ``chest=44in,waist=97cm`` into cm."""
    if not spec or not spec.strip():
        return {}
    unit = unit.lower()
    out: dict[str, float] = {}
    for part in re.split(r"[,;]+", spec.strip()):
        part = part.strip()
        if not part:
            continue
        m = re.match(
            r"^([a-zA-Z_]+)\s*=\s*([0-9.]+)\s*(in|cm|inch|inches)?$",
            part,
            re.I,
        )
        if not m:
            raise ValueError(f"bad tape token: {part!r} (use bust=44,waist=38)")
        level = normalize_level(m.group(1))
        val = float(m.group(2))
        u = (m.group(3) or unit).lower()
        if u in ("in", "inch", "inches"):
            val *= CM_PER_IN
        elif u != "cm":
            raise ValueError(f"unknown unit in {part!r}")
        out[level] = val
    return out


def girths_from_markerless_json(data: dict) -> dict[str, float]:
    raw: dict[str, float] = {}
    for lv in data.get("levels", []):
        name = normalize_level(lv.get("name", ""))
        g = lv.get("girth_cm")
        if name in GIRTH_LEVELS and g is not None:
            raw[name] = float(g)
    if not raw:
        for k, v in data.get("girths_cm", {}).items():
            nk = normalize_level(k)
            if nk in GIRTH_LEVELS:
                raw[nk] = float(v)
    return raw


def fit_affine_girth(anchors_cm: dict[str, float], raw_girths_cm: dict[str, float]) -> tuple[float, float]:
    """Least-squares fit calibrated = scale * raw + offset over shared levels."""
    pairs = [
        (raw_girths_cm[k], anchors_cm[k])
        for k in anchors_cm
        if k in raw_girths_cm and raw_girths_cm[k] > 0
    ]
    if len(pairs) < 1:
        raise ValueError("need at least one tape anchor matching a raw girth level")
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if len(pairs) == 1:
        # single anchor: preserve relative shape — scale through anchor, offset 0
        x0, y0 = pairs[0]
        return y0 / x0, 0.0
    n = float(len(pairs))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x < 1e-6:
        raise ValueError("tape anchors do not span distinct raw levels")
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    scale = cov / var_x
    offset = mean_y - scale * mean_x
    return scale, offset


def fit_profile(
    anchors_cm: dict[str, float],
    raw_girths_cm: dict[str, float],
    name: str = "custom",
    notes: str = "",
) -> CalibrationProfile:
    scale, offset = fit_affine_girth(anchors_cm, raw_girths_cm)
    return CalibrationProfile(
        name=name,
        scale=round(scale, 5),
        offset_cm=round(offset, 3),
        anchors_cm={k: round(v, 2) for k, v in anchors_cm.items()},
        raw_girths_cm={k: round(v, 2) for k, v in raw_girths_cm.items()},
        notes=notes,
    )


def apply_girth_calibration(
    girths_cm: dict[str, float],
    profile: CalibrationProfile,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in girths_cm.items():
        nk = normalize_level(k)
        if nk not in GIRTH_LEVELS or v is None:
            continue
        out[nk] = round(profile.scale * float(v) + profile.offset_cm, 1)
    return out


def load_profile(path: str | Path) -> CalibrationProfile:
    data = json.loads(Path(path).read_text())
    return CalibrationProfile.from_dict(data)


def save_profile(profile: CalibrationProfile, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile.to_dict(), indent=2))
    return p


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Fit or apply tape calibration")
    sub = p.add_subparsers(dest="cmd", required=True)

    fit_p = sub.add_parser("fit", help="fit profile from raw JSON + tape")
    fit_p.add_argument("--raw", type=Path, required=True, help="markerless/engine JSON")
    fit_p.add_argument("--tape-in", type=str, help="tape in inches: bust=44,waist=38")
    fit_p.add_argument("--tape-cm", type=str, help="tape in cm: bust=112,waist=97")
    fit_p.add_argument("--name", type=str, default="custom")
    fit_p.add_argument("--out", type=Path, default=root / "calibration" / "profiles" / "custom.json")

    apply_p = sub.add_parser("apply", help="print calibrated girths from a profile")
    apply_p.add_argument("--profile", type=Path, required=True)

    args = p.parse_args()
    if args.cmd == "fit":
        data = json.loads(args.raw.read_text())
        raw = girths_from_markerless_json(data)
        if args.tape_cm:
            anchors = parse_tape_spec(args.tape_cm, unit="cm")
        elif args.tape_in:
            anchors = parse_tape_spec(args.tape_in, unit="in")
        else:
            fit_p.error("provide --tape-in or --tape-cm")
        prof = fit_profile(anchors, raw, name=args.name)
        save_profile(prof, args.out)
        print(f"Saved {args.out}")
        print(f"  scale={prof.scale:.4f}  offset_cm={prof.offset_cm:.2f}")
        print(f"  anchors: {prof.anchors_cm}")
        cal = apply_girth_calibration(raw, prof)
        print("  calibrated girths (cm):", cal)
        inches = {k: round(v / CM_PER_IN, 1) for k, v in cal.items()}
        print("  calibrated girths (in):", inches)
    else:
        prof = load_profile(args.profile)
        cal = apply_girth_calibration(prof.raw_girths_cm, prof)
        print(json.dumps({"profile": prof.name, "girths_cm": cal,
                          "girths_in": {k: round(v / CM_PER_IN, 1) for k, v in cal.items()}}, indent=2))


if __name__ == "__main__":
    main()
