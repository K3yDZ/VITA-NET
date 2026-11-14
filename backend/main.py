"""VITA-NET backend - FastAPI service."""

import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

try:
    from logger import setup_logging  # type: ignore
    setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

log = logging.getLogger("vitanet.main")

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import HTTPException as FastAPIHTTPException

import database
import mock_sensors
import advisor
import analytics
import mission as mission_mod
from models import VitalsReading, AdviceRequest, AdviceResponse, Astronaut
from thresholds import evaluate_vitals
from auth import decode_jwt

# Crew size config — default 6 (Artemis), configurable via env, max 200
CREW_SIZE = max(1, min(int(os.getenv("CREW_SIZE", "6")), 200))

# Extended Artemis-style roster (6 crew)
ARTEMIS_ROSTER = [
    Astronaut(id="a1", name="Mara Ibáñez", role="Commander"),
    Astronaut(id="a2", name="Kenji Watanabe", role="Flight Engineer"),
    Astronaut(id="a3", name="Amara Bello", role="Mission Specialist"),
    Astronaut(id="a4", name="Deniz Aydın", role="Medical Officer"),
    Astronaut(id="a5", name="Priya Sharma", role="Mission Specialist"),
    Astronaut(id="a6", name="Carlos Mendes", role="Mission Specialist"),
]

def get_roster():
    """Return first CREW_SIZE astronauts from ARTEMIS_ROSTER."""
    return ARTEMIS_ROSTER[:CREW_SIZE]

ROSTER = get_roster()
ROSTER_IDS = {a.id for a in ROSTER}

# Request ID middleware
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from logger import set_request_id, clear_request_id
        rid = request.headers.get("x-request-id") or set_request_id()
        set_request_id(rid)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = rid
            return response
        finally:
            clear_request_id()

async def lifespan(app: FastAPI):
    database.init_db()
    # Seed astronauts table from ROSTER (always upsert to handle config changes)
    try:
        for a in ROSTER:
            database.upsert_astronaut(a.id, a.name, a.role)
        log.info("Seeded/updated astronauts table with %d crew", len(ROSTER))
    except Exception as e:
        log.warning("Astronaut seed failed: %s", e)
    log.info("DB ready")
    yield
    log.info("Shutdown")

app = FastAPI(title="VITA-NET Health Monitor API", version="0.2.0", lifespan=lifespan)

# Exception handlers to ensure HTTPExceptions are returned as proper responses
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# JWT authentication middleware
class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth in dev if disabled
        if os.getenv('AUTH_REQUIRED', 'true').lower() == 'false':
            return await call_next(request)
        # Exempt endpoints (exact paths only — no broad prefixes for write endpoints)
        exempt_exact = {
            "/",
            "/api/health",
            "/health",
            "/api/advice",
            "/api/assistant/chat",
            "/api/iss/position",
            "/api/mission/hazards",
            "/api/analytics",
            "/api/analytics/summary",
        }
        # Allow GET on /api/astronauts and /api/astronauts/{id} without auth
        if request.method == "GET" and (request.url.path == "/api/astronauts" or request.url.path.startswith("/api/astronauts/")):
            return await call_next(request)
        # Allow GET on /api/analytics/summary and /api/analytics/astronaut/{id} without auth
        if request.method == "GET" and (request.url.path == "/api/analytics/summary" or request.url.path.startswith("/api/analytics/astronaut/")):
            return await call_next(request)
        path = request.url.path
        # Exempt static files (css, js, images, fonts, etc.)
        if any(path.startswith(f"/{prefix}") for prefix in ("css/", "js/", "img/", "images/", "fonts/", "assets/", "locales/", "favicon")):
            return await call_next(request)
        if path in exempt_exact:
            return await call_next(request)

        auth = request.headers.get('Authorization')
        if not auth or not auth.lower().startswith('bearer '):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing token"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        token = auth.split(' ', 1)[1]
        try:
            payload = decode_jwt(token)
            request.state.user = payload
        except ValueError as e:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error: token validation failed"}
            )
        return await call_next(request)

app.add_middleware(JWTAuthMiddleware)




allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
DEFAULT_ORIGINS = ["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:8000", "http://127.0.0.1:8000"]
# Production check must fire before defaults are applied (was dead code)
if os.getenv("ENV", "").lower() == "production" and not allowed_origins:
    raise RuntimeError("ALLOWED_ORIGINS must be set in production")
if not allowed_origins:
    allowed_origins = DEFAULT_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Rate limiter: in-memory sliding window per IP with proxy support
import time
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse

# Trusted proxies for X-Forwarded-For support (comma-separated CIDR or IPs)
TRUSTED_PROXIES = [p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()]

def get_client_ip(request: Request) -> str:
    """Extract real client IP respecting X-Forwarded-For from trusted proxies."""
    # Check X-Forwarded-For if behind trusted proxy
    xff = request.headers.get("x-forwarded-for")
    if xff and TRUSTED_PROXIES:
        # Only trust XFF if the immediate peer (request.client.host) is a trusted proxy
        peer = request.client.host if request.client else ""
        if peer in TRUSTED_PROXIES or any(_ip_in_cidr(peer, cidr) for cidr in TRUSTED_PROXIES):
            # X-Forwarded-For: client, proxy1, proxy2... take first (original client)
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _ip_in_cidr(ip: str, cidr: str) -> bool:
    """Simple CIDR check for IPv4."""
    try:
        import ipaddress
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except Exception:
        return False


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[key] = [ts for ts in self.requests[key] if ts > window_start]
        if len(self.requests[key]) >= self.max_requests:
            oldest = self.requests[key][0]
            retry_after = int(oldest + self.window_seconds - now) + 1
            return False, max(retry_after, 1)
        self.requests[key].append(now)
        return True, 0

advice_limiter = RateLimiter(30, 60)
chat_limiter = RateLimiter(40, 60)
vitals_limiter = RateLimiter(60, 60)

async def rate_limit_advice(request: Request, call_next):
    if not request.url.path.startswith("/api/advice"):
        return await call_next(request)
    client_ip = get_client_ip(request)
    allowed, retry = advice_limiter.is_allowed(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry)},
        )
    return await call_next(request)

async def rate_limit_chat(request: Request, call_next):
    if not request.url.path.startswith("/api/assistant/chat"):
        return await call_next(request)
    client_ip = get_client_ip(request)
    allowed, retry = chat_limiter.is_allowed(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry)},
        )
    return await call_next(request)

async def rate_limit_vitals(request: Request, call_next):
    if not request.url.path.startswith("/api/astronauts/") or not request.url.path.endswith("/vitals"):
        return await call_next(request)
    if request.method != "POST":
        return await call_next(request)
    client_ip = get_client_ip(request)
    allowed, retry = vitals_limiter.is_allowed(client_ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry)},
        )
    return await call_next(request)

app.middleware("http")(rate_limit_advice)
app.middleware("http")(rate_limit_chat)
app.middleware("http")(rate_limit_vitals)

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/health")
def health_alias():
    # Alias for external tooling that probes the bare path (agent harnesses, LB probes).
    return {"status": "ok"}


@app.get("/api/astronauts")
def list_astronauts():
    # Prefer DB, fallback to ROSTER
    try:
        db_list = database.list_astronauts()
        if db_list:
            return [Astronaut(id=r["id"], name=r["name"], role=r["role"]) for r in db_list]
    except Exception:
        pass
    return ROSTER


@app.get("/api/astronauts/{astronaut_id}")
def get_astronaut(astronaut_id: str):
    _check_known(astronaut_id)
    try:
        db_list = database.list_astronauts()
        for r in db_list:
            if r["id"] == astronaut_id:
                return Astronaut(id=r["id"], name=r["name"], role=r["role"])
    except Exception:
        pass
    # Fallback to in-memory roster
    for a in ROSTER:
        if a.id == astronaut_id:
            return a
    raise HTTPException(status_code=404, detail="astronaut not found")


@app.post("/api/astronauts")
def create_astronaut(a: Astronaut = Body(...)):
    try:
        database.upsert_astronaut(a.id, a.name, a.role)
    except Exception as e:
        log.warning("create astronaut failed: %s", e)
    ROSTER_IDS.add(a.id)
    return a


@app.delete("/api/astronauts/{astronaut_id}")
def delete_astronaut(astronaut_id: str):
    try:
        database.delete_astronaut(astronaut_id)
    except Exception:
        pass
    ROSTER_IDS.discard(astronaut_id)
    return {"deleted": astronaut_id}


def _check_known(astronaut_id: str):
    # Allow any id that exists in DB or ROSTER â€" dynamic roster support
    if astronaut_id in ROSTER_IDS:
        return
    try:
        ids = {r["id"] for r in database.list_astronauts()}
        if astronaut_id in ids:
            ROSTER_IDS.add(astronaut_id)
            return
    except Exception:
        pass
    # Also allow if they've logged vitals before
    try:
        if database.get_history(astronaut_id, 1):
            ROSTER_IDS.add(astronaut_id)
            return
    except Exception:
        pass
    # For backwards compat, allow any a* id
    if astronaut_id.startswith("a"):
        ROSTER_IDS.add(astronaut_id)
        return
    log.warning("Unknown astronaut id: %s", astronaut_id)
    raise HTTPException(status_code=404, detail="unknown astronaut id")


@app.get("/api/astronauts/{astronaut_id}/vitals/simulate")
def simulate_vitals(astronaut_id: str):
    _check_known(astronaut_id)
    reading = mock_sensors.generate_reading(astronaut_id)
    evaluation = evaluate_vitals(reading)
    return {"vitals": reading, "evaluation": evaluation}


@app.post("/api/astronauts/{astronaut_id}/vitals")
def post_vitals(astronaut_id: str, reading: VitalsReading = Body(...)):
    _check_known(astronaut_id)
    database.insert_reading(astronaut_id, reading)
    log.info("Vitals stored astronaut=%s hr=%.0f", astronaut_id, reading.heartRate)
    return {"stored": True, "evaluation": evaluate_vitals(reading)}


@app.get("/api/astronauts/{astronaut_id}/history")
def get_history(astronaut_id: str, limit: int = 100):
    # Don't strict-check for history â€" allow any id
    return database.get_history(astronaut_id, min(limit, 500))


# --- Analytics ---
@app.get("/api/analytics/summary")
def analytics_summary():
    return analytics.compute_summary()


@app.get("/api/analytics/astronaut/{astronaut_id}")
def analytics_astronaut(astronaut_id: str):
    return analytics.compute_astronaut_analytics(astronaut_id)


# --- ISS / Mission ---
@app.get("/api/iss/position")
def iss_position():
    return mission_mod.get_iss_position()


@app.get("/api/mission/hazards")
def mission_hazards():
    return mission_mod.get_hazards()


@app.post("/api/advice", response_model=AdviceResponse)
def post_advice(req: AdviceRequest = Body(...)):
    text, source = advisor.generate_advice(req)
    log.info("Advice astronaut=%s source=%s alerts=%d", req.astronaut.id, source, len(req.alerts))
    return AdviceResponse(advice=text, source=source)



# --- Assistant chat ---
import re
from pydantic import BaseModel as _BM2, Field as _Field

_MAX_CHAT_LEN = 500


def _sanitize_chat(s: str) -> str:
    """Strip control chars, limit length for prompt safety."""
    if not s:
        return ""
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)
    return s[:_MAX_CHAT_LEN]


class ChatRequest(_BM2):
    message: str = _Field(max_length=1000)
    lang: str = "en"
    roster: list = _Field(default_factory=list)
    selected: dict | None = None


@app.post("/api/assistant/chat")
def assistant_chat(req: ChatRequest = Body(...)):
    msg = _sanitize_chat(req.message)
    if not msg:
        raise HTTPException(status_code=400, detail="empty message")
    lang = (req.lang or "en").lower().split("-")[0]
    # Build a concise context for the advisor LLM
    roster_ctx = ""
    if req.roster:
        lines = []
        for a in req.roster[:12]:
            v = a.get("vitals", {})
            name = _sanitize_chat(a.get("name", ""))
            role = _sanitize_chat(a.get("role", ""))
            lines.append(f"- {name} ({role}): HR {v.get('heartRate')} bpm, BP {v.get('bpSys')}/{v.get('bpDia')}, SpO2 {v.get('spo2')}%, Temp {v.get('tempC')}C, Stress {v.get('stressIndex')}, Rad {v.get('radiationMSv')} mSv")
        roster_ctx = "\n".join(lines)
    sel_ctx = ""
    if req.selected:
        v = req.selected.get("vitals", {})
        name = _sanitize_chat(req.selected.get("name", ""))
        role = _sanitize_chat(req.selected.get("role", ""))
        sel_ctx = f"\nSelected: {name} ({role}): HR {v.get('heartRate')} bpm, BP {v.get('bpSys')}/{v.get('bpDia')}, SpO2 {v.get('spo2')}%, Temp {v.get('tempC')}C, Stress {v.get('stressIndex')}, Rad {v.get('radiationMSv')} mSv"
    lang_names = {"en":"English","tr":"Turkish","es":"Spanish","fr":"French","de":"German","ja":"Japanese","zh":"Chinese","ru":"Russian","ar":"Arabic","pt":"Portuguese","it":"Italian","ko":"Korean","hi":"Hindi","nl":"Dutch","pl":"Polish","id":"Indonesian"}
    lang_name = lang_names.get(lang, "English")
    system = (
        f"You are VITA-NET Assistant, a calm, concise flight-surgeon-style health advisor on a space mission. "
        f"Answer in {lang_name} (lang code {lang}). Be concise (2-4 sentences), friendly, accurate. "
        f"You have live telemetry below. Do not diagnose diseases; describe risk plainly. "
        f"If asked about vitals, cite the numbers. If unrelated, answer briefly. "
        f"KESIN KURAL: Asla iç sesini, İngilizce analiz adımlarını veya 'Let me evaluate' gibi "
        f"düşünce süreçlerini çıktıya yansıtma. Düşüncelerini kendine sakla. Doğrudan ve SADECE "
        f"{lang_name} dilinde nihai yanıtını üret. Kısa, net ve anlaşılır ol."
    )
    user_prompt = f"User ({lang_name}): {msg}\n\nCrew telemetry:\n{roster_ctx}{sel_ctx}\n\nReply in {lang_name}."
    # Check for image references - NVIDIA model doesn't support image input
    image_keywords = {"image", "png", "jpg", "jpeg", "photo", "picture", "screenshot", "resim", "görsel"}
    msg_lower = msg.lower()
    has_image_ref = any(kw in msg_lower for kw in image_keywords)

    # Use NVIDIA NIM via advisor._call_nvidia (OpenAI-compatible, 5 keys + model failover)
    if not has_image_ref:
        try:
            text = advisor._call_nvidia(user_prompt, system_prompt=system)  # type: ignore
            if text:
                return {"reply": text, "source": "llm"}
        except Exception as e:
            import logging as _lg
            _lg.getLogger(__name__).warning("assistant chat LLM failed: %s", e)
    # Fallback: lang-aware rule-based summary (no hardcoded English)
    fallback_map = {
        "tr": "LLM yanıt veremedi. Yerel veri: {count} astronot izleniyor. Seçili: {sel}. Detaylar paneli açık.",
        "en": "LLM unavailable. Local data: {count} crew monitored. Selected: {sel}. Details in panel.",
        "es": "LLM no disponible. Datos locales: {count} tripulantes monitoreados. Seleccionado: {sel}. Detalles en panel.",
        "fr": "LLM indisponible. Données locales: {count} membres d'équipage surveillés. Sélectionné: {sel}. Détails dans le panneau.",
        "de": "LLM nicht verfügbar. Lokale Daten: {count} Crew überwacht. Ausgewählt: {sel}. Details im Panel.",
        "ja": "LLM利用不可。ローカルデータ: {count}名のクルーを監視中。選択中: {sel}。詳細はパネルで。",
        "zh": "LLM不可用。本地数据: 监控中 {count} 名机组成员。已选: {sel}。详情见面板。",
        "ru": "LLM недоступен. Локальные данные: отслеживается {count} членов экипажа. Выбран: {sel}. Подробности на панели.",
        "ar": "LLM غير متاح. البيانات المحلية: مراقبة {count} من أفراد الطاقم. المحدد: {sel}. التفاصيل في اللوحة.",
        "pt": "LLM indisponível. Dados locais: {count} tripulantes monitorados. Selecionado: {sel}. Detalhes no painel.",
        "it": "LLM non disponibile. Dati locali: {count} membri equipaggio monitorati. Selezionato: {sel}. Dettagli nel pannello.",
        "ko": "LLM 사용 불가. 로컬 데이터: {count}명 승무원 모니터링 중. 선택됨: {sel}. 패널에서 상세 확인.",
        "hi": "LLM उपलब्ध नहीं। स्थानीय डेटा: {count} चालक दल की निगरानी। चयनित: {sel}। पैनल में विवरण।",
        "nl": "LLM niet beschikbaar. Lokale data: {count} bemanningsleden in de gaten. Geselecteerd: {sel}. Details in paneel.",
        "pl": "LLM niedostępny. Dane lokalne: monitorowanie {count} członków załogi. Wybrany: {sel}. Szczegóły w panelu.",
        "id": "LLM tidak tersedia. Data lokal: {count} awak dikawasi. Dipilih: {sel}. Detail di panel.",
    }
    count = len(req.roster or [])
    sel_name = (req.selected or {}).get("name", "none")
    fb = fallback_map.get(lang, fallback_map["en"]).format(count=count, sel=sel_name)
    return {"reply": fb, "source": "local"}


@app.post("/api/reset")
async def reset_demo(request: Request):
    """Reset all vitals to safe state - clears logs and resets astronaut vitals. Requires auth."""
    # Require authentication for destructive operation
    if not getattr(request.state, "user", None):
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        database.reset_all()
        log.info("Demo reset to safe state by user=%s", request.state.user.get("sub", "unknown"))
    except Exception as e:
        log.warning("Reset failed: %s", e)
    return {"reset": True, "message": "Reset to safe state"}

if os.getenv("SERVE_FRONTEND", "1") == "1":
    try:
        from fastapi.staticfiles import StaticFiles
        frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
        if frontend_dir.is_dir() and (frontend_dir / "index.html").exists():
            app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
            log.info("Frontend mounted from %s (single-port mode)", frontend_dir)
        else:
            log.warning("Frontend dir not found: %s - API-only mode", frontend_dir)
    except Exception as e:
        log.warning("Frontend mount skipped: %s", e)

