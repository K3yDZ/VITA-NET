import httpx, json, sqlite3, pathlib, sys

BASE = "http://localhost:8000"
ok = 0
fail = 0

def check(name, fn):
    global ok, fail
    try:
        fn()
        print(f"  PASS {name}")
        ok += 1
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        fail += 1

def test_health():
    r = httpx.get(f"{BASE}/api/health", timeout=5)
    assert r.status_code == 200 and r.json()["status"] == "ok"

def test_astronauts_list():
    r = httpx.get(f"{BASE}/api/astronauts", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 4, f"expected >=4 got {len(data)}"
    print(f"       roster: {len(data)} crew -> {[x['name'] for x in data[:3]]}...")

def test_create_astronaut():
    payload = {"id": "a_test99", "name": "Test Astro", "role": "Tester"}
    r = httpx.post(f"{BASE}/api/astronauts", json=payload, timeout=5)
    assert r.status_code == 200
    # verify appears in list
    r2 = httpx.get(f"{BASE}/api/astronauts", timeout=5)
    ids = [x["id"] for x in r2.json()]
    assert "a_test99" in ids

def test_post_vitals():
    for i in range(5):
        payload = {"heartRate": 72+i, "bpSys": 118, "bpDia": 78, "spo2": 98.0, "tempC": 36.6, "stressIndex": 20, "radiationMSv": 5.0+i*0.1, "hrv": 55}
        r = httpx.post(f"{BASE}/api/astronauts/a1/vitals", json=payload, timeout=5)
        assert r.status_code == 200
        assert r.json()["stored"] is True

def test_history():
    r = httpx.get(f"{BASE}/api/astronauts/a1/history?limit=3", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 3, f"history len {len(data)}"
    print(f"       history latest hr={data[0].get('heart_rate')}")

def test_analytics_summary():
    r = httpx.get(f"{BASE}/api/analytics/summary", timeout=5)
    assert r.status_code == 200
    j = r.json()
    assert "metrics" in j and "total_readings" in j
    print(f"       analytics summary: {j['total_readings']} readings, metrics={list(j['metrics'].keys())[:3]}")

def test_analytics_astronaut():
    r = httpx.get(f"{BASE}/api/analytics/astronaut/a1", timeout=5)
    assert r.status_code == 200
    j = r.json()
    assert "metrics" in j
    # after 5 vitals, should have computed stats
    assert j["count"] >= 5
    print(f"       a1 analytics count={j['count']} anomalies={j.get('anomalies')} interventions={len(j.get('interventions',[]))}")

def test_iss():
    r = httpx.get(f"{BASE}/api/iss/position", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "lat" in j and "lon" in j
    print(f"       iss: lat={j['lat']:.2f} lon={j['lon']:.2f} source={j.get('source')}")

def test_hazards():
    r = httpx.get(f"{BASE}/api/mission/hazards", timeout=5)
    assert r.status_code == 200
    print(f"       hazards: {r.json()}")

def test_advice_nominal():
    payload = {"astronaut": {"id": "a1", "name": "Mara Ibanez", "role": "Commander"}, "vitals": {"heartRate": 68, "bpSys": 112, "bpDia": 72, "spo2": 98.0, "tempC": 36.6, "stressIndex": 20, "hrv": 60, "radiationMSv": 5}, "radiationMSv": 5, "alerts": []}
    r = httpx.post(f"{BASE}/api/advice", json=payload, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert "advice" in j and "source" in j
    print(f"       advice nominal: {j['advice'][:80]}... source={j['source']}")

def test_advice_crit():
    payload = {"astronaut": {"id": "a1", "name": "Mara Ibanez", "role": "Commander"}, "vitals": {"heartRate": 145, "bpSys": 185, "bpDia": 115, "spo2": 88.0, "tempC": 39.2, "stressIndex": 85, "hrv": 20, "radiationMSv": 55}, "radiationMSv": 55, "alerts": ["HR crit 145", "BP grade3", "SpO2 low 88%", "Radiation watch 55 mSv"]}
    r = httpx.post(f"{BASE}/api/advice", json=payload, timeout=10)
    assert r.status_code == 200
    print(f"       advice crit: {r.json()['advice'][:80]}...")

def test_frontend():
    r = httpx.get(f"{BASE}/", timeout=5)
    assert r.status_code == 200
    html = r.text
    checks = ["google_translate_element", "voice-mic-btn", "alerts-drawer", "roster-search", "dashboard-extra.css", "detail-tabs", "add-astronaut-modal"]
    try:
        import httpx as _httpx2
        _app_js = _httpx2.get(f"{BASE}/js/app.js", timeout=5).text
    except Exception:
        _app_js = ""
    _combined = html + _app_js
    for _imp in ["voice.js", "mission.js", "analytics.js"]:
        if _imp not in _app_js:
            checks.append(_imp)
    missing = [c for c in checks if c not in _combined]
    assert not missing, f"missing in index.html: {missing}"
    print(f"       frontend index: {len(html)} bytes, all markers present")

def test_frontend_assets():
    for path in ["js/app.js", "js/voice.js", "js/mission.js", "js/analytics.js", "js/mockData.js", "css/dashboard-extra.css"]:
        r = httpx.get(f"{BASE}/{path}", timeout=5)
        assert r.status_code == 200 and len(r.content) > 500, f"{path} bad {r.status_code} len={len(r.content) if r else 0}"

def test_db_tables():
    db = pathlib.Path(__file__).parent / "vitanet.db"
    conn = sqlite3.connect(str(db))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    for t in ["astronauts", "vitals_log", "alerts_log", "mission_events"]:
        assert t in tables, f"table {t} missing, got {tables}"
    print(f"       db tables: {tables}")

def test_delete_astronaut():
    r = httpx.delete(f"{BASE}/api/astronauts/a_test99", timeout=5)
    assert r.status_code == 200

print("=== VITA-NET drive test ===")
for name, fn in [
    ("GET /api/health", test_health),
    ("GET /api/astronauts", test_astronauts_list),
    ("POST /api/astronauts", test_create_astronaut),
    ("POST /api/astronauts/a1/vitals x5", test_post_vitals),
    ("GET /api/astronauts/a1/history", test_history),
    ("GET /api/analytics/summary", test_analytics_summary),
    ("GET /api/analytics/astronaut/a1", test_analytics_astronaut),
    ("GET /api/iss/position", test_iss),
    ("GET /api/mission/hazards", test_hazards),
    ("POST /api/advice nominal", test_advice_nominal),
    ("POST /api/advice crit", test_advice_crit),
    ("GET / frontend", test_frontend),
    ("GET / frontend assets", test_frontend_assets),
    ("DB tables", test_db_tables),
    ("DELETE /api/astronauts/a_test99", test_delete_astronaut),
]:
    check(name, fn)

print(f"\n=== {ok} passed, {fail} failed ===")
sys.exit(1 if fail else 0)
