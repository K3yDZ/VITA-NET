// thresholds.js — reference ranges and status evaluation for each vital.
//
// AUTO-GENERATED from thresholds-spec.json — DO NOT EDIT DIRECTLY.
// Run: python generate_thresholds.py
//
// Sourcing notes (see README.md "Reference values" for the longer version):
// - Heart rate / SpO2 / temperature: standard clinical reference ranges.
// - Blood pressure: WHO/ISH categories (the brief specifically asked for
//   WHO comparisons). Note the AHA's 2017 guideline uses a stricter,
//   lower-threshold scale — the numbers below are intentionally the WHO
//   ones, not the AHA ones.
// - Radiation: WHO does not publish astronaut radiation limits, so this
//   uses NASA's 2022 career effective-dose limit (600 mSv, all ages/sexes)
//   plus the NCRP's 50 mSv/yr terrestrial radiation-worker limit as an
//   intermediate "watch" reference.
// - Stress index: a simulated composite score for this prototype, not a
//   validated clinical measurement.
//
// STATUS is always one of "ok" | "watch" | "crit".

export const STATUS = { OK: "ok", WATCH: "watch", CRIT: "crit" };

export const RADIATION_WATCH_MSV = 50;
export const RADIATION_CAREER_LIMIT_MSV = 600;

export function evalHeartRate(bpm) {
  if (bpm < 40 || bpm > 140) return STATUS.CRIT;
  if (bpm < 50 || bpm > 100) return STATUS.WATCH;
  return STATUS.OK;
}

// WHO/ISH blood pressure categories (mmHg): optimal <120/80, normal
// 120-129/80-84, high-normal 130-139/85-89, grade 1 140-159/90-99,
// grade 2 160-179/100-109, grade 3 (crisis) >=180/>=110.
export function evalBloodPressure(sys, dia) {
  if (sys >= 180 || dia >= 110) return { status: STATUS.CRIT, stage: "grade3" };
  if (sys >= 160 || dia >= 100) return { status: STATUS.CRIT, stage: "grade2" };
  if (sys >= 140 || dia >= 90) return { status: STATUS.WATCH, stage: "grade1" };
  if (sys >= 130 || dia >= 85) return { status: STATUS.WATCH, stage: "high-normal" };
  if (sys < 90 || dia < 60) return { status: STATUS.WATCH, stage: "low" };
  return { status: STATUS.OK, stage: "normal" };
}

export function evalSpo2(pct) {
  if (pct < 90) return STATUS.CRIT;
  if (pct < 95) return STATUS.WATCH;
  return STATUS.OK;
}

export function evalTemp(celsius) {
  if (celsius >= 39 || celsius < 35) return STATUS.CRIT;
  if (celsius >= 37.8 || celsius < 36) return STATUS.WATCH;
  return STATUS.OK;
}

// radiationMSv: cumulative dose for the *current mission*, in mSv.
// watchLine mirrors the terrestrial radiation-worker annual limit (50 mSv)
// as an early-warning reference; careerLimit is NASA's 600 mSv standard.
export function evalRadiation(cumulativeMSv) {
  if (cumulativeMSv >= RADIATION_CAREER_LIMIT_MSV * 0.8) return STATUS.CRIT;
  if (cumulativeMSv >= RADIATION_WATCH_MSV) return STATUS.WATCH;
  return STATUS.OK;
}

// 0-100 simulated composite (see file header note).
export function evalStress(index) {
  if (index >= 80) return STATUS.CRIT;
  if (index >= 55) return STATUS.WATCH;
  return STATUS.OK;
}

export const REFS = {
  heartRate: { source: "Clinical HR 50-100 bpm", url: "https://www.who.int/health-topics" },
  bp: { source: "WHO/ISH 2024", url: "https://www.who.int/news-room/fact-sheets/detail/hypertension" },
  spo2: { source: "Clinical SpO2 95-100%", url: "https://www.who.int/health-topics" },
  temp: { source: "Clinical 36-37.8 C", url: "https://www.who.int/health-topics" },
  radiation: { source: "NASA 600 mSv career, NCRP 50 mSv/yr", url: "https://www.nasa.gov/humans-in-space" },
  stress: { source: "Simulated composite", url: "" },
};
export function explain(key){ return REFS[key] || null; }

const WORST = { ok: 0, watch: 1, crit: 2 };
export function worstStatus(...statuses) {
  return statuses.reduce((a, b) => (WORST[b] > WORST[a] ? b : a), STATUS.OK);
}

// Evaluate a full vitals reading and return per-metric status plus an
// overall roll-up used for the roster status chip.
export function evaluateVitals(v) {
  const bp = evalBloodPressure(v.bpSys, v.bpDia);
  const per = {
    heartRate: evalHeartRate(v.heartRate),
    bp: bp.status,
    bpStage: bp.stage,
    spo2: evalSpo2(v.spo2),
    temp: evalTemp(v.tempC),
    radiation: evalRadiation(v.radiationMSv),
    stress: evalStress(v.stressIndex),
  };
  const overall = worstStatus(per.heartRate, per.bp, per.spo2, per.temp, per.radiation, per.stress);
  return { per, overall };
}
