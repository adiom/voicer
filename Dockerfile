# Whisper Transcription Service Dockerfile

FROM python:3.11-slim

# Метаданные
LABEL maintainer="Your Name"
LABEL description="FastAPI service for audio transcription using faster-whisper"
LABEL version="1.0.0"

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование requirements и установка Python зависимостей
COPY requirements_service.txt .
RUN pip install --no-cache-dir -r requirements_service.txt

# Копирование кода приложения
COPY models.py .
COPY database.py .
COPY transcriber.py .
COPY whisper_service.py .
COPY config.yaml .

# Создание необходимых директорий
RUN mkdir -p /app/uploads /app/results /app/data

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=8000
ENV DB_PATH=/app/data/transcription_service.db

# Порт
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Запуск сервиса
CMD ["python", "-m", "uvicorn", "whisper_service:app", "--host", "0.0.0.0", "--port", "8000"]
