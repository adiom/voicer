"""
Pydantic модели для Whisper Transcription Service
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class JobStatus(str, Enum):
    """Статусы задач транскрипции"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WhisperModel(str, Enum):
    """Доступные модели Whisper"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"


class TranscriptionSegment(BaseModel):
    """Сегмент транскрипции с таймкодами"""
    id: int
    start: float = Field(..., description="Время начала в секундах")
    end: float = Field(..., description="Время окончания в секундах")
    text: str = Field(..., description="Текст сегмента")
    confidence: Optional[float] = Field(None, description="Уровень уверенности")
    words: Optional[List[Dict[str, Any]]] = Field(None, description="Отдельные слова с таймкодами")


class TranscriptionRequest(BaseModel):
    """Запрос на транскрипцию одного файла"""
    file_path: str = Field(..., description="Путь к аудио файлу")
    language: Optional[str] = Field("ru", description="Язык аудио (ISO 639-1)")
    model: Optional[WhisperModel] = Field(WhisperModel.SMALL, description="Модель Whisper")
    word_timestamps: bool = Field(False, description="Включить таймкоды для слов")
    vad_filter: bool = Field(True, description="Использовать VAD фильтр")
    initial_prompt: Optional[str] = Field(None, description="Начальный промпт для контекста")

    @validator('language')
    def validate_language(cls, v):
        if v and len(v) not in [2, 3]:
            raise ValueError("Язык должен быть в формате ISO 639-1/639-3 (например, 'ru', 'en')")
        return v.lower() if v else v


class BatchRequest(BaseModel):
    """Запрос на batch обработку директории"""
    directory: str = Field(..., description="Путь к директории с аудио файлами")
    language: Optional[str] = Field("ru", description="Язык аудио")
    model: Optional[WhisperModel] = Field(WhisperModel.SMALL, description="Модель Whisper")
    file_pattern: Optional[str] = Field("*.wav", description="Паттерн для фильтрации файлов")
    merge_results: bool = Field(True, description="Объединить результаты всех файлов")
    read_manifest: bool = Field(True, description="Читать manifest.json если есть")
    parallel: bool = Field(False, description="Параллельная обработка файлов")


class AutoProcessRequest(BaseModel):
    """Запрос на авто-обработку chunks из run.py"""
    chunks_pattern: Optional[str] = Field("audio_chunks_*", description="Паттерн директорий chunks")
    base_path: Optional[str] = Field("./", description="Базовая директория для поиска")
    language: Optional[str] = Field("ru", description="Язык аудио")
    model: Optional[WhisperModel] = Field(WhisperModel.SMALL, description="Модель Whisper")


class TranscriptionResult(BaseModel):
    """Результат транскрипции"""
    text: str = Field(..., description="Полный текст транскрипции")
    segments: List[TranscriptionSegment] = Field(default_factory=list, description="Сегменты с таймкодами")
    language: str = Field(..., description="Определенный язык")
    duration: float = Field(..., description="Длительность аудио в секундах")
    processing_time: float = Field(..., description="Время обработки в секундах")
    model_used: str = Field(..., description="Использованная модель")


class JobProgress(BaseModel):
    """Прогресс выполнения задачи"""
    current: int = Field(0, description="Текущий прогресс")
    total: int = Field(0, description="Всего элементов")
    percentage: float = Field(0.0, description="Процент выполнения")
    current_file: Optional[str] = Field(None, description="Текущий обрабатываемый файл")
    speed_factor: Optional[float] = Field(None, description="Скорость обработки (audio_sec/real_sec)")
    eta_seconds: Optional[float] = Field(None, description="Оценочное время завершения")


class JobInfo(BaseModel):
    """Информация о задаче транскрипции"""
    id: str = Field(..., description="ID задачи")
    status: JobStatus = Field(..., description="Статус задачи")
    file_path: Optional[str] = Field(None, description="Путь к файлу")
    directory: Optional[str] = Field(None, description="Директория (для batch)")
    language: str = Field(..., description="Язык транскрипции")
    model: str = Field(..., description="Модель Whisper")
    progress: JobProgress = Field(default_factory=JobProgress, description="Прогресс выполнения")
    created_at: datetime = Field(default_factory=datetime.now, description="Время создания")
    updated_at: datetime = Field(default_factory=datetime.now, description="Время обновления")
    completed_at: Optional[datetime] = Field(None, description="Время завершения")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")
    result: Optional[TranscriptionResult] = Field(None, description="Результат транскрипции")


class JobCreateResponse(BaseModel):
    """Ответ при создании задачи"""
    job_id: str = Field(..., description="ID созданной задачи")
    status: JobStatus = Field(..., description="Начальный статус")
    message: str = Field(..., description="Сообщение")


class JobListResponse(BaseModel):
    """Список задач"""
    jobs: List[JobInfo] = Field(..., description="Список задач")
    total: int = Field(..., description="Всего задач")
    page: int = Field(1, description="Номер страницы")
    page_size: int = Field(50, description="Размер страницы")


class HealthResponse(BaseModel):
    """Health check ответ"""
    status: str = Field(..., description="Статус сервиса")
    version: str = Field(..., description="Версия сервиса")
    models_loaded: List[str] = Field(default_factory=list, description="Загруженные модели")
    active_jobs: int = Field(0, description="Активные задачи")
    total_jobs: int = Field(0, description="Всего задач")


class ModelInfo(BaseModel):
    """Информация о модели Whisper"""
    name: str = Field(..., description="Название модели")
    size_mb: int = Field(..., description="Размер модели в МБ")
    speed: str = Field(..., description="Относительная скорость")
    accuracy: str = Field(..., description="Относительная точность")
    recommended_for: str = Field(..., description="Рекомендации по использованию")


class ExportFormat(str, Enum):
    """Форматы экспорта"""
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    JSON = "json"


class ErrorResponse(BaseModel):
    """Стандартный ответ об ошибке"""
    error: str = Field(..., description="Тип ошибки")
    message: str = Field(..., description="Сообщение об ошибке")
    details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные детали")
