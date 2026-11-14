import { initI18n, setLang, getLang, onLangChange, t, applyToDom, getSupported, getLangLabels } from "./i18n.js";
import { initStarfield } from "./starfield.js";
import { createRoster, tickVitals, applyManualVitals, setMode, addAstronaut, removeAstronaut } from "./mockData.js";
import { evaluateVitals, RADIATION_WATCH_MSV } from "./thresholds.js";
import { buildAlerts, inferMood, getAdvice } from "./advisor.js";
import { drawTrendChart } from "./charts.js";
import { checkBackend, logReading, fetchHistory } from "./api.js";
import { speak, stopSpeaking, isSpeaking, ttsSupported, sttSupported, startListening, stopListening, isListening } from "./voice.js";
import { renderMissionPanel, fetchISSPosition, EMERGENCY_SCENARIOS } from "./mission.js";
// Re-export for external access
export { EMERGENCY_SCENARIOS };
import { fetchSummary, fetchAstronautAnalytics, renderAnalyticsPanel } from "./analytics.js";
import { initAssistant } from "./assistant.js";

const TICK_MS = 4000;
const ADVICE_EVERY_N_TICKS = 3;

// Offline mode state
let offlineMode = localStorage.getItem("vitanet.offline") === "true";

// Crew size config (persisted)
let crewSize = parseInt(localStorage.getItem("vitanet.crewSize") || "6", 10);

const VITAL_DEFS = [
  { key: "heartRate", labelKey: "vital_heart_rate", unit: "bpm", statusKey: "heartRate", get: (v) => Math.round(v.heartRate) },
  { key: "bp", labelKey: "vital_bp", unit: "mmHg", statusKey: "bp", get: (v) => `${Math.round(v.bpSys)}/${Math.round(v.bpDia)}` },
  { key: "spo2", labelKey: "vital_spo2", unit: "%", statusKey: "spo2", get: (v) => v.spo2.toFixed(1) },
  { key: "radiation", labelKey: "vital_radiation", unit: "mSv", statusKey: "radiation", get: (v, a) => Math.round(a.radiationMSv) },
  { key: "stress", labelKey: "vital_stress", unit: "", statusKey: "stress", get: (v) => Math.round(v.stressIndex) },
  { key: "temp", labelKey: "vital_temp", unit: "\u00b0C", statusKey: "temp", get: (v) => v.tempC.toFixed(1) },
];

const CHART_METRICS = [
  { key: "heartRate", labelKey: "vital_heart_rate", unit: " bpm", refLine: 100, series: (h) => h.heartRate },
  { key: "bpSys", labelKey: "vital_bp", unit: " mmHg", refLine: 140, series: (h) => h.bpSys },
  { key: "spo2", labelKey: "vital_spo2", unit: "%", refLine: 95, series: (h) => h.spo2 },
  { key: "radiationMSv", labelKey: "vital_radiation", unit: " mSv", refLine: RADIATION_WATCH_MSV, series: (h) => h.radiationMSv },
  { key: "stressIndex", labelKey: "vital_stress", unit: "", refLine: 55, series: (h) => h.stressIndex },
  { key: "tempC", labelKey: "vital_temp", unit: "\u00b0C", refLine: 37.8, series: (h) => h.tempC },
];

let roster = [];
let selectedId = null;
let tickCount = 0;
let missionStart = Date.now();
let currentChartMetric = "heartRate";
let currentTab = "vitals"; // vitals | analytics | mission
let issPosition = null;

// Pagination + search/filter for 50-100 scale
let rosterPage = 0;
const ROSTER_PER_PAGE = 12;
let rosterSearch = "";
let rosterStatusFilter = "all"; // all | ok | watch | crit

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// Focus trap utility for modals
function trapFocus(element) {
  const focusable = element.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  function handleTab(e) {
    if (e.key !== 'Tab') return;
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  element.addEventListener('keydown', handleTab);
  first?.focus();
  return () => element.removeEventListener('keydown', handleTab);
}

function statusOf(astronaut) {
  return evaluateVitals({ ...astronaut.vitals, radiationMSv: astronaut.radiationMSv });
}

function filteredRoster() {
  let list = roster;
  if (rosterSearch) {
    const q = rosterSearch.toLowerCase();
    list = list.filter(a => a.name.toLowerCase().includes(q) || a.role.toLowerCase().includes(q));
  }
  if (rosterStatusFilter !== "all") {
    list = list.filter(a => statusOf(a).overall === rosterStatusFilter);
  }
  return list;
}

// ---------- roster ----------
function renderRoster() {
  const grid = $("#roster-grid");
  const filtered = filteredRoster();
  const totalPages = Math.max(1, Math.ceil(filtered.length / ROSTER_PER_PAGE));
  if (rosterPage >= totalPages) rosterPage = totalPages - 1;
  if (rosterPage < 0) rosterPage = 0;
  const pageItems = filtered.slice(rosterPage * ROSTER_PER_PAGE, (rosterPage + 1) * ROSTER_PER_PAGE);

  grid.innerHTML = "";
  for (const a of pageItems) {
    const { overall } = statusOf(a);
    const card = document.createElement("button");
    card.className = "crew-card" + (a.id === selectedId ? " is-selected" : "");
    card.setAttribute("aria-pressed", a.id === selectedId ? "true" : "false");
    card.innerHTML = `
      <div class="crew-card-head">
        <div class="crew-avatar">${a.initials}</div>
        <div>
          <div class="crew-name">${a.name}</div>
          <div class="crew-role">${a.role}</div>
        </div>
        <span class="status-chip ${overall}">${t("status_" + overall)}</span>
      </div>
      <div class="crew-mini-vitals mono">
        <span>HR <b>${Math.round(a.vitals.heartRate)}</b></span>
        <span>Rad <b>${Math.round(a.radiationMSv)}</b> mSv</span>
        <span>Str <b>${Math.round(a.vitals.stressIndex)}</b></span>
      </div>
      <button class="crew-remove-btn" data-remove="${a.id}" title="${t("remove_title")}" aria-label="${t("remove_title")} ${a.name}">✕</button>
    `;
    card.addEventListener("click", (e) => {
      if (e.target.closest("[data-remove]")) return;
      selectAstronaut(a.id);
    });
    const rmBtn = card.querySelector("[data-remove]");
    if (rmBtn) rmBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (confirm(t("remove_confirm", { name: a.name }))) {
        removeAstronaut(roster, a.id);
        if (selectedId === a.id) { selectedId = null; $("#detail-panel-wrap").classList.remove("is-open"); $("#detail-panel").innerHTML = `<p id="detail-empty" data-i18n="select_prompt">${t("select_prompt")}</p>`; }
        renderRoster();
        renderAlertsTicker();
      }
    });
    grid.appendChild(card);
  }
  $("#roster-count").textContent = filtered.length === roster.length ? t("roster_count", { n: roster.length }) : `${filtered.length} / ${roster.length}`;
  renderRosterPagination(totalPages, filtered.length);
}

function renderRosterPagination(totalPages, filteredCount) {
  let el = $("#roster-pagination");
  if (!el) {
    el = document.createElement("div");
    el.id = "roster-pagination";
    el.className = "roster-pagination";
    $("#roster-section").appendChild(el);
  }
  if (totalPages <= 1 && !rosterSearch && rosterStatusFilter === "all") { el.innerHTML = ""; return; }
  let html = "";
  if (totalPages > 1) {
    html += `<button ${rosterPage === 0 ? "disabled" : ""} data-page="prev">‹</button>`;
    html += `<span class="mono" style="font-size:0.78rem;color:var(--text-muted)">${rosterPage + 1} / ${totalPages}</span>`;
    html += `<button ${rosterPage >= totalPages - 1 ? "disabled" : ""} data-page="next">›</button>`;
  }
  if (filteredCount === 0) html += `<span style="color:var(--text-faint);font-size:0.8rem">${t("no_matches")}</span>`;
  el.innerHTML = html;
  const prev = el.querySelector("[data-page=prev]");
  const next = el.querySelector("[data-page=next]");
  if (prev) prev.addEventListener("click", () => { rosterPage--; renderRoster(); });
  if (next) next.addEventListener("click", () => { rosterPage++; renderRoster(); });
}

function renderAlertsTicker() {
  const box = $("#alerts-ticker");
  if (!box) return;
  box.innerHTML = "";
  const rows = [];
  for (const a of roster) {
    for (const alert of buildAlerts(a)) {
      if (alert.level !== "ok") rows.push({ name: a.name, ...alert });
    }
  }
  // summary badge
  const critCount = rows.filter(r => r.level === "crit").length;
  const watchCount = rows.filter(r => r.level === "watch").length;
  const badge = $("#alerts-badge");
  if (badge) {
    badge.textContent = rows.length ? `${rows.length}` : "";
    badge.dataset.count = String(rows.length);
    badge.style.display = rows.length ? "" : "none";
  }
  const drawerCount = $("#alert-drawer-count");
  if (drawerCount) drawerCount.textContent = rows.length ? `${critCount} ${t("alert_crit")} · ${watchCount} ${t("alert_watch")} · ${rows.length} ${t("alert_total")}` : t("alert_drawer_all_nominal");

  rows.slice(0, 30).forEach((r) => {
    const div = document.createElement("div");
    div.className = "alert-row " + r.level;
    div.innerHTML = `<span class="who mono">${r.name.split(" ")[0]}</span><span>${r.text}</span>`;
    box.appendChild(div);
  });
  if (rows.length === 0) {
    const div = document.createElement("div");
    div.style.cssText = "color:var(--status-ok);font-size:0.82rem;padding:0.3rem 0";
    div.textContent = t("alert_all_clear");
    box.appendChild(div);
  }
}

// ---------- detail panel ----------
function selectAstronaut(id) {
  selectedId = id;
  $("#detail-panel-wrap").classList.add("is-open");
  renderRoster();
  renderDetail();
}

function closeDetail() {
  $("#detail-panel-wrap").classList.remove("is-open");
}

function renderDetail(refreshAdvice = true) {
  const panel = $("#detail-panel");
  const astronaut = roster.find((a) => a.id === selectedId);
  if (!astronaut) {
    panel.innerHTML = `<p id="detail-empty" data-i18n="select_prompt">${t("select_prompt")}</p>`;
    return;
  }

  const tpl = $("#tpl-detail");
  const isFirstRender = !$("#d-name", panel);
  if (isFirstRender) {
    panel.innerHTML = "";
    panel.appendChild(tpl.content.cloneNode(true));
    applyToDom(panel);
    $("#close-detail", panel).addEventListener("click", closeDetail);
    const backBtn = $("#back-detail", panel) || document.getElementById("back-detail");
    if (backBtn && !backBtn.dataset.bound) { backBtn.dataset.bound="1"; backBtn.addEventListener("click", closeDetail); }
    $$("[data-mode]", panel).forEach((btn) => {
      btn.addEventListener("click", () => {
        setMode(astronaut, btn.dataset.mode);
        $$("[data-mode]", panel).forEach((b) => b.classList.toggle("is-active", b === btn));
        $("#d-manual-form", panel).hidden = btn.dataset.mode !== "manual";
        if (btn.dataset.mode === "manual") buildManualForm(astronaut);
        renderDetail(false);
      });
    });
    const metricSelect = $("#d-chart-metric", panel);
    CHART_METRICS.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.key;
      opt.textContent = t(m.labelKey);
      metricSelect.appendChild(opt);
    });
    metricSelect.value = currentChartMetric;
    metricSelect.addEventListener("change", () => {
      currentChartMetric = metricSelect.value;
      renderChart(astronaut);
    });
    // Tab switching
    $$("[data-tab]", panel).forEach((btn) => {
      btn.addEventListener("click", () => {
        currentTab = btn.dataset.tab;
        $$("[data-tab]", panel).forEach(b => b.classList.toggle("is-active", b.dataset.tab === currentTab));
        updateTabVisibility(panel, astronaut);
      });
    });
  }

  $("#d-avatar", panel).textContent = astronaut.initials;
  $("#d-name", panel).textContent = `${astronaut.name} — ${astronaut.role}`;
  $$("[data-mode]", panel).forEach((b) => b.classList.toggle("is-active", b.dataset.mode === astronaut.mode));
  $("#d-manual-form", panel).hidden = astronaut.mode !== "manual";
  if (astronaut.mode === "manual" && !$("#d-manual-form", panel).querySelector("input")) buildManualForm(astronaut);
  $$("[data-tab]", panel).forEach((b) => b.classList.toggle("is-active", b.dataset.tab === currentTab));

  const { per } = statusOf(astronaut);
  const vitalsGrid = $("#d-vitals", panel);
  vitalsGrid.innerHTML = "";
  VITAL_DEFS.forEach((def) => {
    const status = per[def.statusKey];
    const tile = document.createElement("div");
    tile.className = "vital-tile " + status;
    const fillPct = status === "ok" ? 33 : status === "watch" ? 66 : 100;
    tile.innerHTML = `
      <div class="label">${t(def.labelKey)}</div>
      <div class="value mono">${def.get(astronaut.vitals, astronaut)}<span class="unit">${def.unit}</span></div>
      <div class="range-bar"><div class="fill ${status}" style="width:${fillPct}%"></div></div>
    `;
    vitalsGrid.appendChild(tile);
  });

  const _bd = document.getElementById("back-detail");
  if (_bd && !_bd.dataset.bound) { _bd.dataset.bound="1"; _bd.addEventListener("click", closeDetail); }
  $("#d-mood", panel).textContent = t(inferMood(astronaut.vitals));
  updateTabVisibility(panel, astronaut);
  if (refreshAdvice) refreshAdvisor(astronaut);
}

function updateTabVisibility(panel, astronaut) {
  const vitalsTab = $("#tab-vitals", panel);
  const analyticsTab = $("#tab-analytics", panel);
  const missionTab = $("#tab-mission", panel);
  if (vitalsTab) vitalsTab.hidden = currentTab !== "vitals";
  if (analyticsTab) {
    analyticsTab.hidden = currentTab !== "analytics";
    if (currentTab === "analytics") loadAnalyticsTab(astronaut);
  }
  if (missionTab) {
    missionTab.hidden = currentTab !== "mission";
    if (currentTab === "mission") renderMissionPanel($("#mission-panel", panel), [astronaut], issPosition);
  }
  // Chart visibility tied to vitals tab
  const chartWrap = $("#d-chart-wrap", panel);
  if (chartWrap) chartWrap.hidden = currentTab !== "vitals";
  const moodWrap = $("#d-mood-wrap", panel);
  if (moodWrap) moodWrap.hidden = currentTab !== "vitals";
  if (currentTab === "vitals") renderChart(astronaut);
}

async function loadAnalyticsTab(astronaut) {
  const container = $("#analytics-panel");
  if (!container) return;
  container.innerHTML = `<p style="color:var(--text-faint)">Loading analytics…</p>`;
  const data = await fetchAstronautAnalytics(astronaut.id);
  if (data) renderAnalyticsPanel(container, data);
  else {
    // Fallback: compute from local history
    const hist = astronaut.history;
    if (!hist.length) { container.innerHTML = `<p style="color:var(--text-faint)">Not enough data yet.</p>`; return; }
    const metrics = ["heartRate","bpSys","spo2","tempC","stressIndex","radiationMSv"];
    const m = {};
    for (const k of metrics) {
      const vals = hist.map(h => h[k]).filter(v => v != null);
      if (!vals.length) continue;
      const avg = vals.reduce((a,b)=>a+b,0)/vals.length;
      m[k] = { avg, min: Math.min(...vals), max: Math.max(...vals), count: vals.length };
    }
    renderAnalyticsPanel(container, { metrics, count: hist.length, interventions: [] });
  }
}

function renderChart(astronaut) {
  const metric = CHART_METRICS.find((m) => m.key === currentChartMetric) || CHART_METRICS[0];
  const points = astronaut.history.map((h) => ({ v: metric.series(h) }));
  drawTrendChart($("#d-chart"), points, { unit: metric.unit, refLine: metric.refLine });
}

async function refreshAdvisor(astronaut) {
  const feed = $("#d-advisor");
  const { text, source } = await getAdvice(astronaut);
  if (astronaut.id !== selectedId) return;
  if (!feed) return;
  feed.innerHTML = `
    <div class="advisor-msg">
      ${text}
      <span class="src">${t(source === "llm" ? "advisor_source_llm" : "advisor_source_local")}</span>
    </div>
  `;
}

function buildManualForm(astronaut) {
  const form = $("#d-manual-form");
  // Always rebuild to reflect current values (fixes stale input bug)
  form.innerHTML = "";
  const fields = [
    { key: "heartRate", labelKey: "vital_heart_rate", step: "1" },
    { key: "bpSys", labelKey: "vital_bp", step: "1", suffix: "sys" },
    { key: "bpDia", labelKey: "vital_bp", step: "1", suffix: "dia" },
    { key: "spo2", labelKey: "vital_spo2", step: "0.1" },
    { key: "tempC", labelKey: "vital_temp", step: "0.1" },
    { key: "stressIndex", labelKey: "vital_stress", step: "1" },
    { key: "radiationMSv", labelKey: "vital_radiation", step: "0.1" },
  ];
  fields.forEach((f) => {
    const wrap = document.createElement("div");
    const current = f.key === "radiationMSv" ? astronaut.radiationMSv : astronaut.vitals[f.key];
    wrap.innerHTML = `
      <label>${t(f.labelKey)}${f.suffix ? " (" + t("suffix_" + f.suffix) + ")" : ""}</label>
      <input type="number" step="${f.step}" name="${f.key}" value="${Number(current).toFixed(1)}" />
    `;
    form.appendChild(wrap);
  });
  const btn = document.createElement("button");
  btn.type = "submit";
  btn.className = "apply-btn";
  btn.textContent = t("manual_apply");
  form.appendChild(btn);

  form.onsubmit = (e) => {
    e.preventDefault();
    // Capture selectedId at submit time to avoid closure stale-astronaut bug
    const target = roster.find(a => a.id === selectedId);
    if (!target) return;
    const data = new FormData(form);
    const patch = {};
    for (const [key, val] of data.entries()) patch[key] = parseFloat(val);
    applyManualVitals(target, patch);
    logReading(target.id, { ...target.vitals, radiationMSv: target.radiationMSv });
    renderRoster();
    renderDetail();
  };
}

// ---------- mission clock ----------
function renderClock() {
  const elapsed = Date.now() - missionStart;
  const s = Math.floor(elapsed / 1000);
  const dd = String(Math.floor(s / 86400)).padStart(3, "0");
  const hh = String(Math.floor((s % 86400) / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  $("#mission-clock").textContent = `MET ${dd}:${hh}:${mm}:${ss}`;
}

// ---------- backend indicator ----------
async function pollBackend() {
  const indicator = $("#backend-indicator");
  const online = await checkBackend();
  indicator.dataset.state = online ? "online" : "offline";
  $("#backend-indicator-label").textContent = t(online ? "backend_online" : "backend_offline");
}

async function pollISS() {
  try { issPosition = await fetchISSPosition(); } catch {}
}

// ---------- simulation loop ----------
function tick() {
  tickCount++;
  for (const a of roster) {
    tickVitals(a);
    if (!offlineMode) {
      logReading(a.id, { ...a.vitals, radiationMSv: a.radiationMSv });
    }
  }
  renderRoster();
  renderAlertsTicker();
  const selected = roster.find((a) => a.id === selectedId);
  if (selected) renderDetail(tickCount % ADVICE_EVERY_N_TICKS === 0);
}

// ---------- voice command handler ----------
function handleVoiceCommand(transcript) {
  const lower = transcript.toLowerCase();
  // "show mara" / "select kenji"
  for (const a of roster) {
    if (lower.includes(a.name.split(" ")[0].toLowerCase()) || lower.includes(a.name.toLowerCase())) {
      selectAstronaut(a.id);
      speak(t("showing_crew", { name: a.name }));
      return;
    }
  }
  if (lower.includes("reset") || lower.includes("safe")) {
    doResetDemo();
    speak(t("reset_done"));
    return;
  }
  // fallback: read advisor for selected
  const sel = roster.find(a => a.id === selectedId);
  if (sel) {
    const feed = $("#d-advisor");
    if (feed?.textContent) speak(feed.textContent.trim());
  }
}

async function doResetDemo() {
  // Call backend reset if online and not in offline mode
  if (!offlineMode) {
    try {
      await fetch("/api/reset", { method: "POST" });
    } catch (e) {
      // Silent fail, use local reset
    }
  }

  // Re-seed all astronauts
  const fresh = createRoster(crewSize);
  // Keep roster length, replace vitals
  for (let i = 0; i < roster.length && i < fresh.length; i++) {
    roster[i].vitals = fresh[i].vitals;
    roster[i].radiationMSv = fresh[i].radiationMSv;
    roster[i].history = [];
    roster[i].mode = "live";
  }
  // Remove extra if roster was larger
  if (roster.length > fresh.length) {
    // keep custom astronauts, just reset vitals
    for (let i = fresh.length; i < roster.length; i++) {
      const f = fresh[i % fresh.length];
      roster[i].vitals = { ...f.vitals };
      roster[i].radiationMSv = Math.random() * 8;
      roster[i].history = [];
      roster[i].mode = "live";
    }
  }
  renderRoster();
  renderAlertsTicker();
  if (selectedId) renderDetail();
}

// ---------- boot ----------

function updateOfflineIndicator() {
  const btn = $("#offline-toggle-btn");
  if (btn) {
    if (offlineMode) {
      btn.textContent = t("offline_active");
      btn.classList.add("is-active");
    } else {
      btn.textContent = t("offline_mode");
      btn.classList.remove("is-active");
    }
  }
  const indicator = $("#backend-indicator");
  const label = $("#backend-indicator-label");
  if (indicator && label) {
    if (offlineMode) {
      indicator.dataset.state = "offline";
      label.textContent = t("backend_offline");
    }
  }
}

function openSettingsModal() {
  const modal = $("#settings-modal");
  if (!modal) return;
  const crewSizeInput = $("#settings-crew-size");
  if (crewSizeInput) crewSizeInput.value = String(crewSize);
  modal.hidden = false;
  const box = modal.querySelector('.modal-box');
  if (box) modal._focusCleanup = trapFocus(box);
}

function closeSettingsModal() {
  const modal = $("#settings-modal");
  if (!modal) return;
  if (modal._focusCleanup) { modal._focusCleanup(); modal._focusCleanup = null; }
  modal.hidden = true;
}

function saveSettings(e) {
  e.preventDefault();
  const crewSizeInput = $("#settings-crew-size");
  const newSize = parseInt(crewSizeInput?.value || "6", 10);
  if (newSize >= 1 && newSize <= 200 && newSize !== crewSize) {
    crewSize = newSize;
    localStorage.setItem("vitanet.crewSize", String(crewSize));
    // Recreate roster with new size
    const fresh = createRoster(crewSize);
    // Preserve existing astronauts' vitals if they exist in new roster
    for (let i = 0; i < Math.min(roster.length, fresh.length); i++) {
      fresh[i].vitals = roster[i].vitals;
      fresh[i].radiationMSv = roster[i].radiationMSv;
      fresh[i].history = roster[i].history;
      fresh[i].mode = roster[i].mode;
    }
    roster = fresh;
    renderRoster();
    renderAlertsTicker();
    if (selectedId) renderDetail();
  }
  closeSettingsModal();
}

// ---------- theme ----------
function initTheme() {
  const btn = document.getElementById("theme-toggle");
  const saved = localStorage.getItem("vitanet.theme");
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  const initial = saved || (prefersLight ? "light" : "dark");
  document.documentElement.setAttribute("data-theme", initial);
  if (btn) {
    btn.textContent = initial === "light" ? "🌙" : "☀️";
    btn.title = initial === "light" ? "Dark mode" : "Light mode";
    btn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const next = cur === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("vitanet.theme", next);
      btn.textContent = next === "light" ? "🌙" : "☀️";
      btn.title = next === "light" ? "Dark mode" : "Light mode";
    });
  }
}

async function boot() {
  initTheme();
  initStarfield();
  await initI18n();

  // native lang-select doldur
  const langSelect = document.getElementById("lang-select");
  if (langSelect) {
    const labels = getLangLabels();
    const supported = getSupported();
    langSelect.innerHTML = supported.map(c => `<option value="${c}">${labels[c] || c}</option>`).join("");
    langSelect.value = getLang();
    langSelect.addEventListener("change", (e) => setLang(e.target.value));
  }

  // Initialize offline mode indicator
  updateOfflineIndicator();

  // Initialize crew size from localStorage
  const savedCrewSize = parseInt(localStorage.getItem("vitanet.crewSize") || "6", 10);
  if (savedCrewSize >= 1 && savedCrewSize <= 6) {
    crewSize = savedCrewSize;
  }

  roster = createRoster(crewSize);
  // Backend history varsa yükle (opsiyonel, offline da calisir)
  for (const a of roster) {
    try {
      const hist = await fetchHistory(a.id, 60);
      if (hist && hist.length) {
        a.history = hist.map(r => ({
          t: new Date(r.ts).getTime(),
          heartRate: r.heart_rate, bpSys: r.bp_sys, bpDia: r.bp_dia,
          spo2: r.spo2, tempC: r.temp_c, stressIndex: r.stress_index,
          radiationMSv: r.radiation_msv, hrv: r.hrv ?? 50,
        }));
        const last = a.history[a.history.length - 1];
        if (last) {
          a.vitals = { heartRate: last.heartRate, bpSys: last.bpSys, bpDia: last.bpDia, spo2: last.spo2, tempC: last.tempC, stressIndex: last.stressIndex, hrv: last.hrv };
          a.radiationMSv = last.radiationMSv;
        }
      }
    } catch {}
  }

  renderRoster();
  renderAlertsTicker();
  renderClock();

  // Search + filter
  const searchInput = $("#roster-search");
  if (searchInput) searchInput.addEventListener("input", (e) => { rosterSearch = e.target.value; rosterPage = 0; renderRoster(); });
  const statusFilter = $("#roster-status-filter");
  if (statusFilter) statusFilter.addEventListener("change", (e) => { rosterStatusFilter = e.target.value; rosterPage = 0; renderRoster(); });

  // Add astronaut
  const addBtn = $("#add-astronaut-btn");
  if (addBtn) addBtn.addEventListener("click", () => openAddModal());
  const addForm = $("#add-astronaut-form");
  if (addForm) addForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(addForm);
    const name = String(fd.get("name") || "").trim();
    const role = String(fd.get("role") || "").trim();
    if (!name) return;
    addAstronaut(roster, { name, role: role || "Crew Member" });
    closeAddModal();
    renderRoster();
    renderAlertsTicker();
  });
  const addCancel = $("#add-astronaut-cancel");
  if (addCancel) addCancel.addEventListener("click", closeAddModal);
  const addModal = $("#add-astronaut-modal");
  if (addModal) addModal.addEventListener("click", (e) => { if (e.target === addModal) closeAddModal(); });

  // Reset demo
  const resetBtn = $("#reset-demo-btn");
  if (resetBtn) resetBtn.addEventListener("click", doResetDemo);

  // Offline mode toggle
  const offlineBtn = $("#offline-toggle-btn");
  if (offlineBtn) {
    offlineBtn.addEventListener("click", () => {
      offlineMode = !offlineMode;
      localStorage.setItem("vitanet.offline", String(offlineMode));
      updateOfflineIndicator();
      if (offlineMode) {
        // Force backend check to show offline
        const indicator = $("#backend-indicator");
        if (indicator) {
          indicator.dataset.state = "offline";
          $("#backend-indicator-label").textContent = t("backend_offline");
        }
      } else {
        pollBackend();
      }
    });
  }

  // Settings modal
  const settingsBtn = $("#settings-btn");
  if (settingsBtn) settingsBtn.addEventListener("click", openSettingsModal);
  const settingsModal = $("#settings-modal");
  if (settingsModal) settingsModal.addEventListener("click", (e) => { if (e.target === settingsModal) closeSettingsModal(); });
  const settingsForm = $("#settings-form");
  if (settingsForm) settingsForm.addEventListener("submit", saveSettings);
  const settingsCancel = $("#settings-cancel");
  if (settingsCancel) settingsCancel.addEventListener("click", closeSettingsModal);

  // Alerts drawer
  const alertsToggle = $("#alerts-toggle");
  const alertsDrawer = $("#alerts-drawer");
  if (alertsToggle && alertsDrawer) {
    alertsToggle.addEventListener("click", () => alertsDrawer.classList.toggle("is-open"));
    const closeBtn = $("#alerts-drawer-close");
    if (closeBtn) closeBtn.addEventListener("click", () => alertsDrawer.classList.remove("is-open"));
  }

  // Eski voice-mic-btn header'da yok — guard sadece legacy crash engeli (asistan mic ayri)
  try {
    const legacyMic = document.getElementById("voice-mic-btn");
    if (legacyMic) legacyMic.style.display = "none";
  } catch {}

  onLangChange(() => {
    applyToDom();
    renderRoster();
    renderAlertsTicker();
    if (selectedId) {
      const p = $("#detail-panel");
      if (p) p.innerHTML = "";
      renderDetail();
    }
  });

  try { initAssistant({ getRoster: () => roster, getSelected: () => roster.find(a=>a.id===selectedId), selectAstronaut, t }); } catch(e){ console.warn("assistant init", e); }
  // expose for mission.js emergency simulator (graph bridge initAssistant→Frontend Advisor Logic)
  // use getter so reassigned roster stays live
  Object.defineProperty(window, "__VITANET_ROSTER__", { get: () => roster, configurable: true });
  window.__VITANET_RENDER_ROSTER__ = renderRoster;
  window.__VITANET_RENDER_DETAIL__ = () => { if (selectedId) renderDetail(); };
  window.__VITANET_RENDER_ALERTS__ = renderAlertsTicker;
  window.__VITANET_RENDER_MISSION__ = () => { const c = document.getElementById("mission-panel"); if (c) renderMissionPanel(c, roster, issPosition); };
  window.__VITANET_TRIGGER_ADVICE__ = (id) => { const a = roster.find(x=>x.id===id); if(a) refreshAdvisor(a); };
  // Bridge for testing/emergency simulator access
  console.log("[app.js] Setting EMERGENCY_SCENARIOS bridge");
  window.__VITANET_EMERGENCY_SCENARIOS__ = EMERGENCY_SCENARIOS;
  pollBackend();
  pollISS();
  setInterval(pollBackend, 10000);
  setInterval(pollISS, 30000);
  setInterval(renderClock, 1000);
  setInterval(tick, TICK_MS);
}

function openAddModal() {
  const m = $("#add-astronaut-modal");
  if (!m) return;
  m.hidden = false;
  const box = m.querySelector('.modal-box');
  if (box) m._focusCleanup = trapFocus(box);
}
function closeAddModal() {
  const m = $("#add-astronaut-modal");
  if (!m) return;
  if (m._focusCleanup) { m._focusCleanup(); m._focusCleanup = null; }
  m.hidden = true;
  const f = $("#add-astronaut-form");
  if (f) f.reset();
}

boot();


