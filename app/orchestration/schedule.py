"""Schedule management — создание APScheduler-расписаний для доставки."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from apscheduler import AsyncScheduler, CoalescePolicy
from apscheduler.triggers.interval import IntervalTrigger

from app.delivery.engine import deliver_payload
from app.events import DeliveryScheduledEvent

from .dlq import _schedule_end_times

__all__ = [
    "create_delivery_schedule",
]


async def create_delivery_schedule(
    scheduler: AsyncScheduler,
    *,
    destination: str,
    url: str,
    body: dict | list | None,
    headers: list[tuple[str, str]] | None,
    timeout: int,
    pause: int,
    ttl: int,
    trace_id: str | None = None,
    message_id: str,
) -> str:
    """Создать APScheduler Schedule для доставки payload'а.

    Первый fire time — ``now`` (немедленно).
    Последний — ``now + ttl`` секунд.
    Между ними — ``pause`` секунд.

    После истечения TTL расписание завершается автоматически.
    """
    schedule_id = f"delivery_{destination}_{uuid4().hex}"

    now = datetime.now(timezone.utc)
    end = now + timedelta(seconds=ttl)

    # Сохраняем end_time для DLQ-детекции
    _schedule_end_times[schedule_id] = end

    await scheduler.add_schedule(
        deliver_payload,
        IntervalTrigger(
            seconds=max(1, pause),
            start_time=now,
            end_time=end,
        ),
        id=schedule_id,
        args=[url, body, headers, timeout, destination, message_id, trace_id],
        misfire_grace_time=None,
        coalesce=CoalescePolicy.latest,
    )

    DeliveryScheduledEvent(
        message_id=message_id,
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        pause=pause,
        ttl=ttl,
        trace_id=trace_id,
        end_time=end.isoformat(),
    ).emit()

    return schedule_id
