"""Delivery — HTTP POST доставка с retry, circuit breaker и middleware.

Re-export для APScheduler: планировщик сериализует ``deliver_payload``
как ``app.delivery:deliver_payload``, поэтому функция должна быть
доступна как атрибут пакета ``app.delivery``.
"""

from __future__ import annotations

from .engine import deliver_payload
from .semaphore import _shutting_down, wait_for_in_flight

__all__ = [
    "_shutting_down",
    "deliver_payload",
    "wait_for_in_flight",
]
