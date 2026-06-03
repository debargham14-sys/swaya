"""
Stage 5 (data) - Order spec sheet + tolerance tiers.

The order spec is everything the QC pipeline compares the finished blouse
against. In production it is loaded from the database using the order_id that
the tailor app obtained from the cutting region's QR code; here it can also be
provided inline as JSON or loaded from ``pipeline/qc/specs/<order_id>.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent / "specs"

# Generic per-tier default tolerance (mm) when a dimension has no explicit entry.
DEFAULT_TIER_TOLERANCE_MM = {"couture": 2.0, "bespoke": 3.0, "express": 5.0}

# Per-dimension tolerances (mm) as (couture, bespoke, express), from the QC checklist.
TOLERANCE_TABLE_MM: dict[str, tuple[float, float, float]] = {
    "bust": (3.0, 5.0, 8.0),
    "underbust": (3.0, 3.0, 3.0),
    "waist": (5.0, 5.0, 5.0),
    "shoulder_width": (3.0, 3.0, 3.0),
    "across_front": (5.0, 5.0, 5.0),
    "across_back": (5.0, 5.0, 5.0),
    "total_length": (5.0, 5.0, 5.0),
    "armhole_depth": (3.0, 3.0, 3.0),
    "armhole_circumference": (5.0, 5.0, 5.0),
    "sleeve_length": (5.0, 5.0, 5.0),
    "bicep": (5.0, 5.0, 5.0),
    "wrist": (3.0, 3.0, 3.0),
}

_TIER_INDEX = {"couture": 0, "bespoke": 1, "express": 2}

# Symmetry tolerance is uniform per the checklist.
SYMMETRY_TOLERANCE_MM = 2.0


def tolerance_mm(dimension: str, tier: str) -> float:
    tier = tier.lower()
    row = TOLERANCE_TABLE_MM.get(dimension)
    if row is not None:
        return row[_TIER_INDEX.get(tier, 1)]
    return DEFAULT_TIER_TOLERANCE_MM.get(tier, 3.0)


@dataclass
class OrderSpec:
    order_id: str
    customer_name: str = ""
    tier: str = "bespoke"          # couture | bespoke | express
    variant: str = "sleeveless"    # sleeveless | full_sleeve
    design_code: str = ""
    fabric: str = ""
    # Target dimensions in mm; circumference dims (bust/underbust/waist...) are
    # stored as full circumference to match the measured 2 x flat-width values.
    target_dims_mm: dict[str, float] = field(default_factory=dict)
    # Construction features expected to be present (Stage 7).
    features: list[dict] = field(default_factory=list)
    special_instructions: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "OrderSpec":
        return cls(
            order_id=str(data.get("order_id", "")),
            customer_name=data.get("customer_name", ""),
            tier=str(data.get("tier", "bespoke")).lower(),
            variant=str(data.get("variant", "sleeveless")),
            design_code=data.get("design_code", ""),
            fabric=data.get("fabric", ""),
            target_dims_mm={k: float(v) for k, v in data.get("target_dims_mm", {}).items()},
            features=list(data.get("features", [])),
            special_instructions=data.get("special_instructions", ""),
        )

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "customer_name": self.customer_name,
            "tier": self.tier,
            "variant": self.variant,
            "design_code": self.design_code,
            "fabric": self.fabric,
            "target_dims_mm": self.target_dims_mm,
            "features": self.features,
            "special_instructions": self.special_instructions,
        }


class OrderRepository:
    """Resolve an OrderSpec from an in-memory registry or the specs/ folder.

    Swap for a Mongo-backed implementation later without changing callers.
    """

    def __init__(self, specs_dir: Path = SPECS_DIR, registry: dict[str, OrderSpec] | None = None) -> None:
        self._specs_dir = specs_dir
        self._registry: dict[str, OrderSpec] = registry or {}

    def register(self, spec: OrderSpec) -> None:
        self._registry[spec.order_id] = spec

    def get(self, order_id: str) -> OrderSpec | None:
        if order_id in self._registry:
            return self._registry[order_id]
        path = self._specs_dir / f"{order_id}.json"
        if path.is_file():
            return OrderSpec.from_dict(json.loads(path.read_text()))
        return None


def load_spec(*, order_id: str | None = None, spec_json: str | dict | None = None,
              repo: OrderRepository | None = None) -> OrderSpec:
    """Resolve a spec from inline JSON (preferred) or an order_id lookup."""
    if spec_json is not None:
        data = spec_json if isinstance(spec_json, dict) else json.loads(spec_json)
        return OrderSpec.from_dict(data)
    if order_id:
        spec = (repo or OrderRepository()).get(order_id)
        if spec is None:
            raise ValueError(f"order spec not found for order_id={order_id!r}")
        return spec
    raise ValueError("provide spec_json or order_id to load an order spec")
