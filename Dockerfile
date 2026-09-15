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

# CPU-only torch first. The default wheel carries the CUDA
# runtime, which adds roughly 2 GB to the image for no benefit
# on a server that only runs the VAD model.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.4.1"

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
COPY app/ ./app/

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# One worker on purpose. The API key pool, its rate limiters,
# and the pipeline thread pool are all per-process state. A
# second uvicorn worker would mean two independent views of the
# same provider quota, and the published limits would stop
# being enforced correctly. Scale with pipeline_workers, or
# move the key accounting into a shared store first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
