# V-AI CLI Control

A full-featured FastAPI application that allows a custom GPT to completely control a Linux server through CLI commands with interactive capabilities.

## Features

- **FastAPI with Pydantic Validation**: Full-featured REST API with automatic validation and documentation
- **Interactive Command Support**: Handle commands requiring user input (yes/no prompts, interactive sessions)
- **Security**: API key authentication, command filtering, and path restrictions
- **Session Management**: Multi-step operations with session tracking
- **Real-time System Monitoring**: System status, resource usage, and health checks
- **Comprehensive Error Handling**: Detailed error reporting and logging

## Quick Start

1. **Clone and Setup**:
   ```bash
   git clone <repository-url>
   cd v-ai-cli-control
   ./start.sh
   ```

2. **Configure Environment**:
   Edit `.env` file to set your API key and security settings:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start Server**:
   ```bash
   python main.py
   # Or use uvicorn directly:
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access API Documentation**:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## API Endpoints

### Core Command Execution

- **POST `/execute`**: Execute CLI commands
  - Simple commands (non-interactive)
  - Interactive commands (returns session ID)
  - Background commands (future feature)

- **POST `/interactive/{session_id}`**: Send input to interactive sessions

### Session Management

- **GET `/sessions`**: List all active sessions
- **GET `/sessions/{session_id}`**: Get session information
- **DELETE `/sessions/{session_id}`**: Terminate a session

### System Information

- **GET `/system/status`**: Get system status (uptime, memory, disk, load)
- **GET `/health`**: Health check endpoint

### Quick Commands

- **POST `/quick-commands/yes-no`**: Handle yes/no prompts easily

## Usage Examples

### 1. Simple Command Execution

```bash
curl -X POST "http://localhost:8000/execute" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "ls -la",
    "command_type": "simple",
    "timeout": 30
  }'
```

### 2. Interactive Command

```bash
# Start interactive command
curl -X POST "http://localhost:8000/execute" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "sudo apt update",
    "command_type": "interactive"
  }'

# Send input to session
curl -X POST "http://localhost:8000/interactive/SESSION_ID" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SESSION_ID",
    "input_text": "y"
  }'
```

### 3. Yes/No Prompt Handling

```bash
curl -X POST "http://localhost:8000/quick-commands/yes-no?session_id=SESSION_ID&answer=true" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 4. System Status

```bash
curl -X GET "http://localhost:8000/system/status" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Configuration

### Environment Variables (.env)

```bash
# API Configuration
SECRET_KEY=your-secret-key-here
API_KEY=your-api-key-for-authentication

# Security Settings
ALLOWED_COMMANDS=ls,pwd,whoami,ps,df,free,uname,date,uptime,cat,grep,find,which,echo
RESTRICTED_PATHS=/etc/shadow,/etc/passwd,/root
MAX_COMMAND_TIMEOUT=30

# Server Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
```

## Security Features

1. **API Key Authentication**: All endpoints require valid API key
2. **Command Filtering**: Configurable allowed commands list
3. **Path Restrictions**: Prevent access to sensitive files/directories
4. **Input Validation**: Pydantic models validate all inputs
5. **Timeout Protection**: Commands have configurable timeouts
6. **Session Management**: Isolated interactive sessions

## GPT Integration

This API is designed to be easily integrated with custom GPTs. The GPT can:

1. Execute any allowed CLI command
2. Handle interactive prompts automatically
3. Monitor system status
4. Manage multiple concurrent operations
5. Get detailed error information

## Development

### Requirements

- Python 3.8+
- FastAPI
- Pydantic v2
- pexpect (for interactive commands)
- psutil (for system monitoring)

### Installation

```bash
pip install -r requirements.txt
```

### Running in Development

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Security Considerations

- Always use HTTPS in production
- Set strong API keys
- Configure command restrictions appropriately
- Monitor logs for suspicious activity
- Consider firewall rules for API access
- Regular security updates

## License

[Add your license here]