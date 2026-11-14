"""Hybrid advisor: rule-based fallback + OpenRouter (multi-key) + NVIDIA NIM (5 keys) + Google Gemini + Anthropic fallback.

Priority order:
  1. OpenRouter (3 keys + model failover) — skip via ADVISOR_SKIP_OPENROUTER=1
  2. NVIDIA NIM (5 keys + model failover, integrate.api.nvidia.com)
  3. Google Gemini (direct API)
  4. Anthropic direct (ANTHROPIC_API_KEY)
  5. Rule-based (always works, offline-proof)

OpenRouter advantage: single API for 40+ models.
NVIDIA NIM advantage: OpenAI-compatible, generous free quota, 5 key rotation.
Gemini advantage: fast/cheap models (gemini-1.5-flash).
Auto failover on 429/quota to next model/key.
"""

import os
import logging
import time
import re
from models import AdviceRequest
from thresholds import evaluate_vitals, RADIATION_WATCH_MSV

logger = logging.getLogger(__name__)

# Prompt injection prevention: sanitize user-supplied strings before inserting into LLM prompt
_MAX_ALERT_LEN = 80
_MAX_ALERTS = 10
_MAX_CHAT_LEN = 500


def _sanitize_for_prompt(s: str) -> str:
    """Strip control chars, limit length — safe to embed in LLM prompt."""
    if not s:
        return ""
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)  # remove control chars
    return s[:_MAX_CHAT_LEN]


def _sanitize_alerts(alerts: list[str]) -> list[str]:
    """Sanitize each alert, cap count and length."""
    out = []
    for a in alerts[:_MAX_ALERTS]:
        clean = _sanitize_for_prompt(a)
        if clean:
            out.append(clean[:_MAX_ALERT_LEN])
    return out

# ------------------------------------------------------------
# Rule-based (her zaman hazir)
# ------------------------------------------------------------

def rule_based_advice(req: AdviceRequest) -> str:
    v = req.vitals
    result = evaluate_vitals(v)
    per = result["per"]

    if v.radiationMSv >= RADIATION_WATCH_MSV:
        return "Radiation trending upward \u2014 confirm shielded-area location per mission protocol."
    if per["stress"] != "ok" and per["heartRate"] != "ok":
        return "Vitals suggest fatigue. A rest period and hydration are recommended before the next task block."
    if per["heartRate"] != "ok" and per["spo2"] == "ok":
        return "Elevated heart rate with normal oxygen \u2014 check hydration and recent activity level."
    if per["stress"] == "ok" and per["heartRate"] == "ok" and per["spo2"] == "ok":
        return "All indicators nominal. Keep up the current routine."
    return "Nothing urgent \u2014 a quick personal check-in is still good practice."


SYSTEM_PROMPT = (
    "You are VITA-NET Assistant, a calm, concise flight-surgeon-style health advisor "
    "reviewing astronaut vitals during a space mission. Give ONE short (<=1 sentence) practical "
    "recommendation. Never diagnose a specific disease; describe risk in plain, measured "
    "terms. If everything is nominal, say so briefly and encouragingly. Do not repeat the "
    "raw numbers back verbatim \u2014 the dashboard already shows them. Focus on the single "
    "most actionable next step. "
    "KESIN KURAL: Asla i\u00e7 sesini, \u0130ngilizce analiz ad\u0131mlar\u0131n\u0131 veya 'Let me evaluate' gibi "
    "d\u00fc\u015f\u00fcnce s\u00fcre\u00e7lerini \u00e7\u0131kt\u0131ya yans\u0131tma. D\u00fc\u015f\u00fcncelerini kendine sakla. Do\u011frudan ve SADECE "
    "T\u00fcrk\u00e7e nihai yan\u0131t\u0131n\u0131 \u00fcret. K\u0131sa, net ve anla\u015f\u0131l\u0131r ol. "
    "Kullan\u0131c\u0131 t\u00fcm m\u00fcrettebat\u0131n genel analizini istedi\u011finde a\u015fr\u0131 detaya girme; "
    "karakter s\u0131n\u0131r\u0131n\u0131 a\u015fmamak i\u00e7in \u00e7ok k\u0131sa \u00f6zetler (bullet points) halinde yan\u0131t ver."
)

# ------------------------------------------------------------
# OpenRouter helpers — key + model rotasyonu
# ------------------------------------------------------------

_key_index = 0

DEFAULT_MODELS = [
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
    "meta-llama/llama-3.3-70b-instruct",
    "anthropic/claude-sonnet-4",
]


def _get_openrouter_keys() -> list[str]:
    """3 key'e kadar destekler. Esnek okuma:
    - OPENROUTER_API_KEY="sk-or-v1-aaa,sk-or-v1-bbb,sk-or-v1-ccc"
    - OPENROUTER_API_KEYS="sk-or-v1-aaa,sk-or-v1-bbb"
    - OPENROUTER_API_KEY_1 / _2 / _3 ayri ayri
    """
    keys: list[str] = []
    for env_name in ("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"):
        raw = os.getenv(env_name, "").strip()
        if raw:
            for part in raw.split(","):
                part = part.strip().strip('"').strip("'")
                if part and part not in keys:
                    keys.append(part)
    for i in ("1", "2", "3"):
        raw = os.getenv(f"OPENROUTER_API_KEY_{i}", "").strip().strip('"').strip("'")
        if raw and raw not in keys:
            keys.append(raw)
    return keys


def _get_openrouter_models() -> list[str]:
    raw = os.getenv("OPENROUTER_MODELS", "").strip()
    if not raw:
        raw = os.getenv("OPENROUTER_MODEL", "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if models:
            return models
    # If credits low for expensive models, prefer cheap ones — 402 means 150 tokens too many for sonnet
    return DEFAULT_MODELS

# Downshift OpenRouter max_tokens when credits are low (402 = not enough credits for 150 tokens)
OPENROUTER_MAX_TOKENS = 2048


def _call_openrouter(user_prompt: str, system_prompt: str | None = None) -> str | None:
    global _key_index
    keys = _get_openrouter_keys()
    if not keys:
        return None
    models = _get_openrouter_models()
    import httpx
    headers_base = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://lifeline-health-monitor.local",
        "X-Title": "LIFELINE Health Monitor",
    }
    sys = system_prompt or SYSTEM_PROMPT
    for model in models:
        for ki in range(len(keys)):
            key_idx = (_key_index + ki) % len(keys)
            api_key = keys[key_idx]
            # Retry up to 2 times (3 attempts total) on transient failures
            for attempt in range(3):
                try:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={**headers_base, "Authorization": f"Bearer {api_key}"},
                            json={
                                "model": model,
                                "max_tokens": OPENROUTER_MAX_TOKENS,
                                "messages": [
                                    {"role": "system", "content": sys},
                                    {"role": "user", "content": user_prompt},
                                ],
                            },
                        )
                        if resp.status_code == 429:
                            logger.warning(f"[advisor] OpenRouter 429 model={model} key#{key_idx+1} attempt={attempt+1}")
                            if attempt < 2:
                                time.sleep(1.0)
                                continue
                            break  # Retries exhausted, try next key
                        if resp.status_code in (401, 403):
                            logger.warning(f"[advisor] OpenRouter auth fail model={model} key#{key_idx+1} -> next key")
                            break  # Don't retry auth failures
                        if resp.status_code == 404:
                            logger.warning(f"[advisor] OpenRouter model not found: {model} -> next model")
                            break
                        if resp.status_code >= 400:
                            logger.warning(f"[advisor] OpenRouter HTTP {resp.status_code} model={model} key#{key_idx+1}: {resp.text[:200]}")
                            if resp.status_code >= 500 and attempt < 2:
                                time.sleep(1.0)
                                continue
                            break
                        data = resp.json()
                        text = ""
                        try:
                            text = (data["choices"][0]["message"]["content"] or "").strip()
                        except (KeyError, IndexError, TypeError):
                            text = ""
                        if text:
                            _key_index = (key_idx + 1) % len(keys)
                            logger.info(f"[advisor] OpenRouter OK model={model} key#{key_idx+1}")
                            return text
                        else:
                            logger.warning(f"[advisor] OpenRouter empty response model={model}")
                            break
                except httpx.TimeoutException:
                    logger.warning(f"[advisor] OpenRouter timeout model={model} key#{key_idx+1} attempt={attempt+1}")
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    break  # Retries exhausted, try next key
                except Exception as e:
                    logger.warning(f"[advisor] OpenRouter error model={model} key#{key_idx+1} attempt={attempt+1}: {type(e).__name__}: {e}")
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    break
    return None


# ------------------------------------------------------------
# NVIDIA NIM helpers — 5 key + model rotasyonu (OpenAI-compatible)
# ------------------------------------------------------------

_nvidia_key_index = 0

# NVIDIA NIM'de bedava ve aktif modeller (OpenAI-compatible endpoint)
# Kullanici .env'de NVIDIA_MODELS ile override edebilir
# Kaynak: https://build.nvidia.com/explore/discover
DEFAULT_NVIDIA_MODELS = [
    # Meta Llama 3.x series (confirmed free tier)
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.3-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    # Microsoft Phi-3 (small, fast)
    "microsoft/phi-3.5-mini-instruct",
    "microsoft/phi-3-mini-128k-instruct",
    # Google Gemma (small, efficient)
    "google/gemma-2-9b-it",
    "google/gemma-2-2b-it",
    # NVIDIA Nemotron
    "nvidia/nemotron-3-ultra-550b-a55b",
    # Mistral
    "mistral/mistral-7b-instruct-v0.3",
    # DeepSeek
    "deepseek/deepseek-chat",
    # Cohere Command R
    "cohere/command-r",
]


def _get_nvidia_keys() -> list[str]:
    """5 key'e kadar destekler. Esnek okuma:
    - NVIDIA_API_KEY="nvapi-aaa,nvapi-bbb,..."
    - NVIDIA_API_KEYS="nvapi-aaa,nvapi-bbb"
    - NVIDIA_NIM_API_KEY / NVIDIA_NIM_API_KEYS (alias)
    - NVIDIA_API_KEY_1 .. _5 / NVIDIA_NIM_API_KEY_1 .. _5 ayri ayri
    """
    keys: list[str] = []
    for env_name in ("NVIDIA_API_KEY", "NVIDIA_API_KEYS", "NVIDIA_NIM_API_KEY", "NVIDIA_NIM_API_KEYS"):
        raw = os.getenv(env_name, "").strip()
        if raw:
            for part in raw.split(","):
                part = part.strip().strip('"').strip("'")
                if part and part not in keys:
                    keys.append(part)
    for prefix in ("NVIDIA_API_KEY_", "NVIDIA_NIM_API_KEY_"):
        for i in ("1", "2", "3", "4", "5"):
            raw = os.getenv(f"{prefix}{i}", "").strip().strip('"').strip("'")
            if raw and raw not in keys:
                keys.append(raw)
    return keys


def _get_nvidia_models() -> list[str]:
    raw = os.getenv("NVIDIA_MODELS", "").strip()
    if not raw:
        raw = os.getenv("NVIDIA_MODEL", "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if models:
            return models
    return DEFAULT_NVIDIA_MODELS


def _get_nvidia_base_url() -> str:
    return os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip().rstrip("/") or "https://integrate.api.nvidia.com/v1"


def _call_nvidia(user_prompt: str, system_prompt: str | None = None) -> str | None:
    """NVIDIA NIM'e istek at, fail olursa None don. Key+model failover dahil. OpenAI-compatible."""
    global _nvidia_key_index
    keys = _get_nvidia_keys()
    if not keys:
        return None
    models = _get_nvidia_models()
    base_url = _get_nvidia_base_url()
    import httpx
    headers_base = {"Content-Type": "application/json"}
    sys = system_prompt or SYSTEM_PROMPT
    for model in models:
        for ki in range(len(keys)):
            key_idx = (_nvidia_key_index + ki) % len(keys)
            api_key = keys[key_idx]
            # Retry up to 2 times (3 attempts total) on transient failures
            for attempt in range(3):
                try:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(
                            f"{base_url}/chat/completions",
                            headers={**headers_base, "Authorization": f"Bearer {api_key}"},
                            json={
                                "model": model,
                                "max_tokens": 2048,
                                "temperature": 0.7,
                                "messages": [
                                    {"role": "system", "content": sys},
                                    {"role": "user", "content": user_prompt},
                                ],
                            },
                        )
                        if resp.status_code == 429:
                            logger.warning(f"[advisor] NVIDIA 429 model={model} key#{key_idx+1} attempt={attempt+1}")
                            if attempt < 2:
                                time.sleep(1.0)
                                continue
                            break  # Retries exhausted, try next key
                        if resp.status_code in (401, 403):
                            logger.warning(f"[advisor] NVIDIA auth fail model={model} key#{key_idx+1} -> next key")
                            break  # Don't retry auth failures
                        if resp.status_code == 404:
                            logger.warning(f"[advisor] NVIDIA model not found: {model} -> next model")
                            break
                        if resp.status_code >= 400:
                            logger.warning(f"[advisor] NVIDIA HTTP {resp.status_code} model={model} key#{key_idx+1}: {resp.text[:200]}")
                            if resp.status_code >= 500 and attempt < 2:
                                time.sleep(1.0)
                                continue
                            break
                        data = resp.json()
                        text = ""
                        reasoning = ""
                        try:
                            msg = data["choices"][0]["message"]
                            text = (msg.get("content") or "").strip()
                            reasoning = (msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
                            # Some models (gpt-oss-20b, reasoning variants) put answer in reasoning when content is null
                            if not text and reasoning and len(reasoning) > 20:
                                # Only use reasoning as fallback if it looks like an actual answer (not chain-of-thought prefix)
                                # For gpt-oss-20b reasoning is chain-of-thought, so skip; for others content should be present with enough max_tokens
                                pass
                        except (KeyError, IndexError, TypeError):
                            text = ""
                        if text:
                            _nvidia_key_index = (key_idx + 1) % len(keys)
                            logger.info(f"[advisor] NVIDIA OK model={model} key#{key_idx+1}")
                            return text
                        else:
                            # 150 tokens too few for reasoning models with long reasoning — retry is handled by failover to next model
                            logger.warning(f"[advisor] NVIDIA empty content model={model} reasoning_len={len(reasoning)} -> next model")
                            break
                except httpx.TimeoutException:
                    logger.warning(f"[advisor] NVIDIA timeout model={model} key#{key_idx+1} attempt={attempt+1}")
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    break  # Retries exhausted, try next key
                except Exception as e:
                    logger.warning(f"[advisor] NVIDIA error model={model} key#{key_idx+1} attempt={attempt+1}: {type(e).__name__}: {e}")
                    if attempt < 2:
                        time.sleep(1.0)
                        continue
                    break
    return None


# ------------------------------------------------------------
# Google Gemini (direct API)
# ------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        return None
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client
    except Exception as e:
        logger.warning(f"[advisor] Gemini client init fail: {e}")
        return None


def _call_gemini(user_prompt: str, system_prompt: str | None = None) -> str | None:
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        # Combine system + user prompt for Gemini
        full_prompt = f"{system_prompt or SYSTEM_PROMPT}\n\n{user_prompt}"
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
        )
        text = (response.text or "").strip()
        return text or None
    except Exception as e:
        logger.warning(f"[advisor] Gemini call failed: {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------
# Anthropic direkt (fallback)
# ------------------------------------------------------------

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        _anthropic_client = Anthropic(api_key=api_key)
        return _anthropic_client
    except Exception as e:
        logger.warning(f"[advisor] Anthropic client init fail: {e}")
        return None


def _call_anthropic(user_prompt: str, system_prompt: str | None = None) -> str | None:
    client = _get_anthropic_client()
    if client is None:
        return None
    try:
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        msg = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt or SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        return text or None
    except Exception as e:
        logger.warning(f"[advisor] Anthropic call failed: {type(e).__name__}: {e}")
        return None


# ------------------------------------------------------------
# Ana fonksiyon — disariya acik tek yer
# ------------------------------------------------------------

def _build_user_prompt(req: AdviceRequest) -> str:
    clean_alerts = _sanitize_alerts(req.alerts)
    return (
        f"Astronaut: {req.astronaut.name} ({req.astronaut.role})\n"
        f"Heart rate: {req.vitals.heartRate:.0f} bpm\n"
        f"Blood pressure: {req.vitals.bpSys:.0f}/{req.vitals.bpDia:.0f} mmHg\n"
        f"SpO2: {req.vitals.spo2:.1f}%\n"
        f"Temperature: {req.vitals.tempC:.1f} C\n"
        f"Stress index (0-100 simulated): {req.vitals.stressIndex:.0f}\n"
        f"Cumulative mission radiation: {req.radiationMSv:.0f} mSv\n"
        f"Active alerts: {', '.join(clean_alerts) if clean_alerts else 'none'}\n"
        f"Constraint: Return exactly 1 sentence. No diagnosis. Actionable next step only."
    )


def generate_advice(req: AdviceRequest) -> tuple[str, str]:
    """Returns (advice_text, source) where source is 'llm' or 'local'."""
    # ponytail: ADVISOR_FORCE_LOCAL=1 skips all LLM calls — upgrade when per-request flag needed
    if os.getenv("ADVISOR_FORCE_LOCAL", "").strip() in ("1", "true", "True"):
        return rule_based_advice(req), "local"
    # Skip OpenRouter tier when credits low (ADVISOR_SKIP_OPENROUTER=1)
    skip_openrouter = os.getenv("ADVISOR_SKIP_OPENROUTER", "").strip() in ("1", "true", "True")
    prompt = _build_user_prompt(req)

    # 1) OpenRouter
    if not skip_openrouter:
        text = _call_openrouter(prompt)
        if text:
            return text, "llm"

    # 2) NVIDIA NIM (5 key failover)
    text = _call_nvidia(prompt)
    if text:
        return text, "llm"

    # 3) Google Gemini
    text = _call_gemini(prompt)
    if text:
        return text, "llm"

    # 4) Anthropic direkt
    text = _call_anthropic(prompt)
    if text:
        return text, "llm"

    # 5) Rule-based fallback
    return rule_based_advice(req), "local"





