"""
Geometry of the standardized Swaya QC framework.

The QC framework is the perimeter strip torn from an A1 stencil sheet. It is the
SAME for every order: a generic measurement reference (cm scales + four corner
ChArUco/ArUco fiducials + magenta hem & symmetry lines) that the tailor lays
over any finished blouse for QC photography.

All coordinates are in millimetres in the framework's own coordinate system:
  - origin (0, 0) at the TOP-LEFT corner of the sheet
  - +x to the right, +y downward (image convention)

The four corner fiducials are single ArUco markers (DICT_4X4_50) with ids:
    0 = top-left, 1 = top-right, 2 = bottom-right, 3 = bottom-left
This is the robust subset of the "ChArUco corners" design and yields the four
reference points needed for the px <-> mm homography. It can be upgraded to full
ChArUco boards later without changing the engine interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A1 portrait sheet
SHEET_W_MM = 594.0
SHEET_H_MM = 841.0

# Perimeter strip width (the QC framework itself)
PERIMETER_MM = 50.0

# Corner fiducials
FIDUCIAL_MM = 40.0
FIDUCIAL_DICT = "DICT_4X4_50"
# id -> (x, y) of the marker CENTRE in framework mm, clockwise from top-left.
CORNER_INSET_MM = 30.0  # centre inset from the nearest sheet corner


def _corner_centers(w: float, h: float, inset: float) -> dict[int, tuple[float, float]]:
    return {
        0: (inset, inset),                # top-left
        1: (w - inset, inset),            # top-right
        2: (w - inset, h - inset),        # bottom-right
        3: (inset, h - inset),            # bottom-left
    }


@dataclass(frozen=True)
class FrameworkSpec:
    """Physical layout of one QC framework (defaults = standard A1)."""

    sheet_w_mm: float = SHEET_W_MM
    sheet_h_mm: float = SHEET_H_MM
    perimeter_mm: float = PERIMETER_MM
    fiducial_mm: float = FIDUCIAL_MM
    fiducial_dict: str = FIDUCIAL_DICT
    corner_inset_mm: float = CORNER_INSET_MM
    # Fiducial centres (id -> (x_mm, y_mm)). Filled in __post_init__-style factory.
    fiducial_centers_mm: dict[int, tuple[float, float]] = field(
        default_factory=lambda: _corner_centers(SHEET_W_MM, SHEET_H_MM, CORNER_INSET_MM)
    )

    # ---- Inner measurement zone (the hollow centre of the picture frame) ----
    @property
    def zone_x0_mm(self) -> float:
        return self.perimeter_mm

    @property
    def zone_y0_mm(self) -> float:
        return self.perimeter_mm

    @property
    def zone_x1_mm(self) -> float:
        return self.sheet_w_mm - self.perimeter_mm

    @property
    def zone_y1_mm(self) -> float:
        return self.sheet_h_mm - self.perimeter_mm

    @property
    def zone_w_mm(self) -> float:
        return self.zone_x1_mm - self.zone_x0_mm

    @property
    def zone_h_mm(self) -> float:
        return self.zone_y1_mm - self.zone_y0_mm

    @property
    def zone_corners_mm(self) -> list[tuple[float, float]]:
        """Inner-edge rectangle, clockwise from top-left."""
        return [
            (self.zone_x0_mm, self.zone_y0_mm),
            (self.zone_x1_mm, self.zone_y0_mm),
            (self.zone_x1_mm, self.zone_y1_mm),
            (self.zone_x0_mm, self.zone_y1_mm),
        ]

    # ---- Magenta reference lines ----
    @property
    def hem_line_y_mm(self) -> float:
        """Horizontal hem reference, just inside the bottom strip."""
        return self.zone_y1_mm

    @property
    def symmetry_line_x_mm(self) -> float:
        """Vertical alignment reference on the right inside edge.

        Note: this is the tailor's alignment aid. The QC symmetry stage folds
        the blouse along its OWN detected centre axis, not this edge line.
        """
        return self.zone_x1_mm

    @property
    def zone_center_x_mm(self) -> float:
        return (self.zone_x0_mm + self.zone_x1_mm) / 2.0

    def fiducial_ids(self) -> list[int]:
        return sorted(self.fiducial_centers_mm.keys())

    def to_dict(self) -> dict:
        return {
            "sheet_w_mm": self.sheet_w_mm,
            "sheet_h_mm": self.sheet_h_mm,
            "perimeter_mm": self.perimeter_mm,
            "fiducial_mm": self.fiducial_mm,
            "fiducial_dict": self.fiducial_dict,
            "fiducial_centers_mm": {str(k): list(v) for k, v in self.fiducial_centers_mm.items()},
            "zone_mm": {
                "x0": self.zone_x0_mm,
                "y0": self.zone_y0_mm,
                "x1": self.zone_x1_mm,
                "y1": self.zone_y1_mm,
            },
            "hem_line_y_mm": self.hem_line_y_mm,
            "symmetry_line_x_mm": self.symmetry_line_x_mm,
        }


STANDARD_A1 = FrameworkSpec()
