"""
Интеграционные тесты: Docker-сервис отвечает на все конепы из документации (OpenAPI).

По умолчанию проверяется продакшен-сервис на Railway. Переопределить URL:
    VOICER_BASE_URL=https://<ваш домен> python -m pytest tests/test_integration.py
"""
import os

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


def test_docs_list_paths():
    """/openapi.json содержит все документированные пути."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in OPENAPI_PATHS:
        assert p in paths, f"missing path {p}"
