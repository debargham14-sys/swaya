# SMPL-X model files (license-gated — you must download)

The engine's 3D backend needs the SMPL-X body model, which is **not redistributable**.

1. Register and accept the license at **https://smpl-x.is.tue.mpg.de**
2. Download the SMPL-X models and place here:
   ```
   models/smplx/SMPLX_NEUTRAL.npz   (and/or SMPLX_MALE.npz, SMPLX_FEMALE.npz)
   ```
3. Verify:
   ```bash
   python -c "from pipeline import smpl_backend as s; print(s.smplx_model_available())"  # -> True
   ```

Once present, the unified engine auto-uses the 3D mesh path:
```bash
python -m pipeline.measure_engine --front F.jpg --side S.jpg --height 166 --weight 49 --prefer smplx
```

## For per-person shape from photos (not just the mean body)
Install a fitter that predicts SMPL-X shape `betas` from images:
```bash
pip install "git+https://github.com/shubham-goel/4D-Humans.git"  # HMR2.0 (needs detectron2)
```
(Also requires the SMPL model above.) The recovered mesh both yields girths and
drives the 3D try-on avatar.
