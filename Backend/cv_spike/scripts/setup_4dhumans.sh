#!/usr/bin/env bash
# Install 4D-Humans (HMR2.0) into the project venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

export PIP_NO_COMPILE=1
pip install -q wheel setuptools
pip install -q gdown yacs einops timm webdataset dill pandas scikit-image pyrender pytorch-lightning omegaconf rtree
pip install -q --no-build-isolation "git+https://github.com/mattloper/chumpy"

if [[ ! -d vendor/4D-Humans ]]; then
  git clone --depth 1 https://github.com/shubham-goel/4D-Humans.git vendor/4D-Humans
fi
pip install -q --no-build-isolation vendor/4D-Humans

echo ""
echo "4D-Humans installed. Next steps:"
echo "  1. Download SMPL neutral model -> see models/smpl/README.md"
echo "  2. Run: python scripts/try_4dhumans.py tests/fixtures/profiles/front/dummy_female_01.jpg"
echo "  3. API: prefer=four_d_humans (height inferred from ArUco if omitted)"
