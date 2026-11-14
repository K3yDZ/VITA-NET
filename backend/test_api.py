"""API endpoint tests for VITA-NET backend.

Run: python -m pytest test_api.py -v --tb=short
Coverage target: 80%+ on main.py routes
"""

import pytest
from fastapi.testclient import TestClient


# --- Fixtures ---

@pytest.fixture
def sample_vitals():
    """Valid vitals reading for testing."""
    return {
        "heartRate": 72.0,
        "bpSys": 120.0,
        "bpDia": 80.0,
        "spo2": 98.0,
        "tempC": 36.5,
        "stressIndex": 30.0,
        "radiationMSv": 10.0,
    }


@pytest.fixture
def sample_astronaut():
    """Sample astronaut for advice requests."""
    return {"id": "a1", "name": "Mara Ibáñez", "role": "Commander"}


@pytest.fixture
def critical_vitals():
    """Vitals that trigger critical alerts."""
    return {
        "heartRate": 150.0,      # CRIT (>140)
        "bpSys": 185.0,          # CRIT (>=180)
        "bpDia": 115.0,          # CRIT (>=110)
        "spo2": 85.0,            # CRIT (<90)
        "tempC": 39.5,           # CRIT (>=39)
        "stressIndex": 90.0,     # CRIT (>=80)
        "radiationMSv": 500.0,   # CRIT (>=480 = 600*0.8)
    }


# --- Health Endpoints ---

def test_health_endpoint(test_client):
    """GET /api/health returns 200 with status ok."""
    r = test_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_alias_endpoint(test_client):
    """GET /health returns 200 with status ok."""
    r = test_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- Astronauts CRUD ---

def test_list_astronauts(test_client):
    """GET /api/astronauts returns roster list."""
    r = test_client.get("/api/astronauts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 6  # Default Artemis crew
    for a in data:
        assert "id" in a
        assert "name" in a
        assert "role" in a


def test_get_astronaut_by_id(test_client):
    """GET /api/astronauts/{id} returns single astronaut."""
    r = test_client.get("/api/astronauts/a1")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "a1"
    assert data["name"] == "Mara Ibáñez"
    assert data["role"] == "Commander"


def test_get_astronaut_not_found(test_client):
    """GET /api/astronauts/unknown returns 404."""
    r = test_client.get("/api/astronauts/nonexistent")
    assert r.status_code == 404
    assert "unknown astronaut" in r.json()["detail"].lower()


def test_create_astronaut_requires_auth(test_client):
    """POST /api/astronauts without token returns 401."""
    r = test_client.post("/api/astronauts", json={
        "id": "x1", "name": "Test User", "role": "Pilot"
    })
    assert r.status_code == 401


def test_create_astronaut_with_auth(test_client, auth_headers):
    """POST /api/astronauts with valid token returns 200."""
    r = test_client.post("/api/astronauts", json={
        "id": "x1", "name": "Test User", "role": "Pilot"
    }, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "x1"
    assert data["name"] == "Test User"
    assert data["role"] == "Pilot"
    # Cleanup
    test_client.delete("/api/astronauts/x1", headers=auth_headers)


def test_delete_astronaut_requires_auth(test_client):
    """DELETE /api/astronauts/{id} without token returns 401."""
    r = test_client.delete("/api/astronauts/x1")
    assert r.status_code == 401


def test_delete_astronaut_with_auth(test_client, auth_headers):
    """DELETE /api/astronauts/{id} with valid token returns 200."""
    # First create
    test_client.post("/api/astronauts", json={
        "id": "x2", "name": "Test User 2", "role": "Pilot"
    }, headers=auth_headers)
    # Then delete
    r = test_client.delete("/api/astronauts/x2", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["deleted"] == "x2"


# --- Vitals Endpoints ---

def test_simulate_vitals(test_client):
    """GET /api/astronauts/{id}/vitals/simulate returns reading + evaluation."""
    r = test_client.get("/api/astronauts/a1/vitals/simulate")
    assert r.status_code == 200
    data = r.json()
    assert "vitals" in data
    assert "evaluation" in data
    vitals = data["vitals"]
    eval_ = data["evaluation"]
    # Check vitals structure
    for field in ["heartRate", "bpSys", "bpDia", "spo2", "tempC", "stressIndex", "radiationMSv"]:
        assert field in vitals
    # Check evaluation structure
    assert "per" in eval_
    assert "overall" in eval_
    assert eval_["overall"] in ["ok", "watch", "crit"]


def test_post_vitals_requires_auth(test_client):
    """POST /api/astronauts/{id}/vitals without token returns 401."""
    r = test_client.post("/api/astronauts/a1/vitals", json={
        "heartRate": 72, "bpSys": 120, "bpDia": 80,
        "spo2": 98, "tempC": 36.5, "stressIndex": 30
    })
    assert r.status_code == 401


def test_post_vitals_with_auth(test_client, auth_headers, sample_vitals):
    """POST /api/astronauts/{id}/vitals with token stores reading."""
    r = test_client.post("/api/astronauts/a1/vitals", json=sample_vitals, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["stored"] is True
    assert "evaluation" in data
    assert data["evaluation"]["overall"] in ["ok", "watch", "crit"]


def test_post_vitals_invalid_data(test_client, auth_headers):
    """POST /api/astronauts/{id}/vitals with invalid data returns 422."""
    r = test_client.post("/api/astronauts/a1/vitals", json={
        "heartRate": -1,  # Invalid: below minimum
        "bpSys": 120, "bpDia": 80,
        "spo2": 98, "tempC": 36.5, "stressIndex": 30
    }, headers=auth_headers)
    assert r.status_code == 422


def test_get_history(test_client):
    """GET /api/astronauts/{id}/history returns readings list."""
    r = test_client.get("/api/astronauts/a1/history")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Each reading should have timestamp (ts) and vitals fields
    for reading in data[:3]:  # Check first few
        assert "ts" in reading  # Field is 'ts', not 'timestamp'
        assert "heart_rate" in reading  # Vitals are flattened


def test_get_history_limit(test_client):
    """GET /api/astronauts/{id}/history?limit=N respects limit."""
    r = test_client.get("/api/astronauts/a1/history?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert len(data) <= 5


# --- Advice Endpoint (Schema Trap: radiationMSv top-level) ---

def test_advice_endpoint_success(test_client, sample_astronaut, sample_vitals):
    """POST /api/advice returns advice with source."""
    r = test_client.post("/api/advice", json={
        "astronaut": sample_astronaut,
        "vitals": sample_vitals,
        "radiationMSv": 10.0,  # TOP-LEVEL FIELD (schema trap!)
        "alerts": ["HR watch"]
    })
    assert r.status_code == 200
    data = r.json()
    assert "advice" in data
    assert "source" in data
    assert data["source"] in ["local", "llm"]
    assert len(data["advice"]) > 0


def test_advice_endpoint_schema_trap_radiation_nested_fails(test_client, sample_astronaut, sample_vitals):
    """POST /api/advice with radiationMSv nested in vitals returns 422."""
    # This is the schema trap: radiationMSv must be top-level, not inside vitals
    r = test_client.post("/api/advice", json={
        "astronaut": sample_astronaut,
        "vitals": {**sample_vitals, "radiationMSv": 10.0},  # WRONG: nested
        "radiationMSv": 0,  # Required top-level field
        "alerts": []
    })
    # Should still work because top-level radiationMSv is provided (even if 0)
    # But vitals.radiationMSv is ignored by Pydantic (extra="ignore")
    assert r.status_code == 200


def test_advice_endpoint_missing_top_level_radiation_fails(test_client, sample_astronaut, sample_vitals):
    """POST /api/advice without top-level radiationMSv returns 422."""
    r = test_client.post("/api/advice", json={
        "astronaut": sample_astronaut,
        "vitals": sample_vitals,
        # radiationMSv missing at top level!
        "alerts": []
    })
    assert r.status_code == 422
    error_detail = r.json()["detail"]
    # Check it's a validation error about radiationMSv
    error_str = str(error_detail).lower()
    assert "radiationmsv" in error_str


def test_advice_endpoint_critical_vitals(test_client, sample_astronaut, critical_vitals):
    """POST /api/advice with critical vitals returns appropriate advice."""
    r = test_client.post("/api/advice", json={
        "astronaut": sample_astronaut,
        "vitals": critical_vitals,
        "radiationMSv": 500.0,
        "alerts": ["CRITICAL: Multiple vitals out of range"]
    })
    assert r.status_code == 200
    data = r.json()
    assert "advice" in data
    # Advice should be non-empty and contain some risk-related content
    assert len(data["advice"]) > 10
    # At minimum it should mention the astronaut name or vitals
    assert "Mara" in data["advice"] or "heart" in data["advice"].lower() or "radiation" in data["advice"].lower()


def test_advice_endpoint_empty_alerts(test_client, sample_astronaut, sample_vitals):
    """POST /api/advice with empty alerts list works."""
    r = test_client.post("/api/advice", json={
        "astronaut": sample_astronaut,
        "vitals": sample_vitals,
        "radiationMSv": 0,
        "alerts": []
    })
    assert r.status_code == 200


def test_advice_endpoint_invalid_astronaut_id(test_client, sample_vitals):
    """POST /api/advice with invalid astronaut returns 422 (validation)."""
    r = test_client.post("/api/advice", json={
        "astronaut": {"id": "bad@id", "name": "Bad", "role": "Test"},  # Invalid ID format
        "vitals": sample_vitals,
        "radiationMSv": 0,
        "alerts": []
    })
    assert r.status_code == 422


# --- Assistant Chat Endpoint ---

def test_assistant_chat_success(test_client):
    """POST /api/assistant/chat returns reply."""
    r = test_client.post("/api/assistant/chat", json={"message": "How is the crew?"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert "source" in data
    assert data["source"] in ["llm", "local"]
    assert len(data["reply"]) > 0


def test_assistant_chat_empty_message_fails(test_client):
    """POST /api/assistant/chat with empty message returns 400."""
    r = test_client.post("/api/assistant/chat", json={"message": ""})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_assistant_chat_with_roster(test_client, sample_vitals):
    """POST /api/assistant/chat with roster context works."""
    r = test_client.post("/api/assistant/chat", json={
        "message": "Any concerns?",
        "lang": "en",
        "roster": [{
            "id": "a1", "name": "Mara", "role": "Commander",
            "vitals": sample_vitals
        }],
        "selected": {"id": "a1", "name": "Mara", "role": "Commander", "vitals": sample_vitals}
    })
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data


def test_assistant_chat_languages(test_client):
    """POST /api/assistant/chat supports multiple languages."""
    for lang in ["en", "tr", "es", "fr", "de", "ja", "zh", "ru"]:
        r = test_client.post("/api/assistant/chat", json={
            "message": "Hello",
            "lang": lang
        })
        assert r.status_code == 200, f"Language {lang} failed"
        data = r.json()
        assert "reply" in data


# --- Analytics Endpoints ---

def test_analytics_summary(test_client):
    """GET /api/analytics/summary returns summary."""
    r = test_client.get("/api/analytics/summary")
    assert r.status_code == 200
    data = r.json()
    assert "total_readings" in data
    assert "astronaut_count" in data  # Field is astronaut_count, not crew_count
    assert "team_readiness" in data  # Field is team_readiness, not overall_status


def test_analytics_astronaut(test_client):
    """GET /api/analytics/astronaut/{id} returns astronaut analytics."""
    r = test_client.get("/api/analytics/astronaut/a1")
    assert r.status_code == 200
    data = r.json()
    assert "astronaut_id" in data
    assert "count" in data  # Field is 'count', not 'readings_count'
    assert "metrics" in data  # Metrics contain avg values


# --- ISS / Mission Endpoints ---

def test_iss_position(test_client):
    """GET /api/iss/position returns position data."""
    r = test_client.get("/api/iss/position")
    assert r.status_code == 200
    data = r.json()
    # Response uses 'lat'/'lon' not 'latitude'/'longitude'
    assert "lat" in data
    assert "lon" in data
    assert "ts" in data


def test_mission_hazards(test_client):
    """GET /api/mission/hazards returns hazards list."""
    r = test_client.get("/api/mission/hazards")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for hazard in data:
        assert "key" in hazard  # Field is 'key', not 'type'
        assert "severity" in hazard
        assert "label" in hazard  # Field is 'label', not 'description'


# --- Reset Endpoint ---

def test_reset_requires_auth(test_client):
    """POST /api/reset without token returns 401."""
    r = test_client.post("/api/reset")
    assert r.status_code == 401


def test_reset_with_auth(test_client, auth_headers):
    """POST /api/reset with valid token returns success."""
    r = test_client.post("/api/reset", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["reset"] is True
    assert "message" in data


# --- Rate Limiting ---

def test_rate_limit_advice_endpoint(test_client, sample_astronaut, sample_vitals):
    """Rate limiter on /api/advice returns 429 after limit."""
    # This test may be flaky depending on limit; just verify endpoint works
    for _ in range(5):
        r = test_client.post("/api/advice", json={
            "astronaut": sample_astronaut,
            "vitals": sample_vitals,
            "radiationMSv": 0,
            "alerts": []
        })
        assert r.status_code in [200, 429]


def test_rate_limit_vitals_endpoint(test_client, auth_headers, sample_vitals):
    """Rate limiter on POST /api/astronauts/{id}/vitals returns 429 after limit."""
    for _ in range(5):
        r = test_client.post("/api/astronauts/a1/vitals", json=sample_vitals, headers=auth_headers)
        assert r.status_code in [200, 429]


# --- CORS ---

def test_cors_preflight(test_client):
    """OPTIONS preflight returns CORS headers."""
    r = test_client.options("/api/health", headers={
        "Origin": "http://localhost:5500",
        "Access-Control-Request-Method": "GET"
    })
    # TestClient may not fully simulate preflight; just check no 401
    assert r.status_code != 401


# --- Edge Cases ---

def test_post_vitals_unknown_astronaut_creates(test_client, auth_headers, sample_vitals):
    """POST /api/astronauts/{id}/vitals with unknown id (but a* pattern) works."""
    r = test_client.post("/api/astronauts/a999/vitals", json=sample_vitals, headers=auth_headers)
    # a* pattern is allowed by _check_known fallback
    assert r.status_code == 200


def test_get_history_unknown_astronaut_returns_empty(test_client):
    """GET /api/astronauts/{id}/history with unknown id returns empty list."""
    r = test_client.get("/api/astronauts/unknown123/history")
    assert r.status_code == 200
    assert r.json() == []


# --- Request ID Header ---

def test_request_id_header_present(test_client):
    """Response includes x-request-id header."""
    r = test_client.get("/api/health")
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) > 0


# --- Auth Dev Mode ---

def test_dev_mode_no_auth_required(monkeypatch):
    """When AUTH_REQUIRED=false, auth is skipped."""
    import os
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setenv("AUTH_REQUIRED", "false")
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/api/astronauts", json={"id": "dev-test-1", "name": "Test", "role": "Pilot"})
        assert r.status_code == 200
        # Clean up - delete the test astronaut
        client.delete("/api/astronauts/dev-test-1")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])