FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY api/ api/
COPY pipeline/ pipeline/
COPY models/pose_landmarker.task models/pose_landmarker.task

ENV PYTHONUNBUFFERED=1
ENV SCAN_STORAGE_BACKEND=gridfs
ENV BUNDLE_TRY_MESH=0

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
