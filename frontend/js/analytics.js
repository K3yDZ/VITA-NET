// analytics.js — frontend analytics panel renderer
// Backend /api/analytics/summary ve /api/analytics/astronaut/{id} verilerini gösterir

import { t } from "./i18n.js";
import { getBase } from "./api.js";

async function fetchAnalytics(url) {
  const base = await getBase();
  if (base === null) return null;
  try {
    const c = new AbortController();
    const id = setTimeout(() => c.abort(), 4000);
    const res = await fetch(`${base}${url}`, { signal: c.signal });
    clearTimeout(id);
    if (res.ok) return await res.json();
  } catch {}
  return null;
}

export async function fetchSummary() {
  return fetchAnalytics("/api/analytics/summary");
}
export async function fetchAstronautAnalytics(id) {
  return fetchAnalytics(`/api/analytics/astronaut/${id}`);
}

function trendArrow(trend) {
  if (trend === "up") return "↗";
  if (trend === "down") return "↘";
  return "→";
}
function trendColor(trend, metric) {
  // HR/stress/radiation up = bad, SpO2 down = bad — basit heuristic
  const badUp = ["heartRate", "stressIndex", "radiationMSv", "tempC"];
  const badDown = ["spo2"];
  if (badUp.includes(metric) && trend === "up") return "var(--status-watch)";
  if (badDown.includes(metric) && trend === "down") return "var(--status-watch)";
  return "var(--text-faint)";
}

export function renderAnalyticsPanel(container, data) {
if (!container || !data) {
    if (container) container.innerHTML = `<p style="color:var(--text-faint)">${t("analytics_empty")}</p>`;
    return;
  }
  const metrics = [
    { key: "heartRate", label: t("vital_heart_rate"), unit: "bpm" },
    { key: "bpSys", label: t("vital_bp") + " sys", unit: "mmHg" },
    { key: "spo2", label: t("vital_spo2"), unit: "%" },
    { key: "tempC", label: t("vital_temp"), unit: "°C" },
    { key: "stressIndex", label: t("vital_stress"), unit: "" },
    { key: "radiationMSv", label: t("vital_radiation"), unit: "mSv" },
  ];
  let html = `<div class="analytics-grid">`;
  for (const m of metrics) {
    const s = data.metrics?.[m.key];
    if (!s) continue;
    const anomalyBadge = s.anomaly ? `<span class="status-chip crit" style="font-size:0.65rem">${t("anomaly_label")}</span>` : "";
    const tr = s.trend ? `<span style="color:${trendColor(s.trend, m.key)}">${trendArrow(s.trend)}</span>` : "";
    html += `<div class="analytics-tile">
      <div style="font-size:0.7rem;color:var(--text-faint)">${m.label} ${tr} ${anomalyBadge}</div>
      <div class="mono" style="font-size:1.05rem;font-weight:600">${s.avg?.toFixed(1) ?? "—"}<span style="font-size:0.65rem;color:var(--text-faint)"> ${m.unit}</span></div>
      <div style="font-size:0.68rem;color:var(--text-faint)">${t("label_min")} ${s.min?.toFixed(1) ?? "—"} · ${t("label_max")} ${s.max?.toFixed(1) ?? "—"} · σ ${s.std?.toFixed(1) ?? "—"}</div>
    </div>`;
  }
  html += `</div>`;
  if (data.interventions?.length) {
    html += `<div style="margin-top:0.75rem;display:flex;flex-direction:column;gap:0.35rem">`;
    for (const iv of data.interventions) {
      html += `<div class="alert-row ${iv.level}"><span>${iv.message}</span></div>`;
    }
    html += `</div>`;
  } else if (data.metrics) {
    html += `<div style="margin-top:0.6rem;color:var(--status-ok);font-size:0.82rem">${t("all_metrics_nominal")}</div>`;
  }
  if (data.count !== undefined) {
    html += `<div style="margin-top:0.5rem;font-size:0.7rem;color:var(--text-faint)">${t("readings_analyzed", { n: String(data.count) })}</div>`;
  }
  container.innerHTML = html; 
}

export function renderRiskMatrix(container, data){
  if(!container||!data) return;
  const metrics=["heartRate","spo2","stressIndex","radiationMSv"];
  let html='<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:0.4rem;margin-bottom:0.6rem">';
  for(const k of metrics){
    const s=data.metrics?.[k];
    if(!s) continue;
    const sev=s.anomaly?"crit": s.trend==="up"&&(k==="heartRate"||k==="stressIndex")?"watch":"ok";
    const col=sev==="crit"?"var(--status-crit-bg)":sev==="watch"?"var(--status-watch-bg)":"var(--bg-panel-raised)";
    html+='<div style="background:'+col+';border:1px solid var(--line);border-radius:6px;padding:0.4rem"><div style="font-size:0.68rem;color:var(--text-faint)">'+k+' '+(s.trend||"")+'</div><div class="mono" style="font-size:0.85rem">'+(s.avg?.toFixed(1)||"—")+'</div></div>';
  }
  html+='</div>';
  container.insertAdjacentHTML("afterbegin", html);
}