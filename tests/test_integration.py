"""
Интеграционные тесты: Docker-сервис отвечает на все конепы из документации (OpenAPI).

По умолчанию проверяется продакшен-сервис на Railway. Переопределить URL:
    VOICER_BASE_URL=https://<ваш домен> python -m pytest tests/test_integration.py
"""
import math
import os
import struct
import time
import wave
from io import BytesIO

import httpx
import pytest

BASE_URL = os.environ.get(
    "VOICER_BASE_URL",
    "https://voicer-production-769f94d8.up.railway.app",
)

GET_ENDPOINTS = [
    "/health",
    "/models",
    "/jobs",
    "/jobs/{job_id}",
    "/jobs/{job_id}/result",
    "/jobs/{job_id}/export/{format}",
    "/webhooks",
    "/docs",
    "/openapi.json",
    "/metrics",
]

POST_ENDPOINTS = [
    "/transcribe",
    "/transcribe/file",
    "/transcribe/batch",
    "/transcribe/auto",
    "/webhooks",
]

DELETE_ENDPOINTS = [
    "/jobs/{job_id}",
    "/webhooks/{webhook_id}",
]

EXPORT_FORMATS = ["txt", "srt", "vtt", "json"]

OPENAPI_PATHS = [
    "/health",
    "/models",
    "/transcribe",
    "/transcribe/file",
    "/transcribe/batch",
    "/transcribe/auto",
    "/jobs",
    "/jobs/{job_id}",
    "/jobs/{job_id}/result",
    "/jobs/{job_id}/export/{format}",
    "/webhooks",
    "/webhooks/{webhook_id}",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoint_responds(path):
    """GET-эндпоинт отвечает (не 5xx)."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get(path.format(job_id="test-job-id", webhook_id="test-webhook-id", format="txt"))
    assert r.status_code < 500


@pytest.mark.parametrize("fmt", EXPORT_FORMATS)
def test_export_endpoints_respond(fmt):
    """GET /jobs/{job_id}/export/{format} для всех форматов."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get(f"/jobs/test-job-id/export/{fmt}")
    assert r.status_code < 500


@pytest.mark.parametrize("path", POST_ENDPOINTS)
def test_post_endpoint_responds(path):
    """POST-эндпоинт отвечает (не 5xx)."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.post(path, json={})
    assert r.status_code < 500


@pytest.mark.parametrize("path", DELETE_ENDPOINTS)
def test_delete_endpoint_responds(path):
    """DELETE-эндпоинт отвечает (не 5xx)."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.delete(path.format(job_id="test-job-id", webhook_id="test-webhook-id"))
    assert r.status_code < 500


def test_health_ok():
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"


def _tone_wav_bytes():
    """Минимальный WAV в памяти (1 сек низкого тона, 16кГц mono)."""
    buf = BytesIO()
    sample_rate = 16000
    frames = bytearray()
    for i in range(sample_rate):
        frames += struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)
    return buf.getvalue()


def test_transcription_via_docker():
    """Docker-сервис возвращает расшифровку загруженного аудио:
    POST /transcribe -> поллинг /jobs/{job_id} -> /jobs/{job_id}/result (text)."""
    wav = _tone_wav_bytes()
    token = os.environ.get("VOICER_API_KEY", "test")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        r = client.post(
            "/transcribe",
            files={"file": ("test.wav", wav, "audio/wav")},
            headers=headers,
        )
        assert r.status_code < 500
        job_id = r.json()["job_id"]

        deadline = time.time() + 90
        jr = None
        while time.time() < deadline:
            jr = client.get(f"/jobs/{job_id}", headers=headers)
            if jr.status_code == 200 and jr.json()["status"] in ("completed", "failed"):
                break
            time.sleep(2)

        assert jr is not None and jr.status_code == 200
        status = jr.json()["status"]
        assert status == "completed", f"job failed: {jr.json().get('error_message')}"

        rr = client.get(f"/jobs/{job_id}/result", headers=headers)
        assert rr.status_code == 200
        assert isinstance(rr.json()["text"], str)


def test_docs_list_paths():
    """/openapi.json содержит все документированные пути."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in OPENAPI_PATHS:
        assert p in paths, f"missing path {p}"
