# 1C ESB Gateway - Реализация на Python

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue.svg)](https://docker.com)

Сервер на основе FastAPI, предоставляющий совместимость с протоколом интеграции 1C Enterprise ESB (Enterprise Service Bus).

## Содержание

- [Обзор](#overview)
- [Основные возможности](#key-features)
- [Архитектура](#architecture)
- [Установка](#installation)
- [Конфигурация](#configuration)
- [Ограничения и особые особенности](#limitations-and-special-features)
- [API Эндпоинты](#api-endpoints)
- [Структура JWT Токена](#jwt-token-structure)
- [Безопасность](#security)
- [Разработка](#development)
- [Поддержка Docker](#docker-support)
- [Сценарии использования](#use-cases)
- [Совместимость протокола](#protocol-compatibility)
- [Дополнительные ресурсы](#additional-resources)
- [Лицензия](#license)

## Обзор

Этот проект реализует легковесный шлюз, имитирующий эндпоинты аутентификации и метаданных родного 1C ESB Gateway. Он позволяет приложениям 1C Enterprise аутентифицироваться с использованием потока OIDC (OpenID Connect) client credentials и получать метаданные AMQP каналов для интеграционных целей.

### Основные возможности

- **Эндпоинт OIDC Token**: Реализует `/auth/oidc/token` для генерации JWT токенов с использованием алгоритма RS512
- **Эндпоинт Метаданных**: Предоставляет `/applications/{app}/sys/esb/metadata/channels` для конфигурации каналов
- **Аутентификация JWT**: Генерация и верификация JSON Web Tokens с правильной структурой claims
- **Конфигурация**: Гибкая конфигурация клиентов и приложений через Pydantic модели
- **Проверка состояния**: Простой эндпоинт `/health` для мониторинга

## Архитектура

Сервер следует модульной архитектуре FastAPI:

```
apps/
├── __init__.py      # Инициализация пакета
├── auth.py          # Эндпоинт OIDC token и логика аутентификации
├── config.py        # Модели конфигурации и настройки по умолчанию
├── main.py          # Точка входа FastAPI приложения
├── metadata.py      # Эндпоинт метаданных для AMQP каналов
└── token.py         # Генерация и верификация JWT токенов
```

## Установка

### Предварительные требования

- Python 3.12 или выше
- менеджер пакетов pip/uv

### Настройка

1. Клонируйте репозиторий:
   ```bash
   git clone <repository-url>
   cd pyesb
   ```

2. Установите зависимости:
   ```bash
   uv sync
   # или с pip:
   pip install -e .
   ```

3. Запустите сервер:
   ```bash
   python app/main.py
   ```

## Конфигурация

Сервер использует конфигурацию по умолчанию, которую можно настроить.

### Клиенты по умолчанию

```python
{
    "test": {
        "client_id": "test",
        "client_secret": "test", 
        "user_id": "22af67ef-d0bd-4861-a7ed-519068ee7d68",
        "user_list_id": "099d11dd-c6d9-401d-8c63-991f21876067", 
        "user_presentation": "test"
    }
}
```

### Приложения по умолчанию

```python
{
    "test": [
        {
            "process": "rav::test::Основное::ПроцессИнтеграции1",
            "channel": "Канал1СНазначение", 
            "access": "READ_ONLY"
        },
        {
            "process": "rav::test::Основное::ПроцессИнтеграции1",
            "channel": "Канал1СИсточник",
            "access": "WRITE_ONLY"
        }
    ]
}
```

## Ограничения и особые особенности

### Credentials Аутентификация

⚠️ **ВНИМАНИЕ**: Этот шлюз специально разработан для тестирования и разработки и **не проверяет credentials** клиентов.

- Клиент должен отправлять Basic auth заголовок с любыми credentials (client_id и client_secret)
- **Любые credentials считаются валидными** - шлюз не проверяет их подлинность
- Это намеренное поведение для удобства тестирования - шлюз генерирует токены независимо от предоставленных credentials
- **Это НЕ для продакшн использования** - в продакшн среде требуется полная аутентификация

Эта особенность позволяет быстро протестировать интеграцию с 1C Enterprise без необходимости настройки сложной инфраструктуры аутентификации.

---

## API Эндпоинты

### 1. Проверка состояния

**GET** `/health`

Простой эндпоинт проверки состояния.

**Ответ:**
```json
{
    "status": "ok"
}
```

### 2. Эндпоинт OIDC Token

**POST** `/auth/oidc/token`

Генерирует JWT токены с использованием потока client credentials.

**Headers:**
- `Authorization: Basic <base64(client_id:client_secret)>`

**Тело запроса:**
```form-data
grant_type=client_credentials

**Важно:** **Любые credentials принимаются**. Этот шлюз не проверяет credentials - это mock gateway для разработки/тестирования. Клиент может отправить любые credentials (client_id и client_secret), и они будут приняты без проверки.

**Ответ (200):**
```json
{
    "id_token": "<JWT>",
    "access_token": "Not implemented",
    "token_type": "Bearer"
}
```

### 3. Эндпоинт Метаданных

**GET** `/applications/{app_name}/sys/esb/metadata/channels`

Получение конфигурации AMQP каналов для конкретного приложения.

**Заголовки:**
- `Authorization: Bearer <id_token>`

**Ответ (200):**
```json
[
    {
        "process": "rav::test::Основное::ПроцессИнтеграции1",
        "processDescription": "",
        "channel": "Канал1СНазначение",
        "channelDescription": "",
        "access": "READ_ONLY"
    }
]
```

## Структура JWT Токена

Генерируемые токены содержат следующие claims:

```json
{
    "iss": "unused-issuer",
    "sub": {
        "user-id": "<UUID>",
        "user-list-id": "<UUID>",
        "user-presentation": "<display-name>",
        "auth-identity": {
            "name": "<base64-sha256(client_id)>",
            "domain": "user_tokens"
        }
    },
    "aud": "<client_id>",
    "iat": <timestamp>,
    "exp": <timestamp>,
    "at_hash": "AccessToken hash (not implemented)"
}
```

## Безопасность

- **Генерация RSA Ключей**: Сервер автоматически генерирует пары 2048-bit RSA ключей для подписи и верификации JWT
- **Хранение Ключей**: Ключи хранятся в `keys/private.pem` и `keys/public.pem`
- **Верификация Токенов**: Токены проверяются с использованием алгоритма RS512 с валидацией аудитории
- **Base64 Хеширование**: ID клиентов хешируются с использованием SHA-256 для claims auth-identity.name
- **Авторизация**: **Любые credentials принимаются**. Этот шлюз не проверяет credentials клиента - это mock gateway для разработки/тестирования. Клиент может отправить любые credentials, и они будут приняты

## Разработка

### Запуск тестов

```bash
# Run all tests (excluding Docker integration)
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py -v

# Run specific test files
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v
```

### Code Quality

The project uses `ruff` for linting and formatting:

```bash
# Check for linting issues
ruff check app/

# Format code automatically
ruff format app/
```

## Docker Support

The project includes comprehensive Docker support for easy deployment. See [DOCKER_README.md](DOCKER_README.md) for detailed Docker configuration and usage instructions.

### Quick Docker Start

```bash
# Build and run with Docker Compose
docker-compose up -d

# Test the service
curl http://localhost:9090/health  # Should return {"status":"ok"}

# View logs
docker-compose logs -f app

# Stop the service
docker-compose down
```

### Key Docker Features

- **Multi-stage builds** for optimal image size (~80MB)
- **Persistent key storage** via volume mounts
- **Health checks** built into the container
- **Environment variable configuration** for customization
- **Development mode** with live code reloading support

## Use Cases

This gateway is useful for:

1. **Development/Testing**: Mock 1C ESB Gateway during development without requiring the full 1C platform
2. **Integration Testing**: Test 1C applications against a predictable, controllable endpoint
3. **Hybrid Environments**: Bridge between 1C Enterprise and external systems
4. **Legacy System Migration**: Gradually migrate from native 1C ESB to modern alternatives

## Protocol Compatibility

The server implements the protocol as described in `docs/protocol.md`, ensuring compatibility with 1C Enterprise applications that expect:

- Specific JWT claim structure (RS512 signed)
- OIDC client credentials flow
- AMQP channel metadata format
- Error response formats matching 1C expectations

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes with proper tests
4. Ensure all linting checks pass
5. Submit a pull request

## Additional Resources

- **[DOCKER_README.md](DOCKER_README.md)** - Comprehensive Docker deployment guide
- **[TESTING_SUMMARY.md](TESTING_SUMMARY.md)** - Test coverage and results summary
- **[docs/protocol.md](docs/protocol.md)** - Detailed protocol specifications
- **[todo.md](todo.md)** - Development roadmap and future features

## License

MIT License - See [LICENSE](LICENSE) for details

## 🚀 Additional Resources

### 📚 Project Navigation
- **[AGENT_GUIDE.md](AGENT_GUIDE.md)** - Comprehensive agent navigation guide
- **[NAVIGATION.md](NAVIGATION.md)** - Interactive project navigation
- **[COMMAND_REFERENCE.md](COMMAND_REFERENCE.md)** - Quick command reference
- **[PROJECT_MAP.md](PROJECT_MAP.md)** - Visual architecture diagrams
- **[SUMMARY.md](SUMMARY.md)** - Complete project summary

### 🎯 Quick Navigation
```bash
# Understand the project structure
cat SUMMARY.md

# Get command reference
cat COMMAND_REFERENCE.md

# Find specific code quickly
grep -r "auth" app/ --include="*.py"

# Understand the protocol
docs/protocol.md

# Check technical analysis
cat zed_agent_notes.md

# See development roadmap
cat todo.md
```

### 💡 Navigation Tips
- Use `AGENT_GUIDE.md` for comprehensive documentation
- Use `NAVIGATION.md` for interactive code exploration
- Use `COMMAND_REFERENCE.md` for quick command lookup
- Use `PROJECT_MAP.md` for visual architecture understanding
- Use `SUMMARY.md` for complete project overview

These navigation tools make it easy to find exactly what you need when working with the PyESB project!

---

## 🏆 Project Completion Status

✅ **Core Features Complete**: HTTP server, OIDC authentication, JWT tokens, metadata API, AMQP server

✅ **Documentation Complete**: Comprehensive guides, protocol analysis, technical notes

✅ **Navigation Ready**: Multiple navigation tools for easy project orientation

✅ **Development Ready**: Well-structured codebase with good test coverage

✅ **Deployment Ready**: Docker support with health checks and monitoring

🚀 **Project is ready for use and extension!**