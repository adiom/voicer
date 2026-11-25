import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import whisper_service
from models import TranscriptionResult, TranscriptionSegment
from transcriber import TranscriptionEngine


class MockEngine(TranscriptionEngine):
    """Инжектируется вместо реального engine: не грузит faster-whisper."""

    def __init__(self, *args, **kwargs):
        self.model_name = kwargs.get("model_name") or (args[0] if args else "small")

    def transcribe_file(self, audio_path, **kwargs):
        assert Path(audio_path).exists()
        return TranscriptionResult(
            text="тестовая транскрипция",
            segments=[TranscriptionSegment(id=0, start=0.0, end=1.0, text="тестовая транскрипция")],
            language=kwargs.get("language") or "ru",
            duration=1.0,
            processing_time=0.01,
            model_used="small",
        )


@pytest.fixture
def client(db, monkeypatch, tmp_path):
    uploads = tmp_path / "uploads"
    results = tmp_path / "results"
    uploads.mkdir()
    results.mkdir()
    config = {
        "whisper": {"default_model": "small", "device": "cpu", "compute_type": "int8"},
        "service": {
            "host": "127.0.0.1",
            "port": 8080,
            "upload_dir": str(uploads),
            "results_dir": str(results),
            "max_upload_size_mb": 500,
        },
        "database": {"path": db.db_path, "auto_cleanup_days": 0},
    }
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(whisper_service, "load_config", lambda *a, **k: config)
    monkeypatch.setattr(whisper_service, "Database", lambda path: db)
    monkeypatch.setattr(whisper_service, "TranscriptionEngine", MockEngine)
    with TestClient(whisper_service.app) as c:
        c.headers["Authorization"] = "Bearer test-key"
        yield c


def wait_completed(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    job = client.get(f"/jobs/{job_id}").json()
    while job["status"] not in ("completed", "failed", "cancelled") and time.time() < deadline:
        time.sleep(0.1)
        job = client.get(f"/jobs/{job_id}").json()
    return job


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_models(client):
    r = client.get("/models")
    assert r.status_code == 200
    assert any(m["name"] == "small" for m in r.json())


def test_transcribe_file_job_lifecycle(client, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake audio")
    r = client.post("/transcribe/file", json={"file_path": str(audio), "language": "ru", "model": "small"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    job = wait_completed(client, job_id)
    assert job["status"] == "completed"

    result = client.get(f"/jobs/{job_id}/result").json()
    assert result["text"] == "тестовая транскрипция"


def test_transcribe_file_not_found(client):
    r = client.post("/transcribe/file", json={"file_path": "/nonexistent/a.wav", "language": "ru"})
    assert r.status_code == 404


def test_export_txt(client, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake audio")
    job_id = client.post("/transcribe/file", json={"file_path": str(audio)}).json()["job_id"]
    wait_completed(client, job_id)
    r = client.get(f"/jobs/{job_id}/export/txt")
    assert r.status_code == 200
    assert "тестовая транскрипция" in r.content.decode("utf-8")


def test_jobs_list_and_delete(client, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake audio")
    job_id = client.post("/transcribe/file", json={"file_path": str(audio)}).json()["job_id"]
    wait_completed(client, job_id)

    jobs = client.get("/jobs").json()
    assert jobs["total"] >= 1

    r = client.delete(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert client.get(f"/jobs/{job_id}").status_code == 404
