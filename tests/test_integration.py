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
    "/webhooks",
    "/docs",
    "/openapi.json",
    "/metrics",
]

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
    """Каждый GET-эндпоинт возвращает ответ (не 5xx)."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.get(path)
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


def test_post_endpoints_respond():
    """POST-эндпоинты отвечают ошибкой валидации (422/400) — сервис работает."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        for path in ["/transcribe/file", "/transcribe/batch", "/transcribe/auto", "/webhooks"]:
            r = client.post(path, json={})
            assert r.status_code < 500
