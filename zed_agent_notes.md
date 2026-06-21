# Zed Agent Notes for pyesb Project

## 📋 Project Overview

### 🎯 Core Purpose
This project implements a **1C ESB Gateway-compatible server** that allows 1C Enterprise applications to authenticate using OIDC client credentials flow and retrieve AMQP channel metadata for integration purposes.

### 🏗️ Architecture

**Tech Stack:**
- **FastAPI** - HTTP server framework
- **Qpid Proton** - AMQP 1.0 implementation
- **JWT (RS512)** - Token authentication
- **Pydantic** - Data validation and settings
- **Python 3.12+** - Runtime

**Key Components:**
1. **HTTP Server** - FastAPI endpoints for authentication and metadata
2. **AMQP 1.0 Server** - Qpid Proton-based message broker
3. **JWT Token Service** - RS512 signed tokens with specific 1C-compatible claims
4. **Configuration System** - Pydantic-based settings with file and environment support

## 📂 Project Structure

```
pyesb/
├── app/                    # Main application code
│   ├── __init__.py         # Package initialization
│   ├── main.py             # FastAPI application entry point
│   ├── auth.py             # OIDC token endpoint
│   ├── metadata.py         # Metadata channels endpoint
│   ├── token.py            # JWT token generation/verification
│   ├── config.py           # Configuration models and settings
│   ├── interfaces.py       # Type definitions and validation
│   └── amqp_server.py      # AMQP 1.0 server implementation
│
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── conftest.py         # Test fixtures
│
├── docs/                   # Documentation
│   └── protocol.md         # Detailed protocol specification
│
├── keys/                   # Cryptographic keys (auto-generated)
│   ├── private.pem         # RSA private key for JWT signing
│   └── public.pem          # RSA public key for JWT verification
│
├── .env                    # Environment variables (optional)
├── pyproject.toml          # Project configuration and dependencies
├── README.md               # Project documentation
├── todo.md                 # Development roadmap
└── zed_agent_notes.md      # Agent-specific notes (this file)
```

## 🚀 Main Components Analysis

### 1. 🔐 OIDC Authentication (`auth.py`)

**Endpoint:** `POST /auth/oidc/token`

**Functionality:**
- Accepts client credentials via Basic auth
- **IMPORTANT:** Any credentials are accepted (this is a mock gateway for testing)
- Returns JWT id_token using RS512 algorithm
- Response includes id_token, "Not implemented" access_token, and Bearer token_type

**Error Responses:**
- 400 INVALID_REQUEST - Unsupported grant_type
- 500 INTERNAL_ERROR - Token generation failure

### 2. 📋 Metadata Service (`metadata.py`)

**Endpoint:** `GET /applications/{app_name}/sys/esb/metadata/channels`

**Functionality:**
- Requires Bearer token authentication
- Returns list of AMQP channels configured for the specified application
- Each channel includes process, channel name, access mode (READ_ONLY/WRITE_ONLY)

**Error Responses:**
- 401 UNAUTHENTICATED - Missing or invalid authorization header
- 404 NOT_FOUND - Application not found
- 500 INTERNAL_ERROR - Channel data processing failure

### 3. 📡 AMQP 1.0 Server (`amqp_server.py`)

**Configuration:**
- Listens on port 6698 (configurable)
- Non-blocking implementation using threading
- Integrates with FastAPI's asyncio event loop
- Logs all received messages with metadata

**Key Classes:**
- `AMQPMessageHandler` - Handles incoming AMQP messages
- `NonBlockingAMQPContainer` - Manages AMQP server lifecycle
- `AMQPMessageHandler` - Processes individual messages with full metadata

**Message Logging:**
```
[AMQP] {timestamp} | id={message_id} | source={address} | subject={subject} | type={content_type} | body={body_preview}
```

### 4. 🔑 JWT Token Service (`token.py`)

**Core Functions:**
- `_ensure_keys()` - Generates/loads RSA key pair (2048-bit)
- `create_id_token(client, config)` - Creates JWT with 1C-specific claims
- `verify_id_token(token, config)` - Validates and decodes JWT
- `_hash_client_id(client_id)` - Base64 SHA-256 hash for auth-identity.name

**JWT Claims Structure:**
```json
{
  "iss": "unused-issuer",
  "sub": {
    "user-id": "UUID",
    "user-list-id": "UUID",
    "user-presentation": "display-name",
    "auth-identity": {
      "name": "base64-sha256(client_id)",
      "domain": "user_tokens"
    }
  },
  "aud": "client_id",
  "iat": timestamp,
  "exp": timestamp + 3600,
  "at_hash": "AccessToken hash (not implemented)"
}
```

### 5. 🏥 Health Check (`main.py`)

**Endpoint:** `GET /health`

**Simple response:** `{"status": "ok"}`

### 6. 📝 Configuration System (`config.py`)

**Key Components:**
- `ClientCredentials` - Client authentication credentials
- `Channel` - AMQP channel configuration
- `AppConfig` - Main application configuration
- `Settings` - Environment variable-based settings
- `DEFAULT_CONFIG` - Built-in default configuration

**Configuration Sources:**
1. Environment variables (PYESB_ prefix)
2. Config file (JSON format)
3. Default values (fallback)

**Merge Order:** File values → Environment variables → Default values

**Default Configuration:**
```python
clients = {
    "test": {
        "client_id": "test",
        "client_secret": "test",
        "user_id": "00000000-0000-0000-0000-000000000000",
        "user_list_id": "00000000-0000-0000-0000-000000000000",
        "user_presentation": "Test User"
    }
}

applications = {
    "test": [
        {
            "process": "test_process",
            "process_description": "Test Process",
            "channel": "test_channel",
            "channel_description": "Test Channel",
            "access": "READ_ONLY"
        }
    ]
}
```

## 🛠️ Development Setup

### 📦 Dependencies

**Core Dependencies:**
- fastapi - HTTP framework
- uvicorn[standard] - ASGI server
- pyjwt[crypto] - JWT handling
- cryptography - RSA key generation
- pydantic/pydantic-settings - Data validation
- pytest/pytest-asyncio - Testing
- python-qpid-proton - AMQP 1.0 support

### 🚀 Running the Application

```bash
# Install dependencies
uv sync

# Start the server
python app/main.py

# Or with custom configuration
PYESB_PORT=8080 PYESB_CONFIG_FILE=config.json python app/main.py
```

### 🧪 Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v

# Check code quality
ruff check app/
ruff format app/
```

## 🔐 Security Considerations

### ⚠️ Important Security Notes

**This is a MOCK gateway for development/testing purposes only.**

1. **No Credential Validation** - Any Basic auth credentials are accepted
2. **Plain HTTP** - No TLS encryption (matches 1C behavior in testing)
3. **Static Keys** - RSA keys are stored in filesystem and reused
4. **JWT RS512** - Proper signing and verification with RSA 2048-bit keys

### 🔒 Security Features
- RSA 2048-bit key pair for JWT signing/verification
- Base64 SHA-256 hashing of client IDs for auth-identity claims
- Token expiration (1 hour by default)
- Audience validation in JWT verification

## 📊 Type System (`interfaces.py`)

**Custom Typed Interfaces:**
- `AMQPAddress` - AMQP queue/address names
- `ProcessID` - 1C integration process identifiers
- `ClientID` - OAuth2 client identifiers
- `AccessMode` - READ_ONLY | WRITE_ONLY
- `UserID` - UUID strings for users
- `UserListID` - UUID strings for user lists
- `UserPresentation` - Display names
- `AuthIdentityName` - Base64 SHA-256 hashes
- `IPv4Address` - IPv4 address validation with utilities

**IPv4Address Features:**
- Validation using Python's `ipaddress` module
- Utility methods: `is_loopback()`, `is_private()`, `is_any()`, `is_link_local()`
- Pydantic integration for JSON schema generation

## 🚀 Deployment

### Docker Support

**Key Features:**
- Multi-stage Dockerfile (~80MB image)
- Persistent key storage via volume mounts
- Health checks built into container
- Environment variable configuration
- Development mode with live reloading

**Docker Commands:**
```bash
# Build and run with Docker Compose
docker-compose up -d

# Test the service
curl http://localhost:9090/health

# View logs
docker-compose logs -f app

# Stop the service
docker-compose down
```

### Configuration Options

**Environment Variables:**
- `PYESB_HOST` - HTTP server host (default: 0.0.0.0)
- `PYESB_PORT` - HTTP server port (default: 9090)
- `PYESB_AMQP_PORT` - AMQP server port (default: 6698)
- `PYESB_JWT_ISSUER` - JWT issuer claim (default: unused-issuer)
- `PYESB_TOKEN_TTL_SECONDS` - Token expiration (default: 3600)
- `PYESB_CONFIG_FILE` - JSON config file path

**Config File Example:**
```json
{
  "clients": {
    "my_client": {
      "client_id": "my_client",
      "client_secret": "secret123",
      "user_id": "123e4567-e89b-12d3-a456-426614174000",
      "user_list_id": "123e4567-e89b-12d3-a456-426614174001",
      "user_presentation": "My User"
    }
  },
  "applications": {
    "my_app": [
      {
        "process": "my::namespace::MyProcess",
        "process_description": "My Process",
        "channel": "my_channel",
        "channel_description": "My Channel",
        "access": "READ_ONLY"
      }
    ]
  },
  "host": "0.0.0.0",
  "port": 9090,
  "amqp_port": 6698
}
```

## 📝 Current Status and Roadmap

### 🎯 Implemented Features

✅ **OIDC Token Endpoint** - `/auth/oidc/token`
✅ **Metadata Endpoint** - `/applications/{app}/sys/esb/metadata/channels`
✅ **JWT Token Generation** - RS512 signed tokens with 1C-compatible claims
✅ **AMQP 1.0 Server** - Non-blocking Qpid Proton implementation
✅ **Configuration System** - Pydantic-based with file/environment support
✅ **Health Check** - Simple `/health` endpoint
✅ **Testing** - Unit and integration tests
✅ **Docker Support** - Multi-stage builds with health checks

### 🚀 Future Improvements

🔄 **Enhanced Credential Validation** - Optional real authentication
🔄 **TLS Support** - Secure HTTP and AMQP connections
🔄 **Access Token Implementation** - Currently "Not implemented"
🔄 **AMQP SASL PLAIN Authentication** - Use JWT for AMQP login
🔄 **Message Processing** - Route messages between channels
🔄 **Monitoring and Metrics** - Prometheus integration
🔄 **Logging Improvements** - Structured logging and rotation
🔄 **Configuration UI** - Web interface for managing clients and channels
🔄 **Swagger/OpenAPI Documentation** - Enhanced API documentation

## 🔍 Key Implementation Details

### 🔐 Token Generation Process

1. **Key Management** - Auto-generate RSA 2048-bit keys if missing
2. **Claim Construction** - Build 1C-specific JWT claims structure
3. **Hashing** - Base64 SHA-256 hash of client_id for auth-identity.name
4. **Signing** - RS512 algorithm with private key
5. **Delivery** - Return in JSON response with fixed access_token

### 📡 AMQP Message Handling

1. **Receiver Setup** - Create receiver links for all configured channels
2. **Message Processing** - Extract and log message metadata
3. **Body Handling** - Handle bytes, strings, and complex objects
4. **Error Handling** - Reject messages on processing errors
5. **Acceptance** - Accept successfully processed messages

### 🔄 Configuration Flow

1. **Settings Loading** - Read environment variables
2. **File Loading** - Load JSON config if specified
3. **Merging** - Combine file + environment + defaults
4. **Validation** - Pydantic model validation
5. **Application** - Make config available to all components

### 🧪 Test Strategy

**Unit Tests:**
- Configuration loading and validation
- JWT token generation and verification
- Token claims structure validation
- Metadata serialization
- Error response formats

**Integration Tests:**
- HTTP endpoint functionality
- Token flow (auth → metadata)
- Error scenarios (invalid tokens, missing apps)
- AMQP server startup/shutdown

## 📚 Documentation Resources

- **README.md** - Project overview and usage
- **docs/protocol.md** - Detailed protocol specification from mitm capture
- **todo.md** - Development roadmap and future features
- **DOCKER_README.md** - Docker deployment guide
- **TESTING_SUMMARY.md** - Test coverage and results

## 🔧 Useful Commands

### Development
```bash
# Install dependencies
uv sync

# Run server
python app/main.py

# Run tests
python -m pytest tests/ -v

# Code quality
ruff check app/
ruff format app/

# Generate keys manually
python -c "from app.token import _ensure_keys; _ensure_keys()"
```

### Docker
```bash
# Build and start
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app

# Stop
docker-compose down

# Rebuild
docker-compose build --no-cache && docker-compose up -d
```

### Debugging
```bash
# Check token structure
python -c "from app.config import DEFAULT_CONFIG; from app.token import create_id_token; print(create_id_token(list(DEFAULT_CONFIG.clients.values())[0], DEFAULT_CONFIG))"

# Test config loading
python -c "from app.config import get_settings; print(get_settings().get_config())"

# Test JWT verification
python -c "import jwt; from app.config import get_settings; from app.token import verify_id_token, create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); print(verify_id_token(token, cfg))"
```

## 💡 Project Insights

### 🎯 Why This Project Exists

This project solves the need for **development and testing environments** that mimic the 1C ESB Gateway without requiring the full 1C platform infrastructure. It allows:

1. **Rapid Prototyping** - Test 1C integrations without 1C:Шина
2. **Continuous Integration** - Automated testing of 1