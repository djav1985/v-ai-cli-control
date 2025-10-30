#!/usr/bin/env python3
"""
Simple test script to verify the V-AI CLI Control API is working correctly.
"""

import sys
import os

from fastapi.testclient import TestClient
import main
from executor import CommandExecutor

API_KEY_VALUE = "test-api-key"
os.environ.setdefault("API_KEY", API_KEY_VALUE)
main.API_KEY = API_KEY_VALUE

# Create test client
client = TestClient(main.app)
HEADERS = {"Authorization": f"Bearer {API_KEY_VALUE}"}


def test_environment_command_restrictions_whitespace_handling():
    """Ensure environment lists are stripped and filtered."""

    original_allowed = os.environ.get("ALLOWED_COMMANDS")
    original_restricted = os.environ.get("RESTRICTED_PATHS")

    try:
        os.environ["ALLOWED_COMMANDS"] = "ls, pwd"
        os.environ["RESTRICTED_PATHS"] = "/etc "

        executor = CommandExecutor()

        assert executor._is_command_allowed("pwd") is True
        assert executor._check_path_restrictions("cat /etc/passwd") is False
    finally:
        if original_allowed is None:
            os.environ.pop("ALLOWED_COMMANDS", None)
        else:
            os.environ["ALLOWED_COMMANDS"] = original_allowed

        if original_restricted is None:
            os.environ.pop("RESTRICTED_PATHS", None)
        else:
            os.environ["RESTRICTED_PATHS"] = original_restricted


def test_health_check():
    """Test the health check endpoint"""
    print("Testing health check...")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✓ Health check passed")


def test_simple_command():
    """Test simple command execution"""
    print("\nTesting simple command execution...")

    # Test without API key (should fail)
    response = client.post(
        "/execute", json={"command": "echo 'Hello World'", "command_type": "simple"}
    )
    assert response.status_code == 403  # Forbidden without API key
    print("✓ API key protection working")

    # Test with mock API key
    response = client.post(
        "/execute",
        json={"command": "echo 'Hello World'", "command_type": "simple"},
        headers=HEADERS,
    )

    # Should work even without API_KEY set in environment (no restriction)
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")


def test_system_status():
    """Test system status endpoint"""
    print("\nTesting system status...")
    response = client.get("/system/status", headers=HEADERS)

    print(f"Response status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"System uptime: {data.get('uptime')}")
        print(f"Active sessions: {data.get('active_sessions')}")
        print("✓ System status working")
    else:
        print(f"System status failed: {response.json()}")


def test_input_validation():
    """Test input validation"""
    print("\nTesting input validation...")
    # Test invalid command (empty)
    response = client.post(
        "/execute", json={"command": "", "command_type": "simple"}, headers=HEADERS
    )
    assert response.status_code == 422  # Validation error
    print("✓ Empty command validation working")

    # Test dangerous command pattern
    response = client.post(
        "/execute",
        json={"command": "rm -rf / && echo 'dangerous'", "command_type": "simple"},
        headers=HEADERS,
    )
    # Should either be blocked or restricted
    print(f"Dangerous command response: {response.status_code}")


def test_interactive_command_with_arguments_launches():
    """Interactive commands with arguments should start successfully."""

    start_response = client.post(
        "/execute",
        json={"command": "python3 -i", "command_type": "interactive"},
        headers=HEADERS,
    )
    assert start_response.status_code == 200
    start_data = start_response.json()
    assert start_data["success"] is True
    session_id = start_data["session_id"]
    assert session_id

    try:
        exit_response = client.post(
            f"/interactive/{session_id}",
            json={"session_id": session_id, "input_text": "exit()"},
            headers=HEADERS,
        )
        assert exit_response.status_code == 200
        exit_data = exit_response.json()
        if exit_data.get("is_interactive"):
            delete_response = client.delete(
                f"/sessions/{session_id}", headers=HEADERS
            )
            assert delete_response.status_code == 200
    finally:
        client.delete(f"/sessions/{session_id}", headers=HEADERS)


def test_rejects_separator_after_safe_command():
    """Ensure commands starting with safe verbs still reject separators."""

    response = client.post(
        "/execute",
        json={"command": "ls; echo hacked", "command_type": "simple"},
        headers=HEADERS,
    )
    assert response.status_code == 422
    detail = response.json().get("detail", [])
    assert any("dangerous pattern" in item.get("msg", "") for item in detail)


def test_single_interactive_session_limit():
    """Ensure only one interactive session can run at a time."""
    print("\nTesting single interactive session enforcement...")

    start_response = client.post(
        "/execute",
        json={"command": "python3 -i", "command_type": "interactive"},
        headers=HEADERS,
    )
    assert start_response.status_code == 200
    start_data = start_response.json()
    assert start_data["success"] is True
    session_id = start_data["session_id"]
    assert session_id

    second_response = client.post(
        "/execute",
        json={"command": "python3 -i", "command_type": "interactive"},
        headers=HEADERS,
    )
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["success"] is False
    assert session_id == second_data.get("session_id")
    assert "already active" in second_data.get("error_message", "").lower()

    close_response = client.post(
        f"/interactive/{session_id}",
        json={"session_id": session_id, "input_text": "exit()"},
        headers=HEADERS,
    )
    assert close_response.status_code == 200
    close_data = close_response.json()
    if close_data["is_interactive"]:
        delete_response = client.delete(f"/sessions/{session_id}", headers=HEADERS)
        assert delete_response.status_code == 200

    restart_response = client.post(
        "/execute",
        json={"command": "python3 -i", "command_type": "interactive"},
        headers=HEADERS,
    )
    assert restart_response.status_code == 200
    restart_data = restart_response.json()
    assert restart_data["success"] is True
    new_session_id = restart_data["session_id"]
    assert new_session_id != session_id

    cleanup_response = client.post(
        f"/interactive/{new_session_id}",
        json={"session_id": new_session_id, "input_text": "exit()"},
        headers=HEADERS,
    )
    assert cleanup_response.status_code == 200
    cleanup_data = cleanup_response.json()
    if cleanup_data["is_interactive"]:
        delete_response = client.delete(f"/sessions/{new_session_id}", headers=HEADERS)
        assert delete_response.status_code == 200


def test_interactive_input_without_newline():
    """Ensure interactive input can be sent without automatically appending a newline."""

    start_response = client.post(
        "/execute",
        json={"command": "python3 -i -q", "command_type": "interactive"},
        headers=HEADERS,
    )
    assert start_response.status_code == 200
    start_data = start_response.json()
    assert start_data["success"] is True
    session_id = start_data["session_id"]
    assert session_id

    execute_output = ""
    exit_data = None
    try:
        partial_response = client.post(
            f"/interactive/{session_id}",
            json={
                "session_id": session_id,
                "input_text": "print('A')",
                "send_newline": False,
            },
            headers=HEADERS,
        )
        assert partial_response.status_code == 200
        partial_data = partial_response.json()
        assert partial_data["success"] is True
        assert partial_data["is_interactive"] is True
        partial_output = partial_data.get("stdout", "")
        assert "A\n" not in partial_output
        assert partial_output.rstrip().endswith("print('A')")

        execute_response = client.post(
            f"/interactive/{session_id}",
            json={
                "session_id": session_id,
                "input_text": "",
                "send_newline": True,
            },
            headers=HEADERS,
        )
        assert execute_response.status_code == 200
        execute_data = execute_response.json()
        assert execute_data["success"] is True
        assert execute_data["is_interactive"] is True
        execute_output = execute_data.get("stdout", "")
    finally:
        exit_response = client.post(
            f"/interactive/{session_id}",
            json={"session_id": session_id, "input_text": "exit()", "send_newline": True},
            headers=HEADERS,
        )
        if exit_response.status_code == 200:
            exit_data = exit_response.json()
            if exit_data.get("is_interactive"):
                delete_response = client.delete(f"/sessions/{session_id}", headers=HEADERS)
                assert delete_response.status_code == 200

    assert "A" in (execute_output + (exit_data.get("stdout", "") if exit_data else ""))


if __name__ == "__main__":
    print("V-AI CLI Control API Tests")
    print("=" * 40)

    try:
        test_health_check()
        test_simple_command()
        test_system_status()
        test_input_validation()

        print("\n" + "=" * 40)
        print("All tests completed!")

    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)
