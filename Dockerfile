# Stage 1: build the React dashboard
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # outputs to ../backend/static (see vite.config.ts) -> /backend/static

# Stage 2: Python API serving the built dashboard
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
# The owner's voice: Kokoro 82M (Apache-2.0), int8 ONNX, about 120 MB with its voices
ARG KOKORO_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
RUN mkdir -p /models/kokoro && python -c "import sys, urllib.request as u; [u.urlretrieve(f'{sys.argv[1]}/{f}', f'/models/kokoro/{f}') for f in ('kokoro-v1.0.int8.onnx', 'voices-v1.0.bin')]" "$KOKORO_URL"
ENV TTS_MODEL_DIR=/models/kokoro
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir ".[stt,tts]" \
 && python -c "import onnx_asr; onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v2', quantization='int8')" \
 && python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8')"
COPY --from=web /backend/static ./static
RUN mkdir -p /data/files
ENV DATABASE_URL=sqlite:////data/garagedesk.db FILES_DIR=/data/files
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
