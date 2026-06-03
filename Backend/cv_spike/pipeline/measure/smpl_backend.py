"""
SMPL body-mesh recovery backend (V2 measurement engine).

Backends (auto-detected, best first):
  1. obj           -- pre-exported body mesh (.obj/.ply)
  2. four_d_humans -- 4D-Humans / HMR2.0 (personalized SMPL from front photo)
  3. smplx         -- mean SMPL-X template (fallback only)

Install 4D-Humans: bash scripts/setup_4dhumans.sh
SMPL model (not SMPL-X): see models/smpl/README.md
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import numpy as np

from pipeline.measure import mesh_measure

ROOT = Path(__file__).resolve().parents[2]
SMPL_VENDOR_DATA = ROOT / "models" / "smpl" / "basicModel_neutral_lbs_10_207_0_v1.0.0.pkl"
CACHE_4D = Path.home() / ".cache" / "4DHumans"
SMPL_CACHE = CACHE_4D / "data" / "smpl" / "SMPL_NEUTRAL.pkl"


class BackendUnavailable(RuntimeError):
    pass


def _prepare_4dhumans_runtime() -> None:
    """macOS + headless fixes before importing hmr2 (pulls pyrender/OpenGL)."""
    if platform.system() == "Darwin" and "PYOPENGL_PLATFORM" not in os.environ:
        os.environ["PYOPENGL_PLATFORM"] = "osx"


def _ensure_smpl_for_hmr2() -> None:
    """Convert vendor SMPL (py2 pickle) into HMR2 cache as SMPL_NEUTRAL.pkl."""
    if SMPL_CACHE.is_file():
        return
    src = SMPL_VENDOR_DATA if SMPL_VENDOR_DATA.is_file() else ROOT / "models" / "smpl" / "SMPL_NEUTRAL.pkl"
    if not src.is_file():
        return
    SMPL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    from hmr2.models import convert_pkl

    convert_pkl(str(src), str(SMPL_CACHE))


def _load_hmr2_checkpoint(checkpoint_path: str):
    """Load HMR2 for inference only (no pyrender / OpenGL renderer on headless macOS)."""
    import torch
    from pathlib import Path
    from hmr2.configs import get_config
    from hmr2.models import HMR2, check_smpl_exists

    check_smpl_exists()
    _ensure_smpl_for_hmr2()

    model_cfg_path = Path(checkpoint_path).parent.parent / "model_config.yaml"
    model_cfg = get_config(str(model_cfg_path), update_cachedir=True)
    if (model_cfg.MODEL.BACKBONE.TYPE == "vit") and ("BBOX_SHAPE" not in model_cfg.MODEL):
        model_cfg.defrost()
        model_cfg.MODEL.BBOX_SHAPE = [192, 256]
        model_cfg.freeze()

    _orig_load = torch.load

    def _load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_load(*args, **kwargs)

    torch.load = _load
    try:
        model = HMR2.load_from_checkpoint(
            checkpoint_path, strict=False, cfg=model_cfg, init_renderer=False
        )
    finally:
        torch.load = _orig_load
    return model, model_cfg


def obj_available(mesh_path: str | Path | None) -> bool:
    return bool(mesh_path) and Path(mesh_path).is_file()


def four_d_humans_available() -> bool:
    try:
        _prepare_4dhumans_runtime()
        import torch  # noqa: F401
        import hmr2  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def smplx_model_available() -> bool:
    smplx_dir = ROOT / "models" / "smplx"
    try:
        import smplx  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return any(smplx_dir.glob("SMPLX_*.npz")) or any(smplx_dir.glob("SMPLX_*.pkl"))


def recover_mesh_smplx(betas=None, gender: str = "neutral"):
    if not smplx_model_available():
        raise BackendUnavailable("SMPL-X model files not found. See models/smplx/README.md")
    import smplx
    import torch
    import trimesh

    model = smplx.create(str(ROOT / "models"), model_type="smplx", gender=gender, use_pca=False)
    b = torch.tensor(np.asarray(betas, dtype=np.float32)[None, :]) if betas is not None else None
    out = model(betas=b)
    return trimesh.Trimesh(vertices=out.vertices[0].detach().cpu().numpy(), faces=model.faces, process=False)


def recover_mesh_from_obj(mesh_path: str | Path):
    return mesh_measure.load_mesh(mesh_path)


def _person_bbox_xyxy(image_bgr: np.ndarray, margin: float = 0.08) -> np.ndarray:
    """Tight bbox around the person for HMR2 (full-frame box shrinks the body)."""
    from pipeline.measure.markerless import analyze_view

    h, w = image_bgr.shape[:2]
    mask, _, warn = analyze_view(image_bgr)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.array([[0, 0, w, h]], dtype=np.float32)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw, bh = x1 - x0, y1 - y0
    pad_x = int(bw * margin)
    pad_y = int(bh * margin)
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(w - 1, x1 + pad_x)
    y1 = min(h - 1, y1 + pad_y)
    return np.array([[x0, y0, x1, y1]], dtype=np.float32)


def recover_mesh_4d_humans(image_bgr: np.ndarray):
    """
    Recover a personalized SMPL mesh from a front photo using HMR2.0.
    Checkpoints download to ~/.cache/4DHumans on first run.
    """
    if not four_d_humans_available():
        raise BackendUnavailable(
            "4D-Humans not installed. Run: bash scripts/setup_4dhumans.sh"
        )
    _prepare_4dhumans_runtime()
    _ensure_smpl_for_hmr2()

    import torch
    import trimesh
    from hmr2.models import DEFAULT_CHECKPOINT, download_models
    from hmr2.utils import recursive_to
    from hmr2.datasets.vitdet_dataset import ViTDetDataset

    download_models(str(CACHE_4D))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, model_cfg = _load_hmr2_checkpoint(DEFAULT_CHECKPOINT)
    model = model.to(device).eval()

    boxes = _person_bbox_xyxy(image_bgr)
    rgb = image_bgr[:, :, ::-1].copy()
    ds = ViTDetDataset(model_cfg, rgb, boxes)
    batch = recursive_to(next(iter(torch.utils.data.DataLoader(ds, batch_size=1))), device)
    with torch.no_grad():
        out = model(batch)
    verts = out["pred_vertices"][0].cpu().numpy()
    return trimesh.Trimesh(vertices=verts, faces=model.smpl.faces, process=False)


def recover_mesh(
    image_bgr: np.ndarray | None = None,
    mesh_path: str | Path | None = None,
    prefer: str = "auto",
):
    env = os.environ.get("SWAYA_SMPL_BACKEND")
    order = [prefer] if prefer != "auto" else ([env] if env else []) + [
        "obj", "four_d_humans", "smplx"
    ]
    for backend in order:
        if backend == "obj" and obj_available(mesh_path):
            return recover_mesh_from_obj(mesh_path), "obj"
        if backend == "four_d_humans" and image_bgr is not None and four_d_humans_available():
            return recover_mesh_4d_humans(image_bgr), "four_d_humans"
        if backend == "smplx" and smplx_model_available():
            return recover_mesh_smplx(), "smplx_mean"
    raise BackendUnavailable(
        "No mesh backend available. Install 4D-Humans (scripts/setup_4dhumans.sh) "
        "and SMPL model (models/smpl/README.md), or use prefer=photo."
    )


def measure_from_image_or_mesh(
    height_cm: float,
    image_bgr: np.ndarray | None = None,
    mesh_path: str | Path | None = None,
    prefer: str = "auto",
):
    mesh, backend = recover_mesh(image_bgr, mesh_path, prefer)
    return mesh_measure.measure_mesh(mesh, height_cm), backend


def backend_status() -> dict[str, bool]:
    return {
        "four_d_humans": four_d_humans_available(),
        "smplx": smplx_model_available(),
        "smpl_cached": SMPL_CACHE.is_file(),
        "smpl_vendor": SMPL_VENDOR_DATA.is_file() or (ROOT / "models" / "smpl" / "SMPL_NEUTRAL.pkl").is_file(),
    }
