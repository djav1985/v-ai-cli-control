#!/usr/bin/env python3
"""
Simple test script to verify the V-AI CLI Control API is working correctly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from main import app

# Create test client
client = TestClient(app)

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
    response = client.post("/execute", json={
        "command": "echo 'Hello World'",
        "command_type": "simple"
    })
    assert response.status_code == 403  # Forbidden without API key
    print("✓ API key protection working")
    
    # Test with mock API key
    headers = {"Authorization": "Bearer test-api-key"}
    response = client.post("/execute", json={
        "command": "echo 'Hello World'",
        "command_type": "simple"
    }, headers=headers)
    
    # Should work even without API_KEY set in environment (no restriction)
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")

def test_system_status():
    """Test system status endpoint"""
    print("\nTesting system status...")
    headers = {"Authorization": "Bearer test-api-key"}
    response = client.get("/system/status", headers=headers)
    
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
    headers = {"Authorization": "Bearer test-api-key"}
    
    # Test invalid command (empty)
    response = client.post("/execute", json={
        "command": "",
        "command_type": "simple"
    }, headers=headers)
    assert response.status_code == 422  # Validation error
    print("✓ Empty command validation working")
    
    # Test dangerous command pattern
    response = client.post("/execute", json={
        "command": "rm -rf / && echo 'dangerous'",
        "command_type": "simple"
    }, headers=headers)
    # Should either be blocked or restricted
    print(f"Dangerous command response: {response.status_code}")

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