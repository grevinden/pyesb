"""DLQ (Dead Letter Queue) — детекция permanent failure по истечении TTL."""

from __future__ import annotations

from datetime import datetime, timezone

from app.events import DeliveryExpiredEvent

__all__ = [
    "_attempt_counts",
    "_check_permanent_failure",
    "_cleanup_schedule_tracking",
    "_schedule_end_times",
]

# ── DLQ tracking ────────────────────────────────────────────────────────
# Храним end_time для каждого schedule_id.
# Когда retry исчерпаны, а HTTP всё ещё не 2xx — ``DeliveryExpiredEvent``.
_schedule_end_times: dict[str, datetime] = {}

# Счётчик попыток на schedule (сбрасывается при перезапуске).
_attempt_counts: dict[str, int] = {}


def _cleanup_schedule_tracking(schedule_id: str) -> None:
    """Clean up DLQ tracking data for a completed schedule.

    Вызывается при успешной доставке. Предотвращает утечку памяти.
    """
    _schedule_end_times.pop(schedule_id, None)
    _attempt_counts.pop(schedule_id, None)


def _check_permanent_failure(
    schedule_id: str,
    message_id: str,
    destination: str,
    url: str,
    trace_id: str | None,
) -> None:
    """Проверить, исчерпан ли TTL. Если да — ``DeliveryExpiredEvent``.

    Вызывается из error-handler'ов ``deliver_payload`` перед ``return``.
    Если ``end_time`` в прошлом, а HTTP всё ещё не 2xx — это permanent
    failure (аналог DLQ).
    """
    end_time = _schedule_end_times.get(schedule_id)
    if end_time is None:
        return
    if datetime.now(timezone.utc) < end_time:
        return  # ещё есть попытки

    attempts = _attempt_counts.get(schedule_id, 0)
    DeliveryExpiredEvent(
        schedule_id=schedule_id,
        destination=destination,
        url=url,
        message_id=message_id,
        trace_id=trace_id,
        pause=0,
        ttl=0,
        attempt_count=attempts,
    ).emit()

    # Cleanup: задача завершена (DLQ), чистим tracking
    _cleanup_schedule_tracking(schedule_id)
