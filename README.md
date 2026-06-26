# 1C ESB Gateway (pyesb)

Compatible server for 1C Enterprise ESB integration (OIDC + AMQP + HTTP)

Сервер-прокси для интеграции с 1C Enterprise через ESB. Принимает сообщения
по AMQP (из 1С) или через HTTP POST, доставляет их на внешние URL-адреса
с повторными попытками до истечения TTL и пишет структурированный JSONL-лог
каждого события (доставка, ошибка, lifecycle).

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Веб-фреймворк | **FastAPI** (ASGI + lifespan) |
| Планировщик доставки | **APScheduler** (AsyncScheduler + IntervalTrigger) |
| Хранилище APScheduler | **SQLite** (aiosqlite + SQLAlchemy async) |
| AMQP-сервер | **pyesb-amqp** (Rust-based bridge) |
| HTTP-клиент | **httpx** (AsyncClient) |
| Логирование | **structlog** → **JSONL** (через QueueHandler) |
| Конфигурация | Переменные окружения `FWQ_*` (12-factor app) |
| Запуск | **uv** + **aiorun** |
| Python | **3.13+** |

## Архитектура

### Поток сообщения

```
1C (AMQP) ──▶ pyesb-amqp ──▶ lifespan.amqp_handler() ──▶ APScheduler ──▶ HTTP POST ──▶ Внешний URL
  или                │                                        │
HTTP POST /          │                                        │
  │                   ▼                                        ▼
  └──▶ main.py   PayloadReceivedEvent                  JSONL-лог (data.jsonl)
       (POST /)
```

### Процесс доставки

1. **Приём** — сообщение принимается из AMQP (routing key = `destination`)
   или через HTTP `POST /` (destination = `"http"`).
2. **Планирование** — APScheduler создаёт задачу с `IntervalTrigger` (интервал = `pause`).
3. **Повторы** — задача выполняется повторно через `pause` секунд, пока не истечёт `ttl` с
   момента получения сообщения.
4. **Завершение** — при успешном HTTP-ответе (2xx) задача удаляется; при ошибках (сеть,
   таймаут, статус >= 400) повторяется до TTL.
5. **Счётчик попыток не нужен** — TTL единственный лимит.

### Lifecycle (Graceful Shutdown)

Последовательность остановки:

1. FastAPI перестаёт принимать HTTP-запросы (встроено в uvicorn).
2. **AMQP** — `AmqpServer` закрывает соединения.
3. **Shutdown guard** — `_shutting_down = True`, ожидание in-flight доставок
   (до `FWQ_SHUTDOWN_TIMEOUT` секунд).
4. **Scheduler** — `AsyncScheduler` останавливается.
5. **HTTP client** — `close_http_client()` закрывает пул httpx.
6. **DB** — `close_db()`.

## Установка

```bash
# Установка зависимостей
uv sync

# С тестовыми зависимостями
uv sync --group test
```

## Запуск

```bash
# Разработка (hot-reload)
uv run fastapi dev --host=0.0.0.0 --port=8000

# Продакшен (workers=1, без reload)
uv run python -m app

# Или через fastapi run
uv run fastapi run --host=0.0.0.0 --port=8000
```

## API

| Метод | Путь | Описание |
|--------|------|----------|
| `POST` | `/` | Принять уведомление для HTTP-доставки |
| `GET` | `/health` | Health check (liveness / readiness probe) |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/metrics` | Текущие метрики доставки (in-memory) |
| `GET` | `/metrics/json` | То же, что `/metrics` |

Документация OpenAPI доступна по `/docs` (включена всегда).

### Формат запроса `POST /`

```json
{
  "url": "https://example.com/webhook",
  "body": {"key": "value"},
  "headers": [["Authorization", "Bearer token"]],
  "timeout": 30,
  "pause": 10,
  "ttl": 300,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Конфигурация

Все параметры задаются через переменные окружения с префиксом `FWQ_`.

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `FWQ_BIND_HOST` | `0.0.0.0` | Адрес для привязки сервера |
| `FWQ_BIND_PORT` | `8000` | Порт сервера |
| `FWQ_MAX_CONCURRENT_DELIVERIES` | `50` | Одновременных HTTP-доставок (семафор) |
| `FWQ_SCHEDULER_MAX_CONCURRENT` | `20` | `max_concurrent_jobs` APScheduler |
| `FWQ_SHUTDOWN_TIMEOUT` | `30` | Секунд ожидания in-flight доставок при shutdown |
| `FWQ_LOG_QUEUE_MAXSIZE` | `5000` | Максимум записей в очереди QueueHandler |
| `FWQ_DATABASE_URL` | `sqlite+aiosqlite:///data.db` | Async SQLAlchemy DSN |
| `FWQ_DEFAULT_PAUSE` | `10` | Пауза между retry по умолчанию (сек) |
| `FWQ_DEFAULT_TTL` | `300` | TTL доставки по умолчанию (сек) |
| `FWQ_DEFAULT_TIMEOUT` | `30` | HTTP-таймаут по умолчанию (сек) |

## Каналы обработки

Сервер регистрирует следующие каналы (OIDC metadata):

| Канал | Процесс | Доступ | Описание |
|-------|---------|--------|----------|
| `channel1` | `process1` | `WRITE_ONLY` | `process_description1` / `channel_description1` |
| `channel2` | `process2` | `WRITE_ONLY` | `process_description2` / `channel_description2` |

## Логирование

Все события доставки пишутся в структурированный JSONL через structlog.
Формат записи — Pydantic-модели событий с методом `.emit()`:

```python
DeliveryAttemptEvent(
    schedule_id=schedule_id,
    destination=destination,
    url=url,
    ...
).emit()
```

Каждая запись содержит поля `dt`, `ulid`, `event`, `level` и
контекстные поля (message_id, trace_id, schedule_id, destination и др.).

## Структура проекта

```
pyesb/
├── app/
│   ├── __init__.py          # Пакет приложения
│   ├── __main__.py          # Entry point (uv run python -m app)
│   ├── main.py              # FastAPI app + routes (POST /, GET /metrics, GET /health)
│   ├── models.py            # Pydantic модели (PayloadSchema, Message)
│   ├── lifespan.py          # FastAPI lifespan (APScheduler + AMQP lifecycle)
│   ├── delivery.py          # HTTP delivery engine (retry через APScheduler)
│   ├── middleware.py        # Middleware pipeline (MetricsMiddleware, DeliveryContext)
│   ├── events.py            # Pydantic модели событий логирования
│   ├── log.py               # Структурированный JSONL-лог (structlog bridge)
│   ├── config.py            # Конфигурация (frozen dataclass, env vars FWQ_*)
│   ├── context.py           # ContextVar для message_id / trace_id
│   ├── router.py            # Маршрутизация (trace_id, first_str)
│   ├── tasks.py             # Безопасное создание asyncio-задач
│   └── database.py          # Async SQLite engine singleton (APScheduler)
├── tests/
│   ├── test_smoke.py            # Интеграционные тесты (lifecycle, health, POST)
│   ├── test_job_message.py      # PayloadSchema / Message model tests
│   ├── test_middleware.py       # Middleware pipeline tests
│   ├── test_fault_tolerance.py  # Error handling tests
│   ├── test_router.py           # router.py unit tests
│   └── test_log.py              # log.py unit tests
├── AUDIT.md                # Чеклист аудита безопасности
├── logging.md              # Документация системы логирования
├── logging.yaml            # Пример конфигурации логирования (reference)
├── pyproject.toml          # Конфигурация проекта + зависимости
├── uv.lock                 # Заблокированные зависимости
├── README.md               # Эта документация
└── TODO.md                 # Известные проблемы / feature requests
```

## Тестирование

```bash
# Все тесты
uv run pytest -v

# С coverage
uv run pytest -v --cov=app --cov-report=term-missing

# Конкретный тест
uv run pytest tests/test_smoke.py -v
```

## Развитие

Для добавления новых каналов:

1. Добавьте `ChannelDesription` в `main.py` в вызов `oidc_add_routes`.
2. Укажите уникальные `process`, `channel` и `destination`.
3. Маршрутизация и доставка произойдут автоматически.

## Лицензия

MIT
