# AGENTS.md

## What this is

FastAPI service for audio transcription using **faster-whisper**. Python 3.11, SQLite, single flat structure (no packages/monorepo). Integrates with an external `run.py` that produces `audio_chunks_*` directories with `manifest.json` files.

## Quick commands

```bash
# Install deps
pip install -r requirements_service.txt

# Run locally
python whisper_service.py
# or
uvicorn whisper_service:app --host 0.0.0.0 --port 8000 --reload

# Docker
docker-compose up -d
```

Service runs on port **8000**. Swagger docs at `/docs`.

## Architecture

| File | Role |
|---|---|
| `whisper_service.py` | FastAPI app, endpoints, background task orchestration |
| `transcriber.py` | `TranscriptionEngine` — faster-whisper wrapper, export to SRT/VTT/TXT/JSON |
| `models.py` | Pydantic models and enums (`JobStatus`, `WhisperModel`, request/response schemas) |
| `database.py` | `Database` — SQLite with auto-schema init, job CRUD, transcription storage |
| `config.yaml` | All runtime config (whisper model, device, paths, CORS, logging) |

`whisper_service.py` owns the global `engine` (TranscriptionEngine) and `db` (Database), initialized in the FastAPI `lifespan` handler. Background tasks run transcription synchronously — the FastAPI process handles one transcription at a time.

## Config defaults you should know

- Default model: `small`, language: `ru`, device: `auto` (CUDA > MPS > CPU), compute: `int8`
- VAD filter: on by default
- Upload dir: `./uploads`, results dir: `./results`
- DB path: `./transcription_service.db`
- Max upload: 500 MB

## Gotchas

- **No tests, no linter, no typecheck** configured. There is no CI.
- **No `requirements.txt`** — use `requirements_service.txt` only.
- Background transcription tasks are synchronous and block the worker. Only 1 worker by default (`workers: 1` in config). Setting `reload=True` with uvicorn uses 1 worker anyway.
- Model is loaded once at startup into `engine.model`. Changing config requires restart.
- `TranscriptionResult.segments` is stored as JSON string in SQLite (`segments_json` column) — not a native type.
- The `process_chunks_directory` method in `transcriber.py` only looks for `*.wav` files, not all audio formats.
- `whisper_service.log` is written to CWD on every start — not cleaned up between runs.
- Docker compose mounts `whisper-models` volume to avoid re-downloading models. The `.cache/huggingface` path is for the container, not the host.

## External integration

The service expects chunk directories from `run.py` at the project root (or configurable `base_path`). Use `POST /transcribe/auto` with `chunks_pattern: "audio_chunks_*"` to process them. Each chunk dir should contain `.wav` files and optionally a `manifest.json`.

## Code conventions

- Russian comments and log messages throughout
- Pydantic v2 (`model_dump()`, `model_copy()`)
- No type checking enforced; types are hints only
- SQLite accessed via context manager with auto-commit/rollback
