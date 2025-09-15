from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

class CommandType(str, Enum):
    SIMPLE = "simple"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"

class CommandRequest(BaseModel):
    command: str = Field(..., description="The CLI command to execute", min_length=1, max_length=1000)
    command_type: CommandType = Field(CommandType.SIMPLE, description="Type of command execution")
    working_directory: Optional[str] = Field(None, description="Working directory for command execution")
    timeout: Optional[int] = Field(30, description="Command timeout in seconds", ge=1, le=300)
    environment: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    expect_interactive: bool = Field(False, description="Whether the command expects interactive input")
    
    @validator('command')
    def validate_command(cls, v):
        # Basic security validation - prevent dangerous commands
        dangerous_patterns = [';', '&&', '||', '>', '>>', '|', '`', '$()']
        for pattern in dangerous_patterns:
            if pattern in v and not v.startswith(('ls', 'pwd', 'whoami', 'ps', 'df', 'free', 'uname', 'date', 'uptime')):
                raise ValueError(f"Command contains potentially dangerous pattern: {pattern}")
        return v

class InteractiveResponse(BaseModel):
    session_id: str = Field(..., description="Session ID for the interactive command")
    input_text: str = Field(..., description="Input to send to the interactive command")

class CommandResponse(BaseModel):
    success: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    execution_time: float
    session_id: Optional[str] = None
    is_interactive: bool = False
    error_message: Optional[str] = None

class SessionInfo(BaseModel):
    session_id: str
    command: str
    status: str
    created_at: str
    last_activity: str

class SystemStatus(BaseModel):
    uptime: str
    load_average: List[float]
    memory_usage: Dict[str, Any]
    disk_usage: Dict[str, Any]
    active_sessions: int

class HealthCheck(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: str