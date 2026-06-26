"""Tests for the Message model (E1CMessage with nested Payload)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from pyesb_amqp import E1CMessage

from app.models import Message, PayloadSchema


def make_payload_bytes(
    *,
    url: str = "http://example.com/hook",
    body: dict | list | None = {"ok": 1},
    headers: list[tuple[str, str]] | None = None,
    timeout: int = 10,
    pause: int = 5,
    ttl: int = 60,
    destination: str = "test",
) -> bytes:
    """JSON-encoded Payload, готовый для передачи как body в Message."""
    if headers is None:
        headers = [("X-Api-Key", "secret")]
    return json.dumps(
        {
            "url": url,
            "body": body,
            "headers": headers,
            "timeout": timeout,
            "pause": pause,
            "ttl": ttl,
            "destination": destination,
        }
    ).encode()


def make_kwargs(body: bytes | None = None) -> dict:
    """Минимальные валидные kwargs для Message."""
    uid = uuid4()
    return {
        "body": body if body is not None else make_payload_bytes(),
        "delivery_annotations": None,
        "delivery_id": 1,
        "delivery_tag": b"\x01\x00\x00\x00\x00\x00\x00\x00",
        "footer": None,
        "header": {
            "delivery_count": 0,
            "first_acquirer": True,
            "priority": 0,
            "durable": True,
        },
        "link_output_handle": 0,
        "message_annotations": None,
        "message_format": 0,
        "properties": {
            "message_id": uid,
            "correlation_id": uid,
            "absolute_expiry_time": "2025-01-01T00:00:00Z",
            "creation_time": "2025-01-01T00:00:00Z",
        },
        "application_properties": {
            "integ_sender_code": "sender",
            "integ_recipient_code": "recip",
            "integ_message_body_size": 100,
            "integ_message_correlation_id": uid,
            "integ_message_id": uid,
        },
        "rcv_settle_mode": None,
    }


class TestMessageInit:
    """Создание экземпляра Message."""

    def test_minimal(self) -> None:
        """Валидные данные — body распарсен в PayloadSchema."""
        msg = Message(**make_kwargs())
        assert isinstance(msg, E1CMessage)
        assert isinstance(msg.payload, PayloadSchema)

    def test_body_has_payload_fields(self) -> None:
        """payload — это PayloadSchema со всеми полями."""
        msg = Message(**make_kwargs())
        p = msg.payload
        assert isinstance(p, PayloadSchema)
        assert str(p.url) == "http://example.com/hook"
        assert p.body == {"ok": 1}
        assert p.headers == {("X-Api-Key", "secret")}  # Pydantic coerces to set[tuple]
        assert p.timeout == 10
        assert p.pause == 5
        assert p.ttl == 60

    def test_body_str_input(self) -> None:
        """Json[PayloadSchema] принимает и str, не только bytes."""
        kwargs = make_kwargs()
        kwargs["body"] = kwargs["body"].decode()
        msg = Message(**kwargs)
        assert isinstance(msg.payload, PayloadSchema)

    def test_model_validate_dict(self) -> None:
        """Message.model_validate с dict (эквивалент from_attributes=False)."""
        msg = Message.model_validate(make_kwargs())
        assert isinstance(msg.payload, PayloadSchema)
        assert str(msg.payload.url) == "http://example.com/hook"

    def test_model_validate_from_e1c(self) -> None:
        """Message.model_validate(e1c, from_attributes=True).

        Используем ``E1CMessage.model_construct`` (без валидации),
        чтобы ``delivery_tag`` остался ``bytes`` — иначе ``Message``
        унаследует уже сконвертированный ``int``.
        """
        kwargs = make_kwargs()
        e1c = E1CMessage.model_construct(**kwargs)
        msg = Message.model_validate(e1c, from_attributes=True)
        assert isinstance(msg.payload, PayloadSchema)

    # -- body: invalid JSON -------------------------------------------

    def test_body_invalid_json(self) -> None:
        """Невалидный JSON — ошибка от Json[Payload]."""
        with pytest.raises(ValidationError, match="Invalid JSON"):
            Message(**make_kwargs(body=b"not json"))

    def test_body_wrong_type(self) -> None:
        """JSON не объект — ошибка."""
        with pytest.raises(ValidationError):
            Message(**make_kwargs(body=b'"just a string"'))


class TestMessageInheritance:
    """Наследование от E1CMessage."""

    def test_is_e1c(self) -> None:
        msg = Message(**make_kwargs())
        assert isinstance(msg, E1CMessage)

    def test_e1c_fields_present(self) -> None:
        msg = Message(**make_kwargs())
        assert msg.properties.message_id is not None
        assert isinstance(msg.properties.message_id, UUID)
        assert msg.header.durable is True
        assert msg.application_properties.integ_sender_code == "sender"


class TestMessageSerialization:
    """Сериализация / десериализация."""

    def test_dict_roundtrip_payload(self) -> None:
        """payload проходит roundtrip через dict."""
        msg = Message(**make_kwargs())
        raw = msg.payload.model_dump()
        restored = PayloadSchema.model_validate(raw)
        assert restored.url == msg.payload.url
        assert restored.body == msg.payload.body
        assert restored.timeout == msg.payload.timeout

    def test_json_roundtrip_payload(self) -> None:
        """payload проходит roundtrip через JSON."""
        msg = Message(**make_kwargs())
        raw = msg.payload.model_dump_json()
        restored = PayloadSchema.model_validate_json(raw)
        assert restored.url == msg.payload.url

    def test_payload_dumped_as_dict(self) -> None:
        """Json[PayloadSchema] при dump даёт dict."""
        msg = Message(**make_kwargs())
        dumped = msg.model_dump(mode="json")
        assert isinstance(dumped["payload"], dict)
        assert dumped["payload"]["url"] == "http://example.com/hook"
        assert dumped["payload"]["timeout"] == 10

    def test_json_schema(self) -> None:
        schema = Message.model_json_schema()
        assert schema["title"] == "Message"
        body_prop = schema["properties"]["body"]
        assert body_prop["contentSchema"]["$ref"] == "#/$defs/PayloadSchema"


class TestDeliveryTag:
    """delivery_tag приходит как bytes, конвертируется в int."""

    def test_from_bytes(self) -> None:
        msg = Message(**make_kwargs())
        assert msg.delivery_tag == 1
        assert isinstance(msg.delivery_tag, int)

    @pytest.mark.parametrize(
        "tag_bytes",
        [
            b"\x02\x00\x00\x00\x00\x00\x00\x00",
            b"\xff\xff\xff\xff\xff\xff\xff\xff",
        ],
    )
    def test_various_values(self, tag_bytes: bytes) -> None:
        kwargs = make_kwargs()
        kwargs["delivery_tag"] = tag_bytes
        msg = Message(**kwargs)
        assert isinstance(msg.delivery_tag, int)
        assert msg.delivery_tag == int.from_bytes(tag_bytes, "little")
