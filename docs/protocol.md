# Протокол 1C ESB (по данным mitmproxy capture + документации)

## Формат capture-файла

Файл `stream.bin` — это дамп mitmproxy во встроенном формате сериализации (не JSON, не HAR).
Каждый блок — один HTTP-обмен ("flow") между `1cv8.exe` (клиент) и сервером `1С:Шина` (10.1.30.90).

Структура записи:

```
{длина_блока}:{ключ};{длина_строки}:{значение},{следующий_ключ};...
```

Разделители:
- `;` — ключ=значение
- `,` — следующий ключ в том же объекте  
- `!` — булево false / true
- `#` — разделитель между host и port в address
- `]` — конец массива
- `}` — конец объекта
- `~` — пустое значение

Каждый HTTP-обмен представлен одним блоком "flow", содержащим:
- `request` — HTTP-запрос
- `response` — HTTP-ответ
- `client_conn` — информация о клиентском соединении
- `server_conn` — информация о серверном соединении
- `id`, `type`, `version` — метаданные

Поле `9:websocket;0:~` в начале — это артефакт mitmproxy (WebSocket-захват HTTP), не влияет на суть.

---

## Общая архитектура

```
1cv8.exe (1C Enterprise 8.3)
        │
        ├── HTTP (port 9090) ───────────► 1C:Шина Server (10.1.30.90)
        │     │                              │
        │     ├── /auth/oidc/token           │── Auth Manager (OIDC)
        │     └── /applications/*/sys/esb/   │── Metadata API
        │              metadata/channels     │
        │                                    │
        └── AMQP 1.0 (port 6698) ──────────►│── Встроенный AMQP 1.0 брокер
                                            │    (1C:Шина = ESB Gateway)
```

Клиент: **1cv8.exe** (1C Enterprise 8.3, `User-Agent: 1C+Enterprise/8.3`)

Сервер 1C:Шина (ESB Gateway) на **10.1.30.90**:
- **HTTP** порт **9090** — без TLS, Plain HTTP
- **AMQP 1.0** порт **6698** — встроенный AMQP-брокер

> **Важно:** Дамп зафиксирован в среде, где сервер 1C:Шина реально запущен.
> AMQP-трафик на порту 6698 в дампе **отсутствует** — mitmproxy захватывает только HTTP.

---

## Жизненный цикл сессии

### Этап 1: Аутентификация (OAuth2 Client Credentials)

```
POST /auth/oidc/token HTTP/1.1
Host: tower.local:9090
User-Agent: 1C+Enterprise/8.3
Accept: */*
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64(client_id:client_secret)>
Content-Length: 29

grant_type=client_credentials
```

**Успешный ответ (200):**
```json
{
    "id_token": "eyJ...JWT...",
    "access_token": "Not implemented",
    "token_type": "Bearer"
}
```

**Ошибка (401):**
```json
{
    "error" : {
        "code" : 16,
        "status" : "UNAUTHENTICATED",
        "message" : "Incorrect username or password."
    }
}
```

**Декодированный JWT (id_token):**
```json
{
  "iss": "unused-issuer",
  "sub": {
    "user-id": "22af67ef-d0bd-4861-a7ed-519068ee7d68",
    "user-list-id": "099d11dd-c6d9-401d-8c63-991f21876067",
    "user-presentation": "test",
    "auth-identity": {
      "name": "kgQsv_tArk8mX6Nq16YepTX9nzcBSf8v4-Y18ZN2sM=",
      "domain": "user_tokens"
    }
  },
  "aud": "kgQsv_tArk8mX6Nq16YepTX9nzcBSf8v4-Y18ZN2sM=",
  "iat": 1781978834,
  "exp": 1781982434,
  "at_hash": "AccessToken hash (not implemented)"
}
```

Особенности:
- `access_token` всегда `"Not implemented"` — используется только `id_token`
- `id_token` подписан RS512 (JWT RSASSA-PKCS1-v1_5)
- `aud` (audience) = client_id, совпадает с именем в Basic auth
- auth-identity содержит `name` (хэш client_id) и `domain` = `"user_tokens"`
- Тип токена: `Bearer`
- **Токен живёт 1 час** — `exp - iat = 3600`

---

### Этап 2: Получение метаданных каналов

```
GET /applications/test/sys/esb/metadata/channels HTTP/1.1
Host: tower.local:9090
User-Agent: 1C+Enterprise/8.3
Accept: */*
Authorization: Bearer <id_token>
```

**Структура endpoint:**
```
/applications/{app_name}/sys/esb/metadata/channels
```
Где `{app_name}` = имя приложения в 1C:Шина (в дампе — `test`).

**Успешный ответ (200):**
```json
[{
    "process": "rav::test::Основное::ПроцессИнтеграции1",
    "processDescription": "",
    "channel": "Канал1СНазначение",
    "channelDescription": "",
    "access": "READ_ONLY"
}, {
    "process": "rav::test::Основное::ПроцессИнтеграции1",
    "processDescription": "",
    "channel": "Канал1СИсточник",
    "channelDescription": "",
    "access": "WRITE_ONLY"
}]
```

**Поля:**
| Поле | Описание |
|---|---|
| `process` | Идентификатор процесса интеграции |
| `channel` | Имя AMQP-очереди/address |
| `access` | `READ_ONLY` (consuming), `WRITE_ONLY` (producing) |

**Назначение каналов:**
- `Канал1СНазначение` (READ_ONLY) — **приём** сообщений из 1C (Python должен подписаться)
- `Канал1СИсточник` (WRITE_ONLY) — **отправка** сообщений в 1C (Python публикует ответы)

---

### Этап 3: AMQP 1.0 подключение (порт 6698)

Документация 1C:Шины:
> "Полученный билет должен использоваться при подключении к брокеру сервера «1С:Шины»
> по протоколу AMQP, а также при вызове HTTP и SOAP-сервисов «Шины».
> При подключении к брокеру сервера билет указывается **в качестве имени и пароля** при подключении."

Это означает **SASL PLAIN** с `id_token` как username и password:
```
SASL PLAIN: \0<id_token>\0<id_token>
```

В дампе AMQP-трафик отсутствует, но структура подключения по документации:

1. TCP connect → 10.1.30.90:6698
2. SASL PLAIN auth с id_token (user + password)
3. AMQP Open frame (container-id, hostname)
4. AMQP Begin frame (session)
5. AMQP Attach frame (link) к каналу `Канал1СНазначение` (receiver) или `Канал1СИсточник` (sender)

---

### Этап 4: Retry-loop с опечаткой (баг клиента 1C)

Клиент также безуспешно пытается вызвать:
```
GET /apllications/test/sys/esb/runtime/channels
```
С опечаткой: **`apllications`** вместо **`applications`**.

Сервер отвечает **404 Not Found**:
```json
{
    "error": {
        "code": 5,
        "status": "NOT_FOUND",
        "message": "Application \"apllications\" not found."
    }
}
```

Клиент повторяет запрос ~50+ раз с интервалами:
`6s, 6s, 6s, 10s, 10s, 6s, 10s, 30s, ...`

Каждый раз создаётся новое TCP-соединение. Это retry-loop **без exponential backoff** — баг 1С или неправильная конфигурация.

---

## Схема URL-маршрутов

| Маршрут | Метод | Описание |
|---|---|---|
| `/auth/oidc/token` | POST | OAuth2 Client Credentials → id_token |
| `/applications/{app}/sys/esb/metadata/channels` | GET | Список каналов с типами доступа |
| ~~`/apllications/{app}/sys/esb/runtime/channels`~~ | GET | Сломан (опечатка), не работает |

---

## Формат ответа ошибок

```json
{
    "error": {
        "code": 5,
        "status": "NOT_FOUND",
        "message": "Application \"...\" not found.",
        "details": []
    }
}
```

| Код | Статус | Значение |
|---|---|---|
| 5 | NOT_FOUND | Приложение/ресурс не найдены |
| 16 | UNAUTHENTICATED | Неверные учётные данные |

---

## Сценарий: Python как AMQP 1.0 сервер (без 1C:Шина)

Если сервер 1C:Шина отсутствует, а 1C Enterprise должна подключиться напрямую к Python:

```
1cv8.exe (1C Enterprise 8.3)
        │
        ├── HTTP (port 9090) ──────────► Python Auth Service*
        │     └── /auth/oidc/token           (генерация JWT)
        │
        └── AMQP 1.0 (port 6698) ─────────► Python AMQP 1.0 Server*
                                             (приём/отправка сообщений)
```

* — Python должен реализовать оба endpoint.

---

## Сценарий: RabbitMQ как брокер

```
1cv8.exe (1C Enterprise 8.3)          Python Client
        │                                    │
        │ AMQP 1.0                           │ AMQP 0-9-1 / 1.0
        ▼                                    ▼
  ┌─────────────────┐                  ┌─────────────────┐
  │    RabbitMQ      │◄───────────────►│    Python        │
  │  (AMQP 1.0 via   │                  │  (pika / proton)│
  │   plugin)        │                  │                 │
  └─────────────────┘                  └─────────────────┘
```

Проще в реализации, но требует RabbitMQ как middleware.

---

## Наблюдения и выводы

1. **JWT вместо сессии** — каждый запрос содержит Bearer token. Токен живёт 1 час.
2. **Нет TLS** — весь трафик Plain HTTP. Basic auth и Bearer token в открытом виде.
3. **client_secret статический** — одинаковый во всех сессиях.
4. **1C Enterprise 8.3** — User-Agent: `1C+Enterprise/8.3`.
5. **AMQP 1.0 SASL PLAIN** — id_token передаётся как user + password.
6. **Кириллические имена каналов** — `Канал1СНазначение`, `Канал1СИсточник`.
7. **AMQP-трафик в дампе отсутствует** — только HTTP.
8. **Опечатка `/apllications`** — вызывает бесконечный retry-loop, баг конфигурации 1С.
