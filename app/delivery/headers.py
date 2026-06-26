"""HTTP header validation — защита от CRLF-инъекции.

Предоставляет Pydantic-типы ``SafeHeaderKey`` / ``SafeHeaderValue``
для использования в моделях, а также runtime-функции для проверки
заголовков вне Pydantic (APScheduler args, middleware context).

Пример::

    from app.delivery.headers import SafeHeaderKey, SafeHeaderValue

    class MyModel(BaseModel):
        headers: set[tuple[SafeHeaderKey, SafeHeaderValue]] | None = None
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

__all__ = [
    "HeaderDict",
    "HeaderTuple",
    "SafeHeaderKey",
    "SafeHeaderValue",
    "validate_header_dict",
    "validate_header_pairs",
]

_CRLF_CHARS = frozenset({"\r", "\n", "\r\n"})


def _check_no_crlf(value: str, field_name: str = "value") -> str:
    r"""Проверить, что строка не содержит CR/LF символов.

    Args:
        value: Проверяемая строка.
        field_name: Имя поля для сообщения об ошибке.

    Returns:
        ``value`` без изменений, если проверка пройдена.

    Raises:
        ValueError: Если строка содержит ``\r`` или ``\n``.

    """
    for ch in _CRLF_CHARS:
        if ch in value:
            msg = (
                f"HTTP header {field_name} contains prohibited CR/LF character: {ch!r} in {value!r}"
            )
            raise ValueError(msg)
    return value


def _check_header_key(value: str) -> str:
    """Валидатор для ключа заголовка."""
    return _check_no_crlf(value, field_name="key")


def _check_header_value(value: str) -> str:
    """Валидатор для значения заголовка."""
    return _check_no_crlf(value, field_name="value")


# ── Pydantic-типы для использования в моделях ──────────────────────────

SafeHeaderKey = Annotated[str, AfterValidator(_check_header_key)]
"""Pydantic-тип: строка ключа HTTP-заголовка без CR/LF."""

SafeHeaderValue = Annotated[str, AfterValidator(_check_header_value)]
"""Pydantic-тип: строка значения HTTP-заголовка без CR/LF."""

HeaderTuple = tuple[SafeHeaderKey, SafeHeaderValue]
"""Pydantic-тип: пара ``(key, value)`` с проверкой на CR/LF."""

HeaderDict = dict[SafeHeaderKey, SafeHeaderValue]
"""Pydantic-тип: словарь заголовков с проверкой на CR/LF.

.. caution::
   ``dict[Annotated[...]]`` не тривиально валидируется Pydantic.
   Для runtime-проверки используйте ``validate_header_dict()``.
"""


# ── Runtime-функции (для кода без Pydantic) ────────────────────────────


def validate_header_pairs(
    headers: list[tuple[str, str]] | None,
) -> list[tuple[str, str]] | None:
    """Проверить список пар заголовков на CR/LF (runtime).

    Используется в ``deliver_payload()`` перед передачей в httpx,
    где данные приходят из APScheduler (без Pydantic-валидации).

    Args:
        headers: Список пар ``(key, value)`` или ``None``.

    Returns:
        ``headers`` без изменений, если все пары валидны.

    Raises:
        ValueError: Если хотя бы один ключ или значение содержит CR/LF.

    """
    if headers is None:
        return None
    for key, value in headers:
        _check_header_key(key)
        _check_header_value(value)
    return headers


def validate_header_dict(headers: dict[str, str] | None) -> dict[str, str] | None:
    """Проверить словарь заголовков на CR/LF (runtime).

    Используется в ``DeliveryContext`` для защиты middleware-цепочки.

    Args:
        headers: Словарь ``{key: value}`` или ``None``.

    Returns:
        ``headers`` без изменений, если все пары валидны.

    Raises:
        ValueError: Если хотя бы один ключ или значение содержит CR/LF.

    """
    if headers is None:
        return None
    for key, value in headers.items():
        _check_header_key(key)
        _check_header_value(value)
    return headers
