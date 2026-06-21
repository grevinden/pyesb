# 🤖 Agent Navigation Guide for pyesb Project

## 📋 Project Summary

**PyESB** - 1C ESB Gateway compatible server for development and testing
- **Purpose**: Mock 1C Enterprise Service Bus for integration testing
- **Tech Stack**: FastAPI, Qpid Proton (AMQP 1.0), JWT RS512, Pydantic
- **Status**: ✅ Production-ready for development/testing scenarios

## 🚀 Quick Navigation Commands

### 📂 Project Structure Overview
```bash
# Get complete project summary
cat SUMMARY.md

# Quick command reference
cat COMMAND_REFERENCE.md

# Detailed architecture diagrams
cat PROJECT_MAP.md

# Agent-specific technical notes
cat zed_agent_notes.md

# Development roadmap
cat todo.md
```

### 🔍 Code Search Patterns
```bash
# Find authentication-related code
grep -r "auth" app/ --include="*.py"

# Find JWT token handling
grep -r "jwt\|token" app/ --include="*.py" | grep -v "__pycache__"

# Find AMQP server implementation
grep -r "amqp\|proton" app/ --include="*.py"

# Find configuration loading
grep -r "config\|settings" app/ --include="*.py" | grep -v "__pycache__"

# Find test cases
find tests/ -name "*.py" -exec grep -l "def test_" {} \;
```

### 🧪 Testing Commands
```bash
# Run all tests (skip Docker integration)
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py -v

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests only
python -m pytest tests/integration/ -v

# Run specific test file
python -m pytest tests/unit/test_auth.py -v

# Check code quality
ruff check app/
ruff format app/
```

### 🚀 Development Commands
```bash
# Install dependencies
uv sync

# Start development server
python app/main.py

# Start with custom port
PYESB_PORT=8080 python app/main.py

# Generate RSA keys manually
python -c "from app.token import _ensure_keys; _ensure_keys()"

# Test token generation
python -c "from app.config import DEFAULT_CONFIG; from app.token import create_id_token; print(create_id_token(list(DEFAULT_CONFIG.clients.values())[0], DEFAULT_CONFIG))"

# Test configuration loading
python -c "from app.config import get_settings; print(get_settings().get_config())"
```

### 🐳 Docker Commands
```bash
# Build and start with Docker Compose
docker-compose up -d

# Check service health
curl http://localhost:9090/health

# View container logs
docker-compose logs -f app

# Stop containers
docker-compose down

# Rebuild with cache clearing
docker-compose build --no-cache && docker-compose up -d

# Check container status
docker-compose ps
```

### 📊 API Testing
```bash
# Get health status
curl http://localhost:9090/health

# Get OIDC token (basic auth with any credentials)
curl -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic dGVzdDp0ZXN0" \
  -d "grant_type=client_credentials"

# Get metadata channels (requires valid JWT)
curl -X GET http://localhost:9090/applications/test/sys/esb/metadata/channels \
  -H "Authorization: Bearer <your-jwt-token>"
```

## 📂 File Navigation Guide

### 🎯 Core Application Files

#### `app/main.py` - FastAPI Entry Point
- **Purpose**: Main application startup and route registration
- **Key Components**:
  - FastAPI app initialization
  - Endpoint registration
  - AMQP server integration
  - Health check endpoint
- **Navigation Tips**: Look for `@app.on_event("startup")` and `@app.on_event("shutdown")` for lifecycle management

#### `app/auth.py` - OIDC Authentication
- **Purpose**: `/auth/oidc/token` endpoint implementation
- **Key Components**:
  - Basic auth credential extraction
  - JWT token generation
  - Error response handling
- **Navigation Tips**: Search for `INVALID_REQUEST` and `INTERNAL_ERROR` error responses

#### `app/metadata.py` - Metadata Service
- **Purpose**: `/applications/{app}/sys/esb/metadata/channels` endpoint
- **Key Components**:
  - JWT token verification
  - Application channel lookup
  - Response serialization
- **Navigation Tips**: Look for `UNAUTHENTICATED`, `NOT_FOUND`, and `INTERNAL_ERROR` error responses

#### `app/token.py` - JWT Token Service
- **Purpose**: JWT generation and verification
- **Key Components**:
  - RSA key management
  - JWT claims construction
  - Token signing and verification
- **Navigation Tips**: Search for `_ensure_keys()` and `create_id_token()` functions

#### `app/config.py` - Configuration System
- **Purpose**: Settings and configuration management
- **Key Components**:
  - Pydantic settings models
  - Configuration file loading
  - Environment variable parsing
- **Navigation Tips**: Look for `BaseSettings`, `AppConfig`, and `DEFAULT_CONFIG`

#### `app/interfaces.py` - Type System
- **Purpose**: Custom type definitions and validation
- **Key Components**:
  - IPv4 address validation
  - Process ID and Channel types
  - Custom Pydantic types
- **Navigation Tips**: Search for `TypedDict` and `Annotated` usage

#### `app/amqp_server.py` - AMQP 1.0 Server
- **Purpose**: Non-blocking AMQP message broker
- **Key Components**:
  - Qpid Proton integration
  - Message handling
  - Threaded server implementation
- **Navigation Tips**: Look for `NonBlockingAMQPContainer` and `AMQPMessageHandler` classes

### 🧪 Test Files

#### `tests/unit/` - Unit Tests
- **Structure**:
  - `test_auth.py` - Authentication endpoint tests
  - `test_metadata.py` - Metadata endpoint tests
  - `test_token.py` - JWT token tests
  - `test_config.py` - Configuration tests
  - `test_interfaces.py` - Type system tests

#### `tests/integration/` - Integration Tests
- **Structure**:
  - `test_api_integration.py` - HTTP API integration tests
  - `test_amqp_server.py` - AMQP server tests
  - `test_token_flow.py` - Full token flow tests

#### `tests/conftest.py` - Test Fixtures
- **Key Components**:
  - Test client setup
  - Configuration fixtures
  - Mock dependencies

## 🔍 Search Strategies

### 🎯 Finding Specific Functionality

| **Need to Find** | **Search Command** | **Key Files** |
|-----------------|-------------------|---------------|
| **Authentication logic** | `grep -r "Basic auth\|client_credentials" app/` | `auth.py` |
| **JWT token generation** | `grep -r "create_id_token\|RS512" app/` | `token.py` |
| **AMQP server setup** | `grep -r "proton\|AMQPContainer" app/` | `amqp_server.py` |
| **Configuration loading** | `grep -r "get_settings\|AppConfig" app/` | `config.py` |
| **Error handling** | `grep -r "INTERNAL_ERROR\|UNAUTHENTICATED" app/` | All endpoint files |
| **Type definitions** | `grep -r "TypedDict\|Annotated" app/` | `interfaces.py` |
| **Test fixtures** | `grep -r "@pytest.fixture" tests/` | `conftest.py` |

### 📝 Understanding Code Flow

#### 🔄 OIDC Token Flow
1. **Request**: `POST /auth/oidc/token` with Basic auth
2. **Processing**: `auth.py` - extract credentials, call `create_id_token()`
3. **Token Creation**: `token.py` - build claims, sign with RSA key
4. **Response**: JSON with `id_token`, `access_token`, `token_type`

#### 📋 Metadata Flow
1. **Request**: `GET /applications/{app}/sys/esb/metadata/channels` with Bearer token
2. **Verification**: `metadata.py` - verify JWT using `verify_id_token()`
3. **Lookup**: Find application in config
4. **Response**: JSON array of channel configurations

#### 📡 AMQP Message Flow
1. **Server Start**: `amqp_server.py` creates `NonBlockingAMQPContainer`
2. **Message Receive**: `AMQPMessageHandler` processes incoming messages
3. **Logging**: Extract and log message metadata
4. **Accept/Reject**: Handle message based on processing result

## 🎯 Common Tasks

### 📝 Adding a New Client

1. **Edit configuration** (JSON file or environment variables):
   ```json
   {
     "clients": {
       "new_client": {
         "client_id": "new_client",
         "client_secret": "secret123",
         "user_id": "123e4567-e89b-12d3-a456-426614174000",
         "user_list_id": "123e4567-e89b-12d3-a456-426614174001",
         "user_presentation": "New User"
       }
     }
   }
   ```

2. **Add application configuration** (optional):
   ```json
   {
     "applications": {
       "new_app": [
         {
           "process": "new::namespace::Process",
           "channel": "new_channel",
           "access": "READ_ONLY"
         }
       ]
     }
   }
   ```

### 🔧 Adding a New Endpoint

1. **Create new file** in `app/` directory (e.g., `app/new_endpoint.py`)

2. **Define route** in `main.py`:
   ```python
   from app.new_endpoint import router
   app.include_router(router)
   ```

3. **Implement endpoint** with proper error handling:
   ```python
   from fastapi import APIRouter, HTTPException, status
   
   router = APIRouter()
   
   @router.get("/new/path")
   async def new_endpoint():
       try:
           # Implementation logic
           return {"status": "ok"}
       except Exception as e:
           raise HTTPException(
               status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
               detail="INTERNAL_ERROR"
           )
   ```

### 🧪 Writing Tests

1. **Unit test** example:
   ```python
   # tests/unit/test_new_endpoint.py
   import pytest
   from fastapi.testclient import TestClient
   from app.main import app
   
   client = TestClient(app)
   
   def test_new_endpoint():
       response = client.get("/new/path")
       assert response.status_code == 200
       assert response.json() == {"status": "ok"}
   ```

2. **Integration test** example:
   ```python
   # tests/integration/test_new_endpoint_integration.py
   import pytest
   from fastapi.testclient import TestClient
   from app.main import app
   
   @pytest.mark.asyncio
   async def test_new_endpoint_integration():
       client = TestClient(app)
       response = client.get("/new/path")
       assert response.status_code == 200
   ```

### 🔐 Regenerating RSA Keys

```bash
# Remove existing keys
rm -f keys/private.pem keys/public.pem

# Generate new keys
python -c "from app.token import _ensure_keys; _ensure_keys()"

# Verify keys were created
ls -la keys/
```

## 📊 Debugging Tips

### 🐛 Common Issues

#### **JWT Verification Failing**
```bash
# Check key files exist
ls -la keys/

# Verify key format
openssl rsa -in keys/private.pem -check
openssl pkey -in keys/public.pem -pubin -text

# Test token generation
python -c "from app.config import get_settings; from app.token import create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); print(token)"

# Test token verification
python -c "import jwt; from app.config import get_settings; from app.token import verify_id_token, create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); print(verify_id_token(token, cfg))"
```

#### **AMQP Server Not Starting**
```bash
# Check port availability
netstat -tuln | grep 6698

# Test AMQP server startup
python -c "from app.amqp_server import NonBlockingAMQPContainer; from app.config import get_settings; cfg = get_settings().get_config(); container = NonBlockingAMQPContainer(cfg); container.start()"

# Check logs for errors
python app/main.py 2>&1 | grep -i amqp
```

#### **Configuration Loading Issues**
```bash
# Test configuration loading
python -c "from app.config import get_settings; print(get_settings().get_config())"

# Check environment variables
env | grep PYESB_

# Test JSON config file
python -c "import json; from app.config import AppConfig; config = json.load(open('config.json')); print(AppConfig(**config))"
```

## 🚀 Performance Optimization

### 🔄 AMQP Performance
- **Current**: Threaded implementation with one thread per message
- **Optimization**: Consider async I/O with `asyncio` and Qpid Proton's async API
- **Monitoring**: Add Prometheus metrics for message rates and processing times

### 📈 HTTP Performance
- **Current**: Uvicorn single worker
- **Optimization**: Use multiple workers in production:
  ```bash
  uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 9090
  ```

### 💾 Memory Management
- **Current**: Keys loaded into memory at startup
- **Optimization**: Consider key caching or secure memory handling for sensitive operations

## 📝 Documentation Strategy

### 🎯 Documenting New Features

1. **Code comments**: Add docstrings to functions and classes
2. **README updates**: Update the main README with new features
3. **Protocol docs**: Update `docs/protocol.md` if protocol changes
4. **Test coverage**: Add comprehensive tests with clear descriptions

### 📋 Documentation Files

- **README.md**: User-facing documentation and quick start
- **docs/protocol.md**: Technical protocol specifications
- **todo.md**: Development roadmap and future features
- **DOCKER_README.md**: Docker deployment documentation
- **TESTING_SUMMARY.md**: Test coverage and results

## 🔄 Continuous Integration

### 🧪 Test Automation

```bash
# Add to CI/CD pipeline

# 1. Install dependencies
uv sync

# 2. Run linter
ruff check app/

# 3. Run formatter
ruff format app/ --check

# 4. Run tests
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py -v

# 5. Build Docker image
docker-compose build

# 6. Run container tests
docker-compose up -d
docker-compose exec app python -m pytest tests/integration/ -v
docker-compose down
```

## 🏁 Project Completion Checklist

### ✅ Core Features
- [x] OIDC Token Endpoint (`/auth/oidc/token`)
- [x] Metadata Endpoint (`/applications/{app}/sys/esb/metadata/channels`)
- [x] JWT Token Generation (RS512)
- [x] AMQP 1.0 Server
- [x] Configuration System
- [x] Health Check Endpoint
- [x] Unit Tests
- [x] Integration Tests
- [x] Docker Support

### 📚 Documentation
- [x] README.md with comprehensive guides
- [x] Protocol documentation
- [x] Development roadmap
- [x] Docker deployment guide
- [x] Test coverage summary

### 🔧 Quality Assurance
- [x] Code formatting (ruff)
- [x] Linting (ruff)
- [x] Type hints
- [x] Error handling
- [x] Configuration validation

### 🚀 Deployment Ready
- [x] Docker multi-stage build
- [x] Health checks
- [x] Environment variables
- [x] Config file support
- [x] Logging setup

## 💡 Pro Tips

### 🔍 Navigation Shortcuts
```bash
# Quick file search
find . -name "*.py" -exec grep -l "search_term" {} \;

# Find all imports
grep -r "^from\|^import" app/ --include="*.py" | sort | uniq

# Find class definitions
grep -r "^class " app/ --include="*.py"

# Find function definitions
grep -r "^def " app/ --include="*.py"
```

### 📊 Code Analysis
```bash
# Count lines of code
find app/ -name "*.py" -exec wc -l {} + | sort -n

# Find most complex functions
python -m radial -o complexity app/

# Find unused imports
ruff check app/ --select I
```

### 🔗 External Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Qpid Proton Documentation**: https://qpid.apache.org/proton/
- **JWT Documentation**: https://pyjwt.readthedocs.io/
- **Pydantic Documentation**: https://pydantic.dev/
- **1C ESB Documentation**: (Internal 1C documentation)

## 📞 Support Resources

### 💬 Community Resources
- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For general questions and support
- **Documentation**: Comprehensive guides and examples

### 🔧 Professional Support
- **Consulting**: Available for enterprise deployments
- **Training**: Workshops on 1C integration development
- **Custom Development**: Tailored solutions for specific requirements

---

**Last Updated**: 2024-01-01
**Version**: 1.0.0
**Maintainer**: Development Team

This guide provides comprehensive navigation and development support for the PyESB project. Use the search strategies and commands to quickly locate and understand any part of the codebase!
