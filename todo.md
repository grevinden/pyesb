# План реализации: Python ↔ 1C через AMQP 1.0

## Архитектура

```
┌──────────────┐     AMQP 1.0      ┌────────────┐     AMQP 0-9-1    ┌──────────┐
│  1C Enterprise │ ────────────────► │  RabbitMQ  │ ◄──────────────► │  Python  │
│  (1cv8.exe)   │    port 5672      │  (broker)  │      port 5672   │  (pika)  │
└──────┬───────┘                    └────────────┘                  └────┬─────┘
       │                                                                  │
       │  HTTP (auth)                                                     │  HTTP (auth)
       │  port 9090                                                       │  port 9090
       └──────────────────────────┐    ┌──────────────────────────────────┘
                                  ▼    ▼
                          ┌────────────────┐
                          │  Python Auth   │
                          │  HTTP Server   │
                          │  (FastAPI)     │
                          └────────────────┘
```

**Компоненты Python:**

| Компонент | Порт | Протокол | Назначение |
|-----------|------|----------|------------|
| Auth Service | 9090 | HTTP | OIDC token endpoint для 1C |
| AMQP Consumer | — | AMQP 0-9-1 (к RabbitMQ) | Приём сообщений из `Канал1СНазначение` |
| AMQP Producer | — | AMQP 0-9-1 (к RabbitMQ) | Отправка ответов в `Канал1СИсточник` |

---

## Этап 0: Инфраструктура

### 0.1 Установка RabbitMQ

```bash
# Docker (рекомендуется)
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=esb \
  -e RABBITMQ_DEFAULT_PASS=esb \
  rabbitmq:4-management

# Включить AMQP 1.0 плагин (уже включён в 4.x по умолчанию)
docker exec rabbitmq rabbitmq-plugins enable rabbitmq_amqp1_0
```

**Или через system RabbitMQ:**
```bash
sudo apt install rabbitmq-server
sudo rabbitmq-plugins enable rabbitmq_amqp1_0
sudo systemctl start rabbitmq-server
```

### 0.2 Создание очередей в RabbitMQ

Через веб-консоль (`http://localhost:15672`, user: `esb`, pass: `esb`):
- Создать очередь `Канал1СНазначение` (durable)
- Создать очередь `Канал1СИсточник` (durable)

Или через `rabbitmqadmin`:
```bash
rabbitmqadmin declare queue name=Канал1СНазначение durable=true
rabbitmqadmin declare queue name=Канал1СИсточник durable=true
```

### 0.3 Зависимости Python

```bash
uv add fastapi uvicorn pika httpx pyjwt
```

---

## Этап 1: Auth Service (HTTP, порт 9090)

**Файл:** `auth.py`

**Назначение:** Замена штатного Auth Manager 1C:Шины. 1C обращается к этому endpoint для получения JWT.

**Endpoint:**

```
POST /auth/oidc/token
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

**Ответ:**
```json
{
  "id_token": "<JWT RS512>",
  "access_token": "Not implemented",
  "token_type": "Bearer"
}
```

**Что нужно сделать:**
- [ ] Реализовать FastAPI приложение
- [ ] Проверить Basic Auth (client_id:client_secret)
- [ ] Сгенерировать JWT (RS512) с `sub` (user-id) и `exp` (1 час)
- [ ] Отдавать статический список каналов по `/applications/{app}/sys/esb/metadata/channels`
- [ ] Логировать все запросы

**GET /applications/{app}/sys/esb/metadata/channels:**
```json
[{
  "process": "pyesb::default::MainProcess",
  "channel": "Канал1СНазначение",
  "access": "READ_ONLY"
}, {
  "process": "pyesb::default::MainProcess",
  "channel": "Канал1СИсточник",
  "access": "WRITE_ONLY"
}]
```

---

## Этап 2: AMQP Consumer (приём сообщений)

**Файл:** `consumer.py`

**Назначение:** Подключиться к RabbitMQ, слушать очередь `Канал1СНазначение`, писать сообщения в лог.

- [ ] Подключиться к RabbitMQ через `pika.BlockingConnection`
- [ ] Объявить очередь `Канал1СНазначение`
- [ ] Подписаться (basic_consume)
- [ ] В callback: логировать тело сообщения, headers, timestamp
- [ ] Обрабатывать по одному сообщению (basic_qos=1)
- [ ] Ack после обработки

```python
# Прототип callback
def on_message(ch, method, props, body):
    logger.info("Получено сообщение:")
    logger.info("  Body: %s", body)
    logger.info("  Headers: %s", props.headers)
    logger.info("  Content-Type: %s", props.content_type)
    ch.basic_ack(delivery_tag=method.delivery_tag)
```

---

## Этап 3: AMQP Producer (отправка ответов)

**Файл:** `producer.py`

**Назначение:** Публиковать сообщения-ответы в очередь `Канал1СИсточник`.

- [ ] Подключиться к RabbitMQ
- [ ] Функция `send_reply(message_body, correlation_id)`
- [ ] Публиковать с нужными headers
- [ ] Опционально: поддержка `RecipientCode` header для маршрутизации

```python
def send_reply(body: str, correlation_id: str = None):
    channel.basic_publish(
        exchange='',
        routing_key='Канал1СИсточник',
        body=body,
        properties=pika.BasicProperties(
            correlation_id=correlation_id,
            content_type='application/json',
            headers={'RecipientCode': '1C'}  # если нужно
        )
    )
```

---

## Этап 4: Объединение в сервис

**Файл:** `main.py` + `config.py`

- [ ] `Config` класс: RabbitMQ host/port/credentials, HTTP port, JWT secret
- [ ] Чтение конфига из переменных окружения (pydantic-settings)
- [ ] Запуск Auth Service + Consumer в одном процессе (через asyncio)
- [ ] Graceful shutdown (SignalHandler)

```python
class Settings(BaseSettings):
    rabbitmq_host: str = 'localhost'
    rabbitmq_port: int = 5672
    rabbitmq_user: str = 'esb'
    rabbitmq_pass: str = 'esb'
    http_port: int = 9090
    jwt_private_key: str = '...'
    jwt_public_key: str = '...'
```

---

## Этап 5: Настройка 1C

- [ ] В 1C Enterprise указать:
  - HTTP endpoint: `http://python-host:9090`
  - AMQP endpoint: `python-host:5672` (RabbitMQ)
  - Client ID / Client Secret (согласовать с Python Auth Service)
- [ ] Получить id_token (логируем)
- [ ] Проверить подключение: 1C шлёт сообщение → Python ловит в `Канал1СНазначение`

---

## Этап 6: Тестирование

- [ ] Mock-тест: `curl` запрос к Auth Service → получить JWT
- [ ] Mock-тест: Опубликовать сообщение в RabbitMQ вручную → проверить лог consumer
- [ ] Mock-тест: Вызвать producer → проверить очередь в RabbitMQ
- [ ] Интеграционный тест: 1C реально подключается и шлёт сообщение

---

## Проверка 1C-соединения вручную (curl + скрипты)

### Получить токен:
```bash
curl -s -X POST http://localhost:9090/auth/oidc/token \
  -u "client_id:client_secret" \
  -d "grant_type=client_credentials" \
  | jq .
```

### Отправить сообщение через AMQP 1.0 напрямую:
```bash
# Через qpid-proton-tools (если установлен)
uv run python -c "
from proton import Messenger
m = Messenger()
m.start()
msg = Message()
msg.address = 'Канал1СНазначение'
msg.body = 'test'
m.put(msg)
m.send()
m.stop()
"
```

### Проверить очередь RabbitMQ:
```bash
curl -s -u esb:esb http://localhost:15672/api/queues | jq '.[].name'
```

---

## Схема data flow

```
1C отправляет сообщение:
  POST (auth) → получает id_token
  AMQP 1.0 → RabbitMQ (exchange → Канал1СНазначение)
  Python consumer ← читает из Канал1СНазначение
  → Пишет в лог
  → Выполняет бизнес-логику
  → Публикует ответ в Канал1СИсточник (producer)
  RabbitMQ → доставляет 1C
```

---

## Черновик структуры проекта

```
pyesb/
├── pyproject.toml
├── README.md
├── todo.md
├── protocol.md
├── stream.bin
├── config.py          # pydantic-settings
├── auth.py            # FastAPI (порт 9090)
├── consumer.py        # pika consumer
├── producer.py        # pika producer
├── main.py            # точка входа
└── tests/
    ├── test_auth.py
    └── test_amqp.py
```

---

## План по этапам

| Этап | Что делает | Файлы | Готовность |
|------|-----------|-------|------------|
| **0** | Инфраструктура (RabbitMQ, зависимости) | — | ⬜ |
| **1** | Auth HTTP Server | `auth.py`, `config.py` | ⬜ |
| **2** | Consumer (приём, логгирование) | `consumer.py` | ⬜ |
| **3** | Producer (отправка ответов) | `producer.py` | ⬜ |
| **4** | Сервис (main, graceful shutdown) | `main.py` | ⬜ |
| **5** | Настройка 1C | — | ⬜ |
| **6** | Тестирование | `tests/` | ⬜ |
