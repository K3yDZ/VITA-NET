// mission.js — ISS position + hazard simulation + EVA state + Emergency Simulator
// ISS konumu: backend /api/iss/position proxy üzerinden (30s cache)
// Tehlikeler ve EVA: tamamen simüle, backend /api/mission/state

import { t } from "./i18n.js";
import { getBase } from "./api.js";

console.log("[mission.js] Module loaded, bridging EMERGENCY_SCENARIOS");

const HAZARD_TYPES = [
  { key: "micrometeoroid", labelKey: "haz_micrometeoroid", icon: "☄️" },
  { key: "radiation_storm", labelKey: "haz_radiation_storm", icon: "☢️" },
  { key: "debris_field", labelKey: "haz_debris_field", icon: "🛰️" },
  { key: "thermal_stress", labelKey: "haz_thermal_stress", icon: "🌡️" },
];

// --- Emergency Simulator: 5 senaryo ---
export const EMERGENCY_SCENARIOS = [
  {
    id: "radiation_spike",
    labelKey: "emergency_radiation_spike",
    icon: "☢️",
    apply: (a) => {
      a.radiationMSv = 950; // WATCH threshold üstü (1000 crit)
      a.vitals.stressIndex = 85;
      a.vitals.heartRate = Math.min(a.vitals.heartRate + 15, 130);
    },
  },
  {
    id: "cardiac_event",
    labelKey: "emergency_cardiac_event",
    icon: "❤️‍🩹",
    apply: (a) => {
      a.vitals.heartRate = 135;
      a.vitals.bpSys = 170;
      a.vitals.bpDia = 105;
      a.vitals.stressIndex = 92;
      a.vitals.spo2 = Math.max(a.vitals.spo2 - 3, 88);
    },
  },
  {
    id: "hypoxia",
    labelKey: "emergency_hypoxia",
    icon: "🫁",
    apply: (a) => {
      a.vitals.spo2 = 82;
      a.vitals.heartRate = 118;
      a.vitals.stressIndex = 88;
      a.vitals.tempC = Math.max(a.vitals.tempC - 0.5, 35.5);
    },
  },
  {
    id: "eva_suit_leak",
    labelKey: "emergency_eva_suit_leak",
    icon: "👨‍🚀",
    apply: (a) => {
      // EVA'daki astronot için oksijen kaybı simülasyonu
      a.vitals.spo2 = 85;
      a.vitals.heartRate = 125;
      a.vitals.stressIndex = 95;
      // radiation artır (EVA'da koruma az)
      a.radiationMSv = Math.max(a.radiationMSv, 800);
    },
  },
  {
    id: "decompression",
    labelKey: "emergency_decompression",
    icon: "💥",
    apply: (a) => {
      a.vitals.bpSys = 90;
      a.vitals.bpDia = 55;
      a.vitals.heartRate = 140;
      a.vitals.spo2 = 78;
      a.vitals.stressIndex = 98;
      a.vitals.tempC = 35.0;
    },
  },
  {id:"oxygen_depletion",labelKey:"emergency_oxygen_depletion",icon:"O2",apply:(a)=>{a.vitals.spo2=84;a.vitals.heartRate=122;a.vitals.stressIndex=90;}},  {id:"thermal_runaway",labelKey:"emergency_thermal_runaway",icon:"HT",apply:(a)=>{a.vitals.tempC=38.8;a.vitals.heartRate=120;a.vitals.stressIndex=86;}},  {id:"radiation_storm_eva",labelKey:"emergency_radiation_storm_eva",icon:"ST",apply:(a)=>{a.radiationMSv=Math.max(a.radiationMSv,850);a.vitals.stressIndex=88;a.vitals.heartRate=118;}},  {id:"cardiac_arrhythmia",labelKey:"emergency_cardiac_arrhythmia",icon:"ECG",apply:(a)=>{a.vitals.heartRate=148;a.vitals.bpSys=175;a.vitals.bpDia=110;a.vitals.spo2=90;}},  {id:"psych_stress",labelKey:"emergency_psych_stress",icon:"PSY",apply:(a)=>{a.vitals.stressIndex=96;a.vitals.heartRate=110;a.vitals.hrv=22;}},];

// Bridge for external access (testing, emergency simulator) - runs at module load
// Moved to app.js where import is evaluated

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Simüle EVA/ISS state — her astronot için
export function generateMissionState(astronaut) {
  // Deterministic pseudo-random based on id + time
  const seed = astronaut.id.charCodeAt(1) * 1000 + (Date.now() / 60000 | 0);
  const rnd = (n) => { const x = Math.sin(seed * 9999 + n * 777) * 10000; return x - Math.floor(x); };

  const isEVA = rnd(1) < 0.25; // %25 EVA'da
  const evaMinutes = isEVA ? Math.floor(rnd(2) * 120) + 10 : 0;
  const oxygenMinutesLeft = isEVA ? Math.max(0, 360 - evaMinutes + Math.floor(rnd(3) * 60)) : null;
  const distanceKm = Math.floor(rnd(4) * 400) + (isEVA ? 0 : 0); // ISS'e uzaklık (EVA'da artar)
  const evaDistanceKm = isEVA ? +(rnd(5) * 0.5).toFixed(2) : 0;

  // Tehlike simülasyonu
  const hazards = [];
  for (let i = 0; i < HAZARD_TYPES.length; i++) {
    if (rnd(10 + i) < 0.18) {
      const severity = rnd(20 + i) < 0.5 ? "watch" : rnd(20 + i) < 0.8 ? "crit" : "watch";
      const h = HAZARD_TYPES[i];
      hazards.push({ ...h, severity, distanceKm: Math.floor(rnd(30 + i) * 500) + 10 });
    }
  }

  const returnUrgency = (!isEVA) ? "none" : oxygenMinutesLeft < 60 ? "crit" : oxygenMinutesLeft < 150 ? "watch" : "ok";

  return { isEVA, evaMinutes, oxygenMinutesLeft, distanceKm, evaDistanceKm, hazards, returnUrgency };
}

export function renderMissionPanel(container, roster, issPos) {
  if (!container) return;
  container.innerHTML = "";

  // Emergency Simulator toolbar
  const toolbar = document.createElement("div");
  toolbar.className = "emergency-toolbar";
  toolbar.style.cssText = "display:flex;gap:0.4rem;margin-bottom:0.75rem;flex-wrap:wrap;align-items:center";
  toolbar.innerHTML = `<span style="font-size:0.75rem;color:var(--text-faint)">${t("emergency_sim_label")}</span>`;
  EMERGENCY_SCENARIOS.forEach(scn => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "add-btn";
    btn.style.cssText = "font-size:0.7rem;padding:0.3em 0.6em;white-space:nowrap";
    btn.innerHTML = `${scn.icon} ${t(scn.labelKey) || scn.id}`;
    btn.onclick = () => triggerEmergency(scn.id);
    toolbar.appendChild(btn);
  });
  container.appendChild(toolbar);

  // ISS position header
  const issEl = document.createElement("div");
  issEl.className = "mission-iss-bar";
  if (issPos) {
    issEl.innerHTML = `<span class="mono">${t("iss_label")}: ${issPos.lat.toFixed(2)}°, ${issPos.lon.toFixed(2)}°</span> <span style="color:var(--text-faint);font-size:0.75rem">${t("alt_label")} · ${new Date(issPos.ts * 1000).toLocaleTimeString()}</span>`;
  } else {
    issEl.innerHTML = `<span style="color:var(--text-faint)">${t("iss_unavailable")}</span>`;
  }
  container.appendChild(issEl);
  const anyHold=roster.some(a=>{const ms=generateMissionState(a);return ms.isEVA&&ms.returnUrgency==="crit";}); if(anyHold){const hold=document.createElement("div");hold.className="alert-row crit";hold.style.cssText="margin-bottom:0.6rem;font-weight:600;cursor:pointer";hold.textContent=t("eva_hold");hold.onclick=()=>{const m=document.createElement("div");m.className="modal-overlay";m.innerHTML='<div class="modal-box hud-panel"><h3 data-i18n="eva_hold_checklist">EVA Hold Checklist</h3><ul style="font-size:0.82rem;line-height:1.6"><li data-i18n="eva_checklist_tether">Secure tether</li><li data-i18n="eva_checklist_o2">Check O2 seal</li><li data-i18n="eva_checklist_airlock">Confirm airlock</li><li data-i18n="eva_checklist_surgeon">Alert surgeon</li></ul><button onclick="this.closest(\'.modal-overlay\').remove()" data-i18n="btn_close">Close</button></div>';m.onclick=e=>{if(e.target===m)m.remove();};document.body.appendChild(m);};container.appendChild(hold);} try{const topicsEl=document.createElement("div");topicsEl.style.cssText="display:flex;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.6rem";[t("topic_radiation"),t("topic_hypoxia"),t("topic_fatigue")].forEach(tt=>{const c=document.createElement("div");c.style.cssText="font-size:0.68rem;padding:0.3em 0.6em;border:1px solid var(--line);border-radius:999px;background:var(--bg-panel-raised)";c.textContent=tt;topicsEl.appendChild(c);});container.appendChild(topicsEl);}catch{}

  for (const a of roster) {
    const ms = generateMissionState(a);
    const card = document.createElement("div");
    card.className = "mission-card";
    const evaLabel = ms.isEVA ? `<span class="status-chip watch">${t("eva_min", { n: ms.evaMinutes })}</span>` : `<span class="status-chip ok">${t("aboard_iss")}</span>`;
    const oxyInfo = ms.isEVA ? `<div class="mono" style="font-size:0.78rem;color:${ms.returnUrgency === "crit" ? "var(--status-crit)" : ms.returnUrgency === "watch" ? "var(--status-watch)" : "var(--text-muted)"}">${t("o2_left", { n: ms.oxygenMinutesLeft, d: ms.evaDistanceKm })}</div>` : "";
    const hazardsHtml = ms.hazards.length
      ? ms.hazards.map(h => `<div class="alert-row ${h.severity}"><span>${h.icon} ${t(h.labelKey)}</span><span class="mono" style="margin-left:auto;font-size:0.75rem">${h.distanceKm} km</span></div>`).join("")
      : `<div style="color:var(--text-faint);font-size:0.82rem">${t("haz_none")}</div>`;
    const returnHtml = ms.returnUrgency === "crit"
      ? `<div class="alert-row crit">${t("return_urgent")}</div>`
      : ms.returnUrgency === "watch"
        ? `<div class="alert-row watch">${t("return_soon")}</div>` : "";

    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.4rem">
        <div class="crew-avatar" style="width:28px;height:28px;font-size:0.65rem">${a.initials}</div>
        <span style="font-weight:600;font-size:0.88rem">${a.name}</span>
        ${evaLabel}
      </div>
      ${oxyInfo}
      <div style="margin-top:0.5rem;display:flex;flex-direction:column;gap:0.3rem">${hazardsHtml}</div>
      ${returnHtml}
    `;
    container.appendChild(card);
  }
}

// Emergency trigger - roster'dan rastgele birini seçip senaryo uygular, UI yeniler
export function triggerEmergency(scenarioId) {
  const scenario = EMERGENCY_SCENARIOS.find(s => s.id === scenarioId);
  if (!scenario) return;

  // app.js'teki roster'e erişim için global window üzerinden
  const roster = window.__VITANET_ROSTER__;
  if (!roster || !roster.length) return;

  const target = roster[Math.floor(Math.random() * roster.length)];
  scenario.apply(target);

  // Anlık UI yenileme - app.js fonksiyonlarını çağır
  if (window.__VITANET_RENDER_ROSTER__) window.__VITANET_RENDER_ROSTER__();
  if (window.__VITANET_RENDER_DETAIL__) window.__VITANET_RENDER_DETAIL__();
  if (window.__VITANET_RENDER_ALERTS__) window.__VITANET_RENDER_ALERTS__();
  if (window.__VITANET_RENDER_MISSION__) window.__VITANET_RENDER_MISSION__();

  // Advisor'ı tetikle (sonraki tick'te zaten gidecek ama hemen de güzel olur)
  if (window.__VITANET_TRIGGER_ADVICE__) window.__VITANET_TRIGGER_ADVICE__(target.id);
}

// ISS fetch (backend proxy, fallback to direct)
export async function fetchISSPosition() {
  const base = await getBase();
  if (base === null) return null;
  try {
    const c = new AbortController();
    const id = setTimeout(() => c.abort(), 4000);
    const res = await fetch(`${base}/api/iss/position`, { signal: c.signal });
    clearTimeout(id);
    if (res.ok) return await res.json();
  } catch {}
  return null;
}
