"""Server-side mirror of frontend/js/thresholds.js.

AUTO-GENERATED from thresholds-spec.json — DO NOT EDIT DIRECTLY.
Run: python generate_thresholds.py

Sourcing is identical to the frontend file: WHO/ISH blood pressure
categories, NASA's 2022 600 mSv career radiation limit with a 50 mSv/yr
watch line, standard clinical ranges for heart rate/SpO2/temperature, and
a simulated (non-clinical) stress index.
"""

from models import VitalsReading

RADIATION_WATCH_MSV = 50
RADIATION_CAREER_LIMIT_MSV = 600

REFS = {
    "heartRate": {"source": "Clinical HR 50-100 bpm", "url": "https://www.who.int/health-topics"},
    "bp": {"source": "WHO/ISH 2024", "url": "https://www.who.int/news-room/fact-sheets/detail/hypertension"},
    "spo2": {"source": "Clinical SpO2 95-100%", "url": "https://www.who.int/health-topics"},
    "temp": {"source": "Clinical 36-37.8 C", "url": "https://www.who.int/health-topics"},
    "radiation": {"source": "NASA 600 mSv career, NCRP 50 mSv/yr", "url": "https://www.nasa.gov/humans-in-space"},
    "stress": {"source": "Simulated composite", "url": ""},
}

def explain(key: str) -> dict | None:
    return REFS.get(key)

STATUS_ORDER = {"ok": 0, "watch": 1, "crit": 2}

def worst(*statuses: str) -> str:
    return max(statuses, key=lambda s: STATUS_ORDER[s])

def eval_heart_rate(bpm: float) -> str:
    if bpm < 40 or bpm > 140:
        return "crit"
    if bpm < 50 or bpm > 100:
        return "watch"
    return "ok"

def eval_blood_pressure(sys: float, dia: float) -> tuple[str, str]:
    if sys >= 180 or dia >= 110:
        return "crit", "grade3"
    if sys >= 160 or dia >= 100:
        return "crit", "grade2"
    if sys >= 140 or dia >= 90:
        return "watch", "grade1"
    if sys >= 130 or dia >= 85:
        return "watch", "high-normal"
    if sys < 90 or dia < 60:
        return "watch", "low"
    else:
        return "ok", "normal"

def eval_spo2(pct: float) -> str:
    if pct < 90:
        return "crit"
    if pct < 95:
        return "watch"
    return "ok"

def eval_temp(celsius: float) -> str:
    if celsius >= 39 or celsius < 35:
        return "crit"
    if celsius >= 37.8 or celsius < 36:
        return "watch"
    return "ok"

def eval_radiation(cumulative_msv: float) -> str:
    if cumulative_msv >= RADIATION_CAREER_LIMIT_MSV * 0.8:
        return "crit"
    if cumulative_msv >= RADIATION_WATCH_MSV:
        return "watch"
    return "ok"

def eval_stress(index: float) -> str:
    if index >= 80:
        return "crit"
    if index >= 55:
        return "watch"
    return "ok"

def evaluate_vitals(v: VitalsReading) -> dict:
    bp_status, bp_stage = eval_blood_pressure(v.bpSys, v.bpDia)
    per = {
        "heartRate": eval_heart_rate(v.heartRate),
        "bp": bp_status,
        "bpStage": bp_stage,
        "spo2": eval_spo2(v.spo2),
        "temp": eval_temp(v.tempC),
        "radiation": eval_radiation(v.radiationMSv),
        "stress": eval_stress(v.stressIndex),
    }
    overall = worst(per["heartRate"], per["bp"], per["spo2"], per["temp"], per["radiation"], per["stress"])
    return {"per": per, "overall": overall}
