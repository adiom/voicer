"""
SQLite database management для Whisper Transcription Service
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import contextmanager

from models import JobStatus, JobInfo, TranscriptionResult, JobProgress

logger = logging.getLogger(__name__)


class Database:
    """Менеджер SQLite базы данных для транскрипций"""

    def __init__(self, db_path: str = "./transcription_service.db"):
        """
        Инициализация базы данных

        Args:
            db_path: Путь к файлу SQLite базы данных
        """
        self.db_path = db_path
        self._init_database()

    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Создание таблиц если их нет"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица задач
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    file_path TEXT,
                    directory TEXT,
                    language TEXT NOT NULL,
                    model TEXT NOT NULL,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    progress_percentage REAL DEFAULT 0.0,
                    current_file TEXT,
                    speed_factor REAL,
                    eta_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT
                )
            """)

            # Таблица результатов транскрипции
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    job_id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    segments_json TEXT NOT NULL,
                    language TEXT NOT NULL,
                    duration REAL NOT NULL,
                    processing_time REAL NOT NULL,
                    model_used TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
                )
            """)

            # Таблица ошибок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    error_details TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
                )
            """)

            # Индексы для быстрого поиска
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_job ON errors(job_id)")

            logger.info(f"Database initialized at {self.db_path}")

    def create_job(
        self,
        job_id: str,
        file_path: Optional[str] = None,
        directory: Optional[str] = None,
        language: str = "ru",
        model: str = "small",
        total_items: int = 1
    ) -> str:
        """
        Создать новую задачу транскрипции

        Args:
            job_id: Уникальный ID задачи
            file_path: Путь к файлу (для single file)
            directory: Путь к директории (для batch)
            language: Язык транскрипции
            model: Модель Whisper
            total_items: Всего элементов для обработки

        Returns:
            ID созданной задачи
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (
                    id, status, file_path, directory, language, model,
                    progress_current, progress_total, progress_percentage,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, JobStatus.PENDING.value, file_path, directory, language, model,
                0, total_items, 0.0, now, now
            ))

        logger.info(f"Created job {job_id}: file={file_path}, dir={directory}, model={model}")
        return job_id

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None
    ):
        """
        Обновить статус задачи

        Args:
            job_id: ID задачи
            status: Новый статус
            error_message: Сообщение об ошибке (если есть)
        """
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            if status == JobStatus.COMPLETED or status == JobStatus.FAILED:
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, updated_at = ?, completed_at = ?
                    WHERE id = ?
                """, (status.value, error_message, now, now, job_id))
            else:
                cursor.execute("""
                    UPDATE jobs
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE id = ?
                """, (status.value, error_message, now, job_id))

            # Если есть ошибка, записать в таблицу ошибок
            if error_message and status == JobStatus.FAILED:
                cursor.execute("""
                    INSERT INTO errors (job_id, error_message, timestamp)
                    VALUES (?, ?, ?)
                """, (job_id, error_message, now))

        logger.info(f"Job {job_id} status updated to {status.value}")

    def update_job_progress(
        self,
        job_id: str,
        current: int,
        total: int,
        current_file: Optional[str] = None,
        speed_factor: Optional[float] = None,
        eta_seconds: Optional[float] = None
    ):
        """
        Обновить прогресс задачи

        Args:
            job_id: ID задачи
            current: Текущий прогресс
            total: Всего элементов
            current_file: Текущий обрабатываемый файл
            speed_factor: Скорость обработки
            eta_seconds: Оценка времени завершения
        """
        percentage = (current / total * 100.0) if total > 0 else 0.0
        now = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs
                SET progress_current = ?,
                    progress_total = ?,
                    progress_percentage = ?,
                    current_file = ?,
                    speed_factor = ?,
                    eta_seconds = ?,
                    updated_at = ?
                WHERE id = ?
            """, (current, total, percentage, current_file, speed_factor, eta_seconds, now, job_id))

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """
        Получить информацию о задаче

        Args:
            job_id: ID задачи

        Returns:
            Информация о задаче или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Получить результат транскрипции если есть
            result = None
            if row['status'] == JobStatus.COMPLETED.value:
                cursor.execute("SELECT * FROM transcriptions WHERE job_id = ?", (job_id,))
                trans_row = cursor.fetchone()
                if trans_row:
                    result = TranscriptionResult(
                        text=trans_row['text'],
                        segments=json.loads(trans_row['segments_json']),
                        language=trans_row['language'],
                        duration=trans_row['duration'],
                        processing_time=trans_row['processing_time'],
                        model_used=trans_row['model_used']
                    )

            return JobInfo(
                id=row['id'],
                status=JobStatus(row['status']),
                file_path=row['file_path'],
                directory=row['directory'],
                language=row['language'],
                model=row['model'],
                progress=JobProgress(
                    current=row['progress_current'],
                    total=row['progress_total'],
                    percentage=row['progress_percentage'],
                    current_file=row['current_file'],
                    speed_factor=row['speed_factor'],
                    eta_seconds=row['eta_seconds']
                ),
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                error_message=row['error_message'],
                result=result
            )

    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobInfo]:
        """
        Получить список задач

        Args:
            status: Фильтр по статусу
            limit: Максимальное количество
            offset: Смещение

        Returns:
            Список задач
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (status.value, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM jobs
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            rows = cursor.fetchall()
            jobs = []

            for row in rows:
                jobs.append(JobInfo(
                    id=row['id'],
                    status=JobStatus(row['status']),
                    file_path=row['file_path'],
                    directory=row['directory'],
                    language=row['language'],
                    model=row['model'],
                    progress=JobProgress(
                        current=row['progress_current'],
                        total=row['progress_total'],
                        percentage=row['progress_percentage'],
                        current_file=row['current_file'],
                        speed_factor=row['speed_factor'],
                        eta_seconds=row['eta_seconds']
                    ),
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message']
                ))

            return jobs

    def save_transcription(
        self,
        job_id: str,
        text: str,
        segments: List[Dict[str, Any]],
        language: str,
        duration: float,
        processing_time: float,
        model_used: str
    ):
        """
        Сохранить результат транскрипции

        Args:
            job_id: ID задачи
            text: Полный текст
            segments: Сегменты с таймкодами
            language: Язык
            duration: Длительность аудио
            processing_time: Время обработки
            model_used: Использованная модель
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO transcriptions (
                    job_id, text, segments_json, language,
                    duration, processing_time, model_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, text, json.dumps(segments), language,
                duration, processing_time, model_used
            ))

        logger.info(f"Saved transcription for job {job_id}: {len(text)} chars, {len(segments)} segments")

    def delete_job(self, job_id: str) -> bool:
        """
        Удалить задачу

        Args:
            job_id: ID задачи

        Returns:
            True если удалена успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Deleted job {job_id}")
        return deleted

    def get_statistics(self) -> Dict[str, Any]:
        """
        Получить статистику по задачам

        Returns:
            Словарь со статистикой
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Общее количество задач по статусам
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM jobs
                GROUP BY status
            """)
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # Среднее время обработки
            cursor.execute("""
                SELECT AVG(processing_time) as avg_time
                FROM transcriptions
            """)
            avg_time = cursor.fetchone()['avg_time'] or 0.0

            # Всего транскрибировано аудио (в секундах)
            cursor.execute("""
                SELECT SUM(duration) as total_duration
                FROM transcriptions
            """)
            total_duration = cursor.fetchone()['total_duration'] or 0.0

            return {
                "total_jobs": sum(status_counts.values()),
                "by_status": status_counts,
                "avg_processing_time": avg_time,
                "total_audio_duration": total_duration,
                "active_jobs": status_counts.get(JobStatus.PROCESSING.value, 0) +
                              status_counts.get(JobStatus.PENDING.value, 0)
            }

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Удалить старые завершённые/упавшие задачи

        Args:
            days: Удалять задачи старше N дней

        Returns:
            Количество удалённых задач
        """
        if days <= 0:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Найти старые задачи
            cursor.execute("""
                SELECT id FROM jobs
                WHERE status IN (?, ?, ?)
                AND datetime(completed_at) < datetime('now', ?)
            """, (
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                f'-{days} days'
            ))
            old_job_ids = [row['id'] for row in cursor.fetchall()]

            if not old_job_ids:
                return 0

            # Удалить связанные транскрипции
            placeholders = ','.join(['?'] * len(old_job_ids))
            cursor.execute(f"DELETE FROM transcriptions WHERE job_id IN ({placeholders})", old_job_ids)
            cursor.execute(f"DELETE FROM errors WHERE job_id IN ({placeholders})", old_job_ids)
            cursor.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", old_job_ids)

            deleted = len(old_job_ids)
            logger.info(f"Cleaned up {deleted} old jobs (>{days} days)")
            return deleted
