"""pyesb-webhooker — Webhook Delivery Service.

FastAPI + APScheduler + async SQLite.
Принимает уведомления по AMQP (из 1С) или HTTP POST,
доставляет на внешние URL с retry до истечения TTL.
Все события — Pydantic-модели с ``.emit()``, пишутся в JSONL напрямую.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from pyesb_amqp.oidc import ChannelDesription
from pyesb_amqp.oidc import add_routes as oidc_add_routes

from .delivery.middleware import duration_buckets
from .events import PayloadReceivedEvent
from .ingress.models import PayloadSchema
from .ingress.router import resolve_trace_id
from .lifespan import lifespan

# ---------------------------------------------------------------------------
# Архитектура приёма сообщений
#
# 1. 1С запрашивает OIDC metadata → получает список каналов
#    (process + channel).
# 2. На стороне 1С администратор связывает приложение+канал
#    с именем очереди (destination).
# 3. При отправке 1С кладёт routing-key = destination.
#    amqp_handler(destination, msg) получает destination из routing key.
#
# HTTP POST / — альтернатива без OIDC, destination="http".
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# App — FastAPI инстанс
# ---------------------------------------------------------------------------

app = oidc_add_routes(
    ChannelDesription(
        access="WRITE_ONLY",
        process="WebhookDeliveryService",
        channel="HttpPost",
        destination="HttpPost",
        process_description="Сервис доставки уведомлений",
        channel_description="Отправка сообщение через HTTP POST",
    ),
    app=FastAPI(
        title="pyesb-webhooker",
        description=(
            "Webhook Delivery Service — доставщик уведомлений.\n"
            "Принимает сообщения по AMQP (из 1С) или HTTP POST "
            "и доставляет на внешние URL с повторными попытками до истечения TTL."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        redirect_slashes=False,
        openapi_url="/openapi.json",
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
        debug=__debug__,
    ),
)


# ---------------------------------------------------------------------------
# POST / — альтернатива AMQP (для отладки / внешних систем)
# ---------------------------------------------------------------------------


@app.post("/", status_code=204, response_model=None)
async def post(
    payload: PayloadSchema,
    request: Request,
) -> None:
    """Принять уведомление для HTTP-доставки.

    **Формат тела** — JSON, соответствующий ``PayloadSchema``.

    **HTTP-режим:** отправьте POST на ``/`` с ``Content-Type: application/json``.
    Сервер сгенерирует ``message_id`` (UUIDv4) и создаст расписание доставки.

    **AMQP-режим (из 1С):** отправьте сообщение в очередь AMQP с routing key
    ``= destination``. Тело сообщения — тот же JSON, ``message_id`` берётся
    из свойств AMQP-сообщения (``properties.message_id``).

    **Процесс доставки:**
    1. Первая попытка POST на ``url`` — немедленно.
    2. При ошибке (сеть, таймаут, HTTP-статус >= 400) — повтор через ``pause`` секунд.
    3. Попытки продолжаются до истечения ``ttl`` секунд с момента получения.
    4. При успехе (HTTP 2xx) расписание удаляется — повторных попыток не будет.
    """
    from .orchestration.schedule import create_delivery_schedule

    scheduler = request.app.state.scheduler
    message_id = str(uuid4())
    # ── trace_id: из HTTP-заголовка x-trace-id (необязательный, None = трассировка выключена) ──
    trace_id = resolve_trace_id(request.headers.get("x-trace-id"))

    schedule_id = await create_delivery_schedule(
        scheduler,
        destination="http",
        url=str(payload.url),
        body=payload.body,
        headers=list(payload.headers) if payload.headers else None,
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        trace_id=trace_id,
        message_id=message_id,
    )

    PayloadReceivedEvent(
        message_id=message_id,
        destination="http",
        url=str(payload.url),
        headers=payload.headers,
        timeout=payload.timeout,
        pause=payload.pause,
        ttl=payload.ttl,
        trace_id=trace_id,
        schedule_id=schedule_id,
    ).emit()


# ---------------------------------------------------------------------------
# GET /metrics — метрики доставки (in-memory)
# ---------------------------------------------------------------------------


@app.get("/metrics", status_code=200)
@app.get("/metrics/json", status_code=200)
async def get_metrics(request: Request) -> dict[str, object]:
    """Текущие метрики доставки сообщений.

    Счётчики сбрасываются при перезапуске процесса (in-memory).
    Поля: total_attempts, success_count, failure_count, avg_duration_ms,
    duration_histogram.
    """
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is None:
        return {"status": "unavailable", "reason": "metrics not initialized"}
    return {
        "status": "ok",
        **metrics.stats,
        "duration_buckets_ms": duration_buckets,
    }


# ---------------------------------------------------------------------------
# GET /health — health check (K8s liveness / readiness probe)
# ---------------------------------------------------------------------------


@app.get("/health/live", status_code=200)
@app.get("/health/ready", status_code=200)
@app.get("/health", status_code=200)
async def health(request: Request) -> dict[str, object]:
    """Health check — статус компонентов системы.

    Возвращает состояние scheduler'а, количество in-flight доставок,
    и uptime сервера.
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    from app.delivery.semaphore import _in_flight, _shutting_down

    return {
        "status": "ok",
        "scheduler": scheduler is not None,
        "in_flight": len(_in_flight),
        "shutting_down": _shutting_down,
    }
