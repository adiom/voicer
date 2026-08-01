FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements_service.txt .
RUN pip install --no-cache-dir -r requirements_service.txt

COPY models.py .
COPY database.py .
COPY transcriber.py .
COPY whisper_service.py .
COPY config.yaml .

RUN mkdir -p /app/uploads /app/results /app/data

ENV PYTHONUNBUFFERED=1
ENV SERVICE_HOST=0.0.0.0
ENV WHISPER_MODEL=tiny
ENV WHISPER_DEVICE=cpu
ENV WHISPER_COMPUTE_TYPE=int8
ENV DB_PATH=/tmp/transcription_service.db

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

CMD ["python", "whisper_service.py"]
