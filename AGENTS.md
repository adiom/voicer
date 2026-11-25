# AGENTS.md

Короткая справка для будущих агентов: как запускать, тестировать, деплоить и какие неочевидные подвохи присутствуют.

## Запуск сервиса

- Зависимости: `pip install -r requirements_service.txt`
- Запуск: `python3 whisper_service.py` (или `uvicorn whisper_service:app`). Читает `PORT` (Railway его задаёт; Dockerfile выставляет `ENV PORT=8080`).
- Конфиг: `config.yaml` (default_model `tiny` — по умолчанию под free-план Railway; `service.port: 8080`).
- Лог-файл `whisper_service.log` пишется в cwd — gitignored, не коммитить.
- `API_KEY` (из `.env`) — без него большинство эндпоинтов доступны, почти все под `Depends(verify_api_key)`.

## Тесты

- Основной запуск: `python3 -m pytest tests/ -q`
  - `tests/test_database.py` — логика базы данных (SQLite в tmp)
  - `tests/test_exports.py` — экспорт srt/vtt/json/txt
  - `tests/test_service.py` — жизненный цикл задач через `TestClient` (in-process, **без Docker**), часть тестов с `MockEngine`
  - `tests/test_phrases.py` + `tests/data/phrases.json` — набор фраз с расшифровками
- `tests/test_transcription.py` — end-to-end транскрипция реального WAV через `TranscriptionEngine(model_name="tiny")`. **Пропускается (`importorskip`), если не установлен `faster_whisper`** (локально на 3.15 `av` не собирается — в CI 3.11 ставится нормально).
- `tests/test_integration.py` — тестирует работающий Docker-сервис: проверяет, что все эндпоинты из OpenAPI отвечают; по умолчанию идёт на prod — `https://voicer-production-769f94d8.up.railway.app`, переопределить `VOICER_BASE_URL`. `test_transcription_via_docker` делает реальный POST /transcribe и поллинг результата.
- **Репо `Canfly/voicer-ci`** — CI репо (action). Там `tests/` — копия тестов, job `test` делает `checkout adiom/voicer` и запускает `python -m pytest voicer-ci/tests -q` (путь к проекту в conftest: соседний каталог `voicer/`).
- Пример результата CI: https://github.com/Canfly/voicer-ci/actions/runs/45536281983 — job `test` → «48 passed».

## Lint

- `ruff check .` — конфиг `ruff.toml` (`select F, E4, E7`; `.agents` исключён).

## Архитектура

- `whisper_service.py` — FastAPI app, lifespan инициализирует `db`, `engine`, запускает `uvicorn.run`.
- `transcriber.py` — `TranscriptionEngine`, импорт `faster_whisper` **лениво** (лишний импорт не ломает тесты без движка).
- `models.py` — Pydantic-модели (включая `WebhookInfo`, `WebhookCreateRequest`).
- `database.py` — SQLite: таблицы `jobs`, `transcriptions`, `errors`, `webhooks`; важно — `PRAGMA foreign_keys = ON` на каждом соединении (без него каскад удаления сломан).

## Деплой (Railway)

- Проект `voicer` (free): https://railway.com/project/6960587e-e744-409f-9d08-9c4ee19b1fc2
- Домен: `https://voicer-production-769f94d8.up.railway.app` (теперь в `railway status --json` как `source.repo`)
- Репо проекта: `adiom/voicer` (основной); CI в `Canfly/voicer-ci`.

## Подводные камни (gotchas)

- Сервис читает `PORT`, а `docker-compose` ставит `SERVICE_PORT=8000` + мапит порт 8000 — реально сервис работает на 8080, компоновку пришлось починить переменным `PORT=8000`.
- `.agents/skills/` — установленные skills (fastapi-expert, fastapi-templates, use-railway), `skills-lock.json` — не трогать без нужды.
- Пользователь не хочет CI в аккаунте `adiom` — всё деплоится через `Canfly/voicer-ci`.
