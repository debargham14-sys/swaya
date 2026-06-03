"""
Swaya QC (quality-check) engine.

A staged computer-vision pipeline that inspects a finished blouse photographed
inside the standardized QC framework, then compares it against the order's spec
sheet and emits a structured QC report.

Mirrors the body-measurement engine in ``pipeline/measure_engine.py``:
dataclass results with ``.to_dict()``, an orchestrator (``qc_engine.run_qc``),
and a CLI ``main()``.
"""

from __future__ import annotations
