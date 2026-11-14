#!/usr/bin/env python3
"""Tek tikla VITA-NET — tek port (8000) uzerinde frontend + backend.

Calistir:  python start.py          veya cift tikla start.bat / start.ps1
Durdur:   Ctrl+C

Tek port: FastAPI hem /api/* hem de frontend/index.html'i serve eder.
Logger logs/ klasorunu otomatik acar, dated + latest.log yazar.
"""

import os
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

# Oncelik: venv varsa onu kullan (cift tikta PATH bos gelebilir)
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
VENV_PYTHON_POSIX = ROOT / "venv" / "bin" / "python"
if VENV_PYTHON.exists():
    sys.executable  # noqa
    # Alt process venv'i gorsun
    os.environ["VIRTUAL_ENV"] = str(ROOT / "venv")
    os.environ["PATH"] = str(ROOT / "venv" / "Scripts") + os.pathsep + os.environ.get("PATH", "")
elif VENV_PYTHON_POSIX.exists():
    os.environ["VIRTUAL_ENV"] = str(ROOT / "venv")
    os.environ["PATH"] = str(ROOT / "venv" / "bin") + os.pathsep + os.environ.get("PATH", "")

# Logger'i boot'tan once kur (start.py'nin kendi loglari da dosyaya gitsin)
try:
    sys.path.insert(0, str(BACKEND_DIR))
    from logger import setup_logging
    dated, latest = setup_logging()
    print(f"[start] logs -> {dated.name} + latest.log")
except Exception as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    print(f"[start] logger fallback: {e}", file=sys.stderr)

import logging
log = logging.getLogger("vitanet.start")

PORT = int(os.getenv("VITA_NET_PORT", "8000"))
HOST = os.getenv("VITA_NET_HOST", "localhost")
URL = f"http://{HOST}:{PORT}"
# 0.0.0.0 dinle ama tarayiciya localhost ac
BROWSER_URL = f"http://localhost:{PORT}"

RELOAD = os.getenv("VITA_NET_RELOAD", "1") == "1"


def preflight() -> bool:
    ok = True
    if not FRONTEND_DIR.is_dir():
        log.error("frontend/ klasoru yok: %s", FRONTEND_DIR)
        ok = False
    if not (BACKEND_DIR / "main.py").exists():
        log.error("backend/main.py yok")
        ok = False
    if not (BACKEND_DIR / ".env").exists():
        log.warning(".env yok — backend rule-based modda calisacak (.env.example -> .env kopyala)")
    # Port dolu mu hizli kontrol
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        if s.connect_ex((HOST if HOST != "0.0.0.0" else "localhost", PORT)) == 0:
            log.warning("Port %d dolu gorunuyor — uvicorn hata verebilir (baska process kullaniyor olabilir)", PORT)
    return ok


def main():
    preflight()
    log.info("Starting VITA-NET on %s (reload=%s) — %s", URL, RELOAD, BROWSER_URL)

    # Tarayiciyi 1.5 sn sonra ac (server ayaga kalksin)
    def _open():
        time.sleep(1.4)
        try:
            webbrowser.open(BROWSER_URL)
            log.info("Browser opened -> %s", BROWSER_URL)
        except Exception as e:
            log.warning("Browser acilamadi: %s — manuel ac: %s", e, BROWSER_URL)

    import threading
    threading.Thread(target=_open, daemon=True).start()

    # Single-port zorunlu
    os.environ["SERVE_FRONTEND"] = "1"

    # Uvicorn'u direkt calistir (reload destegi RELOAD ile)
    try:
        import uvicorn
    except ImportError:
        log.error("uvicorn yok — pip install -r backend/requirements.txt")
        sys.exit(1)

    # reload=True iken app string ile verilir, yoksa objeyle
    if RELOAD:
        uvicorn.run("main:app", host=HOST, port=PORT, reload=True, reload_dirs=[str(BACKEND_DIR)], app_dir=str(BACKEND_DIR))
    else:
        # No-reload path: app objesi import et
        sys.path.insert(0, str(BACKEND_DIR))
        from main import app  # noqa: E402
        uvicorn.run(app, host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped (Ctrl+C)")
