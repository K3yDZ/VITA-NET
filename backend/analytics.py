"""Analytics engine — averages, std dev, trend, anomaly detection, intervention suggestions."""

import math
import os
import database

ANOMALY_STD_MULTIPLIER = float(os.getenv("ANOMALY_STD_MULTIPLIER", "2.0"))
if ANOMALY_STD_MULTIPLIER <= 0:
    ANOMALY_STD_MULTIPLIER = 2.0


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg": None, "min": None, "max": None, "std": None, "trend": "stable"}
    n = len(values)
    avg = sum(values) / n
    mn, mx = min(values), max(values)
    variance = sum((x - avg) ** 2 for x in values) / n
    std = math.sqrt(variance)
    # Trend: compare first half avg vs second half avg
    if n >= 6:
        half = n // 2
        first_avg = sum(values[:half]) / half
        second_avg = sum(values[half:]) / (n - half)
        diff_ratio = (second_avg - first_avg) / (abs(first_avg) + 1e-9)
        if diff_ratio > 0.05:
            trend = "up"
        elif diff_ratio < -0.05:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"
    return {"count": n, "avg": round(avg, 2), "min": round(mn, 2), "max": round(mx, 2), "std": round(std, 2), "trend": trend}


def _is_anomaly(value: float, avg: float, std: float) -> bool:
    if std is None or std < 0.5:
        return False
    return abs(value - avg) > ANOMALY_STD_MULTIPLIER * std


def compute_astronaut_analytics(astronaut_id: str, limit: int = 1000) -> dict:
    rows = database.get_history(astronaut_id, limit)
    if not rows:
        return {"astronaut_id": astronaut_id, "count": 0, "metrics": {}, "interventions": []}

    # rows are dicts with keys: heart_rate, bp_sys, bp_dia, spo2, temp_c, stress_index, radiation_msv, hrv
    metric_map = {
        "heartRate": "heart_rate",
        "bpSys": "bp_sys",
        "bpDia": "bp_dia",
        "spo2": "spo2",
        "tempC": "temp_c",
        "stressIndex": "stress_index",
        "radiationMSv": "radiation_msv",
    }

    metrics = {}
    anomalies = []
    for label, col in metric_map.items():
        vals = [r[col] for r in rows if r.get(col) is not None]
        s = _stats(vals)
        # anomaly check on latest value
        latest = vals[-1] if vals else None
        is_anom = False
        if latest is not None and s["avg"] is not None and s["std"] is not None:
            is_anom = _is_anomaly(latest, s["avg"], s["std"])
            if is_anom:
                anomalies.append(label)
        s["anomaly"] = is_anom
        s["latest"] = round(latest, 2) if latest is not None else None
        metrics[label] = s

    # Intervention logic
    interventions = []
    hr = metrics.get("heartRate", {})
    spo2 = metrics.get("spo2", {})
    stress = metrics.get("stressIndex", {})
    rad = metrics.get("radiationMSv", {})

    if hr.get("anomaly") and spo2.get("anomaly"):
        interventions.append({"level": "crit", "message": "Heart rate and SpO₂ both anomalous — possible hypoxia or cardiac stress. Immediate check required."})
    elif hr.get("anomaly") and stress.get("avg") and stress["avg"] > 55:
        interventions.append({"level": "watch", "message": "Elevated heart rate with high stress — recommend rest and hydration."})
    if spo2.get("latest") is not None and spo2["latest"] < 95:
        interventions.append({"level": "crit" if spo2["latest"] < 90 else "watch", "message": f"SpO₂ at {spo2['latest']}% — check life-support and oxygen supply."})
    if rad.get("latest") is not None and rad["latest"] >= 50:
        interventions.append({"level": "crit" if rad["latest"] >= 480 else "watch", "message": f"Cumulative radiation {rad['latest']} mSv — review shielding protocol."})
    if hr.get("trend") == "up" and hr.get("avg") and hr["avg"] > 90:
        interventions.append({"level": "watch", "message": "Heart rate trending upward — monitor for fatigue or exertion."})
    if not interventions and not anomalies:
        interventions = []

    return {
        "astronaut_id": astronaut_id,
        "count": len(rows),
        "metrics": metrics,
        "anomalies": anomalies,
        "interventions": interventions,
    }


def compute_summary(limit_per_astronaut: int = 1000) -> dict:
    astronauts = database.list_astronauts()
    if not astronauts:
        # fallback to vitals_log distinct ids
        astronauts = [{"id": r["astronaut_id"]} for r in database.get_all_astronaut_ids()]

    all_metrics = {}
    all_interventions = []
    total_readings = 0

    for a in astronauts:
        aid = a["id"] if isinstance(a, dict) else a[0]
        data = compute_astronaut_analytics(aid, limit_per_astronaut)
        total_readings += data["count"]
        for k, v in data["metrics"].items():
            if k not in all_metrics:
                all_metrics[k] = {"avgs": [], "mins": [], "maxs": []}
            if v["avg"] is not None:
                all_metrics[k]["avgs"].append(v["avg"])
            if v["min"] is not None:
                all_metrics[k]["mins"].append(v["min"])
            if v["max"] is not None:
                all_metrics[k]["maxs"].append(v["max"])
        for iv in data["interventions"]:
            all_interventions.append({"astronaut_id": aid, **iv})

    # Aggregate across crew
    summary_metrics = {}
    for k, v in all_metrics.items():
        if v["avgs"]:
            summary_metrics[k] = {
                "avg": round(sum(v["avgs"]) / len(v["avgs"]), 2),
                "min": round(min(v["mins"]), 2) if v["mins"] else None,
                "max": round(max(v["maxs"]), 2) if v["maxs"] else None,
                "count": len(v["avgs"]),
            }

        # team readiness: 100 - avg stress (simple)
    avg_stress = None
    if "stressIndex" in summary_metrics:
        avg_stress = summary_metrics["stressIndex"]["avg"]
    team_readiness = round(max(0, 100 - (avg_stress or 30)), 1) if avg_stress is not None else 85.0
    # risk matrix simple
    risk_matrix = {}
    for k, v in summary_metrics.items():
        risk_matrix[k] = "watch" if v["avg"] and v["avg"] > 70 else "ok"
    return {
            "team_readiness": team_readiness,
            "risk_matrix": risk_matrix,
            "total_readings": total_readings,
        "astronaut_count": len(astronauts),
        "metrics": summary_metrics,
        "interventions": all_interventions,
    }
