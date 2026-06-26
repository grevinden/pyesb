# Audit: pyesb — 1C ESB Gateway

> Комплексный аудит проекта по всем параметрам.
> Создан: 2026-06-26

---

## 1. Зависимости (Dependencies / Pip)

### 1.1 pyproject.toml
- [ ] `requires-python = ">=3.13"` — допустимый минимум?
- [ ] `fastapi[standard-no-fastapi-cloud-cli]` — все лишние extras отключены?
- [ ] `apscheduler>=4.0.0a6` — alpha-версия в production. Есть ли стабильный релиз?
- [ ] `pyesb-amqp` — git-зависимость (`[tool.uv.sources]`). Нет версионирования.
- [ ] `httpx>=0.28.1` — используется. Проверить зависимости httpx (httpcore, h11).
- [ ] `sniffio>=1.3.1` — как transitive dependency? Нужна ли явно?
- [ ] `aiorun>=2025.1.1` — корректное использование `shutdown_waits_for`.
- [ ] `python-ulid>=3.1.0` — только для генерации ULID в логах.

### 1.2 Transitive dependencies
- [ ] `uv.lock` — проверить на known vulnerabilities (`uv audit`).
- [ ] `uv.lock` — нет ли дублирования версий (разные версии одного пакета)?

### 1.3 Group: dev / test
- [ ] `asgi-lifespan` — только для тестов, корректно в `[dependency-groups] test`.
- [ ] `icecream` — в `dev`. Актуально?
- [ ] `pytest-asyncio` — `asyncio_mode = "auto"` корректно.

### 1.4 Security
- [ ] `uv audit` — проверить все зависимости на CVE.
- [ ] `pip-audit` / `safety` — альтернативная проверка.

### 1.5 Cleanup
- [x] `sniffio>=1.3.1` — удалена (transitive dependency).
- [x] `icecream>=2.2.0` из dev — удалена (не используется в коде).

---

## 2. Архитектура

### 2.1 Модульная структура
- [x] Нет циклических импортов. (`delivery.py` не импортирует `log.py` напрямую — хорошо, через `context.py`.)
- [x] Принцип единственной ответственности (SRP) для каждого модуля:
  - `main.py` — только `app` + роуты. ✅
  - `models.py` — **создан**: `PayloadSchema`, `Message`.
  - `lifespan.py` — **создан**: `lifespan()`, `amqp_handler()`.
  - `delivery.py` — движок доставки. Чисто.
  - `events.py` — Pydantic-модели событий. Чисто.
  - `log.py` — настройка логирования. Чисто.
  - `config.py` — конфигурация. Чисто.
  - `router.py` — извлечение destination/trace_id. Чисто.
  - `tasks.py` — safe task creation. Чисто.
  - `context.py` — contextvars. Чисто.
  - `middleware.py` — middleware pipeline. Чисто.
  - `database.py` — engine singleton. Чисто.

### 2.2 Layer separation
- [ ] Transport → Router → Dispatcher → Worker layers соблюдены?
- [ ] Domain logic не зависит от инфраструктуры (AmqpServer, APScheduler).

### 2.3 Configuration
- [ ] Все параметры вынесены в `config.py` (env vars).
- [ ] Нет хардкода в `delivery.py` (`_MAX_BODY_CHARS`, `_MAX_RESPONSE_BODY_CHARS`).
- [ ] Валидация env vars при старте (типы, диапазоны).

### 2.4 Shutdown sequence
- [x] 5-фазный shutdown: AMQP → guard → scheduler → **close_http_client()** → db.
- [x] `wait_for_in_flight` — force cancel после таймаута.
- [x] `close_http_client()` — добавлен в shutdown (закрытие пула httpx).
- [x] `stop_logging_queue()` — последний flush.

---

## 3. Асинхронность (Async)

### 3.1 Asyncio task management
- [ ] `safe_create_task` — корректен (CancelledError swallowed, остальные logged + re-raised).
- [ ] Нет `asyncio.create_task` без обёртки `safe_create_task`.
- [ ] `stderr_to_jsonl` — создаётся через `safe_create_task`.

### 3.2 Concurrency
- [x] `Semaphore(50)` — второй уровень контроля над `max_concurrent_jobs=20`.
- [x] `Semaphore` не утекает (release в `finally`).
- [x] `_in_flight` — set задач, корректно чистится в `finally`.
- [x] Shared `httpx.AsyncClient` с `limits=Limits(max_connections=50)` — пул соединений.

### 3.3 Blocking calls
- [x] `asyncio.to_thread(os.write, 1, data)` — неблокирующая запись.
- [x] `loop.run_in_executor(None, os.read, ...)` — неблокирующее чтение pipe.
- [x] `datetime.now(timezone.utc)` — легковесная операция (не IO).
- [x] `json.dumps` в `deliver_payload` — вынесен в `asyncio.to_thread`.
- [x] `json.dumps` в `_jsonl_line` — вызывается из фоновой asyncio-задачи (лёгкий).

### 3.4 APScheduler async
- [ ] `AsyncScheduler` — корректные параметры (`max_concurrent_jobs`, `TaskDefaults`).
- [ ] `misfire_grace_time=None` — осознанное решение?
- [ ] `CoalescePolicy.latest` — корректно для delivery retry.

### 3.5 ContextVars propagation
- [ ] `ContextVar` устанавливается в `deliver_payload`.
- [ ] Structlog processor `_add_context_vars` inject в event_dict.
- [ ] ContextVar propagation при `shutdown_waits_for`? (aiorun fork?)

---

## 4. Код (Code Quality)

### 4.1 Typing
- [ ] All public functions have type annotations.
- [ ] `Any` usage — оправдано? (`app.state.*`, `exc_info()`).
- [ ] `noqa: F821` в `main.py` для `app.state.scheduler`, `app.state.metrics`.
- [ ] `# type: ignore[union-attr]` — задокументировано?

### 4.2 Linting
- [ ] `ruff check` — 0 errors.
- [ ] `mypy --strict` — 0 errors.
- [ ] `pyright` — 0 errors.

### 4.3 Code duplication
- [ ] `resolve_trace_id` вызывается и в AMQP handler, и в POST handler.
- [ ] `fmt_headers` — единая функция.
- [ ] `_truncate_json`, `_truncate_text` — только в `delivery.py`.

### 4.4 Docstrings
- [ ] PEP 257: все модули + публичные классы + функции.
- [ ] Docstrings в `delivery.py` — некоторые строки вне функции (`wait_for_in_flight` docstring после первой строки).

### 4.5 Naming
- [ ] `_shutting_down` — module-level flag. Конвенция OK.
- [ ] `_in_flight` — module-level set. ОК.
- [ ] `_delivery_semaphore` — module-level. ОК.
- [ ] `_schedule_end_times`, `_attempt_counts` — module-level dicts. **Потенциальная утечка памяти** — не чистятся при remove_schedule.

---

## 5. Ошибки (Error Handling)

### 5.1 Exception taxonomy
- [ ] В `delivery.py`:
  - `httpx.HTTPStatusError` → `DeliveryHttpErrorEvent` (warning), retry
  - `Exception` → `DeliveryFailedEvent` (error), retry
  - Unhandled → `deliver_payload` завершается, APScheduler перезапускает?
- [ ] В `amqp_handler`:
  - `Exception` → `HandlerFailedEvent` (error), return False

### 5.2 Retry logic
- [x] IntervalTrigger с TTL — APScheduler сам повторяет.
- [x] `_check_permanent_failure` — DLQ-детекция + cleanup tracking (C3).
- [ ] Нет лимита попыток, только TTL. **Риск: бесконечные retry при коротком pause и длинном TTL.**

### 5.3 Unhandled exceptions
- [ ] `safe_create_task` — единственный entry point для фоновых задач.
- [ ] `main.py` — `try/except BaseException` вокруг `run()`.

### 5.4 `B027` suppressed
- [ ] `noqa: B027` для `before()` / `after()` в `Middleware` — intentional (optional hooks).

---

## 6. Безопасность (Security)

### 6.1 Input validation
- [ ] `PayloadSchema` — Pydantic валидация всех полей.
- [ ] `Message` — `Json[PayloadSchema]` вложенная валидация.
- [ ] `url: HttpUrl` — Pydantic валидирует URL.
- [ ] `headers` — `set[tuple[str, str]]` — возможна header injection.

### 6.2 Secrets
- [ ] Нет хардкоженных credentials.
- [ ] AMQP / OIDC credentials — через env vars (pyesb-amqp).

### 6.3 TLS
- [x] `verify=False` — SSL отключён (требование заказчика). Фиксировано в shared `httpx.AsyncClient`.

### 6.4 Audit trail
- [ ] Все события логируются через Pydantic models.
- [ ] `delivery_count` — AMQP redelivery detection.
- [ ] `trace_id` — сквозная трассировка.

### 6.5 OIDC
- [ ] OIDC add_routes — через `pyesb-amqp`. Корректность конфигурации?
- [ ] Channel descriptions хардкожены в `main.py`.

---

## 7. Тестирование

### 7.1 Test coverage
- [x] Смок-тесты (lifecycle, health, metrics) — есть (`test_smoke.py`).
- [x] Модели (Message, PayloadSchema) — есть (`test_job_message.py`).
- [x] Middleware pipeline — есть (`test_middleware.py`, `test_fault_tolerance.py`).
- [x] Shutdown flow — минимально (`test_fault_tolerance.py`).
- [x] **`router.py`** — 11 тестов (`tests/test_router.py`). **Добавлены.**
- [x] **`log.py`** — 10 тестов (`tests/test_log.py`). **Добавлены.**
- [ ] `config.py` — нет тестов.
- [ ] `events.py` — нет интеграционных тестов emit.
- [ ] AMQP handler path — нет тестов.
- [ ] DLQ / `_check_permanent_failure` — нет тестов.
- [ ] `wait_for_in_flight` — force cancel path — нет тестов.

### 7.2 Test quality
- [ ] Fixtures — `client` в `test_smoke.py` использует `LifespanManager`.
- [ ] Mock usage — `patch` для `UnhandledTaskErrorEvent.emit`.
- [ ] Edge cases: invalid JSON, missing fields, CancelledError, concurrent tasks.

### 7.3 Slow tests
- [ ] `test_semaphore_acquire_release_blocks_at_limit` — `asyncio.sleep(0.05)`.
- [ ] `test_concurrent_tasks_all_complete` — `asyncio.sleep(0.01)` × 10.

---

## 8. Логирование (Logging)

### 8.1 Architecture
- [ ] QueueHandler + QueueListener — неблокирующее логирование.
- [ ] `_StructlogAwareQueueHandler` — корректно сохраняет event_dict.
- [ ] `ProcessorFormatter` + `foreign_pre_chain` — единый JSONL для structlog и stdlib.

### 8.2 Log events
- [ ] Все события через Pydantic models + `.emit()`.
- [ ] `extra = "forbid"` — опечатки в полях → Pydantic error.
- [ ] `_event_name`, `_level` — ClassVar, не dump'ятся.

### 8.3 stderr redirect
- [ ] Rust tracing (pyesb-amqp) → pipe → stderr_to_jsonl → stdout.
- [ ] `_detect_stderr_level` — эвристика для traceback.
- [ ] Утечка pipe fd при ошибке?

### 8.4 Log levels
- [ ] `exception` level — `FatalErrorEvent`, `UnhandledTaskErrorEvent`.
- [ ] `error` — `DeliveryFailedEvent`, `HandlerFailedEvent`.
- [ ] `warning` — `DeliveryExpiredEvent`, `DeliveryHttpErrorEvent`, `ShutdownTimeoutEvent`.
- [ ] `info` — все штатные события.

### 8.5 PII / sensitive data
- [x] **Header sanitization добавлен** — structlog processor `_sanitize_headers` маскирует `Authorization`, `X-Api-Key`, `Cookie` в логах.
- [ ] `body`, `response_body` — могут содержать PII (не маскируются).

---

## 9. Производительность (Performance)

### 9.1 Concurrency limits
- [ ] `Semaphore(50)` — обоснован? Количество соединений httpx (default pool=10).
- [ ] `max_concurrent_jobs=20` — APScheduler глобальный лимит.

### 9.2 httpx connection pool
- [x] **Исправлено:** один `AsyncClient` на все доставки (shared, lazy init).
- [x] `limits=Limits(max_connections=MAX_CONCURRENT_DELIVERIES, max_keepalive_connections=...)`.
- [x] `close_http_client()` — закрывается при shutdown.

### 9.3 Database
- [x] SQLite `data.db` — только APScheduler.
- [x] **WAL mode включён** (`PRAGMA journal_mode=wal`, `PRAGMA busy_timeout=5000`).
- [x] `setup_db()` — вызывается при startup.
- [x] `check_same_thread=False`.
- [x] WAL через `@event.listens_for` на `sync_engine` (работает и для in-memory БД).
- [x] `engine.dispose()` — вызывается при shutdown.

### 9.4 Memory
- [x] `_schedule_end_times` — **исправлено**: чистится при success и DLQ.
- [x] `_attempt_counts` — **исправлено**: чистится при success и DLQ.
- [x] `_in_flight` — set, чистится в finally. OK.
- [ ] QueueHandler queue — `maxsize=5000`. Переполнение → blocking?

### 9.5 JSON serialization
- [x] `json.dumps` в `deliver_payload` — вынесен в `asyncio.to_thread`.
- [x] Pydantic `.model_dump(mode='json')` — OK, легковесный.

---

## 10. DevOps / Deploy

### 10.1 Health checks
- [ ] `GET /health` — status, scheduler, in_flight, shutting_down.
- [ ] `GET /health/live`, `GET /health/ready`.

### 10.2 Metrics
- [x] `GET /metrics` — total_attempts, success_count, failure_count, avg_duration_ms.
- [x] **Histogram добавлен:** `duration_histogram` с buckets [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000] мс.
- [x] `duration_buckets_ms` — включён в ответ `/metrics`.

### 10.3 Docker
- [ ] `Dockerfile` отсутствует.
- [ ] `docker-compose.yml` отсутствует (нужен для MySQL/RabbitMQ? Нет, SQLite).

### 10.4 Startup / Shutdown
- [ ] `uv run fastapi dev` / `uv run fastapi run`.
- [ ] `__main__.py` — ручной запуск через uvicorn + aiorun. **b Несоответствие: fastapi CLI vs __main__.py?**
- [ ] `workers=1` жёстко в коде.

### 10.5 Environment
- [ ] Префикс `FWQ_` — 12-factor app.
- [ ] `BIND_HOST=0.0.0.0` по умолчанию. **Security risk в production.**

### 10.6 Logging in production
- [ ] JSONL на stdout — совместимо с Docker/k8s log collector.
- [ ], `uvicorn` + `apscheduler` logger level `INFO`.

---

## 11. Документация

### 11.1 README.md
- [ ] Описание проекта.
- [ ] Быстрый старт.
- [ ] **Устаревшая структура проекта** — неполная (нет `app/`, `tests/`, `logging.md`).

### 11.2 logging.md
- [ ] Архитектура, все события, JSONL формат, timeline reconstruction.
- [ ] Нет описания `MiddlewarePipeline`.
- [ ] Нет описания `stderr redirect`.

### 11.3 OpenAPI / Swagger
- [ ] `docs_url="/docs"` — включено.
- [ ] Pydantic models reflected в OpenAPI schema.

### 11.4 Code comments
- [ ] Docstrings на русском — OK.
- [ ] Комментарии в коде — на русском.

---

## 12. TODO.md (known issues)

- [ ] **`url`** — что именно? Поддержка множественных URL?
- [ ] **`body`** — размер? Поддержка streaming?
- [ ] **`headers`** — кастомные заголовки для доставки.
- [ ] **`read_timeount`** — опечатка (timeount → timeout). Новый параметр?
- [ ] **`пауза_повтора`** — переменная pause между retry? Exponential backoff?
- [ ] **`колво_попыток`** — лимит попыток вместо TTL?
- [ ] **`skip ssl check`** — `httpx.AsyncClient(verify=False)`. Security issue.

---

## 13. Финальный отчёт

### Критические (Critical)
| # | Проблема | Модуль | Риск |
|---|----------|--------|------|
| # | Проблема | Модуль | Статус |
|---|----------|--------|--------|
| C1 | `main.py` — монолит (модели + lifespan + routes) | `main.py` | ✅ **Исправлено**: models.py + lifespan.py + main.py |
| C2 | httpx.AsyncClient создаётся на каждый запрос | `delivery.py` | ✅ **Исправлено**: shared client с пулом |
| C3 | `_schedule_end_times`, `_attempt_counts` — утечка памяти | `delivery.py` | ✅ **Исправлено**: cleanup при success/DLQ |
| C4 | `apscheduler>=4.0.0a6` — alpha версия | `pyproject.toml` | ⚠️ Остаётся (нет stable) |
| C5 | pyesb-amqp — git dependency без версии | `pyproject.toml` | ✅ **Исправлено**: зафиксирован commit |
| C6 | Нет тестов для router, log | `tests/` | ✅ **Исправлено**: 21 новых тестов (router + log) |
| C7 | `skip ssl check` — отключение верификации | delivery.py | ✅ **Подтверждено**: verify=False (требование заказчика) |

### Исправлено (High)
| # | Проблема | Модуль | Статус |
|---|----------|--------|--------|
| H1 | `json.dumps` в async-контексте | `delivery.py` | ✅ **Исправлено**: asyncio.to_thread |
| H3 | Нет histogram метрик | `middleware.py` | ✅ **Исправлено**: duration_histogram |
| H4 | WAL mode для SQLite не включён | `database.py` | ✅ **Исправлено**: setup_db() с WAL |

### Остаются открытыми
| # | Проблема | Модуль | Статус |
|---|----------|--------|--------|
| H2 | Нет Dockerfile | проект | ⏳ Нужен |
| H5 | stderr pipe надёжность | `log.py` | ⏳ Нужен review |
| M1 | PII в логах (headers) | `events.py` | ✅ **Исправлено**: header sanitization processor |
| M2 | docstring вне функции (wait_for_in_flight) | `delivery.py` | ⏳ Нужен review |
| M3 | `BIND_HOST=0.0.0.0` по умолчанию | `config.py` | ⏳ Нужен review |
| M4 | `_MAX_BODY_CHARS`, `_MAX_RESPONSE_BODY_CHARS` хардкод | `delivery.py` | ⏳ Нужен review |
| L1 | README.md — устаревшая структура | `README.md` | ⏳ Нужен review |
| L2 | `noqa: F821` для app.state | `lifespan.py` | ⏳ Нужен review |
