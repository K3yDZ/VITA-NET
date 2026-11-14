# VITA-NET — Crew Health Monitor (NASA Space Apps 2026)

> **Prototype for the NASA Space Apps Challenge** — Simulated data, not a certified medical device.

VITA-NET monitors astronaut vitals against WHO/NASA thresholds with rule-based alerts and an optional LLM health advisor. Works fully offline in the browser; backend adds persistence and LLM failover.

---

## Quick Start

### Backend (FastAPI, port 8000)
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
# source .venv/bin/activate                        # macOS/Linux
pip install -r requirements.txt
copy .env.example .env   # then add API keys (optional)
uvicorn main:app --reload --port 8000
```

### Frontend (no build step, vanilla ES modules)
```bash
cd frontend
python -m http.server 5500
# open http://localhost:5500
```
**Single-port mode:** with `SERVE_FRONTEND=1` (default), frontend also served at `http://localhost:8000/`.

---

## Architecture

```
Browser (frontend/)                          Python (backend/)
─────────────────────────────────────────────────────────────────
index.html + css/                            main.py — FastAPI routes + lifespan seed
js/app.js      — boot, sim loop, roster      models.py — Pydantic (VitalsReading, Astronaut, AdviceRequest/Response)
js/api.js      — fetch with local fallback   database.py — SQLite init/history/alerts/mission_events
js/thresholds.js — WHO/NASA eval (client)    thresholds.py — server mirror of evaluate_vitals
js/advisor.js  — alerts, mood, advice        advisor.py — LLM chain (OpenRouter→NVIDIA→Gemini→Anthropic→local)
js/charts.js   — canvas line charts          mock_sensors.py — random-walk vitals generator
js/i18n.js     — 16 locales, native          analytics.py — compute_summary, per-astronaut analytics
js/starfield.js — canvas star background     mission.py — ISS position (open-notify cache) + hazards
js/voice.js    — TTS/STT
js/mission.js  — ISS, hazards, Emergency Sim
js/analytics.js — analytics panel renderer
js/assistant.js — chat drawer, voice, fallback
locales/*.json — 16 languages (en/tr/es/fr/de/ja/zh/ru/ar/pt/it/ko/hi/nl/pl/id)
```

**Key design decisions:**
- Frontend **never depends on backend** — `js/api.js` always falls back to local rule logic. Demo never breaks if backend is down.
- Thresholds duplicated: `frontend/js/thresholds.js` ↔ `backend/thresholds.py` — keep in sync.
- `SERVE_FRONTEND=1` mounts `frontend/` as static files (single-port demo).
- No bundler, no npm, no CDN runtime deps — plain ES modules + canvas charts.
- **Ponytail mode** — minimum code, stdlib/native first, no new deps, no abstraction, deletion > addition.

---

## LLM Advisor Chain (`backend/advisor.py`)

`generate_advice(req)` → first success wins:

1. **OpenRouter** — multi-key (`OPENROUTER_API_KEY`/`_1/_2/_3`) + model list (`OPENROUTER_MODELS`). Models ordered cheap→expensive: `gpt-4o-mini`, `gemini-2.0-flash-001`, `llama-3.3-70b-instruct`, `claude-sonnet-4`. Max tokens: 45.
2. **NVIDIA NIM** — 5 keys (`NVIDIA_API_KEY`/`_1..5`, alias `NVIDIA_NIM_API_KEY_1..5`), OpenAI-compatible at `integrate.api.nvidia.com/v1`. Curated free-tier model list (~30 models). Max tokens: 150.
3. **Google Gemini** — `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-1.5-flash`). Max tokens: 120.
4. **Anthropic** — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-sonnet-4-5-20250929`). Max tokens: 120.
5. **Rule-based** — always works, zero config (`rule_based_advice`).

**Failover:** Each provider rotates keys on 429/401/5xx; next model on 404. `ADVISOR_FORCE_LOCAL=1` skips all LLM calls.

**Frontend call:** `js/advisor.js:getAdvice()` → POST `/api/advice` → `main.py:post_advice` → `advisor.generate_advice()`. Silent fallback to local tip on any error.

**Assistant chat:** `js/assistant.js:sendToBackend()` → POST `/api/assistant/chat` → `main.py:assistant_chat` → `advisor._call_nvidia()` (NVIDIA only, OpenAI-compatible).

---

## Environment Variables (`backend/.env`)

| Variable | Purpose | Example |
|---|---|---|
| `OPENROUTER_API_KEY` | Comma-separated keys (or `_1/_2/_3`) | `sk-or-v1-aaa,sk-or-v1-bbb` |
| `OPENROUTER_MODELS` | Model failover order | `openai/gpt-4o-mini,google/gemini-2.0-flash-001` |
| `NVIDIA_API_KEY` | Comma-separated (or `_1..5`) | `nvapi-aaa,nvapi-bbb` |
| `NVIDIA_MODELS` | Override NVIDIA model list | `meta/llama-3.3-70b-instruct,meta/llama-3.3-8b-instruct` |
| `GEMINI_API_KEY` | Google API key | `AIza...` |
| `GEMINI_MODEL` | Model name | `gemini-1.5-flash` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `ANTHROPIC_MODEL` | Model name | `claude-sonnet-4-5-20250929` |
| `ALLOWED_ORIGINS` | CORS allow-list (comma-separated) | `http://localhost:5500,http://127.0.0.1:5500` |
| `SERVE_FRONTEND` | Mount frontend at `/` | `1` (default) |
| `ADVISOR_FORCE_LOCAL` | Skip all LLM calls | `0` (default) |
| `CREW_SIZE` | Default roster size (1–200) | `6` |

---

## Reference Values

| Vital | Source | Ranges |
|---|---|---|
| Heart rate, BP, SpO₂, Temperature | WHO clinical ranges | BP uses WHO/ISH categories (optimal / normal / high-normal / grade 1–3 hypertension) — **not** AHA 2017 |
| Radiation (career) | NASA 2022 | 600 mSv effective dose limit (all ages/sexes) |
| Radiation (annual watch line) | NCRP | 50 mSv/yr terrestrial worker limit |
| Stress index, Mood | Simulated composite | NOT validated clinical/psych measurements — built to be replaced by real sensor-derived metrics (e.g., HRV) |

---

## UI Overview

| Panel | Features |
|---|---|
| **Roster** | Crew cards with status chips (ok/watch/crit), search, filter, pagination, add/remove |
| **Detail (Vitals tab)** | Vital tiles with range bars, trend chart (canvas), mood read-out, advisor note |
| **Detail (Analytics tab)** | Per-astronaut stats (avg/min/max/count), intervention log |
| **Detail (Mission tab)** | ISS position (live), altitude, hazards, EVA O₂/distance, return guidance |
| **Alerts drawer** | Real-time crit/watch summary with counts |
| **Assistant** | Chat drawer with voice I/O, local fallback when backend offline |
| **Emergency Simulator** | One-click scenarios: Radiation Spike, Cardiac Event, Hypoxia, EVA Suit Leak, Decompression |
| **Settings** | Crew size (1–200), offline mode toggle, theme (light/dark) |

---

## i18n — 16 Locales

`frontend/locales/{en,tr,es,fr,de,ja,zh,ru,ar,pt,it,ko,hi,nl,pl,id}.json` — native, no Google widget. Switch via header dropdown. All UI strings externalized including alerts, advisor tips, mission hazards, roles, voice commands.

---

## Recent Optimizations (2026-10-29)

See `SYNC.md` for full log:

- OpenRouter models reordered cheap→expensive (reduces latency/cost on first attempt)
- NVIDIA model list trimmed to confirmed free-tier models only
- System prompt tightened: space-medicine context, ≤1 sentence, no diagnosis, cite numbers
- Token limits reduced: OpenRouter 60→45, NVIDIA 150→100, Anthropic 200→120
- Added `ADVISOR_SKIP_OPENROUTER` env to skip expensive first tier
- Structured logging: `model`, `key_idx`, `latency_ms`, `source` fields

---

## Demo Checklist

- [ ] Backend starts: `uvicorn main:app --reload --port 8000`
- [ ] Frontend loads: `http://localhost:5500` or `http://localhost:8000/`
- [ ] Roster shows 6 crew with live vitals updating every 4s
- [ ] Click crew → detail panel opens with vitals, chart, mood, advisor
- [ ] Alerts drawer updates in real time
- [ ] Switch language → all UI translates (16 locales)
- [ ] Emergency Simulator triggers scenarios
- [ ] Assistant chat works (LLM if keys set, local fallback otherwise)
- [ ] Offline mode toggle → dashboard still fully functional
- [ ] Reset Demo button restores safe state
- [ ] Theme toggle (light/dark) persists

---

## License

MIT — prototype for NASA Space Apps Challenge 2026.