#!/usr/bin/env python3
"""
Demo script showing various V-AI CLI Control API usage examples.
This demonstrates how a GPT could interact with the system.
"""

import requests
import json
import time

# Configuration
API_BASE = "http://localhost:8000"
API_KEY = "test-api-key"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def print_response(response):
    """Pretty print API response"""
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print("-" * 50)


def demo_simple_commands():
    """Demonstrate simple command execution"""
    print("=== SIMPLE COMMANDS DEMO ===\n")

    commands = ["whoami", "pwd", "ls -la", "df -h", "free -h", "uptime"]

    for cmd in commands:
        print(f"Executing: {cmd}")
        response = requests.post(
            f"{API_BASE}/execute",
            headers=HEADERS,
            json={"command": cmd, "command_type": "simple"},
        )
        print_response(response)


def demo_interactive_session():
    """Demonstrate interactive command session"""
    print("=== INTERACTIVE SESSION DEMO ===\n")

    # Start interactive Python session
    print("Starting interactive Python session...")
    response = requests.post(
        f"{API_BASE}/execute",
        headers=HEADERS,
        json={"command": "python3", "command_type": "interactive"},
    )
    print_response(response)

    if response.status_code == 200 and response.json().get("success"):
        session_id = response.json().get("session_id")

        # Send Python commands
        python_commands = [
            "print('Hello from interactive Python!')",
            "x = 2 + 2",
            "print(f'2 + 2 = {x}')",
            "import os",
            "print(f'Current directory: {os.getcwd()}')",
            "exit()",
        ]

        for cmd in python_commands:
            print(f"Sending to Python: {cmd}")
            response = requests.post(
                f"{API_BASE}/interactive/{session_id}",
                headers=HEADERS,
                json={"session_id": session_id, "input_text": cmd},
            )
            print_response(response)
            time.sleep(0.5)


def demo_system_monitoring():
    """Demonstrate system status monitoring"""
    print("=== SYSTEM MONITORING DEMO ===\n")

    print("Getting system status...")
    response = requests.get(f"{API_BASE}/system/status", headers=HEADERS)
    print_response(response)

    print("Getting health status...")
    response = requests.get(f"{API_BASE}/health", headers=HEADERS)
    print_response(response)


def demo_session_management():
    """Demonstrate session management"""
    print("=== SESSION MANAGEMENT DEMO ===\n")

    # Start a session
    print("Starting a cat session...")
    response = requests.post(
        f"{API_BASE}/execute",
        headers=HEADERS,
        json={"command": "cat", "command_type": "interactive"},
    )
    print_response(response)

    if response.status_code == 200 and response.json().get("success"):
        session_id = response.json().get("session_id")

        # List sessions
        print("Listing all sessions...")
        response = requests.get(f"{API_BASE}/sessions", headers=HEADERS)
        print_response(response)

        # Get specific session info
        print(f"Getting info for session {session_id}...")
        response = requests.get(f"{API_BASE}/sessions/{session_id}", headers=HEADERS)
        print_response(response)

        # Send some input
        print("Sending input to cat...")
        response = requests.post(
            f"{API_BASE}/interactive/{session_id}",
            headers=HEADERS,
            json={"session_id": session_id, "input_text": "Hello from cat session!"},
        )
        print_response(response)

        # Use yes/no quick command
        print("Sending 'yes' using quick command...")
        response = requests.post(
            f"{API_BASE}/quick-commands/yes-no?session_id={session_id}&answer=true",
            headers=HEADERS,
        )
        print_response(response)

        # Terminate session
        print(f"Terminating session {session_id}...")
        response = requests.delete(f"{API_BASE}/sessions/{session_id}", headers=HEADERS)
        print_response(response)


def demo_security_features():
    """Demonstrate security features"""
    print("=== SECURITY FEATURES DEMO ===\n")

    # Test without API key
    print("Testing request without API key (should fail)...")
    response = requests.post(
        f"{API_BASE}/execute", json={"command": "whoami", "command_type": "simple"}
    )
    print_response(response)

    # Test dangerous command
    print("Testing dangerous command (should be blocked)...")
    response = requests.post(
        f"{API_BASE}/execute",
        headers=HEADERS,
        json={"command": "rm -rf / && echo dangerous", "command_type": "simple"},
    )
    print_response(response)

    # Test empty command
    print("Testing empty command (should fail validation)...")
    response = requests.post(
        f"{API_BASE}/execute",
        headers=HEADERS,
        json={"command": "", "command_type": "simple"},
    )
    print_response(response)


if __name__ == "__main__":
    print("V-AI CLI Control API Demo")
    print("=" * 50)
    print("This demonstrates how a GPT can interact with the system")
    print("=" * 50)

    try:
        # Check if server is running
        response = requests.get(f"{API_BASE}/health", headers=HEADERS)
        if response.status_code != 200:
            print("Error: API server is not running or not accessible")
            print("Please start the server with: python3 main.py")
            exit(1)

        print("✓ API server is running\n")

        demo_simple_commands()
        demo_system_monitoring()
        demo_session_management()
        demo_interactive_session()
        demo_security_features()

        print("\n" + "=" * 50)
        print("Demo completed successfully!")
        print("The API is ready for GPT integration.")

    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API server")
        print("Please start the server with: python3 main.py")
    except Exception as e:
        print(f"Error: {e}")
