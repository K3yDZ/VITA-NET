"""ISS position proxy (30s cache) + hazard/EVA simulation."""

import time
import random
import logging
import httpx

log = logging.getLogger(__name__)

_iss_cache: dict = {}
_ISS_TTL = 30  # seconds

# Fallback ISS position (over Atlantic) if API unreachable
_FALLBACK = {"lat": 28.5, "lon": -80.6, "ts": 0, "source": "fallback"}


def get_iss_position() -> dict:
    now = time.time()
    if _iss_cache.get("ts") and now - _iss_cache["ts"] < _ISS_TTL:
        return _iss_cache["data"]

    # Try open-notify, then wheretheiss
    for url in [
        "http://api.open-notify.org/iss-now.json",
        "https://api.wheretheiss.at/v1/satellites/25544",
    ]:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url)
                if r.status_code == 200:
                    j = r.json()
                    if "iss_position" in j:
                        data = {"lat": float(j["iss_position"]["latitude"]), "lon": float(j["iss_position"]["longitude"]), "ts": j.get("timestamp", int(now)), "source": "open-notify"}
                    elif "latitude" in j:
                        data = {"lat": float(j["latitude"]), "lon": float(j["longitude"]), "ts": int(now), "source": "wheretheiss"}
                    else:
                        continue
                    _iss_cache["ts"] = now
                    _iss_cache["data"] = data
                    return data
        except Exception as e:
            log.warning("ISS fetch %s failed: %s", url, e)
            continue

    # Return cached or fallback
    if _iss_cache.get("data"):
        return _iss_cache["data"]
    fb = {**_FALLBACK, "ts": int(now)}
    return fb


def get_hazards(seed: int = 0) -> list[dict]:
    """Simulated hazards — deterministic-ish per minute."""
    rnd = random.Random(int(time.time() / 60) + seed)
    hazards = []
    types = [
        ("micrometeoroid", "Micrometeoroid flux elevated"),
        ("radiation_storm", "Solar particle event — elevated flux"),
        ("debris_field", "Tracked debris conjunction"),
        ("thermal_stress", "Thermal cycling stress"),
    ]
    for key, label in types:
        if rnd.random() < 0.2:
            severity = "crit" if rnd.random() < 0.3 else "watch"
            hazards.append({"key": key, "label": label, "severity": severity, "distance_km": rnd.randint(10, 600)})
    return hazards
