import sqlite3

from models import JobStatus


def test_create_job_defaults(db):
    db.create_job("job1", file_path="/tmp/a.wav", language="ru", model="small")
    job = db.get_job("job1")
    assert job.status == JobStatus.PENDING
    assert job.language == "ru"
    assert job.model == "small"


def test_update_job_status_and_completed_at(db):
    db.create_job("job1", language="ru", model="small")
    db.update_job_status("job1", JobStatus.PROCESSING)
    job = db.get_job("job1")
    assert job.status == JobStatus.PROCESSING
    assert job.completed_at is None
    db.update_job_status("job1", JobStatus.COMPLETED)
    assert db.get_job("job1").completed_at is not None


def test_save_and_get_transcription_result(db):
    db.create_job("job1", language="ru", model="small")
    db.update_job_status("job1", JobStatus.COMPLETED)
    segments = [{"id": 0, "start": 0.0, "end": 1.5, "text": "привет"}]
    db.save_transcription("job1", "привет", segments, "ru", 1.5, 0.1, "small")
    job = db.get_job("job1")
    assert job.result is not None
    assert job.result.text == "привет"
    assert job.result.segments[0].text == "привет"
    assert job.result.model_used == "small"


def test_delete_job_removes_rows(db):
    db.create_job("job1", language="ru", model="small")
    db.update_job_status("job1", JobStatus.COMPLETED)
    db.save_transcription("job1", "x", [{"id": 0, "start": 0, "end": 1, "text": "x"}], "ru", 1.0, 0.1, "small")
    assert db.delete_job("job1")
    assert db.get_job("job1") is None


def test_delete_job_no_orphans(db):
    db.create_job("job1", language="ru", model="small")
    db.delete_job("job1")
    with sqlite3.connect(db.db_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM transcriptions WHERE job_id='job1'").fetchone()[0]
    assert n == 0


def test_list_jobs(db):
    db.create_job("job1", language="ru", model="small")
    db.create_job("job2", language="en", model="base")
    assert len(db.list_jobs()) == 2
    assert len(db.list_jobs(status=JobStatus.PENDING)) == 2
    assert len(db.list_jobs(status=JobStatus.COMPLETED)) == 0


def test_statistics(db):
    db.create_job("job1", language="ru", model="small")
    db.create_job("job2", language="ru", model="small")
    db.update_job_status("job2", JobStatus.FAILED, "err")
    stats = db.get_statistics()
    assert stats["total_jobs"] == 2


def test_cleanup_old_jobs(db):
    db.create_job("job1", language="ru", model="small")
    db.update_job_status("job1", JobStatus.COMPLETED)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE jobs SET completed_at = datetime('now', '-40 days')")
        conn.commit()
    assert db.cleanup_old_jobs(30) == 1


def test_webhooks_crud(db):
    webhook_id = db.create_webhook("https://example.com/hook", "job_completed")
    hooks = db.list_webhooks(active=None)
    assert len(hooks) == 1
    assert hooks[0].url == "https://example.com/hook"
    assert hooks[0].event_type == "job_completed"
    assert hooks[0].active is True

    active = db.list_webhooks(active=True)
    assert any(h.id == webhook_id for h in active)

    assert db.delete_webhook(webhook_id)
    assert db.list_webhooks(active=None) == []
    assert not db.delete_webhook(webhook_id)


def test_mark_stale_processing(db):
    db.create_job("old", language="ru", model="small")
    db.create_job("fresh", language="ru", model="small")
    db.update_job_status("old", JobStatus.PROCESSING)
    db.update_job_status("fresh", JobStatus.PROCESSING)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE jobs SET updated_at = datetime('now', '-10 days') WHERE id='old'")
        conn.commit()
    assert db.mark_stale_processing(7) == 1
    assert db.get_job("old").status == JobStatus.FAILED
    assert db.get_job("fresh").status == JobStatus.PROCESSING
