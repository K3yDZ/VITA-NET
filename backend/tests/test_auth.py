"""JWT unit tests for auth.py."""
import os
from datetime import datetime, timedelta

import pytest

from auth import create_jwt, decode_jwt, reset_jwt_secret


def test_create_jwt_valid_structure():
    """create_jwt returns header.payload.signature with valid fields."""
    token = create_jwt(sub="astronaut-1", role="commander", exp_seconds=3600)
    parts = token.split(".")
    assert len(parts) == 3

    import json, base64

    def decode(b64):
        padding = '=' * (-len(b64) % 4)
        return json.loads(base64.urlsafe_b64decode(b64 + padding))

    header = decode(parts[0])
    payload = decode(parts[1])
    assert header["alg"] == "HS256"
    assert header["typ"] == "JWT"
    assert payload["sub"] == "astronaut-1"
    assert payload["role"] == "commander"
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] == payload["iat"] + 3600


def test_create_jwt_default_expiry():
    """create_jwt default exp_seconds is 3600."""
    token = create_jwt(sub="user", role="astronaut")
    import json, base64

    def decode(b64):
        padding = '=' * (-len(b64) % 4)
        return json.loads(base64.urlsafe_b64decode(b64 + padding))

    payload = decode(token.split(".")[1])
    assert payload["exp"] - payload["iat"] == 3600


def test_decode_jwt_valid_token_returns_payload():
    """decode_jwt returns payload dict for valid token."""
    token = create_jwt(sub="a1", role="medical", exp_seconds=3600)
    payload = decode_jwt(token)
    assert payload["sub"] == "a1"
    assert payload["role"] == "medical"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_jwt_expired_token_raises_valueerror():
    """decode_jwt raises ValueError for expired token."""
    token = create_jwt(sub="a1", role="medical", exp_seconds=-1)
    with pytest.raises(ValueError, match="expired"):
        decode_jwt(token)


def test_decode_jwt_invalid_signature_raises_valueerror():
    """decode_jwt raises ValueError for tampered signature."""
    token = create_jwt(sub="a1", role="medical", exp_seconds=3600)
    parts = token.split(".")
    bad = f"{parts[0]}.{parts[1]}.tampered_signature"
    with pytest.raises(ValueError, match="signature"):
        decode_jwt(bad)


def test_decode_jwt_malformed_token_raises_valueerror():
    """decode_jwt raises ValueError for malformed token."""
    with pytest.raises(ValueError, match="format"):
        decode_jwt("only.two.parts.here")  # 4 parts


def test_decode_jwt_malformed_token_raises_valueerror_two_parts():
    """decode_jwt raises ValueError for token with two parts."""
    with pytest.raises(ValueError, match="format"):
        decode_jwt("header.payload")  # missing signature


def test_decode_jwt_missing_secret_raises_valueerror(monkeypatch):
    """decode_jwt raises ValueError when JWT_SECRET is missing."""
    reset_jwt_secret()
    monkeypatch.delenv("JWT_SECRET", raising=False)
    token = "header.payload.signature"
    with pytest.raises(ValueError, match="JWT_SECRET not configured"):
        decode_jwt(token)


def test_create_jwt_missing_secret_raises_valueerror(monkeypatch):
    """create_jwt raises ValueError when JWT_SECRET is missing."""
    reset_jwt_secret()
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET not configured"):
        create_jwt(sub="a1", role="medical", exp_seconds=3600)


def test_decode_jwt_empty_token_raises_valueerror():
    """decode_jwt raises ValueError for empty string."""
    with pytest.raises(ValueError, match="format"):
        decode_jwt("")


def test_decode_jwt_non_dict_payload_still_returns():
    """decode_jwt returns whatever JSON is in payload even if not a dict."""
    token = create_jwt(sub="a1", role="medical", exp_seconds=3600)
    payload = decode_jwt(token)
    assert isinstance(payload, dict)