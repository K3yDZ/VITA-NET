#!/usr/bin/env python3
"""
generate_thresholds.py — Reads thresholds-spec.json and generates:
  - frontend/js/thresholds.js
  - backend/thresholds.py

Run from project root: python generate_thresholds.py
"""

import json
import sys
from pathlib import Path

SPEC_PATH = Path("thresholds-spec.json")
JS_OUT = Path("frontend/js/thresholds.js")
PY_OUT = Path("backend/thresholds.py")


def load_spec():
    with SPEC_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def generate_js(spec):
    lines = [
        "// thresholds.js — reference ranges and status evaluation for each vital.",
        "//",
        "// AUTO-GENERATED from thresholds-spec.json — DO NOT EDIT DIRECTLY.",
        "// Run: python generate_thresholds.py",
        "//",
        "// Sourcing notes (see README.md \"Reference values\" for the longer version):",
        "// - Heart rate / SpO2 / temperature: standard clinical reference ranges.",
        "// - Blood pressure: WHO/ISH categories (the brief specifically asked for",
        "//   WHO comparisons). Note the AHA's 2017 guideline uses a stricter,",
        "//   lower-threshold scale — the numbers below are intentionally the WHO",
        "//   ones, not the AHA ones.",
        "// - Radiation: WHO does not publish astronaut radiation limits, so this",
        "//   uses NASA's 2022 career effective-dose limit (600 mSv, all ages/sexes)",
        "//   plus the NCRP's 50 mSv/yr terrestrial radiation-worker limit as an",
        "//   intermediate \"watch\" reference.",
        "// - Stress index: a simulated composite score for this prototype, not a",
        "//   validated clinical measurement.",
        "//",
        "// STATUS is always one of \"ok\" | \"watch\" | \"crit\".",
        "",
        "export const STATUS = { OK: \"ok\", WATCH: \"watch\", CRIT: \"crit\" };",
        "",
    ]

    # Constants
    consts = spec["constants"]
    lines.append(f"export const RADIATION_WATCH_MSV = {consts['RADIATION_WATCH_MSV']};")
    lines.append(f"export const RADIATION_CAREER_LIMIT_MSV = {consts['RADIATION_CAREER_LIMIT_MSV']};")
    lines.append("")

    # Functions
    lines.append("export function evalHeartRate(bpm) {")
    hr = spec["thresholds"]["heartRate"]
    lines.append(f"  if (bpm < {hr['critLow']} || bpm > {hr['critHigh']}) return STATUS.CRIT;")
    lines.append(f"  if (bpm < {hr['watchLow']} || bpm > {hr['watchHigh']}) return STATUS.WATCH;")
    lines.append("  return STATUS.OK;")
    lines.append("}")
    lines.append("")

    # Blood Pressure
    lines.append("// WHO/ISH blood pressure categories (mmHg): optimal <120/80, normal")
    lines.append("// 120-129/80-84, high-normal 130-139/85-89, grade 1 140-159/90-99,")
    lines.append("// grade 2 160-179/100-109, grade 3 (crisis) >=180/>=110.")
    lines.append("export function evalBloodPressure(sys, dia) {")
    bp = spec["thresholds"]["bloodPressure"]
    for stage in bp["stages"]:
        cond = []
        if "sysMin" in stage:
            cond.append(f"sys >= {stage['sysMin']}")
        if "diaMin" in stage:
            cond.append(f"dia >= {stage['diaMin']}")
        if "sysMax" in stage:
            cond.append(f"sys < {stage['sysMax']}")
        if "diaMax" in stage:
            cond.append(f"dia < {stage['diaMax']}")
        if cond:
            lines.append(f"  if ({' || '.join(cond)}) return {{ status: STATUS.{stage['status'].upper()}, stage: \"{stage['stage']}\" }};")
        else:
            lines.append(f"  return {{ status: STATUS.{stage['status'].upper()}, stage: \"{stage['stage']}\" }};")
    lines.append("}")
    lines.append("")

    # SpO2
    spo2 = spec["thresholds"]["spo2"]
    lines.append("export function evalSpo2(pct) {")
    lines.append(f"  if (pct < {spo2['critLow']}) return STATUS.CRIT;")
    lines.append(f"  if (pct < {spo2['watchLow']}) return STATUS.WATCH;")
    lines.append("  return STATUS.OK;")
    lines.append("}")
    lines.append("")

    # Temperature
    temp = spec["thresholds"]["temperature"]
    lines.append("export function evalTemp(celsius) {")
    lines.append(f"  if (celsius >= {temp['critHigh']} || celsius < {temp['critLow']}) return STATUS.CRIT;")
    lines.append(f"  if (celsius >= {temp['watchHigh']} || celsius < {temp['watchLow']}) return STATUS.WATCH;")
    lines.append("  return STATUS.OK;")
    lines.append("}")
    lines.append("")

    # Radiation
    rad = spec["thresholds"]["radiation"]
    lines.append("// radiationMSv: cumulative dose for the *current mission*, in mSv.")
    lines.append("// watchLine mirrors the terrestrial radiation-worker annual limit (50 mSv)")
    lines.append("// as an early-warning reference; careerLimit is NASA's 600 mSv standard.")
    lines.append("export function evalRadiation(cumulativeMSv) {")
    lines.append(f"  if (cumulativeMSv >= RADIATION_CAREER_LIMIT_MSV * {rad['critRatio']}) return STATUS.CRIT;")
    lines.append(f"  if (cumulativeMSv >= RADIATION_WATCH_MSV) return STATUS.WATCH;")
    lines.append("  return STATUS.OK;")
    lines.append("}")
    lines.append("")

    # Stress
    stress = spec["thresholds"]["stress"]
    lines.append("// 0-100 simulated composite (see file header note).")
    lines.append("export function evalStress(index) {")
    lines.append(f"  if (index >= {stress['critLow']}) return STATUS.CRIT;")
    lines.append(f"  if (index >= {stress['watchLow']}) return STATUS.WATCH;")
    lines.append("  return STATUS.OK;")
    lines.append("}")
    lines.append("")

    # REFS
    lines.append("export const REFS = {")
    for key, ref in spec["refs"].items():
        url = f'"{ref["url"]}"' if ref["url"] else '""'
        lines.append(f'  {key}: {{ source: "{ref["source"]}", url: {url} }},')
    lines.append("};")
    lines.append("export function explain(key){ return REFS[key] || null; }")
    lines.append("")

    # WORST
    lines.append("const WORST = { ok: 0, watch: 1, crit: 2 };")
    lines.append("export function worstStatus(...statuses) {")
    lines.append("  return statuses.reduce((a, b) => (WORST[b] > WORST[a] ? b : a), STATUS.OK);")
    lines.append("}")
    lines.append("")

    # evaluateVitals
    lines.append("// Evaluate a full vitals reading and return per-metric status plus an")
    lines.append("// overall roll-up used for the roster status chip.")
    lines.append("export function evaluateVitals(v) {")
    lines.append("  const bp = evalBloodPressure(v.bpSys, v.bpDia);")
    lines.append("  const per = {")
    lines.append("    heartRate: evalHeartRate(v.heartRate),")
    lines.append("    bp: bp.status,")
    lines.append("    bpStage: bp.stage,")
    lines.append("    spo2: evalSpo2(v.spo2),")
    lines.append("    temp: evalTemp(v.tempC),")
    lines.append("    radiation: evalRadiation(v.radiationMSv),")
    lines.append("    stress: evalStress(v.stressIndex),")
    lines.append("  };")
    lines.append("  const overall = worstStatus(per.heartRate, per.bp, per.spo2, per.temp, per.radiation, per.stress);")
    lines.append("  return { per, overall };")
    lines.append("}")

    return "\n".join(lines) + "\n"


def generate_py(spec):
    lines = [
        '"""Server-side mirror of frontend/js/thresholds.js.',
        '',
        'AUTO-GENERATED from thresholds-spec.json — DO NOT EDIT DIRECTLY.',
        'Run: python generate_thresholds.py',
        '',
        'Sourcing is identical to the frontend file: WHO/ISH blood pressure',
        "categories, NASA's 2022 600 mSv career radiation limit with a 50 mSv/yr",
        'watch line, standard clinical ranges for heart rate/SpO2/temperature, and',
        'a simulated (non-clinical) stress index.',
        '"""',
        '',
        'from models import VitalsReading',
        '',
    ]

    # Constants
    consts = spec["constants"]
    lines.append(f"RADIATION_WATCH_MSV = {consts['RADIATION_WATCH_MSV']}")
    lines.append(f"RADIATION_CAREER_LIMIT_MSV = {consts['RADIATION_CAREER_LIMIT_MSV']}")
    lines.append("")

    # REFS
    lines.append("REFS = {")
    for key, ref in spec["refs"].items():
        url = f'"{ref["url"]}"' if ref["url"] else '""'
        lines.append(f'    "{key}": {{"source": "{ref["source"]}", "url": {url}}},')
    lines.append("}")
    lines.append("")

    lines.append('def explain(key: str) -> dict | None:')
    lines.append('    return REFS.get(key)')
    lines.append("")

    lines.append("STATUS_ORDER = {\"ok\": 0, \"watch\": 1, \"crit\": 2}")
    lines.append("")
    lines.append("def worst(*statuses: str) -> str:")
    lines.append('    return max(statuses, key=lambda s: STATUS_ORDER[s])')
    lines.append("")

    # Functions
    hr = spec["thresholds"]["heartRate"]
    lines.append("def eval_heart_rate(bpm: float) -> str:")
    lines.append(f"    if bpm < {hr['critLow']} or bpm > {hr['critHigh']}:")
    lines.append('        return "crit"')
    lines.append(f"    if bpm < {hr['watchLow']} or bpm > {hr['watchHigh']}:")
    lines.append('        return "watch"')
    lines.append('    return "ok"')
    lines.append("")

    # Blood Pressure
    lines.append("def eval_blood_pressure(sys: float, dia: float) -> tuple[str, str]:")
    bp = spec["thresholds"]["bloodPressure"]
    for stage in bp["stages"]:
        cond = []
        if "sysMin" in stage:
            cond.append(f"sys >= {stage['sysMin']}")
        if "diaMin" in stage:
            cond.append(f"dia >= {stage['diaMin']}")
        if "sysMax" in stage:
            cond.append(f"sys < {stage['sysMax']}")
        if "diaMax" in stage:
            cond.append(f"dia < {stage['diaMax']}")
        if cond:
            lines.append(f"    if {' or '.join(cond)}:")
        else:
            lines.append("    else:")
        lines.append(f'        return "{stage["status"]}", "{stage["stage"]}"')
    lines.append("")

    # SpO2
    spo2 = spec["thresholds"]["spo2"]
    lines.append("def eval_spo2(pct: float) -> str:")
    lines.append(f"    if pct < {spo2['critLow']}:")
    lines.append('        return "crit"')
    lines.append(f"    if pct < {spo2['watchLow']}:")
    lines.append('        return "watch"')
    lines.append('    return "ok"')
    lines.append("")

    # Temperature
    temp = spec["thresholds"]["temperature"]
    lines.append("def eval_temp(celsius: float) -> str:")
    lines.append(f"    if celsius >= {temp['critHigh']} or celsius < {temp['critLow']}:")
    lines.append('        return "crit"')
    lines.append(f"    if celsius >= {temp['watchHigh']} or celsius < {temp['watchLow']}:")
    lines.append('        return "watch"')
    lines.append('    return "ok"')
    lines.append("")

    # Radiation
    rad = spec["thresholds"]["radiation"]
    lines.append("def eval_radiation(cumulative_msv: float) -> str:")
    lines.append(f"    if cumulative_msv >= RADIATION_CAREER_LIMIT_MSV * {rad['critRatio']}:")
    lines.append('        return "crit"')
    lines.append("    if cumulative_msv >= RADIATION_WATCH_MSV:")
    lines.append('        return "watch"')
    lines.append('    return "ok"')
    lines.append("")

    # Stress
    stress = spec["thresholds"]["stress"]
    lines.append("def eval_stress(index: float) -> str:")
    lines.append(f"    if index >= {stress['critLow']}:")
    lines.append('        return "crit"')
    lines.append(f"    if index >= {stress['watchLow']}:")
    lines.append('        return "watch"')
    lines.append('    return "ok"')
    lines.append("")

    # evaluate_vitals
    lines.append("def evaluate_vitals(v: VitalsReading) -> dict:")
    lines.append("    bp_status, bp_stage = eval_blood_pressure(v.bpSys, v.bpDia)")
    lines.append("    per = {")
    lines.append('        "heartRate": eval_heart_rate(v.heartRate),')
    lines.append('        "bp": bp_status,')
    lines.append('        "bpStage": bp_stage,')
    lines.append('        "spo2": eval_spo2(v.spo2),')
    lines.append('        "temp": eval_temp(v.tempC),')
    lines.append('        "radiation": eval_radiation(v.radiationMSv),')
    lines.append('        "stress": eval_stress(v.stressIndex),')
    lines.append("    }")
    lines.append('    overall = worst(per["heartRate"], per["bp"], per["spo2"], per["temp"], per["radiation"], per["stress"])')
    lines.append('    return {"per": per, "overall": overall}')

    return "\n".join(lines) + "\n"


def main():
    if not SPEC_PATH.exists():
        print(f"Spec not found: {SPEC_PATH}", file=sys.stderr)
        sys.exit(1)

    spec = load_spec()

    js_code = generate_js(spec)
    py_code = generate_py(spec)

    JS_OUT.write_text(js_code, encoding="utf-8")
    PY_OUT.write_text(py_code, encoding="utf-8")

    print(f"Generated {JS_OUT}")
    print(f"Generated {PY_OUT}")


if __name__ == "__main__":
    main()