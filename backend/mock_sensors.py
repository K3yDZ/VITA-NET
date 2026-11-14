"""Server-side simulated sensor stream.

The frontend already simulates vitals client-side (frontend/js/mockData.js)
so the dashboard works with zero backend. This module exists so the
*architecture* also has a server-side live-sensor-stream path ready to go —
per the brief's note to keep this wired up even though the team's near-term
priority is manual/simulated values rather than a real device feed. Point
GET /api/astronauts/{id}/vitals/simulate at a real sensor gateway later by
replacing generate_reading()'s body; nothing else needs to change.
"""

import random
from models import VitalsReading

# One in-memory "last reading" per astronaut so values random-walk instead
# of jumping around independently on every request.
_last: dict[str, dict] = {}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def generate_reading(astronaut_id: str) -> VitalsReading:
    prev = _last.get(
        astronaut_id,
        {
            "heartRate": 68.0,
            "bpSys": 112.0,
            "bpDia": 72.0,
            "spo2": 98.0,
            "tempC": 36.6,
            "stressIndex": 20.0,
            "radiationMSv": random.uniform(0, 8),
        },
    )

    reading = {
        "heartRate": _clamp(prev["heartRate"] + random.uniform(-3, 3), 45, 150),
        "bpSys": _clamp(prev["bpSys"] + random.uniform(-2.5, 2.5), 85, 175),
        "bpDia": _clamp(prev["bpDia"] + random.uniform(-2, 2), 55, 115),
        "spo2": _clamp(prev["spo2"] + random.uniform(-0.6, 0.6), 88, 100),
        "tempC": _clamp(prev["tempC"] + random.uniform(-0.05, 0.05), 35.2, 39.2),
        "stressIndex": _clamp(prev["stressIndex"] + random.uniform(-4, 4), 0, 100),
        "radiationMSv": prev["radiationMSv"] + random.uniform(0.02, 0.05),
    }
    _last[astronaut_id] = reading
    return VitalsReading(**reading)
