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
    SessionInfo, SystemStatus, HealthCheck, CommandType
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
    title="V-AI CLI Control",
    description="A FastAPI service for GPT-controlled Linux server management through CLI commands",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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

@app.get("/", response_model=HealthCheck)
async def root():
    """Health check endpoint"""
    return HealthCheck(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Detailed health check endpoint"""
    return HealthCheck(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now().isoformat()
    )

@app.post("/execute", response_model=CommandResponse)
async def execute_command(
    request: CommandRequest,
    api_key: str = Depends(verify_api_key)
):
    """Execute a CLI command"""
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

@app.post("/interactive/{session_id}", response_model=CommandResponse)
async def send_interactive_input(
    session_id: str,
    request: InteractiveResponse,
    api_key: str = Depends(verify_api_key)
):
    """Send input to an interactive command session"""
    logger.info(f"Sending input to session {session_id}: {request.input_text}")
    
    try:
        response = command_executor.send_interactive_input(session_id, request.input_text)
        logger.info(f"Interactive input sent successfully: {response.success}")
        return response
        
    except Exception as e:
        logger.error(f"Error sending interactive input: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Interactive input failed: {str(e)}")

@app.get("/sessions", response_model=List[SessionInfo])
async def list_sessions(api_key: str = Depends(verify_api_key)):
    """List all active interactive sessions"""
    try:
        # Clean up inactive sessions first
        command_executor.cleanup_inactive_sessions()
        sessions = command_executor.list_active_sessions()
        logger.info(f"Retrieved {len(sessions)} active sessions")
        return sessions
        
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")

@app.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session_info(
    session_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get information about a specific session"""
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

@app.delete("/sessions/{session_id}")
async def terminate_session(
    session_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Terminate a specific interactive session"""
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

@app.get("/system/status", response_model=SystemStatus)
async def get_system_status(api_key: str = Depends(verify_api_key)):
    """Get current system status"""
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

@app.post("/quick-commands/yes-no")
async def handle_yes_no_prompt(
    session_id: str,
    answer: bool,
    api_key: str = Depends(verify_api_key)
):
    """Handle yes/no prompts by sending 'y' or 'n' to the interactive session"""
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