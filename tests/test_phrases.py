"""
Набор тестовых фраз (tests/data/phrases.json) — загружается и проверяется структура.
"""
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "phrases.json"


def _load_phrases():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_phrases_load():
    phrases = _load_phrases()
    assert phrases, "фразы не загрузились"
    for p in phrases:
        assert p["id"], "пустой id"
        assert p["phrase"], f"пустая фраза: {p['id']}"
        assert p["transcription"], f"пустая расшифровка: {p['id']}"


def test_phrases_ids_unique_and_sorted():
    phrases = _load_phrases()
    ids = [p["id"] for p in phrases]
    assert len(set(ids)) == len(ids), "дубликаты id"
    assert ids == sorted(ids)
