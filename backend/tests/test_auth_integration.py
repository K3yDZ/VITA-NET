"""Integration tests for JWTAuthMiddleware in main.py."""
import pytest


def test_health_no_auth(test_client):
    """GET /api/health requires no auth -> 200."""
    r = test_client.get("/api/health")
    assert r.status_code == 200


def test_health_alias_no_auth(test_client):
    """GET /health requires no auth -> 200."""
    r = test_client.get("/health")
    assert r.status_code == 200


def test_list_astronauts_no_auth(test_client):
    """GET /api/astronauts requires no auth -> 200."""
    r = test_client.get("/api/astronauts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_astronaut_by_id_no_auth(test_client):
    """GET /api/astronauts/{id} requires no auth -> 200."""
    r = test_client.get("/api/astronauts/a1")
    assert r.status_code == 200


def test_create_astronaut_requires_auth_no_token(test_client):
    """POST /api/astronauts without token -> 401."""
    r = test_client.post("/api/astronauts", json={
        "id": "x1", "name": "Test User", "role": "Pilot"
    })
    assert r.status_code == 401


def test_create_astronaut_requires_auth_valid_token(test_client, auth_headers):
    """POST /api/astronauts with valid token -> 200."""
    r = test_client.post("/api/astronauts", json={
        "id": "x1", "name": "Test User", "role": "Pilot"
    }, headers=auth_headers)
    assert r.status_code == 200


def test_delete_astronaut_requires_auth_no_token(test_client):
    """DELETE /api/astronauts/{id} without token -> 401."""
    r = test_client.delete("/api/astronauts/x1")
    assert r.status_code == 401


def test_delete_astronaut_requires_auth_valid_token(test_client, auth_headers):
    """DELETE /api/astronauts/{id} with valid token -> 200."""
    r = test_client.delete("/api/astronauts/x1", headers=auth_headers)
    assert r.status_code == 200


def test_post_vitals_requires_auth_no_token(test_client):
    """POST /api/astronauts/{id}/vitals without token -> 401."""
    r = test_client.post("/api/astronauts/a1/vitals", json={
        "heartRate": 72, "bpSys": 120, "bpDia": 80,
        "spo2": 98, "tempC": 36.5, "stressIndex": 30
    })
    assert r.status_code == 401


def test_reset_requires_auth_no_token(test_client):
    """POST /api/reset without token -> 401."""
    r = test_client.post("/api/reset")
    assert r.status_code == 401


def test_reset_requires_auth_valid_token(test_client, auth_headers):
    """POST /api/reset with valid token -> 200."""
    r = test_client.post("/api/reset", headers=auth_headers)
    assert r.status_code == 200


def test_reset_requires_auth_expired_token(test_client, expired_auth_headers):
    """POST /api/reset with expired token -> 401."""
    r = test_client.post("/api/reset", headers=expired_auth_headers)
    assert r.status_code == 401


def test_reset_requires_auth_invalid_signature(test_client, invalid_auth_headers):
    """POST /api/reset with invalid signature token -> 401."""
    r = test_client.post("/api/reset", headers=invalid_auth_headers)
    assert r.status_code == 401


def test_reset_requires_auth_malformed_token(test_client, malformed_auth_headers):
    """POST /api/reset with malformed token -> 401."""
    r = test_client.post("/api/reset", headers=malformed_auth_headers)
    assert r.status_code == 401


def test_advice_no_auth(test_client):
    """POST /api/advice requires no auth -> 200."""
    r = test_client.post("/api/advice", json={
        "astronaut": {"id": "a1", "name": "Mara", "role": "Commander"},
        "vitals": {"heartRate": 72, "bpSys": 120, "bpDia": 80,
                   "spo2": 98, "tempC": 36.5, "stressIndex": 30},
        "radiationMSv": 0, "alerts": []
    })
    assert r.status_code == 200


def test_assistant_chat_no_auth(test_client):
    """POST /api/assistant/chat requires no auth -> 200."""
    r = test_client.post("/api/assistant/chat", json={"message": "hello"})
    assert r.status_code == 200


def test_iss_position_no_auth(test_client):
    """GET /api/iss/position requires no auth -> 200."""
    r = test_client.get("/api/iss/position")
    assert r.status_code == 200


def test_mission_hazards_no_auth(test_client):
    """GET /api/mission/hazards requires no auth -> 200."""
    r = test_client.get("/api/mission/hazards")
    assert r.status_code == 200


def test_analytics_summary_no_auth(test_client):
    """GET /api/analytics/summary requires no auth -> 200."""
    r = test_client.get("/api/analytics/summary")
    assert r.status_code == 200


def test_analytics_astronaut_no_auth(test_client):
    """GET /api/analytics/astronaut/{id} requires no auth -> 200."""
    r = test_client.get("/api/analytics/astronaut/a1")
    assert r.status_code == 200


def test_missing_bearer_prefix(test_client):
    """Authorization header without Bearer prefix -> 401."""
    r = test_client.post("/api/reset", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401


def test_authorization_header_missing(test_client):
    """No Authorization header -> 401."""
    r = test_client.post("/api/reset")
    assert r.status_code == 401


def test_static_files_no_auth(test_client):
    """Static files are exempt from auth -> 200 or 404."""
    # CSS files should be exempt (return 404 since they don't exist, not 401)
    r = test_client.get("/css/style.css")
    assert r.status_code != 401  # Should not be blocked by auth

    r = test_client.get("/js/app.js")
    assert r.status_code != 401


def test_root_no_auth(test_client):
    """Root path / is exempt from auth."""
    r = test_client.get("/")
    # Either 200 (if frontend mounted) or 404, but not 401
    assert r.status_code != 401


def test_dev_mode_no_auth_required(monkeypatch):
    """When AUTH_REQUIRED=false, auth is skipped."""
    import os
    from fastapi.testclient import TestClient
    from main import app

    # Create a fresh client with AUTH_REQUIRED=false
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/api/astronauts", json={"id": "dev-test-1", "name": "Test", "role": "Pilot"})
        assert r.status_code == 200  # Should succeed without auth
        # Clean up - delete the test astronaut
        client.delete("/api/astronauts/dev-test-1")


def test_decode_jwt_generic_exception(monkeypatch):
    """Test decode_jwt raises ValueError when JWT_SECRET missing."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from auth import decode_jwt, reset_jwt_secret
    reset_jwt_secret()
    with pytest.raises(ValueError, match="JWT_SECRET not configured"):
        decode_jwt("any.token.here")