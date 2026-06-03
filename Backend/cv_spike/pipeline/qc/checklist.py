"""
Stage 7 - The QC checklist: 47 checks across 8 categories.

This module defines the full check schema (so the report always reports against
the complete checklist) and fills it from the geometric stages:

  - Category 1 (dimensional) <- compare.py
  - Category 2 (symmetry)    <- symmetry.py (partial; finer checks scaffolded)
  - Categories 3-8           <- scaffolded as needs_review (feature / seam /
                                surface / drape / human-eye checks to be added)

Method values: "photo" (flat-lay CV), "hanging" (needs hanging photo),
"human" (needs human inspection).
"""

from __future__ import annotations

from dataclasses import dataclass

PHOTO = "photo"
HANGING = "hanging"
HUMAN = "human"


@dataclass(frozen=True)
class CheckDef:
    id: str
    category: int
    category_name: str
    label: str
    method: str
    dimension: str | None = None  # links to a measured dimension name when applicable


_CAT = {
    1: "Dimensional accuracy",
    2: "Symmetry",
    3: "Construction features",
    4: "Seam quality",
    5: "Surface quality",
    6: "3D drape and fit",
    7: "Customer-specific preferences",
    8: "Internal construction",
}


def _c(id, cat, label, method, dim=None) -> CheckDef:
    return CheckDef(id, cat, _CAT[cat], label, method, dim)


CHECKLIST: list[CheckDef] = [
    # Category 1 - Dimensional accuracy (12)
    _c("bust", 1, "Bust circumference", PHOTO, "bust"),
    _c("underbust", 1, "Underbust circumference", PHOTO, "underbust"),
    _c("waist", 1, "Waist circumference", PHOTO, "waist"),
    _c("shoulder_width", 1, "Shoulder width", PHOTO, "shoulder_width"),
    _c("across_front", 1, "Across front", PHOTO, "across_front"),
    _c("across_back", 1, "Across back", PHOTO, "across_back"),
    _c("total_length", 1, "Total blouse length", PHOTO, "total_length"),
    _c("armhole_depth", 1, "Armhole depth", PHOTO, "armhole_depth"),
    _c("armhole_circumference", 1, "Armhole circumference", PHOTO, "armhole_circumference"),
    _c("sleeve_length", 1, "Sleeve length", PHOTO, "sleeve_length"),
    _c("bicep", 1, "Bicep circumference", PHOTO, "bicep"),
    _c("wrist", 1, "Wrist circumference", PHOTO, "wrist"),
    # Category 2 - Symmetry (8)
    _c("shoulder_seam_symmetry", 2, "Shoulder seam symmetry", PHOTO),
    _c("shoulder_seam_angle", 2, "Shoulder seam angle", PHOTO),
    _c("armhole_symmetry", 2, "Armhole symmetry", PHOTO),
    _c("neckline_symmetry", 2, "Neckline symmetry", PHOTO),
    _c("princess_seam_symmetry", 2, "Princess seam symmetry", PHOTO),
    _c("bust_dart_symmetry", 2, "Bust dart symmetry", PHOTO),
    _c("hem_level", 2, "Hem level", PHOTO),
    _c("side_seam_symmetry", 2, "Side seam symmetry", PHOTO),
    # Category 3 - Construction features (9)
    _c("princess_seam_presence", 3, "Princess seam presence", PHOTO),
    _c("bust_dart_presence", 3, "Bust dart presence and position", PHOTO),
    _c("waist_dart_presence", 3, "Waist dart presence", PHOTO),
    _c("closure_presence", 3, "Closure presence", PHOTO),
    _c("closure_alignment", 3, "Closure alignment", PHOTO),
    _c("lining_presence", 3, "Lining presence", PHOTO),
    _c("trim_piping_presence", 3, "Trim/piping presence", PHOTO),
    _c("embellishment_placement", 3, "Embellishment placement", PHOTO),
    _c("sleeve_attachment", 3, "Sleeve attachment", PHOTO),
    # Category 4 - Seam quality (6)
    _c("seam_puckering", 4, "Visible seam puckering", PHOTO),
    _c("stitch_consistency", 4, "Stitch consistency", HUMAN),
    _c("loose_threads", 4, "Loose threads on outer surface", PHOTO),
    _c("even_seam_allowance", 4, "Even seam allowance", PHOTO),
    _c("backstitch_presence", 4, "Backstitch presence at seam ends", HUMAN),
    _c("seam_type_compliance", 4, "Seam type compliance", HUMAN),
    # Category 5 - Surface quality (5)
    _c("fabric_defects", 5, "Fabric defects visible", PHOTO),
    _c("pressing_quality", 5, "Pressing quality", PHOTO),
    _c("no_visible_interfacing", 5, "No visible interfacing", PHOTO),
    _c("hem_finish", 5, "Hem finish", PHOTO),
    _c("color_consistency", 5, "Color consistency", PHOTO),
    # Category 6 - 3D drape and fit (4)
    _c("sleeve_drape", 6, "Sleeve drape", HANGING),
    _c("side_seam_twist", 6, "Side seam twist", HANGING),
    _c("bust_fullness", 6, "Bust fullness", HANGING),
    _c("hem_evenness_hanging", 6, "Hem evenness when hanging", HANGING),
    # Category 7 - Customer-specific preferences (2)
    _c("custom_features_present", 7, "Custom features present", PHOTO),
    _c("embroidery_design_accuracy", 7, "Embroidery design accuracy", PHOTO),
    # Category 8 - Internal construction (1)
    _c("internal_seam_quality", 8, "Internal seam quality", HUMAN),
]

assert len(CHECKLIST) == 47, f"expected 47 checks, got {len(CHECKLIST)}"

CHECK_BY_ID = {c.id: c for c in CHECKLIST}

# Category-2 checks the silhouette mirror can stand in for until finer detectors land.
_SILHOUETTE_PROXY = {"armhole_symmetry", "neckline_symmetry", "side_seam_symmetry"}
