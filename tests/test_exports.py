import json

from models import TranscriptionResult, TranscriptionSegment
from transcriber import TranscriptionEngine


def make_result():
    seg = TranscriptionSegment(id=0, start=0.0, end=1.5, text="привет")
    return TranscriptionResult(
        text="привет",
        segments=[seg],
        language="ru",
        duration=1.5,
        processing_time=0.1,
        model_used="small",
    )


def test_export_srt(tmp_path):
    p = tmp_path / "a.srt"
    TranscriptionEngine.export_srt(make_result(), str(p))
    content = p.read_text()
    assert "00:00:00,000 --> 00:00:01,500" in content
    assert "привет" in content


def test_export_vtt(tmp_path):
    p = tmp_path / "a.vtt"
    TranscriptionEngine.export_vtt(make_result(), str(p))
    assert p.read_text().startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.500" in p.read_text()


def test_export_json(tmp_path):
    p = tmp_path / "a.json"
    TranscriptionEngine.export_json(make_result(), str(p))
    data = json.loads(p.read_text())
    assert data["text"] == "привет"
    assert data["segments"][0]["text"] == "привет"


def test_export_txt(tmp_path):
    p = tmp_path / "a.txt"
    TranscriptionEngine.export_txt(make_result(), str(p))
    assert p.read_text() == "привет"
