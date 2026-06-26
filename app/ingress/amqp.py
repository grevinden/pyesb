"""AMQP handler — парсинг входящих сообщений из 1С."""

from __future__ import annotations

from apscheduler import AsyncScheduler
from pyesb_amqp import AmqpMessage

from app.events import HandlerFailedEvent, PayloadReceivedAMQPEvent
from app.ingress.models import Message
from app.ingress.router import first_str, resolve_trace_id
from app.orchestration.schedule import create_delivery_schedule

__all__ = [
    "amqp_handler",
    "set_scheduler",
]

# Module-level scheduler reference — set during lifespan startup.
# Используется amqp_handler для создания расписаний доставки.
_scheduler: AsyncScheduler | None = None


def set_scheduler(scheduler: AsyncScheduler) -> None:
    """Set the APScheduler instance used by amqp_handler.

    Вызывается из lifespan после создания AsyncScheduler.
    """
    global _scheduler
    _scheduler = scheduler


async def amqp_handler(destination: str, msg: AmqpMessage) -> bool:
    """Обработать AMQP-сообщение: парсинг → создание расписания доставки.

    Returns:
        True если сообщение принято, False если отклонено.

    """
    # ── Пустое тело AMQP: ошибка парсинга, сообщение отклоняется ──
    if msg.body is None or (isinstance(msg.body, bytes) and len(msg.body) == 0):
        HandlerFailedEvent(
            destination=destination,
            error="empty body, cannot deliver",
            body_size=0,
            body_preview="",
        ).emit()
        return False

    try:
        parsed = Message.model_validate(
            msg, from_attributes=True, context={"destination": destination}
        )
        ps = parsed.payload
        message_id = str(parsed.properties.message_id)
        correlation_id = (
            str(parsed.properties.correlation_id) if parsed.properties.correlation_id else None
        )
        _props = parsed.application_properties
        sender_code = first_str(_props.integ_sender_code)
        recipient_code = first_str(_props.integ_recipient_code)
        integ_message_id = str(_props.integ_message_id)
        delivery_count = parsed.header.delivery_count

        # ── trace_id: из AMQP application_properties x-trace-id ──
        _app_props = parsed.application_properties
        trace_id: str | None = None
        if _app_props and _app_props.model_extra:
            trace_id = resolve_trace_id(_app_props.model_extra.get("x-trace-id"))
        if trace_id is None and ps.headers:
            for _k, _v in ps.headers:
                if _k.lower() == "x-trace-id":
                    trace_id = resolve_trace_id(_v)
                    break

        if _scheduler is None:
            HandlerFailedEvent(
                destination=destination,
                error="scheduler not initialized",
                body_size=0,
                body_preview="",
            ).emit()
            return False

        PayloadReceivedAMQPEvent(
            message_id=message_id,
            correlation_id=correlation_id,
            sender_code=sender_code,
            recipient_code=recipient_code,
            integ_message_id=integ_message_id,
            delivery_count=delivery_count,
            destination=destination,
            url=str(ps.url),
            headers=ps.headers,
            timeout=ps.timeout,
            pause=ps.pause,
            ttl=ps.ttl,
            trace_id=trace_id,
            schedule_id=None,
        ).emit()

        schedule_id = await create_delivery_schedule(
            _scheduler,
            destination=destination,
            url=str(ps.url),
            body=ps.body,
            headers=list(ps.headers) if ps.headers else None,
            timeout=ps.timeout,
            pause=ps.pause,
            ttl=ps.ttl,
            trace_id=trace_id,
            message_id=message_id,
        )

        # create_delivery_schedule эмитит DeliveryScheduledEvent
        return True
    except Exception as e:
        _raw = msg.body
        _body_size = len(_raw) if isinstance(_raw, (bytes, str)) else None
        _body_prev = (
            (
                _raw[:200].decode("utf-8", errors="replace")
                if isinstance(_raw, bytes)
                else str(_raw)
            )[:200]
            if _raw is not None
            else None
        )
        HandlerFailedEvent(
            destination=destination,
            error=f"{type(e).__name__}: {e}",
            body_size=_body_size,
            body_preview=_body_prev,
        ).emit()
        return False


__all__ = ["amqp_handler"]
