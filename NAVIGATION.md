# 🧭 Navigation Guide: PyESB Project

## 🚀 Quick Navigation

### 📋 Immediate Orientation

```bash
# Get complete project overview
cat SUMMARY.md

# Get command reference
cat COMMAND_REFERENCE.md

# Get architecture diagrams
cat PROJECT_MAP.md

# Get technical deep dive
cat zed_agent_notes.md

# Get development workflow
cat AGENT_WORKFLOW.md
```

## 📂 Project Structure Navigation

### 🎯 Core Directories

```bash
# Main application code
ls -la app/

# Test suite
ls -la tests/

# Documentation
ls -la docs/

# Cryptographic keys
ls -la keys/

# Configuration files
ls -la *.json *.toml *.yml *.yaml *.env 2>/dev/null
```

### 🔍 File Type Navigation

```bash
# Find all Python files
find . -name "*.py" -type f

# Find test files
find tests/ -name "*.py" -type f

# Find documentation files
find . -name "*.md" -type f

# Find configuration files
find . \( -name "*.json" -o -name "*.toml" -o -name "*.yml" -o -name "*.yaml" \) -type f
```

## 🔍 Code Search Strategies

### 🎯 Finding Specific Code

| **Search Goal** | **Command** | **Key Files** |
|----------------|-------------|---------------|
| **Authentication logic** | `grep -r "Basic auth\|client_credentials" app/` | `app/auth.py` |
| **JWT token generation** | `grep -r "create_id_token\|RS512" app/` | `app/token.py` |
| **AMQP server setup** | `grep -r "proton\|AMQPContainer" app/` | `app/amqp_server.py` |
| **Configuration loading** | `grep -r "get_settings\|AppConfig" app/` | `app/config.py` |
| **Error handling** | `grep -r "HTTPException\|raise" app/` | All endpoint files |
| **Type definitions** | `grep -r "TypedDict\|Annotated" app/` | `app/interfaces.py` |
| **Test fixtures** | `grep -r "@pytest.fixture" tests/` | `tests/conftest.py` |
| **API endpoints** | `grep -r "@app\." app/` | `app/main.py`, `app/auth.py`, `app/metadata.py` |

### 🔄 Understanding Code Flow

```bash
# Find where functions are defined
grep -r "^def " app/ --include="*.py"

# Find where functions are called
grep -r "function_name(" app/ --include="*.py"

# Find class definitions
grep -r "^class " app/ --include="*.py"

# Find imports
grep -r "^from\|^import" app/ --include="*.py" | sort | uniq
```

## 📋 Component-Specific Navigation

### 🔐 Authentication System

```bash
# Main authentication endpoint
read_file app/auth.py

# JWT token service
read_file app/token.py

# Configuration for clients
read_file app/config.py

# Test authentication
ls tests/unit/test_auth.py tests/integration/test_token_flow.py
```

### 📡 AMQP Server

```bash
# AMQP server implementation
read_file app/amqp_server.py

# Configuration for AMQP
read_file app/config.py

# Test AMQP
ls tests/integration/test_amqp_server.py
```

### 📋 Metadata Service

```bash
# Metadata endpoint
read_file app/metadata.py

# JWT verification
read_file app/token.py

# Configuration for applications
read_file app/config.py

# Test metadata
ls tests/unit/test_metadata.py tests/integration/test_api_integration.py
```

### 🏥 Health Check

```bash
# Health endpoint
read_file app/main.py | grep -A 10 "health"

# Test health
ls tests/integration/test_api_integration.py
```

### 📝 Configuration System

```bash
# Configuration implementation
read_file app/config.py

# Type definitions
read_file app/interfaces.py

# Default configuration
read_file app/config.py | grep -A 50 "DEFAULT_CONFIG"

# Test configuration
ls tests/unit/test_config.py
```

## 🧪 Testing Navigation

### 📋 Test Structure

```bash
# Unit tests
ls tests/unit/

# Integration tests
ls tests/integration/

# Test fixtures
read_file tests/conftest.py

# Run all tests
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py -v
```

### 🔍 Finding Tests

```bash
# Find tests for authentication
find tests/ -name "*auth*" -type f

# Find tests for metadata
find tests/ -name "*metadata*" -type f

# Find tests for tokens
find tests/ -name "*token*" -type f

# Find tests for configuration
find tests/ -name "*config*" -type f

# Find tests for AMQP
find tests/ -name "*amqp*" -type f
```

## 🐳 Docker Navigation

### 📦 Docker Files

```bash
# Docker configuration
ls -la Dockerfile docker-compose.yml .dockerignore

# Read Dockerfile
read_file Dockerfile

# Read docker-compose.yml
read_file docker-compose.yml
```

### 🔄 Docker Operations

```bash
# Build and start
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app

# Stop service
docker-compose down
```

### 🔧 Docker Troubleshooting

```bash
# Check container health
curl http://localhost:9090/health

# Execute command in container
docker-compose exec app bash

# Check container ports
docker-compose port app 9090

# View detailed logs
docker-compose logs --tail=100 app
```

## 📚 Documentation Navigation

### 📋 Documentation Files

```bash
# Main documentation
ls -la *.md docs/

# Technical analysis
read_file zed_agent_notes.md

# Protocol documentation
read_file docs/protocol.md

# Development roadmap
read_file todo.md

# Docker documentation
read_file DOCKER_README.md

# Test summary
read_file TESTING_SUMMARY.md
```

### 🔍 Finding Documentation

```bash
# Find all markdown files
find . -name "*.md" -type f

# Find protocol documentation
find . -name "*protocol*" -type f

# Find architecture documentation
find . -name "*map*" -o -name "*architecture*" -type f

# Find command references
find . -name "*command*" -o -name "*reference*" -type f
```

## 📊 API Navigation

### 🔍 Endpoint Documentation

```bash
# Find all endpoints
grep -r "@app\." app/ --include="*.py"

# OIDC token endpoint
grep -r "oidc/token" app/ --include="*.py"

# Metadata endpoint
grep -r "metadata/channels" app/ --include="*.py"

# Health endpoint
grep -r "health" app/ --include="*.py"
```

### 📡 Testing API

```bash
# Test health endpoint
curl http://localhost:9090/health

# Get OIDC token
curl -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic dGVzdDp0ZXN0" \
  -d "grant_type=client_credentials"

# Get metadata channels
JWT_TOKEN="your.jwt.token.here"
curl -X GET "http://localhost:9090/applications/test/sys/esb/metadata/channels" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

## 🔄 Development Workflow Navigation

### 🚀 Development Process

```bash
# 1. Install dependencies
uv sync

# 2. Start development server
python app/main.py

# 3. Make code changes
edit_file app/{component}.py

# 4. Add tests
write_file tests/unit/test_{component}.py

# 5. Run tests
python -m pytest tests/unit/test_{component}.py -v

# 6. Check code quality
ruff check app/
ruff format app/
```

### 🔧 Common Development Tasks

```bash
# Add new client
# Edit config.json or set environment variables

# Add new application
# Edit config.json or set environment variables

# Generate new RSA keys
rm -f keys/private.pem keys/public.pem
python -c "from app.token import _ensure_keys; _ensure_keys()"

# Test token generation
python -c "from app.config import get_settings; from app.token import create_id_token; cfg = get_settings().get_config(); print(create_id_token(list(cfg.clients.values())[0], cfg))"
```

## 🐛 Debugging Navigation

### 🔍 Debugging Strategies

```bash
# Check application logs
python app/main.py 2>&1 | grep -i "error\|warning"

# Run tests with verbose output
python -m pytest tests/ -v -s

# Check specific test output
python -m pytest tests/unit/test_auth.py::test_token_generation -v -s
```

### 🛠️ Common Debugging Scenarios

```bash
# JWT verification failing
# Check key files
ls -la keys/

# Test token generation
python -c "from app.config import get_settings; from app.token import create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); print(token)"

# AMQP server not starting
# Check port availability
netstat -tuln | grep 6698

# Test AMQP startup
python -c "from app.amqp_server import NonBlockingAMQPContainer; from app.config import get_settings; cfg = get_settings().get_config(); container = NonBlockingAMQPContainer(cfg); container.start()"
```

## 📈 Performance Navigation

### 🔍 Performance Monitoring

```bash
# Check response times
time curl -s http://localhost:9090/health

# Monitor HTTP requests
watch -n 1 "curl -s http://localhost:9090/health && echo"

# Check memory usage
top -p $(pgrep -f "python app/main.py")
```

### 📊 Performance Analysis

```bash
# Profile application
python -m cProfile -o profile.stats app/main.py

# Analyze profile data
python -m pstats profile.stats

# Find complexity issues
ruff check app/ --select C
```

## 🏁 Project Completion Checklist

### ✅ Before Finishing Any Task

- [ ] Code changes are minimal and focused
- [ ] All tests pass
- [ ] Code quality checks pass
- [ ] Documentation is updated
- [ ] Navigation guides are updated
- [ ] Changes are properly tested
- [ ] Error scenarios are handled
- [ ] Configuration is properly updated

### 📋 Task Summary Template

```markdown
## Task Summary

**Task**: [Brief description of task]

**Files Modified**:
- `app/{component}.py` - [What changed]
- `tests/unit/test_{component}.py` - [Test additions]

**Changes Made**:
1. [Change 1 description]
2. [Change 2 description]
3. [Change 3 description]

**Testing**:
- ✅ Unit tests pass
- ✅ Integration tests pass  
- ✅ Manual testing completed
- ✅ Error scenarios tested

**Documentation**:
- ✅ README.md updated
- ✅ Docstrings added
- ✅ Navigation guides updated

**Validation**:
- ✅ ruff check passes
- ✅ ruff format passes
- ✅ No regressions detected
```

## 💡 Pro Tips for Efficient Navigation

### 🚀 Fast Navigation Shortcuts

```bash
# Quick file search
find . -name "*.py" -exec grep -l "search_term" {} \;

# Find all test files
find tests/ -name "*.py" -type f

# Find specific imports
grep -r "^from\|^import" app/ --include="*.py" | sort | uniq
```

### 🔍 Code Analysis Shortcuts

```bash
# Find class definitions
grep -r "^class " app/ --include="*.py"

# Find function definitions
grep -r "^def " app/ --include="*.py"

# Find error handling patterns
grep -r "HTTPException\|raise" app/ --include="*.py"
```

### 📝 Documentation Navigation Shortcuts

```bash
# All documentation files
ls -la *.md docs/

# Navigation tools
cat NAVIGATION.md

# Technical analysis
cat zed_agent_notes.md

# Architecture overview
cat PROJECT_MAP.md
```

## 📞 Support and Resources

### 💬 Quick Help Commands

```bash
# Get project summary
cat SUMMARY.md

# Get command reference
cat COMMAND_REFERENCE.md

# Get technical notes
cat zed_agent_notes.md

# Get architecture diagrams
cat PROJECT_MAP.md

# Get development roadmap
cat todo.md
```

### 🔗 External Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Qpid Proton Documentation**: https://qpid.apache.org/proton/
- **JWT Documentation**: https://pyjwt.readthedocs.io/
- **Pydantic Documentation**: https://pydantic.dev/
- **1C ESB Documentation**: (Internal 1C documentation)

## 🏆 Navigation Success Tips

### 🎯 Effective Navigation Strategies

1. **Start with SUMMARY.md** for overall understanding
2. **Use PROJECT_MAP.md** for architectural insights
3. **Use COMMAND_REFERENCE.md** for quick operations
4. **Use zed_agent_notes.md** for technical deep dives
5. **Use AGENT_WORKFLOW.md** for development guidance

### 🔍 Search Best Practices

1. **Be specific** with search terms
2. **Use file patterns** to narrow search scope
3. **Combine grep with find** for complex searches
4. **Use case-insensitive search** when appropriate
5. **Look at test files** for usage examples

### 📚 Documentation Strategy

1. **Read main documentation first** (README.md)
2. **Consult technical notes** for implementation details
3. **Check protocol documentation** for 1C compatibility
4. **Review architecture diagrams** for component relationships
5. **Use navigation guides** for specific tasks

## 🔄 Continuous Integration Navigation

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

### 📊 CI/CD Monitoring

```bash
# Check test results
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py --junitxml=test-results.xml

# Check code quality
ruff check app/ --format=json > lint-results.json

# Check Docker build
DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker-compose build --no-cache
```

## 🏁 Conclusion

This navigation guide provides a **comprehensive roadmap** for efficiently navigating the PyESB project. Use these strategies to:

- ✅ **Quickly understand** the project structure
- ✅ **Efficiently find** specific code or documentation
- ✅ **Effectively debug** issues and problems
- ✅ **Rapidly test** functionality
- ✅ **Seamlessly deploy** with Docker
- ✅ **Successfully develop** new features

The guide includes both **high-level navigation** and **specific search strategies** to help you find exactly what you need, when you need it.

---

**Navigation Guide Version**: 1.0.0
**Last Updated**: 2024-01-01
**Maintainer**: Development Team

For navigation-specific questions or suggestions, refer to the guide or open a GitHub issue.
