import asyncio
import logging
import os
import shlex
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pexpect

from models import CommandResponse, SessionInfo

logger = logging.getLogger(__name__)


class CommandExecutor:
    def __init__(self):
        self.active_sessions: Dict[str, Any] = {}
        self.current_session_id: Optional[str] = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.allowed_commands = (
            os.getenv("ALLOWED_COMMANDS", "").split(",")
            if os.getenv("ALLOWED_COMMANDS")
            else None
        )
        self.restricted_paths = (
            os.getenv("RESTRICTED_PATHS", "").split(",")
            if os.getenv("RESTRICTED_PATHS")
            else []
        )

    def _is_command_allowed(self, command: str) -> bool:
        """Check if command is allowed based on configuration"""
        if not self.allowed_commands:
            return True  # If no restrictions configured, allow all

        # Check if the first word (actual command) is in allowed list
        first_word = command.split()[0] if command.split() else ""
        return first_word in self.allowed_commands

    def _check_path_restrictions(self, command: str) -> bool:
        """Check if command tries to access restricted paths"""
        for restricted in self.restricted_paths:
            if restricted and restricted in command:
                return False
        return True

    async def execute_simple_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
        environment: Optional[Dict[str, str]] = None,
    ) -> CommandResponse:
        """Execute a simple non-interactive command"""

        # Security checks
        if not self._is_command_allowed(command):
            return CommandResponse(
                success=False,
                error_message=f"Command not allowed: {command.split()[0]}",
                execution_time=0.0,
            )

        if not self._check_path_restrictions(command):
            return CommandResponse(
                success=False,
                error_message="Command accesses restricted paths",
                execution_time=0.0,
            )

        start_time = time.time()

        try:
            # Prepare environment
            env = os.environ.copy()
            if environment:
                env.update(environment)

            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                exit_code = process.returncode

                return CommandResponse(
                    success=exit_code == 0,
                    exit_code=exit_code,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    execution_time=time.time() - start_time,
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return CommandResponse(
                    success=False,
                    error_message=f"Command timed out after {timeout} seconds",
                    execution_time=time.time() - start_time,
                )

        except Exception as e:
            return CommandResponse(
                success=False,
                error_message=f"Execution error: {str(e)}",
                execution_time=time.time() - start_time,
            )

    def _has_active_session(self) -> bool:
        """Check whether a live interactive session is already running."""

        if not self.current_session_id:
            return False

        session = self.active_sessions.get(self.current_session_id)
        if not session:
            self.current_session_id = None
            return False

        child = session.get("child")
        if child is None or not child.isalive():
            self._cleanup_session(self.current_session_id)
            return False

        return True

    def start_interactive_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, CommandResponse]:
        """Start an interactive command and return session ID"""

        # Security checks
        if not self._is_command_allowed(command):
            return "", CommandResponse(
                success=False,
                error_message=f"Command not allowed: {command.split()[0]}",
                execution_time=0.0,
            )

        if not self._check_path_restrictions(command):
            return "", CommandResponse(
                success=False,
                error_message="Command accesses restricted paths",
                execution_time=0.0,
            )

        self.cleanup_inactive_sessions()

        if self._has_active_session():
            active_session = self.active_sessions[self.current_session_id]
            return "", CommandResponse(
                success=False,
                stdout="",
                stderr="",
                execution_time=0.0,
                session_id=self.current_session_id,
                is_interactive=True,
                error_message=(
                    "An interactive session is already active. "
                    "Terminate the current session before starting a new one."
                ),
                command_executed=active_session.get("command"),
            )

        session_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            # Set up environment
            env = os.environ.copy()
            if environment:
                env.update(environment)

            # Parse the command into executable and arguments
            try:
                command_parts = shlex.split(command)
            except ValueError as exc:
                raise ValueError(f"Failed to parse command: {exc}") from exc

            if not command_parts:
                raise ValueError("Command cannot be empty")

            executable, *arguments = command_parts

            # Start interactive process using pexpect
            child = pexpect.spawn(
                executable,
                args=arguments,
                cwd=working_directory,
                env=env,
            )
            child.timeout = 1  # Short timeout for non-blocking reads

            # Store session info
            self.active_sessions = {
                session_id: {
                    "child": child,
                    "command": command,
                    "created_at": datetime.now().isoformat(),
                    "last_activity": datetime.now().isoformat(),
                    "working_directory": working_directory,
                }
            }
            self.current_session_id = session_id

            # Try to read initial output
            initial_output = ""
            try:
                initial_output = child.read_nonblocking(size=4096, timeout=0.5).decode(
                    "utf-8", errors="replace"
                )
            except (pexpect.TIMEOUT, pexpect.EOF):
                pass

            return session_id, CommandResponse(
                success=True,
                stdout=initial_output,
                execution_time=time.time() - start_time,
                session_id=session_id,
                is_interactive=True,
            )

        except Exception as e:
            return "", CommandResponse(
                success=False,
                error_message=f"Failed to start interactive command: {str(e)}",
                execution_time=time.time() - start_time,
            )

    def send_interactive_input(
        self, session_id: str, input_text: str, send_newline: bool = True
    ) -> CommandResponse:
        """Send input to an interactive command session"""

        if (
            session_id != self.current_session_id
            or session_id not in self.active_sessions
        ):
            return CommandResponse(
                success=False, error_message="Session not found", execution_time=0.0
            )

        start_time = time.time()
        session = self.active_sessions[session_id]
        child = session["child"]

        try:
            # Send input
            if send_newline:
                child.sendline(input_text)
            else:
                child.send(input_text)
            session["last_activity"] = datetime.now().isoformat()

            # Read response
            output = ""
            try:
                output = child.read_nonblocking(size=4096, timeout=1.0).decode(
                    "utf-8", errors="replace"
                )
            except (pexpect.TIMEOUT, pexpect.EOF) as e:
                if isinstance(e, pexpect.EOF):
                    # Process ended
                    self._cleanup_session(session_id)
                    return CommandResponse(
                        success=True,
                        stdout=output,
                        execution_time=time.time() - start_time,
                        session_id=session_id,
                        is_interactive=False,  # Session ended
                    )

            return CommandResponse(
                success=True,
                stdout=output,
                execution_time=time.time() - start_time,
                session_id=session_id,
                is_interactive=True,
            )

        except Exception as e:
            return CommandResponse(
                success=False,
                error_message=f"Error sending input: {str(e)}",
                execution_time=time.time() - start_time,
                session_id=session_id,
            )

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get information about an active session"""
        self.cleanup_inactive_sessions()
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id]
        return SessionInfo(
            session_id=session_id,
            command=session["command"],
            status="active" if session["child"].isalive() else "terminated",
            created_at=session["created_at"],
            last_activity=session["last_activity"],
        )

    def list_active_sessions(self) -> List[SessionInfo]:
        """List all active sessions"""
        self.cleanup_inactive_sessions()
        sessions = []
        for session_id, session_data in self.active_sessions.items():
            sessions.append(
                SessionInfo(
                    session_id=session_id,
                    command=session_data["command"],
                    status=(
                        "active" if session_data["child"].isalive() else "terminated"
                    ),
                    created_at=session_data["created_at"],
                    last_activity=session_data["last_activity"],
                )
            )
        return sessions

    def _cleanup_session(self, session_id: str):
        """Clean up a session"""
        if session_id in self.active_sessions:
            try:
                child = self.active_sessions[session_id]["child"]
                if child.isalive():
                    child.terminate()
                    child.wait()
            except Exception:
                pass
            del self.active_sessions[session_id]
            if self.current_session_id == session_id:
                self.current_session_id = None

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a specific session"""
        if session_id not in self.active_sessions:
            return False

        try:
            self._cleanup_session(session_id)
            return True
        except Exception:
            return False

    def cleanup_inactive_sessions(self):
        """Clean up terminated or inactive sessions"""
        inactive_sessions = []
        for session_id, session_data in list(self.active_sessions.items()):
            if not session_data["child"].isalive():
                inactive_sessions.append(session_id)

        for session_id in inactive_sessions:
            self._cleanup_session(session_id)

        if not self.active_sessions:
            self.current_session_id = None


# Global executor instance
command_executor = CommandExecutor()
