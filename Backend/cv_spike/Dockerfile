FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgl1-mesa-glx curl \
    && rm -rf /var/lib/apt/lists/*

# Full model: more accurate landmarks/segmentation than lite (accuracy > a few seconds here).
ARG POSE_LANDMARKER_URL=https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
RUN mkdir -p models \
    && curl -fsSL -o models/pose_landmarker.task "${POSE_LANDMARKER_URL}"

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY api/ api/
COPY pipeline/ pipeline/

ENV PYTHONUNBUFFERED=1
ENV SCAN_STORAGE_BACKEND=gridfs
ENV BUNDLE_TRY_MESH=0
# Accuracy-first defaults. MediaPipe pose+segmentation on all views; GrabCut is a
# downscaled fallback only. Tune for speed via env if needed.
ENV SCAN_MAX_IMAGE_EDGE=1280
ENV POSE_SINGLE_SCALE=0
ENV POSE_FRONT_ONLY=0
ENV GRABCUT_WORK_EDGE=512
ENV GRABCUT_ITERS=3
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
