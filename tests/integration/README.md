# Integration Tests

Этот каталог содержит интеграционные тесты для приложения pyesb.

## Структура тестов

### Unit Tests (`tests/unit/`)
- Тестируют отдельные компоненты в изоляции
- Быстрое выполнение, нет внешних зависимостей
- Запуск: `python -m pytest tests/unit/ -v`

### Integration Tests (этот каталог)
- Тестируют полный стек приложения с использованием FastAPI TestClient
- Проверяют HTTP endpoints и потоки аутентификации
- Запуск: `python -m pytest tests/integration/test_auth.py tests/integration/test_metadata.py -v`

### Docker Integration Tests (`test_docker_integration.py`)
- Тестирует против запущенного Docker контейнера
- Требует установленного и работающего Docker
- Эти тесты пропускаются, если нет доступного Docker контейнера

## Запуск всех тестов (кроме Docker)

```bash
python -m pytest tests/unit/ tests/integration/test_auth.py tests/integration/test_metadata.py -v
```

## Запуск интеграционных тестов Docker (если доступен Docker)

1. Сборка Docker-образа:
   ```bash
docker build -t pyesb-app -f ../Dockerfile ..
```

2. Запуск контейнера:
   ```bash
docker run -d --name pyesb-test-container -p 9090:9090 pyesb-app
```

3. Запуск интеграционных тестов Docker:
   ```bash
python -m pytest tests/integration/test_docker_integration.py -v
```

4. Очистка:
   ```bash
docker stop pyesb-test-container
docker rm pyesb-test-container
```

## Покрытие тестами

- ✅ Authentication endpoint (`/auth/oidc/token`)
  - Корректные credentials
  - Некорректные credentials
  - Отсутствие заголовка authorization
  - Некорректные grant types
  
- ✅ Metadata endpoint (`/applications/{app}/sys/esb/metadata/channels`)
  - Успешное получение каналов
  - Обработка некорректного token
  - Обработка отсутствия token
  - Обработка неизвестного приложения
  
- ✅ Генерация и верификация JWT Token
  - Проверка структуры token
  - Обработка истекших токенов
  - Валидация аудитории

## Сводка результатов тестирования

Все тесты должны проходить с текущей реализацией:
```
17 passed, 7 warnings in 2.14s
```

Предупреждения связаны с устаревшим использованием httpx и могут быть проигнорированы на данный момент.