# 📋 Command Reference: PyESB

## 🚀 Quick Command Reference

### 📋 Essential Commands

```bash
# Get project summary
cat SUMMARY.md

# Get command reference (this file)
cat COMMAND_REFERENCE.md

# Get architecture diagrams
cat PROJECT_MAP.md

# Get technical notes
cat zed_agent_notes.md

# Get development workflow
cat AGENT_WORKFLOW.md
```

## 🛠️ Development Commands

### 📦 Dependency Management

```bash
# Install dependencies
uv sync

# Install with pip
pip install -e .

# Add new dependency
uv add <package-name>

# List dependencies
uv pip list

# Update dependencies
uv pip install --upgrade <package-name>
```

### 🚀 Running the Application

```bash
# Start development server
python app/main.py

# Start with custom host/port
PYESB_HOST=0.0.0.0 PYESB_PORT=8080 python app/main.py

# Start with custom config file
PYESB_CONFIG_FILE=config.json python app/main.py

# Generate RSA keys manually
python -c "from app.token import _ensure_keys; _ensure_keys()"

# Check current configuration
python -c "from app.config import get_settings; print(get_settings().get_config())"
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

# Run specific test function
python -m pytest tests/unit/test_auth.py::test_token_generation -v

# Run tests with coverage
python -m pytest tests/ --ignore=tests/integration/test_docker_integration.py --cov=app --cov-report=term-missing

# Run tests in verbose mode with output
python -m pytest tests/ -v -s
```

### 🔧 Code Quality Commands

```bash
# Check code quality (linting)
ruff check app/

# Format code automatically
ruff format app/

# Check formatting without applying
ruff format app/ --check

# Find unused imports
ruff check app/ --select I

# Find complexity issues
ruff check app/ --select C

# Find all linting issues with explanations
ruff check app/ --explain
```

## 🐳 Docker Commands

### 📦 Docker Operations

```bash
# Build and start with Docker Compose
docker-compose up -d

# Build without cache
DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker-compose build --no-cache

# Start existing containers
docker-compose start

# Stop containers
docker-compose stop

# Stop and remove containers
docker-compose down

# Remove containers, networks, and volumes
docker-compose down -v
```

### 🔍 Docker Management

```bash
# List running containers
docker-compose ps

# List all containers (including stopped)
docker ps -a

# View container logs
docker-compose logs -f app

# View logs for specific service
docker-compose logs app

# View previous logs
docker-compose logs --tail=100 app
```

### 🔄 Docker Configuration

```bash
# Change HTTP port
PYESB_PORT=8080 docker-compose up -d

# Change AMQP port
PYESB_AMQP_PORT=5672 docker-compose up -d

# Use custom config file
PYESB_CONFIG_FILE=/path/to/config.json docker-compose up -d

# Mount custom keys directory
# Edit docker-compose.yml first to change volume mount
```

### 🔧 Docker Troubleshooting

```bash
# Check container health
curl http://localhost:9090/health

# Execute command in running container
docker-compose exec app bash

# Check container ports
docker-compose port app 9090

# Check container IP
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' pyesb_app_1

# Restart container
docker-compose restart app

# Remove unused containers
docker system prune
```

## 📡 API Testing Commands

### 🔍 Health Check

```bash
# Test health endpoint
curl http://localhost:9090/health

# Test with JSON output
curl -H "Accept: application/json" http://localhost:9090/health
```

### 🔐 OIDC Token Endpoint

```bash
# Get OIDC token (basic auth)
curl -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic dGVzdDp0ZXN0" \
  -d "grant_type=client_credentials"

# With custom client credentials
curl -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic $(echo -n 'my_client:my_secret' | base64)" \
  -d "grant_type=client_credentials"

# Test invalid grant type
curl -X POST http://localhost:9090/auth/oidc/token \
  -H "Authorization: Basic dGVzdDp0ZXN0" \
  -d "grant_type=invalid"
```

### 📋 Metadata Endpoint

```bash
# Get metadata channels (requires valid JWT)
JWT_TOKEN="your.jwt.token.here"
curl -X GET "http://localhost:9090/applications/test/sys/esb/metadata/channels" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Test with invalid token
curl -X GET "http://localhost:9090/applications/test/sys/esb/metadata/channels" \
  -H "Authorization: Bearer invalid.token.here"

# Test with missing application
curl -X GET "http://localhost:9090/applications/nonexistent/sys/esb/metadata/channels" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Test without authentication
curl -X GET "http://localhost:9090/applications/test/sys/esb/metadata/channels"
```

### 🧪 API Testing Scripts

```bash
#!/bin/bash
# test_api.sh

BASE_URL="http://localhost:9090"

# Test health
echo "Testing health endpoint..."
curl -s $BASE_URL/health

# Get token
echo "\nTesting OIDC token endpoint..."
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/oidc/token" \
  -H "Authorization: Basic dGVzdDp0ZXN0" \
  -d "grant_type=client_credentials")

echo "Token response: $TOKEN_RESPONSE"

# Extract JWT
JWT=$(echo $TOKEN_RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['id_token'])")

# Test metadata
if [ -n "$JWT" ]; then
  echo "\nTesting metadata endpoint..."
  curl -s -X GET "$BASE_URL/applications/test/sys/esb/metadata/channels" \
    -H "Authorization: Bearer $JWT"
fi
```

## 🔍 Debugging Commands

### 🐛 Application Debugging

```bash
# Run with debug logging
PYTHONASYNCIODEBUG=1 python app/main.py

# Check for port conflicts
netstat -tuln | grep 9090
netstat -tuln | grep 6698

# Test specific endpoint
python -c "from fastapi.testclient import TestClient; from app.main import app; client = TestClient(app); print(client.get('/health').json())"

# Test token generation
python -c "from app.config import get_settings; from app.token import create_id_token; cfg = get_settings().get_config(); print(create_id_token(list(cfg.clients.values())[0], cfg))"

# Test token verification
python -c "import jwt; from app.config import get_settings; from app.token import verify_id_token, create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); print(verify_id_token(token, cfg))"
```

### 🔧 Configuration Debugging

```bash
# Check environment variables
env | grep PYESB_

# Test configuration loading
python -c "from app.config import get_settings; print(get_settings().get_config())"

# Test JSON config file
python -c "import json; from app.config import AppConfig; config = json.load(open('config.json')); print(AppConfig(**config))"

# Test default configuration
python -c "from app.config import DEFAULT_CONFIG; print(DEFAULT_CONFIG)"
```

### 📡 AMQP Debugging

```bash
# Check AMQP server startup
python -c "from app.amqp_server import NonBlockingAMQPContainer; from app.config import get_settings; cfg = get_settings().get_config(); container = NonBlockingAMQPContainer(cfg); container.start()"

# Test AMQP connection
python -c "import proton; from app.config import get_settings; cfg = get_settings().get_config(); conn = proton.Connection(); print('AMQP connection test')"

# Check AMQP port availability
nc -zv localhost 6698
telnet localhost 6698
```

### 🔐 JWT Debugging

```bash
# Check RSA keys
ls -la keys/

# Verify key format
openssl rsa -in keys/private.pem -check
openssl pkey -in keys/public.pem -pubin -text

# Decode JWT token manually
python -c "import jwt; token='your.jwt.token.here'; print(jwt.decode(token, options={'verify_signature': False}))"

# Check JWT claims structure
python -c "from app.config import get_settings; from app.token import create_id_token; cfg = get_settings().get_config(); token = create_id_token(list(cfg.clients.values())[0], cfg); import jwt; print(jwt.decode(token, cfg.jwt_public_key, algorithms=['RS512']))"
```

## 📂 File Management Commands

### 📋 File Operations

```bash
# List project structure
tree -L 3 -I '__pycache__|.venv|.git|*.pyc'

# Find Python files
find . -name "*.py" -type f

# Find test files
find tests/ -name "*.py" -type f

# Find configuration files
find . -name "*.json" -o -name "*.toml" -o -name "*.yml" -o -name "*.yaml"
```

### 🔍 Code Search

```bash
# Search for specific code patterns
grep -r "search_term" app/ --include="*.py"

# Find authentication code
grep -r "auth\|token" app/ --include="*.py" | grep -v "__pycache__"

# Find AMQP server code
grep -r "amqp\|proton" app/ --include="*.py"

# Find configuration loading
grep -r "config\|settings" app/ --include="*.py" | grep -v "__pycache__"

# Find error handling
grep -r "HTTPException\|raise" app/ --include="*.py"

# Find test cases
find tests/ -name "*.py" -exec grep -l "def test_" {} \;
```

### 🔄 File Navigation

```bash
# Navigate to app directory
cd app

# Navigate to tests directory
cd tests

# Navigate to docs directory
cd docs

# Navigate back to root
cd ..
```

## 🔄 Configuration Commands

### 📝 Configuration Management

```bash
# Check current configuration
python -c "from app.config import get_settings; print(get_settings().get_config())"

# Create custom config file
cat > config.json << 'EOF'
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
        "channel": "my_channel",
        "access": "READ_ONLY"
      }
    ]
  }
}
EOF

# Run with custom config
PYESB_CONFIG_FILE=config.json python app/main.py

# Run with environment variables
PYESB_PORT=8080 PYESB_HOST=0.0.0.0 python app/main.py

# List all available environment variables
env | grep PYESB_
```

### 🔧 Configuration Validation

```bash
# Validate JSON config
python -c "import json; from app.config import AppConfig; config = json.load(open('config.json')); print(AppConfig(**config))"

# Test configuration merging
python -c "from app.config import get_settings; settings = get_settings(); print('Env vars:', settings.model_dump(exclude_unset=True)); print('Config:', settings.get_config())"

# Check default configuration
python -c "from app.config import DEFAULT_CONFIG; print(DEFAULT_CONFIG)"
```

## 📊 Monitoring Commands

### 🔍 System Monitoring

```bash
# Check running processes
ps aux | grep python

# Check memory usage
top -p $(pgrep -f "python app/main.py")

# Check CPU usage
htop

# Check network connections
netstat -tuln | grep python

# Check open files
lsof -p $(pgrep -f "python app/main.py")
```

### 📈 Performance Monitoring

```bash
# Monitor HTTP requests
watch -n 1 "curl -s http://localhost:9090/health && echo"

# Test response times
time curl -s http://localhost:9090/health

# Monitor AMQP server
watch -n 1 "netstat -tuln | grep 6698"

# Check application logs
tail -f logs/application.log
```

## 🚀 Advanced Commands

### 🔧 Advanced Debugging

```bash
# Run with Python debugger
python -m pdb app/main.py

# Set breakpoints in code
python -c "import sys; sys.breakpointhook()"

# Profile application performance
python -m cProfile -o profile.stats app/main.py

# Analyze profile data
python -m pstats profile.stats
```

### 🔄 Advanced Testing

```bash
# Run tests with specific markers
python -m pytest tests/ -m "unit" -v

# Run tests excluding certain markers
python -m pytest tests/ -m "not docker" -v

# Run tests with timeout
python -m pytest tests/ --timeout=30 -v

# Run tests with retry on failure
python -m pytest tests/ --retries=3 -v
```

### 📦 Advanced Dependency Management

```bash
# Check dependency conflicts
uv pip check

# Freeze dependencies
uv pip freeze > requirements.txt

# Install from requirements.txt
pip install -r requirements.txt

# Update all dependencies
uv pip install --upgrade --upgrade-strategy eager -r requirements.txt
```

## 📚 Documentation Commands

### 🔍 Documentation Generation

```bash
# Generate API documentation
fastapi docs --app app.main:app --host 0.0.0.0 --port 8000

# Generate OpenAPI schema
python -c "from app.main import app; import json; print(json.dumps(app.openapi_schema))"

# Save OpenAPI schema
python -c "from app.main import app; import json; open('openapi.json', 'w').write(json.dumps(app.openapi_schema))"
```

### 🔄 Documentation Updates

```bash
# Update README with new features
edit_file README.md

# Update technical notes
edit_file zed_agent_notes.md

# Update protocol documentation
edit_file docs/protocol.md

# Update development roadmap
edit_file todo.md

# Add new navigation guide
write_file pyesb/NEW_GUIDE.md
```

## 🔄 Utility Commands

### 📋 Project Utilities

```bash
# Count lines of code
find app/ -name "*.py" -exec wc -l {} + | tail -1

# Find most complex functions
python -m radial -o complexity app/

# Find unused imports
ruff check app/ --select I

# Find all imports
grep -r "^from\|^import" app/ --include="*.py" | sort | uniq

# Find class definitions
grep -r "^class " app/ --include="*.py"

# Find function definitions
grep -r "^def " app/ --include="*.py"
```

### 🔧 System Utilities

```bash
# Clean Python cache
find . -name "__pycache__" -type d -exec rm -rf {} +

# Clean test cache
rm -rf .pytest_cache

# Clean ruff cache
rm -rf .ruff_cache

# Remove unused Docker resources
docker system prune -a

# Remove all Docker containers
docker rm -f $(docker ps -aq)
```

## 📋 Command Categories

### 🛠️ Development Commands
- Dependency management
- Application execution
- Code quality tools
- Testing framework

### 🐳 Docker Commands
- Container operations
- Management commands
- Configuration options
- Troubleshooting

### 📡 API Testing Commands
- Health checks
- OIDC authentication
- Metadata endpoints
- Testing scripts

### 🐛 Debugging Commands
- Application debugging
- Configuration debugging
- AMQP debugging
- JWT debugging

### 📂 File Management Commands
- File operations
- Code search
- File navigation

### 🔄 Configuration Commands
- Configuration management
- Configuration validation

### 📊 Monitoring Commands
- System monitoring
- Performance monitoring

### 🚀 Advanced Commands
- Advanced debugging
- Advanced testing
- Advanced dependency management

### 📚 Documentation Commands
- Documentation generation
- Documentation updates

### 🔄 Utility Commands
- Project utilities
- System utilities

## 💡 Pro Tips

### 🚀 Fast Navigation

```bash
# Quick file search
find . -name "*.py" -exec grep -l "search_term" {} \;

# Find all test files
find tests/ -name "*.py" -type f

# Find specific imports
grep -r "^from\|^import" app/ --include="*.py" | sort | uniq
```

### 🔍 Code Analysis

```bash
# Find class definitions
grep -r "^class " app/ --include="*.py"

# Find function definitions
grep -r "^def " app/ --include="*.py"

# Find error handling patterns
grep -r "HTTPException\|raise" app/ --include="*.py"
```

### 📝 Documentation Quick Reference

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

## 📞 Support Resources

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

## 🏁 Conclusion

This command reference provides a **comprehensive collection** of commands for working with the PyESB project. Use these commands to:

- ✅ **Develop** the application
- ✅ **Test** functionality
- ✅ **Debug** issues
- ✅ **Deploy** with Docker
- ✅ **Monitor** performance
- ✅ **Maintain** code quality

The commands are organized by category for easy reference, and include both basic operations and advanced troubleshooting.

---

**Command Reference Version**: 1.0.0
**Last Updated**: 2024-01-01
**Maintainer**: Development Team

For additional commands or specific use cases, consult the project documentation or open a GitHub issue.
