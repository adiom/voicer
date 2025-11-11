"""
FastAPI service для транскрипции аудио с faster-whisper
"""
import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from models import (
    TranscriptionRequest, BatchRequest, AutoProcessRequest, JobCreateResponse,
    JobInfo, JobListResponse, HealthResponse, ModelInfo, ExportFormat,
    JobStatus, ErrorResponse
)
from database import Database
from transcriber import TranscriptionEngine

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whisper_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Глобальные объекты
db: Optional[Database] = None
engine: Optional[TranscriptionEngine] = None
config: dict = {}
active_websockets: dict = {}  # job_id -> list of websockets


def load_config(config_path: str = "config.yaml") -> dict:
    """Загрузка конфигурации"""
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    else:
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {
            "whisper": {
                "default_model": "small",
                "default_language": "ru",
                "device": "auto",
                "compute_type": "int8"
            },
            "service": {
                "host": "0.0.0.0",
                "port": 8000,
                "upload_dir": "./uploads",
                "results_dir": "./results"
            },
            "database": {
                "path": "./transcription_service.db"
            }
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global db, engine, config

    # Startup
    logger.info("Starting Whisper Transcription Service...")

    config = load_config()

    # Создаем директории
    os.makedirs(config["service"]["upload_dir"], exist_ok=True)
    os.makedirs(config["service"]["results_dir"], exist_ok=True)

    # Инициализация БД
    db = Database(config["database"]["path"])

    # Инициализация транскрипции engine
    engine = TranscriptionEngine(
        model_name=config["whisper"]["default_model"],
        device=config["whisper"]["device"],
        compute_type=config["whisper"]["compute_type"]
    )

    logger.info("Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down service...")


# Создание FastAPI приложения
app = FastAPI(
    title="Whisper Transcription Service",
    description="REST API для транскрипции аудио с использованием faster-whisper",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    stats = db.get_statistics()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        models_loaded=[engine.model_name],
        active_jobs=stats["active_jobs"],
        total_jobs=stats["total_jobs"]
    )


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """Получить список доступных моделей Whisper"""
    model_info = TranscriptionEngine.get_model_info()
    models = []

    for name, info in model_info.items():
        models.append(ModelInfo(
            name=name,
            size_mb=info["size_mb"],
            speed=info["speed"],
            accuracy=info["accuracy"],
            recommended_for=f"Рекомендуется для: {info['accuracy']} точность, {info['speed']} скорость"
        ))

    return models


# ============================================================================
# SINGLE FILE TRANSCRIPTION
# ============================================================================

@app.post("/transcribe", response_model=JobCreateResponse)
async def transcribe_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: Optional[str] = "ru",
    model: Optional[str] = None
):
    """
    Upload и транскрибирование аудио файла
    """
    # Сохранить загруженный файл
    job_id = str(uuid.uuid4())
    upload_dir = Path(config["service"]["upload_dir"])
    file_path = upload_dir / f"{job_id}_{file.filename}"

    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"File uploaded: {file_path}")

        # Создать задачу
        model_name = model or config["whisper"]["default_model"]
        db.create_job(job_id, str(file_path), language=language, model=model_name)

        # Запустить транскрипцию в фоне
        background_tasks.add_task(process_transcription, job_id, str(file_path), language, model_name)

        return JobCreateResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            message="Transcription job created successfully"
        )

    except Exception as e:
        logger.error(f"Failed to create transcription job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe/file", response_model=JobCreateResponse)
async def transcribe_file(request: TranscriptionRequest, background_tasks: BackgroundTasks):
    """
    Транскрибирование существующего файла по пути
    """
    if not Path(request.file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")

    job_id = str(uuid.uuid4())
    db.create_job(
        job_id,
        request.file_path,
        language=request.language,
        model=request.model.value
    )

    background_tasks.add_task(
        process_transcription,
        job_id,
        request.file_path,
        request.language,
        request.model.value,
        request.word_timestamps,
        request.vad_filter,
        request.initial_prompt
    )

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Transcription job created successfully"
    )


# ============================================================================
# BATCH PROCESSING
# ============================================================================

@app.post("/transcribe/batch", response_model=JobCreateResponse)
async def transcribe_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    """
    Batch обработка директории с аудио файлами
    """
    directory = Path(request.directory)
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Directory not found")

    # Найти аудио файлы
    audio_files = list(directory.glob(request.file_pattern))
    if not audio_files:
        raise HTTPException(status_code=404, detail="No audio files found in directory")

    job_id = str(uuid.uuid4())
    db.create_job(
        job_id,
        directory=str(directory),
        language=request.language,
        model=request.model.value,
        total_items=len(audio_files)
    )

    background_tasks.add_task(
        process_batch_transcription,
        job_id,
        str(directory),
        request.language,
        request.model.value,
        request.file_pattern,
        request.merge_results
    )

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Batch transcription job created for {len(audio_files)} files"
    )


@app.post("/transcribe/auto", response_model=JobCreateResponse)
async def transcribe_auto(request: AutoProcessRequest, background_tasks: BackgroundTasks):
    """
    Автоматическая обработка chunks директорий из run.py
    """
    base_path = Path(request.base_path)
    pattern = request.chunks_pattern

    # Найти все директории с чанками
    chunks_dirs = list(base_path.glob(pattern))
    if not chunks_dirs:
        raise HTTPException(status_code=404, detail=f"No directories matching '{pattern}' found")

    job_id = str(uuid.uuid4())
    db.create_job(
        job_id,
        directory=str(base_path),
        language=request.language,
        model=request.model.value,
        total_items=len(chunks_dirs)
    )

    background_tasks.add_task(
        process_auto_chunks,
        job_id,
        chunks_dirs,
        request.language,
        request.model.value
    )

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Auto-processing {len(chunks_dirs)} chunks directories"
    )


# ============================================================================
# JOB MANAGEMENT
# ============================================================================

@app.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Получить список всех задач
    """
    jobs = db.list_jobs(status=status, limit=limit, offset=offset)
    stats = db.get_statistics()

    return JobListResponse(
        jobs=jobs,
        total=stats["total_jobs"],
        page=offset // limit + 1,
        page_size=limit
    )


@app.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job_status(job_id: str):
    """
    Получить статус конкретной задачи
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@app.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """
    Получить результат транскрипции
    """
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Job is not completed (status: {job.status})")

    if not job.result:
        raise HTTPException(status_code=404, detail="Result not found")

    return job.result


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Удалить задачу
    """
    success = db.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"message": "Job deleted successfully"}


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@app.get("/jobs/{job_id}/export/{format}")
async def export_result(job_id: str, format: ExportFormat):
    """
    Экспорт результата в различные форматы (SRT, VTT, JSON, TXT)
    """
    job = db.get_job(job_id)
    if not job or job.status != JobStatus.COMPLETED or not job.result:
        raise HTTPException(status_code=404, detail="Job result not found")

    results_dir = Path(config["service"]["results_dir"])
    export_file = results_dir / f"{job_id}.{format.value}"

    try:
        if format == ExportFormat.SRT:
            engine.export_srt(job.result, str(export_file))
        elif format == ExportFormat.VTT:
            engine.export_vtt(job.result, str(export_file))
        elif format == ExportFormat.JSON:
            engine.export_json(job.result, str(export_file))
        elif format == ExportFormat.TXT:
            engine.export_txt(job.result, str(export_file))

        return FileResponse(
            path=str(export_file),
            filename=f"{job_id}.{format.value}",
            media_type="application/octet-stream"
        )

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WEBSOCKET FOR REAL-TIME PROGRESS
# ============================================================================

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket для real-time обновлений прогресса
    """
    await websocket.accept()

    # Добавить websocket к активным
    if job_id not in active_websockets:
        active_websockets[job_id] = []
    active_websockets[job_id].append(websocket)

    try:
        while True:
            # Отправлять обновления статуса
            job = db.get_job(job_id)
            if job:
                await websocket.send_json({
                    "job_id": job_id,
                    "status": job.status.value,
                    "progress": job.progress.model_dump(),
                    "error": job.error_message
                })

                # Если задача завершена, закрыть соединение
                if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    break

            await asyncio.sleep(1)  # Обновлять каждую секунду

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
    finally:
        # Удалить из активных
        if job_id in active_websockets:
            active_websockets[job_id].remove(websocket)
            if not active_websockets[job_id]:
                del active_websockets[job_id]


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def notify_websockets(job_id: str):
    """Уведомить все WebSocket соединения о изменении статуса"""
    if job_id in active_websockets:
        job = db.get_job(job_id)
        message = {
            "job_id": job_id,
            "status": job.status.value,
            "progress": job.progress.model_dump() if job.progress else None
        }

        for ws in active_websockets[job_id]:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {e}")


def process_transcription(
    job_id: str,
    file_path: str,
    language: str,
    model: str,
    word_timestamps: bool = False,
    vad_filter: bool = True,
    initial_prompt: Optional[str] = None
):
    """Background задача для транскрипции одного файла"""
    try:
        db.update_job_status(job_id, JobStatus.PROCESSING)

        def progress_callback(progress: float):
            db.update_job_progress(
                job_id,
                int(progress * 100),
                100,
                current_file=Path(file_path).name
            )

        result = engine.transcribe_file(
            file_path,
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt,
            progress_callback=progress_callback
        )

        db.save_transcription(
            job_id,
            result.text,
            [s.model_dump() for s in result.segments],
            result.language,
            result.duration,
            result.processing_time,
            result.model_used
        )

        db.update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        db.update_job_status(job_id, JobStatus.FAILED, str(e))


def process_batch_transcription(
    job_id: str,
    directory: str,
    language: str,
    model: str,
    file_pattern: str,
    merge_results: bool
):
    """Background задача для batch транскрипции"""
    try:
        db.update_job_status(job_id, JobStatus.PROCESSING)

        dir_path = Path(directory)
        audio_files = sorted(dir_path.glob(file_pattern))

        def progress_callback(current: int, total: int, current_file: str):
            db.update_job_progress(job_id, current, total, current_file=current_file)

        batch_result = engine.transcribe_batch(
            [str(f) for f in audio_files],
            language=language,
            merge_results=merge_results,
            progress_callback=progress_callback
        )

        if merge_results and batch_result["merged_result"]:
            result = batch_result["merged_result"]
            db.save_transcription(
                job_id,
                result.text,
                [s.model_dump() for s in result.segments],
                result.language,
                result.duration,
                result.processing_time,
                result.model_used
            )

        db.update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Batch job {job_id} completed: {batch_result['successful']} successful")

    except Exception as e:
        logger.error(f"Batch job {job_id} failed: {e}")
        db.update_job_status(job_id, JobStatus.FAILED, str(e))


def process_auto_chunks(
    job_id: str,
    chunks_dirs: List[Path],
    language: str,
    model: str
):
    """Background задача для авто-обработки chunks директорий"""
    try:
        db.update_job_status(job_id, JobStatus.PROCESSING)

        all_results = []

        for i, chunks_dir in enumerate(chunks_dirs):
            db.update_job_progress(job_id, i, len(chunks_dirs), current_file=str(chunks_dir))

            result = engine.process_chunks_directory(str(chunks_dir), language=language)
            all_results.append(result)

        # Объединить все результаты
        if all_results:
            combined_text = " ".join([r.text for r in all_results])
            combined_segments = []
            total_duration = 0.0

            for result in all_results:
                for segment in result.segments:
                    shifted = segment.model_copy()
                    shifted.start += total_duration
                    shifted.end += total_duration
                    combined_segments.append(shifted)
                total_duration += result.duration

            db.save_transcription(
                job_id,
                combined_text,
                [s.model_dump() for s in combined_segments],
                language,
                total_duration,
                sum(r.processing_time for r in all_results),
                model
            )

        db.update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Auto-chunks job {job_id} completed")

    except Exception as e:
        logger.error(f"Auto-chunks job {job_id} failed: {e}")
        db.update_job_status(job_id, JobStatus.FAILED, str(e))


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    config = load_config()
    uvicorn.run(
        "whisper_service:app",
        host=config["service"]["host"],
        port=config["service"]["port"],
        reload=False,
        log_level="info"
    )
