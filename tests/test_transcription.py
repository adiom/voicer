"""
End-to-end тест реальной транскрипции: audio -> text через faster-whisper.

Пропускается, если faster-whisper не установлен (например, локально на Python 3.15).
"""
import math
import struct
import wave

import pytest

faster_whisper = pytest.importorskip("faster_whisper")

from transcriber import TranscriptionEngine  # noqa: E402


@pytest.fixture
def tone_wav(tmp_path):
    """Создать тестовый WAV-файл (1 сек низкого тона) в tmp_path."""
    path = tmp_path / "test.wav"
    sample_rate = 16000
    duration_s = 1.0
    frames = bytearray()
    for i in range(int(sample_rate * duration_s)):
        value = int(2000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        frames += struct.pack("<h", value)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)

    return str(path)


def test_transcribe_file_e2e(tone_wav):
    engine = TranscriptionEngine(model_name="tiny", device="cpu", compute_type="int8")
    result = engine.transcribe_file(tone_wav, language="ru", vad_filter=True)

    assert result.model_used == "tiny"
    assert result.duration > 0
    assert result.text is not None
