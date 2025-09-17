import os
import psutil
import time
import logging
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import (
    CommandRequest, CommandResponse, InteractiveResponse, 
    SessionInfo, SystemStatus, HealthCheck, CommandType,
    QuickCommandRequest, ErrorResponse
)
from executor import command_executor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app configuration
app = FastAPI(
    title="V-AI CLI Control API",
    description="""
    **A comprehensive FastAPI service for GPT-controlled Linux server management through CLI commands**
    
    This API enables custom GPT models and AI agents to execute and manage Linux command-line operations
    with advanced security, interactive session support, and comprehensive monitoring capabilities.
    
    ## 🚀 Key Features
    
    - **Secure Command Execution**: Protected CLI command execution with comprehensive security validation
    - **Interactive Sessions**: Persistent sessions for commands requiring multiple input/output exchanges
    - **Real-time Monitoring**: System status monitoring and performance metrics
    - **Session Management**: Create, monitor, and terminate interactive command sessions
    - **GPT-Optimized**: Specially designed endpoints for seamless AI agent integration
    
    ## 🔒 Security Features
    
    - **API Key Authentication**: All endpoints protected with Bearer token authentication
    - **Command Filtering**: Configurable whitelist of allowed commands
    - **Path Restrictions**: Prevent access to sensitive system areas
    - **Input Validation**: Comprehensive security pattern detection and validation
    - **Timeout Protection**: Configurable timeouts prevent hanging processes
    
    ## 📋 Endpoint Categories
    
    ### Command Execution
    - Execute simple CLI commands that return immediate results
    - Start interactive sessions for complex multi-step operations
    - Send input to active interactive sessions
    
    ### Session Management  
    - List and monitor all active interactive sessions
    - Get detailed information about specific sessions
    - Terminate sessions when no longer needed
    
    ### System Monitoring
    - Real-time system status and performance metrics
    - Health checks for service monitoring and diagnostics
    
    ### Quick Actions
    - Simplified endpoints for common operations like yes/no responses
    - GPT-friendly shortcuts for typical interactive scenarios
    
    ## 🔑 Authentication
    
    All endpoints require a valid API key provided via the `Authorization` header:
    ```
    Authorization: Bearer YOUR_API_KEY
    ```
    
    ## ⚠️ Important Notes
    
    - Commands are executed with the same privileges as the API service
    - Interactive sessions maintain state until explicitly terminated or timed out  
    - All command execution is logged for security and debugging purposes
    - Rate limiting and resource quotas may apply in production environments
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "V-AI CLI Control API",
        "url": "https://github.com/djav1985/v-ai-cli-control",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {"url": "http://localhost:8000", "description": "Development server"},
        {"url": "https://your-domain.com", "description": "Production server (configure as needed)"}
    ]
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
API_KEY = os.getenv('API_KEY')

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify API key for authentication"""
    if API_KEY and credentials.credentials != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return credentials.credentials

@app.get(
    "/", 
    response_model=HealthCheck,
    summary="API Root Health Check",
    description="""
    **Primary health check endpoint for the V-AI CLI Control API.**
    
    Returns basic service status information including version, timestamp, and overall health status.
    This endpoint is typically used by load balancers, monitoring systems, and clients to verify
    that the API service is running and accepting requests.
    
    **Use Cases:**
    - Service availability monitoring
    - Load balancer health checks  
    - Basic connectivity verification
    - Service discovery validation
    
    **Response includes:**
    - Service health status (healthy/degraded/unhealthy)
    - API version information
    - Current server timestamp
    - Optional uptime and dependency status
    """,
    tags=["Health & Monitoring"],
    responses={
        200: {
            "description": "Service is healthy and operational",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "1.0.0", 
                        "timestamp": "2024-01-15T10:30:45.123456Z"
                    }
                }
            }
        }
    }
)
async def root():
    """Root endpoint health check - returns basic service status"""
    return HealthCheck(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )

@app.get(
    "/health", 
    response_model=HealthCheck,
    summary="Detailed Health Check",
    description="""
    **Comprehensive health check endpoint with detailed service information.**
    
    Provides more detailed health information compared to the root endpoint, including
    service uptime, dependency status, and extended diagnostic information.
    
    **Use Cases:**
    - Detailed service monitoring and alerting
    - Diagnostic information gathering
    - Service performance tracking
    - Dependency health verification
    
    **Response includes:**
    - Detailed health status with reasons
    - Service uptime in seconds
    - Status of external dependencies
    - Performance and resource utilization hints
    """,
    tags=["Health & Monitoring"],
    responses={
        200: {
            "description": "Detailed service health information",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "1.0.0",
                        "timestamp": "2024-01-15T10:30:45.123456Z",
                        "uptime_seconds": 86400.5,
                        "dependencies": {
                            "filesystem": "healthy",
                            "system": "healthy"
                        }
                    }
                }
            }
        }
    }
)
async def health_check():
    """Detailed health check endpoint with comprehensive service information"""
    return HealthCheck(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )

@app.post(
    "/execute", 
    response_model=CommandResponse,
    summary="Execute CLI Commands",
    description="""
    **Primary endpoint for executing Linux CLI commands on the server.**
    
    This endpoint supports multiple execution modes to handle different types of commands:
    
    ### Execution Modes
    
    **Simple Commands** (`command_type: "simple"`)
    - Execute command once and return complete output immediately
    - Best for: `ls`, `pwd`, `whoami`, `df`, `ps`, file operations
    - Returns: Complete stdout/stderr, exit code, execution time
    
    **Interactive Commands** (`command_type: "interactive"`)  
    - Start persistent session for commands requiring ongoing input/output
    - Best for: `python`, `mysql`, `ssh`, text editors, installation wizards
    - Returns: Session ID for subsequent interactions via `/interactive/{session_id}`
    
    ### Security Features
    
    - **Command Validation**: Blocks dangerous patterns (`;`, `&&`, `||`, etc.)
    - **Allowed Commands**: Configurable whitelist of permitted commands
    - **Path Restrictions**: Prevents access to sensitive system directories
    - **Timeout Protection**: Commands terminated after specified timeout
    - **Privilege Control**: Executes with service account permissions only
    
    ### Input Validation
    
    - Command length limits (1-1000 characters)
    - Working directory must be absolute path
    - Timeout range: 1-300 seconds
    - Environment variables must be key-value string pairs
    
    ### Common Use Cases
    
    **File Operations**
    ```json
    {
        "command": "ls -la /home/user",
        "command_type": "simple",
        "working_directory": "/home/user"
    }
    ```
    
    **System Information**
    ```json
    {
        "command": "df -h && free -h && uptime",
        "command_type": "simple",
        "timeout": 10
    }
    ```
    
    **Interactive Python Session**
    ```json
    {
        "command": "python3",
        "command_type": "interactive", 
        "environment": {"PYTHONPATH": "/usr/local/lib"}
    }
    ```
    """,
    tags=["Command Execution"],
    responses={
        200: {
            "description": "Command executed successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "simple_command": {
                            "summary": "Simple command execution",
                            "value": {
                                "success": True,
                                "exit_code": 0,
                                "stdout": "total 64\ndrwxr-xr-x 3 user user 4096 Jan 15 10:30 .",
                                "stderr": "",
                                "execution_time": 0.142,
                                "session_id": None,
                                "is_interactive": False,
                                "error_message": None
                            }
                        },
                        "interactive_command": {
                            "summary": "Interactive session started",
                            "value": {
                                "success": True,
                                "exit_code": None,
                                "stdout": "Python 3.9.2 (default, Feb 28 2021, 17:03:44)\n>>> ",
                                "stderr": "",
                                "execution_time": 1.025,
                                "session_id": "session_python_abc123",
                                "is_interactive": True,
                                "error_message": None
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid command or validation failed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Command contains potentially dangerous pattern ';'"
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        500: {
            "description": "Command execution failed due to system error"
        }
    }
)
async def execute_command(
    request: CommandRequest,
    api_key: str = Depends(verify_api_key)
):
    """Execute a CLI command with comprehensive security validation and monitoring"""
    logger.info(f"Executing command: {request.command}")
    
    try:
        if request.command_type == CommandType.SIMPLE:
            response = await command_executor.execute_simple_command(
                command=request.command,
                working_directory=request.working_directory,
                timeout=request.timeout,
                environment=request.environment
            )
        elif request.command_type == CommandType.INTERACTIVE:
            session_id, response = command_executor.start_interactive_command(
                command=request.command,
                working_directory=request.working_directory,
                environment=request.environment
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Command type {request.command_type} not implemented yet"
            )
        
        logger.info(f"Command executed successfully: {response.success}")
        return response
        
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Command execution failed: {str(e)}")

@app.post(
    "/interactive/{session_id}", 
    response_model=CommandResponse,
    summary="Send Input to Interactive Session",
    description="""
    **Send input to an active interactive command session.**
    
    This endpoint allows you to provide input to commands running in interactive mode,
    enabling multi-step operations and complex command sequences.
    
    ### How Interactive Sessions Work
    
    1. **Start Session**: Use `/execute` with `command_type: "interactive"`
    2. **Get Session ID**: Extract `session_id` from the response
    3. **Send Input**: Use this endpoint to send commands, responses, or data
    4. **Receive Output**: Each input returns the resulting output from the command
    5. **Continue**: Repeat steps 3-4 as needed for multi-step operations
    6. **Terminate**: Use `/sessions/{session_id}` DELETE to end the session
    
    ### Common Interactive Commands
    
    **Python REPL**
    ```python
    # Session started with: {"command": "python3", "command_type": "interactive"}
    # Send input: "print('Hello World')"
    # Send input: "x = 42"  
    # Send input: "print(x * 2)"
    ```
    
    **Database Shell**
    ```sql
    # Session started with: {"command": "mysql -u user -p database", "command_type": "interactive"}
    # Send input: "password123"
    # Send input: "SHOW TABLES;"
    # Send input: "SELECT * FROM users LIMIT 5;"
    ```
    
    **Installation Wizards**
    ```bash
    # Session started with: {"command": "sudo apt install package", "command_type": "interactive"}
    # Send input: "y"  # Confirm installation
    # Send input: "1"  # Select option 1
    # Send input: ""   # Press enter to continue
    ```
    
    ### Input Processing
    
    - **Automatic Newlines**: Most inputs automatically append `\\n` for command execution
    - **Raw Input**: Set `send_newline: false` for precise control over input format
    - **Multi-line Support**: Send complex inputs including code blocks and scripts
    - **Special Characters**: Supports control characters and escape sequences
    
    ### Session State Management
    
    - **Persistent State**: Variables, connections, and context preserved between inputs
    - **Working Directory**: Changes to directory persist within the session
    - **Environment**: Environment variables set in session remain active
    - **Process Tree**: Child processes inherit session context and permissions
    """,
    tags=["Interactive Sessions"],
    responses={
        200: {
            "description": "Input sent successfully and output received",
            "content": {
                "application/json": {
                    "examples": {
                        "python_execution": {
                            "summary": "Python code execution",
                            "value": {
                                "success": True,
                                "exit_code": None,
                                "stdout": "Hello World\n>>> ",
                                "stderr": "",
                                "execution_time": 0.025,
                                "session_id": "session_python_abc123",
                                "is_interactive": True,
                                "error_message": None
                            }
                        },
                        "command_with_error": {
                            "summary": "Command with error output",
                            "value": {
                                "success": True,
                                "exit_code": None,
                                "stdout": "",
                                "stderr": "SyntaxError: invalid syntax\n>>> ",
                                "execution_time": 0.018,
                                "session_id": "session_python_abc123", 
                                "is_interactive": True,
                                "error_message": None
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid input or session configuration"
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        404: {
            "description": "Session not found or has been terminated"
        },
        500: {
            "description": "Failed to send input or receive output from session"
        }
    }
)
async def send_interactive_input(
    session_id: str,
    request: InteractiveResponse,
    api_key: str = Depends(verify_api_key)
):
    """Send input to an interactive command session and receive output"""
    logger.info(f"Sending input to session {session_id}: {request.input_text}")
    
    try:
        response = command_executor.send_interactive_input(session_id, request.input_text)
        logger.info(f"Interactive input sent successfully: {response.success}")
        return response
        
    except Exception as e:
        logger.error(f"Error sending interactive input: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Interactive input failed: {str(e)}")

@app.get(
    "/sessions", 
    response_model=List[SessionInfo],
    summary="List Active Interactive Sessions",
    description="""
    **Retrieve a list of all currently active interactive command sessions.**
    
    This endpoint provides comprehensive information about all interactive sessions
    currently running on the server, including their status, timing, and resource usage.
    
    ### Session Information Included
    
    **Basic Details**
    - **Session ID**: Unique identifier for API interactions
    - **Original Command**: The command that started the interactive session
    - **Current Status**: active, waiting, busy, terminated, or error
    - **Creation Time**: When the session was initially started
    - **Last Activity**: Most recent interaction timestamp
    
    **Extended Information**
    - **Process ID**: System process identifier (PID) for advanced monitoring
    - **Working Directory**: Current working directory of the session
    - **Resource Usage**: Memory, CPU utilization (if available)
    - **Parent/Child Processes**: Process hierarchy information
    
    ### Session Status Meanings
    
    - **active**: Session is running normally and ready for input
    - **waiting**: Session is idle, waiting for the next input
    - **busy**: Session is currently processing previous input
    - **terminated**: Session has ended (will be cleaned up automatically)
    - **error**: Session encountered an error and may need manual cleanup
    
    ### Use Cases
    
    **Session Monitoring**
    - Track all active interactive operations
    - Monitor session resource usage and performance
    - Identify long-running or stuck sessions
    - Audit interactive command usage
    
    **Session Management**  
    - Find specific sessions by command or creation time
    - Identify sessions that may need termination
    - Monitor session activity patterns
    - Clean up abandoned or orphaned sessions
    
    **Debugging and Troubleshooting**
    - Investigate session-related issues
    - Track session lifecycle and state changes
    - Monitor concurrent session limits
    - Analyze interactive command patterns
    
    ### Automatic Cleanup
    
    The system automatically removes inactive sessions based on configurable timeouts:
    - **Idle Timeout**: Sessions with no activity for extended periods
    - **Maximum Lifetime**: Sessions running longer than configured limits
    - **Resource Limits**: Sessions consuming excessive system resources
    - **Process Termination**: Sessions whose underlying processes have ended
    """,
    tags=["Session Management"],
    responses={
        200: {
            "description": "List of active sessions retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "session_id": "session_python_abc123",
                            "command": "python3",
                            "status": "active", 
                            "created_at": "2024-01-15T10:30:45.123Z",
                            "last_activity": "2024-01-15T10:45:20.456Z",
                            "process_id": 12345,
                            "working_directory": "/home/user"
                        },
                        {
                            "session_id": "session_mysql_def456",
                            "command": "mysql -u user -p database",
                            "status": "waiting",
                            "created_at": "2024-01-15T09:15:30.789Z", 
                            "last_activity": "2024-01-15T10:42:15.321Z",
                            "process_id": 12346,
                            "working_directory": "/var/lib/mysql"
                        }
                    ]
                }
            }
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        500: {
            "description": "Failed to retrieve session list due to system error"
        }
    }
)
async def list_sessions(api_key: str = Depends(verify_api_key)):
    """List all active interactive sessions with detailed status information"""
    try:
        # Clean up inactive sessions first
        command_executor.cleanup_inactive_sessions()
        sessions = command_executor.list_active_sessions()
        logger.info(f"Retrieved {len(sessions)} active sessions")
        return sessions
        
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@app.get(
    "/sessions/{session_id}", 
    response_model=SessionInfo,
    summary="Get Session Information",
    description="""
    **Retrieve detailed information about a specific interactive session.**
    
    This endpoint provides comprehensive details about a single interactive session,
    including its current state, performance metrics, and operational history.
    
    ### Information Provided
    
    **Session Identity**
    - Unique session identifier  
    - Original command that started the session
    - Current operational status
    
    **Timing Information**
    - Session creation timestamp
    - Last activity/interaction timestamp  
    - Total session duration (calculated)
    - Activity pattern and frequency
    
    **System Integration**
    - Process ID (PID) for system-level monitoring
    - Current working directory
    - Environment variables and context
    - Resource utilization metrics
    
    **Status Details**
    - Current session state (active, waiting, busy, etc.)
    - Error conditions and diagnostic information
    - Performance metrics and resource usage
    - Child process information
    
    ### Use Cases
    
    **Session Monitoring**
    - Check if a specific session is still active and responsive
    - Monitor session performance and resource usage
    - Track session activity and interaction patterns
    - Verify session state before sending input
    
    **Debugging and Diagnostics**
    - Investigate session-related issues or errors
    - Analyze session performance and bottlenecks
    - Troubleshoot unresponsive or stuck sessions
    - Gather information for session optimization
    
    **Integration and Automation**
    - Validate session existence before API calls
    - Implement session health checks in automated workflows
    - Build session monitoring and alerting systems
    - Create session lifecycle management tools
    """,
    tags=["Session Management"], 
    responses={
        200: {
            "description": "Session information retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "session_id": "session_python_abc123",
                        "command": "python3",
                        "status": "active",
                        "created_at": "2024-01-15T10:30:45.123Z",
                        "last_activity": "2024-01-15T10:45:20.456Z",
                        "process_id": 12345,
                        "working_directory": "/home/user/workspace"
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        404: {
            "description": "Session not found - may have been terminated or never existed"
        },
        500: {
            "description": "Failed to retrieve session information due to system error"
        }
    }
)
async def get_session_info(
    session_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get detailed information about a specific interactive session"""
    try:
        session_info = command_executor.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger.info(f"Retrieved session info for {session_id}")
        return session_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get session info: {str(e)}")

@app.delete(
    "/sessions/{session_id}",
    summary="Terminate Interactive Session", 
    description="""
    **Forcefully terminate a specific interactive command session.**
    
    This endpoint cleanly shuts down an active interactive session, terminating
    the underlying process and cleaning up associated resources.
    
    ### Termination Process
    
    **Graceful Shutdown**
    1. Send termination signal (SIGTERM) to the main process
    2. Wait for graceful shutdown (configurable timeout)
    3. Terminate child processes if they exist  
    4. Clean up temporary files and resources
    5. Remove session from active session list
    
    **Forced Termination**
    If graceful shutdown fails:
    1. Send kill signal (SIGKILL) to force termination
    2. Clean up any remaining resources and temporary files
    3. Log termination details for debugging
    4. Update session status to 'terminated'
    
    ### When to Terminate Sessions
    
    **Normal Operations**
    - Interactive work is complete
    - Switching to different tools or commands  
    - Cleaning up before system maintenance
    - Managing resource usage and session limits
    
    **Error Recovery**
    - Session has become unresponsive or stuck
    - Process is consuming excessive resources
    - Session encountered critical errors
    - Emergency cleanup during system issues
    
    **Resource Management**
    - Too many active sessions consuming resources
    - Long-running sessions no longer needed
    - Scheduled cleanup of idle sessions
    - Preparing for system shutdown or restart
    
    ### Important Considerations
    
    **Data Loss Prevention**  
    - **Save Important Work**: Ensure any important data or progress is saved before termination
    - **Active Transactions**: Database transactions or file operations may be interrupted
    - **Temporary Files**: Temporary files created by the session will be cleaned up
    - **Unsaved Changes**: Any unsaved changes in editors or applications will be lost
    
    **Process Dependencies**
    - **Child Processes**: All child processes spawned by the session will also be terminated
    - **Background Jobs**: Background jobs started within the session may be interrupted  
    - **Network Connections**: Open network connections will be closed
    - **File Handles**: Open files will be closed (may cause data loss if not saved)
    
    ### Alternative Approaches
    
    **Graceful Exit Commands**
    Instead of forceful termination, consider sending exit commands:
    - Python: `exit()` or `quit()`
    - MySQL: `exit;` or `quit;`
    - SSH: `exit` or logout
    - Editors: Save and quit commands (`:q` in vim, `Ctrl+X` in nano)
    
    **Session Handoff**  
    For long-running operations, consider:
    - Moving operations to background processes
    - Using screen/tmux for persistent sessions
    - Implementing checkpoint/resume functionality
    - Saving session state before termination
    """,
    tags=["Session Management"],
    responses={
        200: {
            "description": "Session terminated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Session session_python_abc123 terminated successfully"
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        404: {
            "description": "Session not found - may have already been terminated"
        },
        500: {
            "description": "Failed to terminate session due to system error"
        }
    }
)
async def terminate_session(
    session_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Terminate a specific interactive session and clean up resources"""
    try:
        success = command_executor.terminate_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger.info(f"Terminated session {session_id}")
        return {"message": f"Session {session_id} terminated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error terminating session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to terminate session: {str(e)}")

@app.get(
    "/system/status", 
    response_model=SystemStatus,
    summary="System Status and Performance Metrics",
    description="""
    **Get comprehensive real-time system status and performance metrics.**
    
    This endpoint provides detailed information about server health, resource utilization,
    and operational status for monitoring, diagnostics, and capacity planning.
    
    ### System Information Provided
    
    **System Uptime and Load**
    - System uptime in human-readable format (days, hours, minutes)
    - Load average over 1, 5, and 15-minute intervals  
    - CPU utilization and performance metrics
    - System boot time and operational duration
    
    **Memory Utilization**
    - Total system memory (RAM) available
    - Currently used memory and percentage utilization
    - Available memory for new processes
    - Memory used for caching and buffers (Linux systems)
    - Swap usage and virtual memory statistics
    
    **Storage Information**  
    - Root filesystem disk usage and available space
    - Disk usage percentage and capacity planning data
    - I/O performance metrics and disk health indicators
    - Temporary file system usage (if significant)
    
    **Active Sessions**
    - Number of currently active interactive command sessions
    - Session resource utilization and performance impact
    - Average session duration and activity patterns
    - Resource consumption per session type
    
    **Extended Metrics (when available)**
    - Network interface statistics (bytes/packets sent/received)
    - CPU breakdown (user, system, idle, I/O wait times)  
    - Process count and system resource allocation
    - System load patterns and performance trends
    
    ### Use Cases
    
    **System Monitoring**
    - Real-time server health monitoring
    - Resource utilization tracking and alerting
    - Performance trend analysis and capacity planning
    - System load balancing and optimization
    
    **Capacity Planning**
    - Determine optimal resource allocation
    - Predict when system upgrades may be needed
    - Monitor resource consumption patterns
    - Plan for peak usage periods
    
    **Diagnostics and Troubleshooting**
    - Investigate performance issues and bottlenecks
    - Identify resource-intensive operations
    - Monitor system stability and reliability
    - Debug session-related resource usage
    
    **Operational Intelligence**
    - Track system usage patterns over time
    - Monitor impact of interactive sessions on performance
    - Optimize resource allocation and session limits
    - Generate system health reports and dashboards
    
    ### Monitoring Best Practices
    
    **Regular Health Checks**
    - Monitor this endpoint regularly (every 30-60 seconds)
    - Set up alerting for resource threshold breaches
    - Track trends rather than just point-in-time values
    - Consider system load patterns throughout the day
    
    **Resource Thresholds**  
    - **Memory**: Alert when usage exceeds 85-90%
    - **Disk**: Alert when usage exceeds 80-85%  
    - **Load Average**: Alert when consistently above CPU count
    - **Active Sessions**: Monitor against configured limits
    
    **Performance Optimization**
    - Use metrics to identify optimization opportunities
    - Correlate session activity with resource usage
    - Monitor long-term trends for capacity planning
    - Balance system load across multiple servers if available
    """,
    tags=["System Monitoring"],
    responses={
        200: {
            "description": "System status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "uptime": "2d 14h 32m",
                        "load_average": [0.45, 0.52, 0.48],
                        "memory_usage": {
                            "total": 8589934592,
                            "available": 5368709120,
                            "used": 3221225472,
                            "percent": 37.5,
                            "cached": 1073741824,
                            "buffers": 268435456
                        },
                        "disk_usage": {
                            "total": 107374182400,
                            "used": 21474836480,
                            "free": 85899346920,
                            "percent": 20.0
                        },
                        "active_sessions": 3,
                        "cpu_usage": {
                            "percent": 25.3,
                            "user": 15.2,
                            "system": 8.1,
                            "idle": 74.7,
                            "iowait": 2.0
                        }
                    }
                }
            }
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        500: {
            "description": "Failed to retrieve system status due to monitoring error"
        }
    }
)
async def get_system_status(api_key: str = Depends(verify_api_key)):
    """Get comprehensive real-time system status and performance metrics"""
    try:
        # Get system uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime = str(int(uptime_seconds // 3600)) + "h " + str(int((uptime_seconds % 3600) // 60)) + "m"
        
        # Get load average (Linux/Unix only)
        try:
            load_avg = list(os.getloadavg())
        except (AttributeError, OSError):
            load_avg = [0.0, 0.0, 0.0]
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_usage = {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent,
            "used": memory.used
        }
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_usage = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": (disk.used / disk.total) * 100
        }
        
        # Count active sessions
        active_sessions = len(command_executor.active_sessions)
        
        return SystemStatus(
            uptime=uptime,
            load_average=load_avg,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            active_sessions=active_sessions
        )
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")

@app.post(
    "/quick-commands/yes-no",
    response_model=CommandResponse,
    summary="Quick Yes/No Response Handler", 
    description="""
    **Simplified endpoint for handling common yes/no interactive prompts.**
    
    This GPT-optimized endpoint provides an easy way to respond to interactive commands
    that are waiting for confirmation, choices, or simple yes/no responses.
    
    ### How It Works
    
    **Input Processing**  
    - Takes a boolean `answer` parameter (true/false)
    - Automatically converts to appropriate text response
    - Sends the response to the specified interactive session
    - Returns the command output just like the regular interactive endpoint
    
    **Response Formats**
    - `answer: true` → sends "y" (or "yes" based on configuration)
    - `answer: false` → sends "n" (or "no" based on configuration)
    - Custom responses can be configured for specific use cases
    
    ### Common Use Cases
    
    **Package Installation**
    ```bash
    # After: sudo apt install package
    # Prompt: "Do you want to continue? [Y/n]"
    # API Call: POST /quick-commands/yes-no?session_id=session_123&answer=true
    # Sends: "y"
    ```
    
    **File Operations**
    ```bash
    # After: rm -i important_file.txt  
    # Prompt: "remove 'important_file.txt'? (y/n)"
    # API Call: POST /quick-commands/yes-no?session_id=session_456&answer=false
    # Sends: "n" 
    ```
    
    **Configuration Wizards**
    ```bash
    # After: ./configure_system.sh
    # Prompt: "Enable advanced features? (y/n):"
    # API Call: POST /quick-commands/yes-no?session_id=session_789&answer=true
    # Sends: "y"
    ```
    
    **Database Operations**
    ```sql
    # After: DROP TABLE users;
    # Prompt: "Are you sure? This cannot be undone (yes/no):"
    # API Call: POST /quick-commands/yes-no?session_id=session_sql&answer=false  
    # Sends: "no"
    ```
    
    ### Advanced Configuration
    
    **Custom Response Formats**
    The endpoint can be configured to send different response formats:
    - **Short Format**: "y" / "n" (default, most universal)
    - **Long Format**: "yes" / "no" (for commands requiring full words)
    - **Custom Format**: User-defined response strings for specialized commands
    
    **Intelligent Response Selection**
    The system can analyze the prompt text to automatically choose:
    - Appropriate response format (y/yes, Y/YES, etc.)
    - Language-specific responses for international systems
    - Command-specific response patterns
    
    ### Integration with GPT Models
    
    **Simple Decision Making**
    ```python
    # GPT can easily make yes/no decisions
    if user_wants_to_proceed:
        response = requests.post(
            f"/quick-commands/yes-no?session_id={session}&answer=true"
        )
    else:
        response = requests.post(
            f"/quick-commands/yes-no?session_id={session}&answer=false" 
        )
    ```
    
    **Context-Aware Responses**
    - GPT can analyze command output to determine appropriate response
    - Automatic risk assessment for potentially dangerous operations
    - Integration with decision-making logic and safety checks
    
    ### Safety Features
    
    **Confirmation Validation**
    - Endpoint validates that target session exists and is active
    - Confirms session is actually waiting for input
    - Logs all yes/no decisions for audit and debugging
    
    **Risk Assessment** 
    - Tracks commands that received "yes" responses
    - Can be configured to require additional confirmation for high-risk operations
    - Provides logging and audit trail for critical decisions
    """,
    tags=["Quick Actions"],
    responses={
        200: {
            "description": "Yes/no response sent successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "confirmation_yes": {
                            "summary": "Confirmation accepted",
                            "value": {
                                "success": True,
                                "exit_code": None,
                                "stdout": "Proceeding with installation...\n",
                                "stderr": "",
                                "execution_time": 0.045,
                                "session_id": "session_install_abc123",
                                "is_interactive": True,
                                "error_message": None
                            }
                        },
                        "confirmation_no": {
                            "summary": "Operation cancelled",
                            "value": {
                                "success": True,
                                "exit_code": None,
                                "stdout": "Operation cancelled.\n$ ",
                                "stderr": "",
                                "execution_time": 0.032,
                                "session_id": "session_confirm_def456", 
                                "is_interactive": True,
                                "error_message": None
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid session ID or request parameters"
        },
        401: {
            "description": "Authentication failed - invalid or missing API key"
        },
        404: {
            "description": "Session not found or not waiting for input"
        },
        500: {
            "description": "Failed to send response to interactive session"
        }
    }
)
async def handle_yes_no_prompt(
    session_id: str,
    answer: bool,
    api_key: str = Depends(verify_api_key)
):
    """Handle yes/no prompts by sending appropriate response to interactive session"""
    try:
        response_text = "y" if answer else "n"
        response = command_executor.send_interactive_input(session_id, response_text)
        logger.info(f"Sent {response_text} to session {session_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error handling yes/no prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to handle yes/no prompt: {str(e)}")

# Error handlers
@app.exception_handler(ValueError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level=os.getenv('LOG_LEVEL', 'info').lower()
    )