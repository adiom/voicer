# Whisper Transcription Service

FastAPI REST service для автоматической транскрипции аудио с использованием **faster-whisper**.

## 🎯 Возможности

- ✅ **Асинхронная обработка** - background tasks для длительных транскрипций
- ✅ **Batch processing** - обработка множества файлов одновременно
- ✅ **Real-time прогресс** - WebSocket для live обновлений
- ✅ **Интеграция с run.py** - автообработка audio_chunks_* директорий
- ✅ **Множественные форматы** - экспорт в TXT, SRT, VTT, JSON
- ✅ **SQLite БД** - управление задачами и результатами
- ✅ **Docker ready** - полная контейнеризация
- ✅ **Production-ready** - CORS, health checks, graceful shutdown

## 📦 Структура проекта

```
voice/
├── whisper_service.py       # FastAPI сервис
├── transcriber.py           # Faster-whisper логика
├── database.py              # SQLite управление
├── models.py                # Pydantic модели
├── config.yaml              # Конфигурация
├── requirements_service.txt # Зависимости
├── Dockerfile               # Docker образ
├── docker-compose.yml       # Orchestration
└── README_SERVICE.md        # Документация
```

## 🚀 Быстрый старт

### Установка

```bash
# Установить зависимости
pip install -r requirements_service.txt

# Или с GPU поддержкой (CUDA)
pip install -r requirements_service.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Запуск сервиса

```bash
# Простой запуск
python whisper_service.py

# Или через uvicorn
uvicorn whisper_service:app --host 0.0.0.0 --port 8000 --reload

# С Docker
docker-compose up -d
```

Сервис будет доступен на `http://localhost:8000`

## 📖 API Документация

После запуска доступна интерактивная документация:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Основные endpoints

#### Health & Info

```bash
# Health check
GET /health

# Список доступных моделей
GET /models
```

#### Транскрипция одного файла

```bash
# Upload и транскрибирование
POST /transcribe
Content-Type: multipart/form-data
{
  "file": <audio.wav>,
  "language": "ru",
  "model": "small"
}

# Транскрибирование существующего файла
POST /transcribe/file
{
  "file_path": "/path/to/audio.wav",
  "language": "ru",
  "model": "small",
  "word_timestamps": false,
  "vad_filter": true
}
```

#### Batch обработка

```bash
# Batch обработка директории
POST /transcribe/batch
{
  "directory": "./audio_files",
  "language": "ru",
  "model": "small",
  "file_pattern": "*.wav",
  "merge_results": true
}

# Автообработка chunks из run.py
POST /transcribe/auto
{
  "chunks_pattern": "audio_chunks_*",
  "base_path": "./",
  "language": "ru",
  "model": "small"
}
```

#### Управление задачами

```bash
# Список всех задач
GET /jobs?status=completed&limit=50&offset=0

# Статус конкретной задачи
GET /jobs/{job_id}

# Получить результат
GET /jobs/{job_id}/result

# Удалить задачу
DELETE /jobs/{job_id}
```

#### Экспорт результатов

```bash
# Экспорт в различные форматы
GET /jobs/{job_id}/export/txt   # Простой текст
GET /jobs/{job_id}/export/srt   # Субтитры SRT
GET /jobs/{job_id}/export/vtt   # WebVTT субтитры
GET /jobs/{job_id}/export/json  # JSON с метаданными
```

#### Real-time прогресс

```javascript
// WebSocket для live обновлений
const ws = new WebSocket('ws://localhost:8000/ws/{job_id}');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Progress:', data.progress.percentage + '%');
  console.log('Status:', data.status);
};
```

## 💡 Примеры использования

### 1. Транскрипция одного файла

```python
import requests

# Создать задачу
response = requests.post('http://localhost:8000/transcribe/file', json={
    'file_path': './audio.wav',
    'language': 'ru',
    'model': 'small'
})

job_id = response.json()['job_id']
print(f"Job created: {job_id}")

# Проверить статус
import time
while True:
    status = requests.get(f'http://localhost:8000/jobs/{job_id}').json()
    print(f"Status: {status['status']} - {status['progress']['percentage']}%")

    if status['status'] == 'completed':
        break
    time.sleep(1)

# Получить результат
result = requests.get(f'http://localhost:8000/jobs/{job_id}/result').json()
print("Transcription:", result['text'])
```

### 2. Batch обработка директории

```python
import requests

response = requests.post('http://localhost:8000/transcribe/batch', json={
    'directory': './my_audio_files',
    'language': 'ru',
    'model': 'small',
    'file_pattern': '*.wav',
    'merge_results': True
})

job_id = response.json()['job_id']
print(f"Batch job started: {job_id}")
```

### 3. Интеграция с run.py

После того как `run.py` создал чанки:

```python
import requests

# Автообработка всех audio_chunks_* директорий
response = requests.post('http://localhost:8000/transcribe/auto', json={
    'chunks_pattern': 'audio_chunks_*',
    'base_path': './',
    'language': 'ru',
    'model': 'small'
})

job_id = response.json()['job_id']
```

### 4. Экспорт субтитров

```python
import requests

# Получить SRT субтитры
response = requests.get(f'http://localhost:8000/jobs/{job_id}/export/srt')

with open('subtitles.srt', 'wb') as f:
    f.write(response.content)
```

### 5. WebSocket мониторинг

```python
import asyncio
import websockets
import json

async def monitor_job(job_id):
    uri = f"ws://localhost:8000/ws/{job_id}"

    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            print(f"Status: {data['status']}")
            print(f"Progress: {data['progress']['percentage']}%")
            print(f"Current file: {data['progress']['current_file']}")

            if data['status'] in ['completed', 'failed']:
                break

asyncio.run(monitor_job('your-job-id'))
```

## ⚙️ Конфигурация

Отредактируйте `config.yaml`:

```yaml
whisper:
  default_model: small  # tiny/base/small/medium/large
  default_language: ru
  device: auto         # cpu/cuda/mps/auto
  compute_type: int8   # int8/float16/float32

service:
  host: 0.0.0.0
  port: 8000
  upload_dir: ./uploads
  results_dir: ./results

database:
  path: ./transcription_service.db
```

## 🐳 Docker

### Сборка и запуск

```bash
# Сборка образа
docker build -t whisper-service .

# Запуск контейнера
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/results:/app/results \
  --name whisper-service \
  whisper-service

# Или через docker-compose
docker-compose up -d
```

### С GPU поддержкой

```yaml
# docker-compose.yml
services:
  whisper-service:
    # ...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 📊 Модели Whisper

| Модель | Размер | Скорость | Точность | Рекомендация |
|--------|--------|----------|----------|--------------|
| tiny | 75 MB | Очень быстрая | Низкая | Тестирование, demo |
| base | 145 MB | Быстрая | Средняя | Черновики, заметки |
| small | 488 MB | Средняя | Хорошая | **Рекомендуется** |
| medium | 1.5 GB | Медленная | Отличная | Высокое качество |
| large | 3.1 GB | Очень медленная | Превосходная | Максимальное качество |
| large-v3 | 3.1 GB | Очень медленная | Лучшая | Production |

## 🔧 Troubleshooting

### Ошибка загрузки модели

```bash
# Предзагрузка модели
python -c "from faster_whisper import WhisperModel; WhisperModel('small')"
```

### Медленная транскрипция

1. Используйте меньшую модель (`tiny`, `base`)
2. Используйте GPU если доступен
3. Уменьшите качество аудио
4. Включите `vad_filter: true`

### Out of memory

1. Уменьшите модель
2. Используйте `compute_type: int8`
3. Обрабатывайте файлы по одному

## 📝 Логирование

Логи доступны:
- В файле: `whisper_service.log`
- В stdout: `docker logs whisper-service`

```python
# Уровень логирования в config.yaml
logging:
  level: INFO  # DEBUG/INFO/WARNING/ERROR
  file: whisper_service.log
```

## 🔐 Production deployment

### Nginx reverse proxy

```nginx
upstream whisper_backend {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://whisper_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://whisper_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Systemd service

```ini
# /etc/systemd/system/whisper-service.service
[Unit]
Description=Whisper Transcription Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/whisper-service
ExecStart=/usr/bin/python3 -m uvicorn whisper_service:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable whisper-service
sudo systemctl start whisper-service
```

## 🤝 Интеграция с run.py

Service автоматически интегрируется с вашим `run.py`:

1. **run.py** создает чанки в `audio_chunks_video1/`
2. **Service** автоматически обнаруживает новые директории
3. Читает `manifest.json` для метаданных
4. Транскрибирует все чанки
5. Объединяет результаты с правильными таймкодами
6. Сохраняет в БД

```python
# Пример: после run.py
import requests

response = requests.post('http://localhost:8000/transcribe/auto', json={
    'chunks_pattern': 'audio_chunks_*',
    'language': 'ru'
})

print(f"Started auto-processing: {response.json()['job_id']}")
```

## 📄 Лицензия

MIT License

## 👨‍💻 Автор

Ваше имя / Команда

## 🔗 Полезные ссылки

- [faster-whisper Documentation](https://github.com/SYSTRAN/faster-whisper)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenAI Whisper](https://github.com/openai/whisper)
