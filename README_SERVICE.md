# Whisper Transcription Service

FastAPI REST service for audio transcription using faster-whisper. Deployed on Railway.

**Production URL:** `https://voicer-production.up.railway.app`

## Quick Start

```bash
pip install -r requirements_service.txt
python whisper_service.py
```

Service starts on port from `$PORT` env (default 8080). Swagger UI at `/docs`.

## Architecture

```
whisper_service.py  — FastAPI app, endpoints, background tasks
transcriber.py      — faster-whisper engine, batch/export logic
database.py         — SQLite job/result management
models.py           — Pydantic models, enums
config.yaml         — all configuration
```

## API Endpoints

### Health
```
GET /health
GET /models
```

### Transcription
```
POST /transcribe          — upload audio (multipart/form-data)
POST /transcribe/file     — transcribe by file path (server-side)
POST /transcribe/batch    — batch process directory
POST /transcribe/auto     — auto-process audio_chunks_* dirs from run.py
```

### Job Management
```
GET    /jobs                  — list jobs (query: status, limit, offset)
GET    /jobs/{job_id}         — job status
GET    /jobs/{job_id}/result  — transcription result
DELETE /jobs/{job_id}         — delete job
```

### Export
```
GET /jobs/{job_id}/export/txt
GET /jobs/{job_id}/export/srt
GET /jobs/{job_id}/export/vtt
GET /jobs/{job_id}/export/json
```

### WebSocket
```
WS /ws/{job_id} — real-time progress updates
```

## Supported Audio Formats

Any format supported by ffmpeg: WAV, MP3, MP4, M4A, FLAC, OGG, WebM, etc.

## Models

| Model | Download | RAM (int8) | Speed | Quality |
|-------|----------|------------|-------|---------|
| tiny | 75 MB | ~512 MB | Fastest | Basic |
| base | 142 MB | ~1 GB | Fast | Good |
| small | 466 MB | ~1.5 GB | Moderate | Great |
| medium | 1.5 GB | ~2.5 GB | Slow | Excellent |

Default: `tiny` (Railway free tier). Change via `WHISPER_MODEL` env var.

## Configuration

`config.yaml` — central config. Key env vars:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8080 | Listening port |
| `WHISPER_MODEL` | tiny | Model name |
| `WHISPER_DEVICE` | cpu | cpu/cuda/mps/auto |
| `WHISPER_COMPUTE_TYPE` | int8 | int8/float16/float32 |
| `DB_PATH` | ./transcription_service.db | SQLite path |
| `LOG_LEVEL` | INFO | Logging level |

## Deploy (Railway)

1. Push to GitHub
2. Railway → New Project → Deploy from GitHub
3. Add env vars in Dashboard
4. Generate domain

Dockerfile is optimized for Railway: includes curl for healthcheck, reads `$PORT`.

## Example Usage

```bash
# Upload and transcribe
curl -X POST https://voicer-production.up.railway.app/transcribe \
  -F "file=@audio.wav" \
  -F "language=ru" \
  -F "model=tiny"

# Check status
curl https://voicer-production.up.railway.app/jobs/{job_id}

# Get result
curl https://voicer-production.up.railway.app/jobs/{job_id}/result
```

## Dependencies

`requirements_service.txt`:
- fastapi, uvicorn, python-multipart, websockets
- pydantic, pydantic-settings
- faster-whisper
- aiofiles, PyYAML, tqdm
