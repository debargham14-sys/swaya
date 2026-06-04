# SMPL model (required for 4D-Humans / HMR2.0)

4D-Humans uses **SMPL** (not SMPL-X). You already have SMPL-X in `models/smplx/`; that is a different model.

1. Register at **https://smplify.is.tue.mpg.de** (or https://smpl.is.tue.mpg.de)
2. Download `basicModel_neutral_lbs_10_207_0_v1.0.0.pkl`
3. Place it at either location (HMR2 checks both):

   ```
   ~/.cache/4DHumans/data/smpl/SMPL_NEUTRAL.pkl
   ```

   or

   ```
   Backend/cv_spike/models/smpl/basicModel_neutral_lbs_10_207_0_v1.0.0.pkl
   ```

   HMR2 will auto-convert/copy to the cache path on first run.

4. First run downloads the HMR2 checkpoint (~1 GB) to `~/.cache/4DHumans/`.

Verify:

```bash
python -c "from pipeline.measure import smpl_backend as s; print(s.four_d_humans_available())"
python scripts/try_4dhumans.py tests/fixtures/profiles/front/dummy_female_01.jpg
```
