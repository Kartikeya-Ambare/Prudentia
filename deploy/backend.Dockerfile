# Backend API and the scheduler share this image (the scheduler runs scripts/scheduler.py instead of the web server).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt requirements.txt
# The CPU build of PyTorch (no multi-GB CUDA download); the server has no GPU. tzdata is for the scheduler's time zone.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && grep -v '^torch' requirements.txt > requirements.docker.txt \
 && pip install -r requirements.docker.txt tzdata

COPY backend/ .

EXPOSE 8000
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
