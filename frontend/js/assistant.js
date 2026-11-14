// assistant.js — VITA-NET chat assistant (text + voice), uses backend /api/assistant/chat
// Standalone chat UI with history, voice I/O, and quick actions.

import { getLang } from "./i18n.js";
import { speak, stopSpeaking } from "./voice.js";
import { getBase } from "./api.js";

let rosterGetter = () => [];
let selectedGetter = () => null;
let selectFn = () => {};
let tFn = (k) => k;

export function initAssistant(opts) {
  rosterGetter = opts.getRoster || rosterGetter;
  selectedGetter = opts.getSelected || selectedGetter;
  selectFn = opts.selectAstronaut || selectFn;
  tFn = opts.t || tFn;

  const fab = document.getElementById("assistant-fab");
  const drawer = document.getElementById("assistant-drawer");
  const closeBtn = document.getElementById("assistant-close");
  const clearBtn = document.getElementById("assistant-clear");
  const form = document.getElementById("assistant-form");
  const input = document.getElementById("assistant-input");
  const log = document.getElementById("assistant-log");
  const statusEl = document.getElementById("assistant-status");

  if (!fab || !drawer) return;

  function openDrawer() { drawer.hidden = false; log?.scrollTo(0, log.scrollHeight); }
  function closeDrawer() { drawer.hidden = true; }
  fab.addEventListener("click", () => { if (drawer.hidden) openDrawer(); else closeDrawer(); });
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (clearBtn) clearBtn.addEventListener("click", () => { if (log) log.innerHTML = ""; setStatus(""); });

  function setStatus(msg) { if (statusEl) statusEl.textContent = msg || ""; }
  function addMsg(role, text) {
    if (!log) return;
    const div = document.createElement("div");
    div.className = "assistant-msg " + (role === "user" ? "user" : "bot");
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }
  function addEmptyIfNeeded() {
    if (log && !log.children.length) {
      const d = document.createElement("div");
      d.style.cssText = "color:var(--text-faint);font-size:0.82rem;padding:0.5rem 0";
      d.setAttribute("data-i18n", "assistant_empty");
      d.textContent = tFn("assistant_empty");
      log.appendChild(d);
    }
  }
  addEmptyIfNeeded();

  async function handleSend(text) {
    const msg = (text ?? input?.value ?? "").trim();
    if (!msg) return;
    // remove empty placeholder
    if (log && log.children.length === 1 && log.firstElementChild?.hasAttribute("data-i18n")) log.innerHTML = "";
    addMsg("user", msg);
    if (input) input.value = "";
    setStatus(tFn("assistant_thinking"));
    try {
      const reply = await sendToBackend(msg);
      setStatus("");
      addMsg("bot", reply);
    } catch (e) {
      setStatus("");
      addMsg("bot", tFn("assistant_error"));
      console.warn("assistant chat", e);
    }
  }

  if (form) form.addEventListener("submit", (e) => { e.preventDefault(); handleSend(); });

  async function sendToBackend(message) {
    // Build context: roster summary + selected vitals
    const roster = rosterGetter() || [];
    const sel = selectedGetter();
    const ctx = {
      message,
      lang: getLang(),
      roster: roster.slice(0, 20).map(a => ({ id: a.id, name: a.name, role: a.role, vitals: { ...a.vitals, radiationMSv: a.radiationMSv } })),
      selected: sel ? { id: sel.id, name: sel.name, role: sel.role, vitals: { ...sel.vitals, radiationMSv: sel.radiationMSv } } : null,
    };
    const base = await getBase();
    if (base !== null) {
      try {
        const c = new AbortController();
        const id = setTimeout(() => c.abort(), 15000);
        const res = await fetch(`${base}/api/assistant/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(ctx),
          signal: c.signal,
        });
        clearTimeout(id);
        if (res.ok) {
          const j = await res.json();
          if (j.reply) return j.reply;
        }
        if (res.status !== 404) {
          const txt = await res.text().catch(() => "");
          if (res.status >= 400) throw new Error(txt.slice(0, 300) || `HTTP ${res.status}`);
        }
      } catch (e) {
        if (String(e).includes("aborted")) throw e;
      }
    }
    // Fallback: local rule-based answer (offline)
    return localFallback(message, roster, sel);
  }

  function localFallback(message, roster, sel) {
    const lower = message.toLowerCase();
    // Simple intent: vitals query
    for (const a of roster) {
      if (lower.includes(a.name.split(" ")[0].toLowerCase())) {
        const v = a.vitals;
        return `${a.name} — HR ${Math.round(v.heartRate)} bpm, BP ${Math.round(v.bpSys)}/${Math.round(v.bpDia)}, SpO₂ ${v.spo2.toFixed(1)}%, Temp ${v.tempC.toFixed(1)}°C, Stress ${Math.round(v.stressIndex)}, Rad ${Math.round(a.radiationMSv)} mSv.`;
      }
    }
    if (lower.includes("hazard") || lower.includes("danger") || lower.includes("asteroid") || lower.includes("tehlike")) {
      return "No active hazards reported. For EVA status and ISS distance, open the Mission tab.";
    }
    if (sel) {
      const v = sel.vitals;
      return `${sel.name} — HR ${Math.round(v.heartRate)} bpm, BP ${Math.round(v.bpSys)}/${Math.round(v.bpDia)}, SpO₂ ${v.spo2.toFixed(1)}%. All values from the dashboard.`;
    }
    return "I can answer about crew vitals, mission status, and hazards. Try: “How is Mara’s heart rate?” or “Any hazards?”";
  }
}
