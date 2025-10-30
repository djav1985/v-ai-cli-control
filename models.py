import shlex
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class CommandType(str, Enum):
    """
    Enumeration of supported command execution types for the CLI control system.

    - SIMPLE: Execute command once and return output immediately
    - INTERACTIVE: Start persistent session allowing multiple input/output exchanges
    - BACKGROUND: Execute command in background and return immediately (future feature)
    """

    SIMPLE = "simple"
    INTERACTIVE = "interactive"
    BACKGROUND = "background"

    class Config:
        """Pydantic configuration for CommandType enum"""

        use_enum_values = True
        json_schema_extra = {
            "examples": ["simple", "interactive"],
            "description": "Type of command execution mode",
        }


class CommandRequest(BaseModel):
    """
    Request model for executing CLI commands on the Linux server.

    This model validates and structures command execution requests with comprehensive
    security validation, timeout controls, and environment customization capabilities.
    """

    command: str = Field(
        ...,
        title="CLI Command",
        description="The Linux CLI command to execute on the server. Must be a valid shell command.",
        min_length=1,
        max_length=1000,
        example="ls -la /home/user",
        pattern=r"^[^\x00-\x1f\x7f-\x9f]*$",  # Prevent control characters
    )

    command_type: CommandType = Field(
        CommandType.SIMPLE,
        title="Execution Mode",
        description=(
            "Specifies how the command should be executed:\n"
            "- **simple**: Execute once and return complete output\n"
            "- **interactive**: Start persistent session for commands requiring input\n"
            "- **background**: Execute asynchronously (not yet implemented)"
        ),
        example="simple",
    )

    working_directory: Optional[str] = Field(
        None,
        title="Working Directory",
        description=(
            "Optional working directory where the command should be executed. "
            "Must be an absolute path that exists on the server. "
            "Defaults to server's current working directory if not specified."
        ),
        example="/home/user/projects",
        pattern=r"^(/[^/\x00]*)+/?$",  # Valid absolute path
    )

    timeout: Optional[int] = Field(
        30,
        title="Command Timeout",
        description=(
            "Maximum time in seconds to wait for command completion. "
            "Prevents hanging processes and ensures responsive API behavior. "
            "Commands exceeding this timeout will be terminated."
        ),
        ge=1,
        le=300,
        example=30,
    )

    environment: Optional[Dict[str, str]] = Field(
        None,
        title="Environment Variables",
        description=(
            "Optional environment variables to set for the command execution. "
            "These variables will be available to the command and any child processes. "
            "Useful for passing configuration or authentication tokens."
        ),
        example={"PATH": "/usr/local/bin:/usr/bin", "LANG": "en_US.UTF-8"},
    )

    expect_interactive: bool = Field(
        False,
        title="Interactive Expectation",
        description=(
            "Indicates whether the command is expected to require interactive input. "
            "When True, the system optimizes for interactive session handling. "
            "Automatically set to True for command_type='interactive'."
        ),
        example=False,
    )

    class Config:
        """Pydantic model configuration"""

        title = "Command Execution Request"
        description = "Request to execute a CLI command on the Linux server"
        json_schema_extra = {
            "examples": [
                {
                    "command": "ls -la",
                    "command_type": "simple",
                    "working_directory": "/home/user",
                    "timeout": 30,
                },
                {
                    "command": "python3",
                    "command_type": "interactive",
                    "environment": {"PYTHONPATH": "/usr/local/lib/python3.9"},
                    "expect_interactive": True,
                },
            ]
        }

    @field_validator("command")
    @classmethod
    def validate_command_security(cls, v: str) -> str:
        """
        Comprehensive security validation for CLI commands.

        Prevents execution of potentially dangerous command patterns while
        allowing safe operations. Blocks command injection attempts and
        restricts access to sensitive system operations.
        """
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")

        # Remove leading/trailing whitespace
        v = v.strip()

        # Split the command to inspect individual tokens
        try:
            tokens = shlex.split(v, posix=True)
        except ValueError as exc:
            raise ValueError(f"Invalid command syntax: {exc}") from exc

        if not tokens:
            raise ValueError("Command cannot be empty")

        first_token = tokens[0]

        # Security validation - prevent dangerous command patterns
        separator_patterns = [";", "&&", "||"]
        dangerous_tokens = {">", ">>", "|"}
        dangerous_operator_substrings = [">>", ">", "|"]
        dangerous_substrings = [
            "`",
            "$(",
            "rm -rf /",
            "dd if=",
            "mkfs",
            "fdisk",
            "parted",
        ]

        # Allow safe commands even with potentially dangerous patterns when the
        # entire command remains simple and free of separators or redirections.
        safe_commands = {
            "ls",
            "pwd",
            "whoami",
            "ps",
            "df",
            "free",
            "uname",
            "date",
            "uptime",
            "cat",
            "grep",
            "find",
            "echo",
            "head",
            "tail",
        }

        def raise_for_pattern(pattern: str) -> None:
            raise ValueError(
                f"Command contains potentially dangerous pattern '{pattern}'. "
                f"This pattern is restricted for security reasons."
            )

        for pattern in dangerous_operator_substrings:
            if pattern in v:
                raise_for_pattern(pattern)

        if first_token in safe_commands:
            remaining_tokens = tokens[1:]
            for token in remaining_tokens:
                if token in dangerous_tokens or token in separator_patterns:
                    raise_for_pattern(token)
            for pattern in dangerous_substrings:
                if pattern in v:
                    raise_for_pattern(pattern)
            remainder = v[len(first_token) :]
            for pattern in separator_patterns:
                if pattern in remainder:
                    raise_for_pattern(pattern)
            return v

        for token in tokens:
            if token in dangerous_tokens or token in separator_patterns:
                raise_for_pattern(token)

        for pattern in separator_patterns:
            if pattern in v:
                raise_for_pattern(pattern)

        for pattern in dangerous_substrings:
            if pattern in v:
                raise_for_pattern(pattern)

        return v

    @model_validator(mode="after")
    def validate_interactive_consistency(self) -> "CommandRequest":
        """
        Ensure consistency between command_type and expect_interactive fields.

        Automatically sets expect_interactive=True when command_type is 'interactive'
        and validates that the configuration makes logical sense.
        """
        command_type = self.command_type
        expect_interactive = self.expect_interactive

        if command_type == CommandType.INTERACTIVE:
            self.expect_interactive = True
        elif expect_interactive and command_type == CommandType.SIMPLE:
            # Warning: this might not work as expected
            pass  # Allow but user should be aware

        return self


class InteractiveResponse(BaseModel):
    """
    Request model for sending input to interactive command sessions.

    Used to provide input to commands that are running in interactive mode,
    such as Python REPL, database shells, or commands waiting for user input.
    """

    session_id: str = Field(
        ...,
        title="Session Identifier",
        description=(
            "Unique identifier for the interactive command session. "
            "This ID is returned when starting an interactive command and "
            "must be used for all subsequent interactions with that session."
        ),
        example="session_abc123xyz789",
        pattern=r"^[a-zA-Z0-9_-]+$",
    )

    input_text: str = Field(
        ...,
        title="Input Text",
        description=(
            "Text input to send to the interactive command session. "
            "Can include newlines and special characters. Common examples: "
            "Python code, SQL queries, shell commands, or simple responses like 'y' or 'n'."
        ),
        max_length=10000,
        example="print('Hello, World!')",
    )

    send_newline: bool = Field(
        True,
        title="Append Newline",
        description=(
            "Whether to automatically append a newline character (\\n) to the input. "
            "Most interactive commands expect a newline to execute the input. "
            "Set to False for partial input or when controlling exact input format."
        ),
        example=True,
    )

    class Config:
        """Pydantic model configuration"""

        title = "Interactive Session Input"
        description = "Input to send to an active interactive command session"
        json_schema_extra = {
            "examples": [
                {
                    "session_id": "session_python_123",
                    "input_text": "print('Hello World')",
                    "send_newline": True,
                },
                {
                    "session_id": "session_mysql_456",
                    "input_text": "SHOW DATABASES;",
                    "send_newline": True,
                },
                {
                    "session_id": "session_confirm_789",
                    "input_text": "y",
                    "send_newline": True,
                },
            ]
        }


class CommandResponse(BaseModel):
    """
    Response model containing the results of command execution.

    Provides comprehensive information about command execution including
    output, error details, performance metrics, and session information.
    """

    success: bool = Field(
        ...,
        title="Execution Success",
        description=(
            "Indicates whether the command executed successfully without errors. "
            "True means the command completed normally with exit code 0. "
            "False indicates an error occurred during execution."
        ),
        example=True,
    )

    exit_code: Optional[int] = Field(
        None,
        title="Process Exit Code",
        description=(
            "The exit code returned by the executed command process. "
            "0 typically indicates success, non-zero values indicate various error conditions. "
            "May be None for interactive sessions or commands that don't complete."
        ),
        example=0,
    )

    stdout: str = Field(
        "",
        title="Standard Output",
        description=(
            "Text output from the command's standard output stream (stdout). "
            "Contains the primary output/results of the command execution. "
            "May be truncated for very large outputs for performance reasons."
        ),
        example="total 64\ndrwxr-xr-x 3 user user 4096 Jan 15 10:30 .",
    )

    stderr: str = Field(
        "",
        title="Standard Error",
        description=(
            "Error output from the command's standard error stream (stderr). "
            "Contains error messages, warnings, and diagnostic information. "
            "Empty string indicates no errors were reported."
        ),
        example="",
    )

    execution_time: float = Field(
        ...,
        title="Execution Duration",
        description=(
            "Time taken to execute the command in seconds (with decimal precision). "
            "Useful for performance monitoring and debugging slow operations. "
            "For interactive sessions, represents time for the current input/output cycle."
        ),
        example=0.245,
        ge=0,
    )

    session_id: Optional[str] = Field(
        None,
        title="Session Identifier",
        description=(
            "Unique identifier for interactive command sessions. "
            "Present when command_type='interactive' or when continuing an interactive session. "
            "Use this ID for subsequent interactions with the same session."
        ),
        example="session_abc123xyz789",
    )

    is_interactive: bool = Field(
        False,
        title="Interactive Session Flag",
        description=(
            "Indicates whether this response is from an interactive command session. "
            "Interactive sessions remain active for additional input/output exchanges. "
            "Simple commands always have this set to False."
        ),
        example=False,
    )

    error_message: Optional[str] = Field(
        None,
        title="Error Description",
        description=(
            "Human-readable description of any error that occurred during execution. "
            "Provides additional context beyond the exit code and stderr output. "
            "Includes system-level errors, timeouts, and security validation failures."
        ),
        example="Command timed out after 30 seconds",
    )

    command_executed: Optional[str] = Field(
        None,
        title="Executed Command",
        description=(
            "The actual command that was executed, including any modifications "
            "made by the system for security or compatibility reasons."
        ),
        example="ls -la /home/user",
    )

    working_directory: Optional[str] = Field(
        None,
        title="Execution Directory",
        description=(
            "The working directory where the command was executed. "
            "Useful for understanding the context of relative path operations."
        ),
        example="/home/user",
    )

    class Config:
        """Pydantic model configuration"""

        title = "Command Execution Response"
        description = "Results and metadata from CLI command execution"
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "exit_code": 0,
                    "stdout": "Hello World\n",
                    "stderr": "",
                    "execution_time": 0.142,
                    "session_id": None,
                    "is_interactive": False,
                    "error_message": None,
                },
                {
                    "success": True,
                    "exit_code": None,
                    "stdout": 'Python 3.9.2 (default, Feb 28 2021, 17:03:44)\n[GCC 10.2.1 20210110] on linux\nType "help", "copyright", "credits" or "license" for more information.\n>>> ',
                    "stderr": "",
                    "execution_time": 1.025,
                    "session_id": "session_python_abc123",
                    "is_interactive": True,
                    "error_message": None,
                },
            ]
        }


class SessionInfo(BaseModel):
    """
    Information about an active interactive command session.

    Provides detailed metadata about interactive sessions including
    status, timing, and resource usage information.
    """

    session_id: str = Field(
        ...,
        title="Session Identifier",
        description=(
            "Unique identifier for this interactive session. "
            "Used to reference the session in all API calls."
        ),
        example="session_python_abc123",
    )

    command: str = Field(
        ...,
        title="Session Command",
        description=(
            "The original command that started this interactive session. "
            "Provides context about what type of interactive environment is running."
        ),
        example="python3",
    )

    status: str = Field(
        ...,
        title="Session Status",
        description=(
            "Current status of the interactive session:\n"
            "- **active**: Session is running and accepting input\n"
            "- **waiting**: Session is waiting for input\n"
            "- **busy**: Session is processing previous input\n"
            "- **terminated**: Session has ended\n"
            "- **error**: Session encountered an error"
        ),
        example="active",
    )

    created_at: str = Field(
        ...,
        title="Creation Timestamp",
        description=(
            "ISO 8601 formatted timestamp when the session was created. "
            "Useful for tracking session age and cleanup operations."
        ),
        example="2024-01-15T10:30:45.123Z",
    )

    last_activity: str = Field(
        ...,
        title="Last Activity Timestamp",
        description=(
            "ISO 8601 formatted timestamp of the last interaction with this session. "
            "Updated whenever input is sent or output is received. "
            "Used for detecting idle sessions."
        ),
        example="2024-01-15T10:45:20.456Z",
    )

    process_id: Optional[int] = Field(
        None,
        title="Process ID",
        description=(
            "Operating system process ID (PID) of the interactive command. "
            "Can be used for advanced monitoring or process management operations."
        ),
        example=12345,
    )

    working_directory: Optional[str] = Field(
        None,
        title="Working Directory",
        description=(
            "Current working directory of the interactive session. "
            "May change during session lifetime based on commands executed."
        ),
        example="/home/user/workspace",
    )

    class Config:
        """Pydantic model configuration"""

        title = "Interactive Session Information"
        description = "Metadata and status information for active interactive sessions"
        json_schema_extra = {
            "examples": [
                {
                    "session_id": "session_python_abc123",
                    "command": "python3",
                    "status": "active",
                    "created_at": "2024-01-15T10:30:45.123Z",
                    "last_activity": "2024-01-15T10:45:20.456Z",
                    "process_id": 12345,
                    "working_directory": "/home/user",
                }
            ]
        }


class SystemStatus(BaseModel):
    """
    Comprehensive system status and performance metrics.

    Provides real-time information about server health, resource utilization,
    and operational status for monitoring and diagnostic purposes.
    """

    uptime: str = Field(
        ...,
        title="System Uptime",
        description=(
            "Human-readable system uptime showing how long the server has been running. "
            "Format: 'XdYhZm' (days, hours, minutes) or 'XhYm' for less than a day. "
            "Useful for understanding system stability and maintenance windows."
        ),
        example="5d 14h 32m",
    )

    load_average: List[float] = Field(
        ...,
        title="System Load Average",
        description=(
            "System load averages over the last 1, 5, and 15 minutes respectively. "
            "Values represent average system load where 1.0 equals full utilization "
            "of a single CPU core. Values > number of CPU cores indicate overload."
        ),
        example=[0.45, 0.52, 0.48],
        min_items=3,
        max_items=3,
    )

    memory_usage: Dict[str, Union[int, float]] = Field(
        ...,
        title="Memory Utilization",
        description=(
            "Detailed memory usage statistics including:\n"
            "- **total**: Total physical memory in bytes\n"
            "- **available**: Available memory for new processes in bytes\n"
            "- **used**: Currently used memory in bytes\n"
            "- **percent**: Memory usage percentage (0-100)\n"
            "- **cached**: Memory used for disk caching (if available)\n"
            "- **buffers**: Memory used for system buffers (if available)"
        ),
        example={
            "total": 8589934592,
            "available": 5368709120,
            "used": 3221225472,
            "percent": 37.5,
            "cached": 1073741824,
            "buffers": 268435456,
        },
    )

    disk_usage: Dict[str, Union[int, float]] = Field(
        ...,
        title="Disk Space Utilization",
        description=(
            "Root filesystem disk usage statistics:\n"
            "- **total**: Total disk space in bytes\n"
            "- **used**: Used disk space in bytes\n"
            "- **free**: Available disk space in bytes\n"
            "- **percent**: Disk usage percentage (0-100)"
        ),
        example={
            "total": 107374182400,
            "used": 21474836480,
            "free": 85899346920,
            "percent": 20.0,
        },
    )

    active_sessions: int = Field(
        ...,
        title="Active Interactive Sessions",
        description=(
            "Number of currently active interactive command sessions. "
            "Each session represents a persistent command environment "
            "that can accept input and provide output over time."
        ),
        example=3,
        ge=0,
    )

    cpu_usage: Optional[Dict[str, float]] = Field(
        None,
        title="CPU Utilization",
        description=(
            "Current CPU usage statistics:\n"
            "- **percent**: Overall CPU usage percentage\n"
            "- **user**: Time spent in user mode\n"
            "- **system**: Time spent in system/kernel mode\n"
            "- **idle**: Time spent idle\n"
            "- **iowait**: Time spent waiting for I/O operations"
        ),
        example={
            "percent": 25.3,
            "user": 15.2,
            "system": 8.1,
            "idle": 74.7,
            "iowait": 2.0,
        },
    )

    network_stats: Optional[Dict[str, int]] = Field(
        None,
        title="Network Statistics",
        description=(
            "Network interface statistics:\n"
            "- **bytes_sent**: Total bytes transmitted\n"
            "- **bytes_recv**: Total bytes received\n"
            "- **packets_sent**: Total packets transmitted\n"
            "- **packets_recv**: Total packets received"
        ),
        example={
            "bytes_sent": 1073741824,
            "bytes_recv": 2147483648,
            "packets_sent": 1048576,
            "packets_recv": 2097152,
        },
    )

    class Config:
        """Pydantic model configuration"""

        title = "System Status and Performance Metrics"
        description = "Comprehensive server health and resource utilization information"
        json_schema_extra = {
            "examples": [
                {
                    "uptime": "2d 14h 32m",
                    "load_average": [0.45, 0.52, 0.48],
                    "memory_usage": {
                        "total": 8589934592,
                        "available": 5368709120,
                        "used": 3221225472,
                        "percent": 37.5,
                    },
                    "disk_usage": {
                        "total": 107374182400,
                        "used": 21474836480,
                        "free": 85899346920,
                        "percent": 20.0,
                    },
                    "active_sessions": 2,
                }
            ]
        }


class HealthCheck(BaseModel):
    """
    API health check response model.

    Provides basic service availability and version information
    for monitoring and diagnostic purposes.
    """

    status: str = Field(
        "healthy",
        title="Service Status",
        description=(
            "Overall health status of the API service:\n"
            "- **healthy**: Service is operational and accepting requests\n"
            "- **degraded**: Service is running but with reduced functionality\n"
            "- **unhealthy**: Service is experiencing critical issues"
        ),
        example="healthy",
    )

    version: str = Field(
        "1.0.0",
        title="API Version",
        description=(
            "Current version of the V-AI CLI Control API service. "
            "Follows semantic versioning (MAJOR.MINOR.PATCH) format. "
            "Useful for client compatibility and feature detection."
        ),
        example="1.0.0",
        pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$",
    )

    timestamp: str = Field(
        ...,
        title="Response Timestamp",
        description=(
            "ISO 8601 formatted timestamp when the health check was performed. "
            "Useful for monitoring response times and service availability tracking."
        ),
        example="2024-01-15T10:30:45.123456Z",
    )

    uptime_seconds: Optional[float] = Field(
        None,
        title="Service Uptime",
        description=(
            "Number of seconds the API service has been running since last restart. "
            "Useful for understanding service stability and deployment timing."
        ),
        example=86400.5,
        ge=0,
    )

    dependencies: Optional[Dict[str, str]] = Field(
        None,
        title="Dependency Status",
        description=(
            "Status of external dependencies and services:\n"
            "Key: dependency name, Value: status ('healthy', 'degraded', 'unhealthy')"
        ),
        example={"database": "healthy", "filesystem": "healthy", "system": "healthy"},
    )

    class Config:
        """Pydantic model configuration"""

        title = "API Health Check Response"
        description = "Service health and availability information"
        json_schema_extra = {
            "examples": [
                {
                    "status": "healthy",
                    "version": "1.0.0",
                    "timestamp": "2024-01-15T10:30:45.123456Z",
                    "uptime_seconds": 86400.5,
                    "dependencies": {"filesystem": "healthy", "system": "healthy"},
                }
            ]
        }


class QuickCommandRequest(BaseModel):
    """
    Request model for quick command shortcuts like yes/no responses.

    Provides a simplified interface for common interactive command responses,
    making it easier for GPT agents to handle typical user prompts.
    """

    session_id: str = Field(
        ...,
        title="Target Session ID",
        description=(
            "Identifier of the interactive session that needs the quick response. "
            "Must be an active session waiting for input."
        ),
        example="session_python_abc123",
    )

    answer: bool = Field(
        ...,
        title="Yes/No Answer",
        description=(
            "Boolean response to send to the interactive session:\n"
            "- **true**: Sends 'y' or 'yes' response\n"
            "- **false**: Sends 'n' or 'no' response"
        ),
        example=True,
    )

    response_format: Optional[str] = Field(
        "short",
        title="Response Format",
        description=(
            "Format of the response to send:\n"
            "- **short**: Send 'y' or 'n'\n"
            "- **long**: Send 'yes' or 'no'\n"
            "- **custom**: Use custom_yes/custom_no values"
        ),
        example="short",
    )

    custom_yes: Optional[str] = Field(
        None,
        title="Custom Yes Response",
        description="Custom text to send for 'yes' responses when response_format='custom'",
        example="confirm",
    )

    custom_no: Optional[str] = Field(
        None,
        title="Custom No Response",
        description="Custom text to send for 'no' responses when response_format='custom'",
        example="cancel",
    )

    class Config:
        """Pydantic model configuration"""

        title = "Quick Command Request"
        description = "Simplified interface for common yes/no interactive responses"
        json_schema_extra = {
            "examples": [
                {
                    "session_id": "session_install_xyz",
                    "answer": True,
                    "response_format": "short",
                },
                {
                    "session_id": "session_confirm_abc",
                    "answer": False,
                    "response_format": "long",
                },
                {
                    "session_id": "session_custom_def",
                    "answer": True,
                    "response_format": "custom",
                    "custom_yes": "proceed",
                    "custom_no": "abort",
                },
            ]
        }


class ErrorResponse(BaseModel):
    """
    Standardized error response model for all API endpoints.

    Provides consistent error reporting with detailed context
    and actionable information for debugging and resolution.
    """

    error: bool = Field(
        True,
        title="Error Flag",
        description="Always True to indicate this is an error response",
        example=True,
    )

    error_type: str = Field(
        ...,
        title="Error Category",
        description=(
            "Category of error that occurred:\n"
            "- **validation**: Input validation failed\n"
            "- **authentication**: Authentication/authorization failed\n"
            "- **execution**: Command execution failed\n"
            "- **system**: System-level error occurred\n"
            "- **timeout**: Operation exceeded time limits\n"
            "- **not_found**: Requested resource doesn't exist"
        ),
        example="validation",
    )

    message: str = Field(
        ...,
        title="Error Message",
        description="Human-readable description of the error that occurred",
        example="Command contains potentially dangerous pattern ';'",
    )

    detail: Optional[Dict[str, Any]] = Field(
        None,
        title="Error Details",
        description=(
            "Additional structured information about the error, "
            "such as field validation errors, system error codes, "
            "or debugging information."
        ),
        example={
            "field": "command",
            "invalid_value": "rm -rf /; echo done",
            "validation_rule": "dangerous_patterns",
        },
    )

    timestamp: str = Field(
        ...,
        title="Error Timestamp",
        description="ISO 8601 timestamp when the error occurred",
        example="2024-01-15T10:30:45.123456Z",
    )

    request_id: Optional[str] = Field(
        None,
        title="Request Identifier",
        description="Unique identifier for the failed request (for debugging)",
        example="req_abc123def456",
    )

    class Config:
        """Pydantic model configuration"""

        title = "API Error Response"
        description = "Standardized error information for failed API requests"
        json_schema_extra = {
            "examples": [
                {
                    "error": True,
                    "error_type": "validation",
                    "message": "Command validation failed",
                    "detail": {"field": "command", "invalid_pattern": ";"},
                    "timestamp": "2024-01-15T10:30:45.123456Z",
                }
            ]
        }
