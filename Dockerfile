FROM python:3.12-slim

# ffmpeg normalizes browser recordings into the 16 kHz mono PCM
# WAV that Silero VAD requires. libgomp1 is a torch runtime
# dependency that the slim image does not ship.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# CPU-only torch (and torchaudio, pinned to the matching
# version) first. The default PyPI wheels carry the CUDA
# runtime, which adds roughly 2 GB to the image for no benefit
# on a server that only runs the VAD model — and, for
# torchaudio specifically, requires a libcudart.so this image
# doesn't have at all, which breaks silero_vad's import at
# build time (it depends on torchaudio with no upper bound, so
# without this pin pip installs whatever the current default
# GPU build is when requirements.txt is processed below).
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.4.1" "torchaudio==2.4.1"

COPY requirements.txt .
RUN pip install -r requirements.txt

# Warm the Silero VAD weights into the image so the first
# request after a deploy does not pay for the download.
RUN python -c "from silero_vad import load_silero_vad; load_silero_vad()"

COPY api/ ./api/
COPY audio/ ./audio/
COPY raw_metrics/ ./raw_metrics/
COPY speech_analysis/ ./speech_analysis/
COPY coaching_engine/ ./coaching_engine/
COPY session_timeline/ ./session_timeline/
COPY visual_analysis/ ./visual_analysis/
COPY visual_coaching/ ./visual_coaching/
COPY progress_report/ ./progress_report/
COPY app/ ./app/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /srv
USER appuser

# Cloud Run injects PORT at container start (default 8080) and
# requires the app to listen on it. No gcloud auth step is
# needed here: Cloud Run attaches a runtime service account and
# credentials are fetched from its metadata server automatically
# (Application Default Credentials), the same mechanism
# google-cloud-storage and the Cloud SQL connector already use in
# app/services/storage.py and app/db/database.py. Grant that
# service account's IAM roles with setup-gcp.sh, not by baking a
# key file into the image.
ENV PORT=8080
EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health')"

# One worker on purpose. The API key pool, its rate limiters,
# and the pipeline thread pool are all per-process state. A
# second uvicorn worker would mean two independent views of the
# same provider quota, and the published limits would stop
# being enforced correctly. Scale with pipeline_workers, or
# move the key accounting into a shared store first. Shell form
# so $PORT is expanded at container start; exec-form CMD would
# pass the literal string "$PORT" to uvicorn instead.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
