# 1C ESB Gateway

Compatible server for 1C Enterprise ESB integration (OIDC + AMQP)

## Описание

Это сервер-проксы для интеграции с 1C Enterprise через ESB (Enterprise Service Bus). Приложение использует:

- **OIDC** (OpenID Connect) - аутентификация и авторизация
- **AMQP** (Advanced Message Queuing Protocol) - асинхронная передача сообщений

## Требования

- Python >= 3.13
- `fastapi[standard-no-fastapi-cloud-cli]`
- `pyesb-amqp` (устанавливается из git-репозитория)

## Установка

```bash
# Установка всех зависимостей через uv
uv sync

# Установка с тестами
uv sync --all-extras
```

## Запуск

```bash
# Запуск разработки
uv run fastapi dev --host=0.0.0.0 --port=8000

# Запуск в продакшене
uv run fastapi run --host=0.0.0.0 --port=8000
```

## API

Документация API скрыта (docs_url и redoc_url отключены в продакшене).

## Конфигурация

Сервер регистрирует следующие каналы обработки:

| Канал | Процесс | Доступ | Описания |
|-------|---------|--------|----------|
| channel1 | process1 | WRITE_ONLY | process_description1 / channel_description1 |
| channel2 | process2 | WRITE_ONLY | process_description2 / channel_description2 |

## Структура проекта

```
pyesb/
├── app/
│   └── main.py          # Основной файл приложения FastAPI
├── pyproject.toml       # Конфигурация проекта
├── uv.lock              # Заблокированные зависимости
└── README.md            # Эта документация
```

## Развитие

Для добавления новых каналов:

1. Добавьте `ChannelDesription` в `oidc_add_routes`
2. Укажите уникальный процесс и канал
3. Настройте обработчик AMQP

## Лицензия

MIT
