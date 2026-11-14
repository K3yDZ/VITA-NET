"""pytest fixtures for VITA-NET backend tests."""
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables BEFORE importing main
os.environ['JWT_SECRET'] = 'test-secret-key-for-testing-minimum-32-chars-long'
os.environ['AUTH_REQUIRED'] = 'true'
os.environ['ALLOWED_ORIGINS'] = 'http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000'

from auth import create_jwt, decode_jwt
from main import app


@pytest.fixture(scope="session")
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI TestClient for integration tests."""
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def valid_token() -> str:
    """Create a valid JWT token for testing."""
    return create_jwt(sub="test-user", role="astronaut", exp_seconds=3600)


@pytest.fixture
def expired_token() -> str:
    """Create an expired JWT token for testing."""
    return create_jwt(sub="test-user", role="astronaut", exp_seconds=-1)


@pytest.fixture
def invalid_signature_token() -> str:
    """Create a token with invalid signature."""
    # Create a valid token first, then tamper with signature
    token = create_jwt(sub="test-user", role="astronaut", exp_seconds=3600)
    parts = token.split('.')
    # Corrupt the signature
    return f"{parts[0]}.{parts[1]}.invalid_signature"


@pytest.fixture
def malformed_token() -> str:
    """Create a malformed token (wrong number of parts)."""
    return "header.payload"  # Missing signature


@pytest.fixture
def auth_headers(valid_token: str) -> dict:
    """Authorization headers with valid token."""
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.fixture
def expired_auth_headers(expired_token: str) -> dict:
    """Authorization headers with expired token."""
    return {"Authorization": f"Bearer {expired_token}"}


@pytest.fixture
def invalid_auth_headers(invalid_signature_token: str) -> dict:
    """Authorization headers with invalid signature token."""
    return {"Authorization": f"Bearer {invalid_signature_token}"}


@pytest.fixture
def malformed_auth_headers(malformed_token: str) -> dict:
    """Authorization headers with malformed token."""
    return {"Authorization": f"Bearer {malformed_token}"}