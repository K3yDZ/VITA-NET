// advisor.js — the "hybrid" health advisor.
//
// 1. buildAlerts() and inferMood() are instant, local, rule-based, and
//    never fail — they're what keeps the dashboard useful with zero
//    backend and zero network.
// 2. getAdvice() tries the backend's /api/advice (rule engine + optional
//    Claude call) for a more personalized note, but always falls back to
//    a local templated tip on any error/timeout so the UI never hangs or
//    shows a broken state — see api.js.
//
// Mood/emotional read-out is an illustrative heuristic (heart-rate
// deviation + a simulated HRV-like composite + stress index), not a
// validated psychological or medical measurement. Treat it as a hook to
// swap in a real model later, not as a diagnosis.

import { t } from "./i18n.js";
const COUNTERMEASURE_MAP={radiation:"Move to shielded area",stress:"Breathing 4-7-8",heartRate:"Hydrate & rest",bp:"Rest seated 5 min",spo2:"Check O2 supply",temp:"Cool environment"};
import { evaluateVitals, RADIATION_WATCH_MSV, RADIATION_CAREER_LIMIT_MSV, STATUS } from "./thresholds.js";
import { requestAdvice } from "./api.js";

function triageNextActions(level){
  if(level==="crit") return ["Immediate return + O2 check","Alert flight surgeon"];
  if(level==="watch") return ["Schedule check within 30 min","Recheck in 10 min"];
  return ["Observe"];
}
export function buildAlerts(astronaut) {
  const v = astronaut.vitals;
  const { per } = evaluateVitals({ ...v, radiationMSv: astronaut.radiationMSv });
  const alerts = [];
  const name = astronaut.name;

  if (per.heartRate === STATUS.CRIT || per.heartRate === STATUS.WATCH) {
    const key = v.heartRate > 100 ? "alert_hr_high" : "alert_hr_low";
    alerts.push({ level: per.heartRate, nextActions: triageNextActions(per.heartRate), text: t(key, { name, value: Math.round(v.heartRate) }) });
  }
  if (per.bp !== STATUS.OK) {
    alerts.push({
      level: per.bp, nextActions: triageNextActions(per.bp),
      text: t("alert_bp_high", { name, stage: per.bpStage, value: `${Math.round(v.bpSys)}/${Math.round(v.bpDia)}` }),
    });
  }
  if (per.spo2 !== STATUS.OK) {
    alerts.push({ level: per.spo2, nextActions: triageNextActions(per.spo2), text: t("alert_spo2_low", { name, value: v.spo2.toFixed(1) }) });
  }
  if (astronaut.radiationMSv >= RADIATION_CAREER_LIMIT_MSV * 0.8) {
    alerts.push({ level: STATUS.CRIT, nextActions: triageNextActions(STATUS.CRIT), text: t("alert_radiation_crit", { name, value: Math.round(astronaut.radiationMSv) }) });
  } else if (astronaut.radiationMSv >= RADIATION_WATCH_MSV) {
    alerts.push({ level: STATUS.WATCH, nextActions: triageNextActions(STATUS.WATCH), text: t("alert_radiation_watch", { name, value: Math.round(astronaut.radiationMSv) }) });
  }
  if (per.stress !== STATUS.OK) {
    alerts.push({ level: per.stress, nextActions: triageNextActions(per.stress), text: t("alert_stress_high", { name, value: Math.round(v.stressIndex) }) });
  }
  if (alerts.length === 0) {
    alerts.push({ level: STATUS.OK, nextActions: triageNextActions(STATUS.OK), text: t("alert_all_clear") });
  }
  return alerts;
}

// Simple, transparent scoring — not a clinical model. High deviation from
// a calm baseline + low HRV-composite + high stress reads as "anxious";
// high deviation + high HRV-composite reads as "excited"; and so on.
export function inferMood(v) {
  const hrDeviation = v.heartRate - 70; // rough resting baseline
  const calmness = v.hrv; // higher = calmer, per our simulated composite
  const stress = v.stressIndex;

  if (stress >= 70 && calmness < 40) return "mood_anxious";
  if (stress >= 55) return "mood_stressed";
  if (hrDeviation > 15 && calmness >= 50) return "mood_excited";
  if (hrDeviation < -8 && stress < 30) return "mood_fatigued";
  if (calmness >= 55 && stress < 35) return "mood_calm";
  return "mood_focused";
}

function localTip(astronaut) {
  const v = astronaut.vitals;
  const { per } = evaluateVitals({ ...v, radiationMSv: astronaut.radiationMSv });
  if (astronaut.radiationMSv >= RADIATION_WATCH_MSV) return t("tip_shelter");
  if (per.stress !== STATUS.OK && per.heartRate !== STATUS.OK) return t("tip_rest");
  if (per.heartRate !== STATUS.OK && per.spo2 === STATUS.OK) return t("tip_hydrate");
  let base; if (astronaut.radiationMSv >= RADIATION_WATCH_MSV) base=t("tip_shelter"); else if (per.stress !== STATUS.OK && per.heartRate !== STATUS.OK) base=t("tip_rest"); else if (per.heartRate !== STATUS.OK && per.spo2 === STATUS.OK) base=t("tip_hydrate"); else if (per.stress === STATUS.OK && per.heartRate === STATUS.OK && per.spo2 === STATUS.OK) base=t("tip_positive"); else base=t("tip_checkin"); const key=per.radiation!=="ok"?"radiation":per.stress!=="ok"?"stress":per.heartRate!=="ok"?"heartRate":per.spo2!=="ok"?"spo2":per.temp!=="ok"?"temp":per.bp!=="ok"?"bp":null; const cm=key?COUNTERMEASURE_MAP[key]:null; return cm? base+" \u2022 "+cm: base;
}

// Returns { text, source: "local" | "llm" }. Never throws.
export async function getAdvice(astronaut) {
  const alerts = buildAlerts(astronaut);
  const { hrv: _hrv, ...restVitals } = astronaut.vitals;
  const vitalsPayload = { ...restVitals };
  try {
    const remote = await requestAdvice({
      astronaut: { id: astronaut.id, name: astronaut.name, role: astronaut.role },
      vitals: vitalsPayload,
      radiationMSv: astronaut.radiationMSv,
      alerts: alerts.map((a) => a.text),
    });
    if (remote?.advice) return { text: remote.advice, source: remote.source ?? "llm" };
  } catch {
    // silent fallback — this is expected whenever the backend isn't running
  }
  return { text: localTip(astronaut), source: "local" };
}
