"""
Транскрипция engine на базе faster-whisper
"""
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import json

from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment

from models import TranscriptionResult, TranscriptionSegment, WhisperModel as WModel

logger = logging.getLogger(__name__)


class TranscriptionEngine:
    """Движок для транскрипции аудио с помощью faster-whisper"""

    # Информация о моделях
    MODEL_INFO = {
        "tiny": {"size_mb": 75, "speed": "очень быстрая", "accuracy": "низкая"},
        "base": {"size_mb": 145, "speed": "быстрая", "accuracy": "средняя"},
        "small": {"size_mb": 488, "speed": "средняя", "accuracy": "хорошая"},
        "medium": {"size_mb": 1500, "speed": "медленная", "accuracy": "очень хорошая"},
        "large": {"size_mb": 3100, "speed": "очень медленная", "accuracy": "отличная"},
        "large-v2": {"size_mb": 3100, "speed": "очень медленная", "accuracy": "отличная"},
        "large-v3": {"size_mb": 3100, "speed": "очень медленная", "accuracy": "лучшая"},
    }

    def __init__(
        self,
        model_name: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        download_root: Optional[str] = None
    ):
        """
        Инициализация транскрипции engine

        Args:
            model_name: Название модели Whisper
            device: Устройство (cpu/cuda/mps/auto)
            compute_type: Тип вычислений (int8/float16/float32)
            download_root: Директория для моделей
        """
        self.model_name = model_name
        self.device = self._detect_device(device)
        self.compute_type = compute_type
        self.model = None
        self.download_root = download_root

        logger.info(f"Initializing TranscriptionEngine: model={model_name}, device={self.device}")
        self._load_model()

    def _detect_device(self, device: str) -> str:
        """Определить доступное устройство"""
        if device != "auto":
            return device

        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA detected, using GPU")
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                logger.info("MPS (Apple Silicon) detected, using GPU")
                return "mps"
        except ImportError:
            pass

        logger.info("Using CPU")
        return "cpu"

    def _load_model(self):
        """Загрузка модели Whisper"""
        try:
            logger.info(f"Loading Whisper model '{self.model_name}'...")
            start_time = time.time()

            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root
            )

            load_time = time.time() - start_time
            logger.info(f"Model loaded successfully in {load_time:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
        word_timestamps: bool = False,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> TranscriptionResult:
        """
        Транскрибировать один аудио файл

        Args:
            audio_path: Путь к аудио файлу
            language: Язык аудио (None = auto-detect)
            word_timestamps: Включить таймкоды для слов
            vad_filter: Использовать VAD фильтр
            initial_prompt: Начальный промпт для контекста
            progress_callback: Callback для прогресса (0.0-1.0)

        Returns:
            Результат транскрипции
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing: {audio_path}")
        start_time = time.time()

        try:
            # Параметры транскрипции
            transcribe_options = {
                "language": language,
                "word_timestamps": word_timestamps,
                "vad_filter": vad_filter,
            }
            if initial_prompt:
                transcribe_options["initial_prompt"] = initial_prompt

            # Транскрипция
            segments_iter, info = self.model.transcribe(audio_path, **transcribe_options)

            # Собираем сегменты
            segments_list = []
            full_text_parts = []
            total_duration = info.duration

            for i, segment in enumerate(segments_iter):
                # Прогресс
                if progress_callback and total_duration > 0:
                    progress = min(segment.end / total_duration, 1.0)
                    progress_callback(progress)

                # Конвертируем слова если есть
                words_data = None
                if word_timestamps and hasattr(segment, 'words'):
                    words_data = [
                        {
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability
                        }
                        for word in segment.words
                    ]

                segment_data = TranscriptionSegment(
                    id=i,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text.strip(),
                    confidence=segment.avg_logprob if hasattr(segment, 'avg_logprob') else None,
                    words=words_data
                )
                segments_list.append(segment_data)
                full_text_parts.append(segment.text.strip())

            processing_time = time.time() - start_time
            full_text = " ".join(full_text_parts)

            logger.info(
                f"Transcription completed: {len(full_text)} chars, "
                f"{len(segments_list)} segments, {processing_time:.2f}s"
            )

            # Финальный прогресс
            if progress_callback:
                progress_callback(1.0)

            return TranscriptionResult(
                text=full_text,
                segments=segments_list,
                language=info.language,
                duration=info.duration,
                processing_time=processing_time,
                model_used=self.model_name
            )

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def transcribe_batch(
        self,
        audio_files: List[str],
        language: Optional[str] = None,
        merge_results: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Транскрибировать несколько файлов

        Args:
            audio_files: Список путей к аудио файлам
            language: Язык аудио
            merge_results: Объединить результаты в один текст
            progress_callback: Callback (current, total, current_file)

        Returns:
            Словарь с результатами
        """
        logger.info(f"Batch transcription: {len(audio_files)} files")
        results = {}
        all_segments = []
        all_text_parts = []
        total_duration = 0.0
        total_processing_time = 0.0

        for i, audio_file in enumerate(audio_files):
            if progress_callback:
                progress_callback(i, len(audio_files), audio_file)

            try:
                result = self.transcribe_file(audio_file, language=language)
                results[audio_file] = result

                if merge_results:
                    # Смещаем таймкоды на накопленную длительность
                    for segment in result.segments:
                        shifted_segment = segment.model_copy()
                        shifted_segment.start += total_duration
                        shifted_segment.end += total_duration
                        all_segments.append(shifted_segment)

                    all_text_parts.append(result.text)
                    total_duration += result.duration

                total_processing_time += result.processing_time

            except Exception as e:
                logger.error(f"Failed to transcribe {audio_file}: {e}")
                results[audio_file] = {"error": str(e)}

        if progress_callback:
            progress_callback(len(audio_files), len(audio_files), "Completed")

        # Объединенный результат
        merged_result = None
        if merge_results and all_text_parts:
            merged_result = TranscriptionResult(
                text=" ".join(all_text_parts),
                segments=all_segments,
                language=language or "unknown",
                duration=total_duration,
                processing_time=total_processing_time,
                model_used=self.model_name
            )

        return {
            "individual_results": results,
            "merged_result": merged_result,
            "total_files": len(audio_files),
            "successful": sum(1 for r in results.values() if not isinstance(r, dict) or "error" not in r),
            "failed": sum(1 for r in results.values() if isinstance(r, dict) and "error" in r)
        }

    def process_chunks_directory(
        self,
        directory: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> TranscriptionResult:
        """
        Обработать директорию с чанками из run.py

        Args:
            directory: Путь к директории audio_chunks_*
            language: Язык аудио
            progress_callback: Callback для прогресса

        Returns:
            Объединенный результат транскрипции
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        logger.info(f"Processing chunks directory: {directory}")

        # Читаем manifest.json если есть
        manifest_path = dir_path / "manifest.json"
        manifest = None
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            logger.info(f"Found manifest with {len(manifest.get('chunks', []))} chunks")

        # Находим все .wav файлы
        audio_files = sorted(dir_path.glob("*.wav"))
        if not audio_files:
            raise ValueError(f"No .wav files found in {directory}")

        logger.info(f"Found {len(audio_files)} audio files")

        # Транскрибируем
        batch_result = self.transcribe_batch(
            [str(f) for f in audio_files],
            language=language,
            merge_results=True,
            progress_callback=progress_callback
        )

        return batch_result["merged_result"]

    def export_srt(self, result: TranscriptionResult, output_path: str):
        """
        Экспорт в SRT формат субтитров

        Args:
            result: Результат транскрипции
            output_path: Путь к выходному файлу
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(result.segments, start=1):
                # Формат SRT: часы:минуты:секунды,миллисекунды
                start_time = self._format_srt_time(segment.start)
                end_time = self._format_srt_time(segment.end)

                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment.text}\n\n")

        logger.info(f"Exported SRT to {output_path}")

    def export_vtt(self, result: TranscriptionResult, output_path: str):
        """
        Экспорт в WebVTT формат

        Args:
            result: Результат транскрипции
            output_path: Путь к выходному файлу
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")

            for segment in result.segments:
                start_time = self._format_vtt_time(segment.start)
                end_time = self._format_vtt_time(segment.end)

                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment.text}\n\n")

        logger.info(f"Exported VTT to {output_path}")

    def export_json(self, result: TranscriptionResult, output_path: str):
        """
        Экспорт в JSON формат

        Args:
            result: Результат транскрипции
            output_path: Путь к выходному файлу
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

        logger.info(f"Exported JSON to {output_path}")

    def export_txt(self, result: TranscriptionResult, output_path: str):
        """
        Экспорт в простой текстовый формат

        Args:
            result: Результат транскрипции
            output_path: Путь к выходному файлу
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result.text)

        logger.info(f"Exported TXT to {output_path}")

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Форматировать время для SRT (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        """Форматировать время для VTT (00:00:00.000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    @classmethod
    def get_model_info(cls) -> Dict[str, Any]:
        """Получить информацию о всех доступных моделях"""
        return cls.MODEL_INFO
