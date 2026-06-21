# 🎯 PyESB Quick Reference

**Instant access to everything you need**

## 📋 At a Glance

| What | Where |
|------|-------|
| **Project Overview** | `README.md` |
| **Comprehensive Guide** | `AGENT_GUIDE.md` |
| **Quick Commands** | `COMMAND_REFERENCE.md` |
| **Interactive Nav** | `NAVIGATION.md` |
| **Visual Maps** | `PROJECT_MAP.md` |
| **Complete Summary** | `SUMMARY.md` |
| **Technical Notes** | `zed_agent_notes.md` |
| **Protocol Docs** | `docs/protocol.md` |
| **Roadmap** | `todo.md` |

---

## 🚀 Instant Commands

### Start
```bash
python app/main.py
```

### Test
```bash
python -m pytest tests/ -v
```

### Docker
```bash
docker-compose up -d
```

### Health
```bash
curl http://localhost:9090/health
```

---

## 🔍 Find Anything

### Find Code
```bash
grep -r "auth" app/ --include="*.py"
grep -r "amqp" app/ --include="*.py" -i
grep -r "token" app/ --include="*.py"
```

### Find Tests
```bash
python -m pytest tests/unit/test_auth.py -v
python -m pytest tests/integration/ -v
```

### Find Config
```bash
cat app/config.py
ls -la keys/
```

---

## 📝 Common Edits

### Add Application
```python
# app/config.py
DEFAULT_APPLICATIONS = {
    "newapp": [
        {
            "process": "rav::newapp::Main",
            "channel": "NewChannel",
            "access": "READ_ONLY"
        }
    ]
}
```

### Add Client
```python
# app/config.py
DEFAULT_CLIENTS = {
    "newclient": {
        "client_id": "newclient",
        "client_secret": "secret",
        "user_id": "a1b2c3d4-5678-90ef-ghij-klmnopqrstuv",
        "user_list_id": "b2c3d4e5-6789-01fg-hiij-klmnopqrstuv",
        "user_presentation": "New Client"
    }
}
```

### Modify JWT
```python
# app/token.py
# Edit create_jwt_token() to add custom claims
def create_jwt_token(client_id: str, client_config: dict) -> str:
    claims = {
        "custom_claim": "custom_value",
        "iss": "unused-issuer",
        # ... existing claims
    }
```

---

## 🐳 Docker Quick

```bash
# Start
docker-compose up -d

# Check
curl http://localhost:9090/health

# Logs
docker-compose logs -f app

# Stop
docker-compose down
```

---

## 🧪 Test Quick

```bash
# All tests
python -m pytest tests/ -v

# Unit only
python -m pytest tests/unit/ -v

# Integration only
python -m pytest tests/integration/ -v

# Specific test
python -m pytest tests/unit/test_auth.py::test_token_creation -v
```

---

## 📊 API Quick

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic $(echo -n "test:test" | base64)" \
  -d "grant_type=client_credentials" \
  | jq -r '.id_token')

# Get metadata
curl http://localhost:9090/applications/test/sys/esb/metadata/channels \
  -H "Authorization: Bearer $TOKEN"

# Health
curl http://localhost:9090/health
```

---

## 🔧 Code Quality

```bash
# Lint
ruff check app/

# Format
ruff format app/

# Sort imports
ruff format app/
```

---

## 🎯 Navigation Shortcuts

```bash
# Project overview
cat SUMMARY.md

# Command reference
cat COMMAND_REFERENCE.md

# Visual maps
cat PROJECT_MAP.md

# Protocol details
docs/protocol.md

# Technical analysis
cat zed_agent_notes.md
```

---

## 🚨 Troubleshooting

| Issue | Command |
|-------|---------|
| **Port 9090 busy** | `lsof -i :9090` → `kill -9 <PID>` |
| **Port 6698 busy** | `lsof -i :6698` → `kill -9 <PID>` |
| **Keys missing** | `mkdir -p keys && python -c "from cryptography.hazmat.primitives.asymmetric import rsa; ...` |
| **Docker errors** | `docker-compose logs app` |
| **JWT issues** | `ls -la keys/` → regenerate if needed |

---

## 🏁 Essential Files

```bash
app/main.py          # FastAPI entry point
app/auth.py          # OIDC authentication
app/token.py         # JWT handling
app/metadata.py      # Channel metadata
app/config.py        # Configuration
app/server.py        # AMQP server

keys/private.pem     # RSA private key
keys/public.pem      # RSA public key

docs/protocol.md     # Protocol specification
```

---

**Last updated**: 2026-06-21  
**Version**: 1.0  
**Keep this open for instant access!**